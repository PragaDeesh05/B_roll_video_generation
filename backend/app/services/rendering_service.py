"""
Rendering Service
FFmpeg-based video rendering with scene stitching, audio sync, and caption burn-in.
Hardened with multi-tier asset caching, automatic duration synchronization, and zero-black-screen guarantees.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OUTPUT_PROFILES: Dict[str, Dict] = {
    "16:9": {
        "width": 1920, "height": 1080,
        "vf": "scale=1920:1080:force_original_aspect_ratio=decrease,"
              "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black",
        "fps": 30,
    },
    "9:16": {
        "width": 1080, "height": 1920,
        "vf": "scale=1080:1920:force_original_aspect_ratio=decrease,"
              "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
        "fps": 30,
    },
    "1:1": {
        "width": 1080, "height": 1080,
        "vf": "scale=1080:1080:force_original_aspect_ratio=decrease,"
              "pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=black",
        "fps": 30,
    },
}


class RenderingService:
    """FFmpeg-based video renderer with resilience and duration synchronization."""

    MAX_DOWNLOAD_RETRIES = 3
    DOWNLOAD_TIMEOUT = 60.0

    @property
    def preset(self) -> str:
        return getattr(settings, "ffmpeg_preset", "ultrafast")

    def render_video(
        self,
        scenes: List[Dict[str, Any]],
        audio_path: Path,
        output_dir: Path,
        aspect_ratio: str,
        srt_path: Optional[Path] = None,
        burn_captions: bool = True,
    ) -> Path:
        """
        Render a complete video for the given aspect ratio with guaranteed duration alignment.

        Args:
            scenes: Scene list with selected_asset_url/local_path for each.
            audio_path: Authoritative narration audio.
            output_dir: Where to save the output MP4.
            aspect_ratio: "16:9", "9:16", or "1:1".
            srt_path: Optional SRT file for caption burn-in.
            burn_captions: Whether to burn captions into video.

        Returns:
            Path to the rendered MP4.
        """
        profile = OUTPUT_PROFILES.get(aspect_ratio, OUTPUT_PROFILES["16:9"])
        ar_tag = aspect_ratio.replace(":", "x")
        output_path = output_dir / f"output_{ar_tag}.mp4"
        segments_dir = output_dir / "segments" / ar_tag
        segments_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = output_dir / f"tmp_render_{ar_tag}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Determine authoritative narration duration
            narration_duration = self._get_media_duration(audio_path)
            if narration_duration <= 0.0:
                # Sum scene durations as fallback
                narration_duration = sum(float(s.get("duration", 5.0)) for s in scenes)
            logger.info(f"Target narration duration for {aspect_ratio}: {narration_duration:.2f}s")

            # 2. Download and prepare each scene clip (resiliently guarantees len(clips) == len(scenes))
            # Persists normalized segments to segments_dir for ultra-fast clip swapping
            scene_clips = self._prepare_scene_clips(scenes, profile, segments_dir, job_dir=output_dir)

            # 2b. Configurable Colour & Brightness Normalization Stage ("Looks Like One Video")
            if getattr(settings, "enable_color_normalization", True) and len(scene_clips) > 1:
                scene_clips = self._apply_color_consistency_stage(scenes, scene_clips, profile, segments_dir)

            # 3. Create a concat list
            concat_file = tmp_dir / "concat.txt"
            valid_clips = [c for c in scene_clips if c.exists() and c.stat().st_size > 0]

            if not valid_clips:
                raise RuntimeError("No valid scene clips available for rendering")

            with open(concat_file, "w", encoding="utf-8") as f:
                for clip in valid_clips:
                    f.write(f"file '{clip.resolve().as_posix()}'\n")

            # 4. Concatenate video clips (fast stream copy first, with dynamic timeout fallback)
            concat_video = tmp_dir / "concat_video.mp4"
            concat_success = False
            try:
                self._run_ffmpeg([
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_file),
                    "-c", "copy",
                    "-an",
                    str(concat_video),
                ], timeout=120)
                if concat_video.exists() and concat_video.stat().st_size > 1000:
                    concat_success = True
                    logger.info("Fast stream-copy video concatenation succeeded.")
            except Exception as copy_err:
                logger.warning(f"Fast stream-copy concat failed ({copy_err}); falling back to ultrafast re-encode")

            if not concat_success:
                scale_timeout = max(600, int(narration_duration * 5))
                self._run_ffmpeg([
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_file),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    str(concat_video),
                ], timeout=scale_timeout)

            # 5. Check video duration vs audio duration and synchronize
            concat_dur = self._get_media_duration(concat_video)
            logger.info(f"Raw concatenated video duration: {concat_dur:.2f}s vs target {narration_duration:.2f}s")

            synced_video = concat_video
            duration_diff = narration_duration - concat_dur

            # If video is shorter than audio by more than 0.1s, hold/pad the last frame
            if duration_diff > 0.1:
                logger.info(f"Padding video by {duration_diff:.2f}s to match narration duration")
                padded_video = tmp_dir / "padded_video.mp4"
                try:
                    pad_timeout = max(300, int(narration_duration * 3))
                    self._run_ffmpeg([
                        "ffmpeg", "-y",
                        "-i", str(concat_video),
                        "-vf", f"tpad=stop_mode=clone:stop_duration={duration_diff:.3f}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                        "-pix_fmt", "yuv420p",
                        "-an",
                        str(padded_video),
                    ], timeout=pad_timeout)
                    if padded_video.exists() and padded_video.stat().st_size > 0:
                        synced_video = padded_video
                except Exception as pe:
                    logger.warning(f"Video tpad failed ({pe}); proceeding with raw concat")

            # If video is longer than audio by more than 0.1s, trim cleanly
            elif duration_diff < -0.1:
                logger.info(f"Trimming video to {narration_duration:.2f}s to match narration")
                trimmed_video = tmp_dir / "trimmed_video.mp4"
                trim_done = False
                try:
                    # Stream copy trim takes < 1 second!
                    self._run_ffmpeg([
                        "ffmpeg", "-y",
                        "-i", str(concat_video),
                        "-t", str(narration_duration),
                        "-c", "copy",
                        "-an",
                        str(trimmed_video),
                    ], timeout=60)
                    if trimmed_video.exists() and trimmed_video.stat().st_size > 0:
                        synced_video = trimmed_video
                        trim_done = True
                except Exception as te:
                    logger.warning(f"Fast copy trim failed ({te}); falling back to ultrafast encode")

                if not trim_done:
                    trim_timeout = max(300, int(narration_duration * 3))
                    self._run_ffmpeg([
                        "ffmpeg", "-y",
                        "-i", str(concat_video),
                        "-t", str(narration_duration),
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                        "-pix_fmt", "yuv420p",
                        "-an",
                        str(trimmed_video),
                    ], timeout=trim_timeout)
                    if trimmed_video.exists() and trimmed_video.stat().st_size > 0:
                        synced_video = trimmed_video

            # 6. Mix in narration audio with exact time limit
            mixed_video = tmp_dir / "mixed.mp4"
            self._run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(synced_video),
                "-i", str(audio_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-t", str(narration_duration),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                str(mixed_video),
            ], timeout=max(300, int(narration_duration * 2)))

            # 7. Optional caption burn-in
            final_input = mixed_video
            if burn_captions and srt_path and srt_path.exists():
                captioned = tmp_dir / "captioned.mp4"
                try:
                    self._burn_captions(mixed_video, srt_path, captioned, profile, duration=narration_duration)
                    if captioned.exists() and captioned.stat().st_size > 0:
                        final_input = captioned
                except Exception as ce:
                    logger.warning(f"Caption burn-in bypassed: {ce}")

            # 8. Final packaging to ensure strict spec compliance (1080p, yuv420p, faststart)
            final_timeout = max(600, int(narration_duration * 4))
            if burn_captions and srt_path and srt_path.exists() and final_input != mixed_video:
                try:
                    self._run_ffmpeg([
                        "ffmpeg", "-y",
                        "-i", str(final_input),
                        "-c", "copy",
                        "-movflags", "+faststart",
                        str(output_path),
                    ], timeout=120)
                except Exception as copy_final_e:
                    logger.warning(f"Fast final copy failed ({copy_final_e}); re-encoding")
                    self._run_ffmpeg([
                        "ffmpeg", "-y",
                        "-i", str(final_input),
                        "-t", str(narration_duration),
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                        "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                        "-movflags", "+faststart",
                        str(output_path),
                    ], timeout=final_timeout)
            else:
                self._run_ffmpeg([
                    "ffmpeg", "-y",
                    "-i", str(final_input),
                    "-t", str(narration_duration),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                    "-movflags", "+faststart",
                    str(output_path),
                ], timeout=final_timeout)

            logger.info(f"Rendered {aspect_ratio} successfully → {output_path} (size={output_path.stat().st_size})")
            return output_path

        finally:
            # Cleanup temp files (segments_dir remains safely preserved for fast clip swaps!)
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def swap_scene_segment(
        self,
        scenes: List[Dict[str, Any]],
        scene_index: int,
        new_asset_path: Path,
        audio_path: Path,
        output_dir: Path,
        aspect_ratio: str,
        srt_path: Optional[Path] = None,
        burn_captions: bool = True,
        is_image: bool = False,
    ) -> Path:
        """
        Replace a single scene's visual clip and re-render only that segment.
        Reassembles the final video via ultrafast stream-copy concat and audio mux.
        Reduces video re-rendering latency from minutes to ~3-5 seconds.
        """
        profile = OUTPUT_PROFILES.get(aspect_ratio, OUTPUT_PROFILES["16:9"])
        ar_tag = aspect_ratio.replace(":", "x")
        output_path = output_dir / f"output_{ar_tag}.mp4"
        segments_dir = output_dir / "segments" / ar_tag
        segments_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = output_dir / f"tmp_swap_{ar_tag}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Ensure all other scene segments exist in segments_dir
            existing_clips = sorted(list(segments_dir.glob("scene_*.mp4")))
            if len(existing_clips) < len(scenes):
                logger.info(f"Backfilling missing segments in {segments_dir} for {aspect_ratio}")
                self._prepare_scene_clips(scenes, profile, segments_dir, job_dir=output_dir)

            # 2. Normalize ONLY the replacement segment for scene_index
            target_scene = scenes[scene_index]
            scene_duration = float(target_scene.get("duration", 5.0))
            staged_clip = segments_dir / f"staged_scene_{scene_index:04d}.mp4"
            final_clip = segments_dir / f"scene_{scene_index:04d}.mp4"

            normalized = None
            if is_image or new_asset_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                normalized = self._image_to_video_clip(new_asset_path, staged_clip, profile, scene_duration)
            else:
                normalized = self._normalize_clip(new_asset_path, staged_clip, profile, scene_duration)

            if not normalized or not staged_clip.exists() or staged_clip.stat().st_size == 0:
                raise RuntimeError(f"Failed to normalize replacement visual {new_asset_path.name}")

            # Atomically replace target clip
            if final_clip.exists():
                try:
                    final_clip.unlink()
                except Exception:
                    pass
            staged_clip.replace(final_clip)
            logger.info(f"Normalized replacement segment {final_clip.name} ({scene_duration:.2f}s)")

            # 3. Create concat list from segments_dir
            concat_file = tmp_dir / "concat.txt"
            all_clips = [segments_dir / f"scene_{i:04d}.mp4" for i in range(len(scenes))]
            missing = [p for p in all_clips if not p.exists() or p.stat().st_size == 0]
            if missing:
                raise RuntimeError(f"Cannot concatenate video: missing segments {[m.name for m in missing]}")

            with open(concat_file, "w", encoding="utf-8") as f:
                for c in all_clips:
                    f.write(f"file '{c.resolve().as_posix()}'\n")

            # 4. Ultrafast stream-copy concat
            concat_video = tmp_dir / "concat_video.mp4"
            concat_success = False
            try:
                self._run_ffmpeg([
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_file),
                    "-c", "copy",
                    "-an",
                    str(concat_video),
                ], timeout=60)
                if concat_video.exists() and concat_video.stat().st_size > 1000:
                    concat_success = True
                    logger.info("Fast stream-copy video concatenation succeeded.")
            except Exception as ce:
                logger.warning(f"Fast copy concat failed ({ce}); falling back to ultrafast encode")

            if not concat_success:
                self._run_ffmpeg([
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_file),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    str(concat_video),
                ], timeout=180)

            # 5. Mix authoritative narration audio
            narration_duration = self._get_media_duration(audio_path)
            if narration_duration <= 0.0:
                narration_duration = sum(float(s.get("duration", 5.0)) for s in scenes)

            mixed_video = tmp_dir / "mixed.mp4"
            self._run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(concat_video),
                "-i", str(audio_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-t", str(narration_duration),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                str(mixed_video),
            ], timeout=60)

            # 6. Burn captions if requested
            final_input = mixed_video
            if burn_captions and srt_path and srt_path.exists():
                captioned = tmp_dir / "captioned.mp4"
                try:
                    self._burn_captions(mixed_video, srt_path, captioned, profile, duration=narration_duration)
                    if captioned.exists() and captioned.stat().st_size > 0:
                        final_input = captioned
                except Exception as c_err:
                    logger.warning(f"Caption burn-in bypassed: {c_err}")

            # 7. Atomically stage and publish final output
            staged_output = output_dir / f"staged_output_{ar_tag}.mp4"
            self._run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(final_input),
                "-c", "copy",
                "-movflags", "+faststart",
                str(staged_output),
            ], timeout=60)

            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            staged_output.replace(output_path)
            logger.info(f"Swap complete! Updated {output_path.name} in place (size={output_path.stat().st_size})")
            return output_path

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _prepare_scene_clips(
        self, scenes: List[Dict], profile: Dict, tmp_dir: Path, job_dir: Optional[Path] = None
    ) -> List[Path]:
        """
        Download or read local asset and prepare normalized scene video clips.
        Guarantees that EVERY scene produces a valid clip matching scene_duration.
        """
        clips = []
        if job_dir is None:
            job_dir = tmp_dir.parent if tmp_dir.parent.name != "segments" else tmp_dir.parent.parent

        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", f"scene_{i+1:03d}")
            scene_duration = float(scene.get("duration", 5.0))
            clip_path = tmp_dir / f"scene_{i:04d}.mp4"
            local_path = scene.get("local_path")
            asset_url = scene.get("selected_asset_url")
            asset_id = str(scene.get("selected_asset_id") or "")

            normalized = None

            # 1. Check if scene has an explicit valid local path
            if local_path and Path(local_path).exists() and Path(local_path).stat().st_size > 1000:
                src_path = Path(local_path)
                if src_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    normalized = self._image_to_video_clip(src_path, clip_path, profile, scene_duration)
                else:
                    normalized = self._normalize_clip(src_path, clip_path, profile, scene_duration)

            # 2. Check candidate_frames and generated_images in job directory
            if not normalized:
                local_candidates = [
                    job_dir / "candidate_frames" / scene_id / f"{asset_id}.jpg",
                    job_dir / "candidate_frames" / scene_id / f"{asset_id}.png",
                    job_dir / "candidate_frames" / scene_id / f"{asset_id}.mp4",
                    job_dir / "generated_images" / scene_id / f"{asset_id}.jpg",
                    job_dir / "generated_images" / scene_id / f"gen_{scene_id}_cand_1.jpg",
                ]
                for cand_file in local_candidates:
                    if cand_file.exists() and cand_file.stat().st_size > 1000:
                        logger.info(f"Scene {scene_id}: Found local pre-cached asset at {cand_file.name}")
                        if cand_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                            normalized = self._image_to_video_clip(cand_file, clip_path, profile, scene_duration)
                        else:
                            normalized = self._normalize_clip(cand_file, clip_path, profile, scene_duration)
                        if normalized:
                            break

            # 3. If still not normalized, scan any candidate frame in scene's candidate folder
            if not normalized:
                scene_cand_dir = job_dir / "candidate_frames" / scene_id
                if scene_cand_dir.exists():
                    for f in scene_cand_dir.glob("*.*"):
                        if f.stat().st_size > 2000 and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".mp4"):
                            logger.info(f"Scene {scene_id}: Using existing candidate frame {f.name}")
                            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                                normalized = self._image_to_video_clip(f, clip_path, profile, scene_duration)
                            else:
                                normalized = self._normalize_clip(f, clip_path, profile, scene_duration)
                            if normalized:
                                break

            # 4. If remote asset URL is available, download it with proper extension
            if not normalized and asset_url and not asset_url.startswith("/jobs/artifacts/download"):
                downloaded = self._download_clip(asset_url, tmp_dir / f"dl_{i:04d}_raw")
                if downloaded and downloaded.exists() and downloaded.stat().st_size > 1000:
                    if downloaded.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                        normalized = self._image_to_video_clip(downloaded, clip_path, profile, scene_duration)
                    else:
                        normalized = self._normalize_clip(downloaded, clip_path, profile, scene_duration)

            # 5. Fallback Tier 1: Search ANY valid image across the entire job
            if not normalized:
                fallback_img = None
                for ext in ("*.jpg", "*.png", "*.webp"):
                    for cand in job_dir.glob(f"**/{ext}"):
                        if cand.stat().st_size > 5000 and "tmp" not in str(cand):
                            fallback_img = cand
                            break
                    if fallback_img:
                        break

                if fallback_img:
                    logger.info(f"Scene {scene_id}: Reusing visual {fallback_img.name} to avoid black screen")
                    normalized = self._image_to_video_clip(fallback_img, clip_path, profile, scene_duration)

            # 6. Fallback Tier 2: Check storage fallback library
            if not normalized:
                fallback_dir = Path(settings.fallback_library_dir)
                if fallback_dir.exists():
                    for f in fallback_dir.glob("*.jpg"):
                        if f.stat().st_size > 5000:
                            normalized = self._image_to_video_clip(f, clip_path, profile, scene_duration)
                            if normalized:
                                break

            # 7. Fallback Tier 3: Styled cinematic ambient generator (zero black screen guarantee)
            if not normalized:
                logger.warning(f"Scene {scene_id}: Generating dynamic ambient visual clip for {scene_duration:.2f}s")
                normalized = self._generate_placeholder(clip_path, profile, scene_duration)

            # Ensure clip was appended
            if normalized and clip_path.exists() and clip_path.stat().st_size > 0:
                clips.append(clip_path)
            else:
                # Emergency basic clip to preserve scene duration and synchronization
                logger.error(f"Scene {scene_id}: Emergency placeholder generation triggered")
                self._generate_placeholder(clip_path, profile, scene_duration)
                clips.append(clip_path)

        return clips

    def _image_to_video_clip(
        self, image_path: Path, output_path: Path, profile: Dict, duration: float
    ) -> Optional[Path]:
        """Convert a static image into an aspect-ratio-normalized video clip with subtle motion."""
        try:
            w, h = profile["width"], profile["height"]
            fps = profile["fps"]
            total_frames = max(1, int(round(duration * fps)))

            # High-performance Ken Burns zoompan with optimal pre-scaling (prevents heavy 4K memory overhead)
            vf = (
                f"scale={int(w*1.15)}:{int(h*1.15)}:force_original_aspect_ratio=increase,"
                f"zoompan=z='min(zoom+0.0010,1.20)':d={total_frames}:"
                f"x='(iw/2-(iw/zoom/2)) + (on/{total_frames})*(iw*0.03)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps},"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p"
            )

            self._run_ffmpeg([
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(image_path),
                "-t", str(duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-an",
                str(output_path),
            ])
            return output_path if output_path.exists() and output_path.stat().st_size > 0 else None
        except Exception as e:
            logger.warning(f"Image zoompan failed ({e}); falling back to static scale/pad")
            try:
                vf = profile["vf"]
                fps = profile["fps"]
                self._run_ffmpeg([
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", str(image_path),
                    "-t", str(duration),
                    "-vf", f"{vf},fps={fps}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    str(output_path),
                ])
                return output_path if output_path.exists() else None
            except Exception as e2:
                logger.error(f"Fallback image to video clip failed: {e2}")
                return None

    def _download_clip(self, url: str, dest: Path) -> Optional[Path]:
        """Download remote asset to local disk with extension detection and retries."""
        for attempt in range(self.MAX_DOWNLOAD_RETRIES):
            try:
                with httpx.Client(
                    timeout=self.DOWNLOAD_TIMEOUT,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                ) as client:
                    resp = client.get(url)
                    resp.raise_for_status()

                    content_type = resp.headers.get("content-type", "").lower()
                    url_low = url.lower().split("?")[0]

                    if "image" in content_type or url_low.endswith((".jpg", ".jpeg", ".png", ".webp")):
                        ext = ".jpg" if "png" not in content_type and not url_low.endswith(".png") else ".png"
                    else:
                        ext = ".mp4"

                    dest_with_ext = dest.with_suffix(ext)
                    dest_with_ext.write_bytes(resp.content)
                    if dest_with_ext.stat().st_size < 1000:
                        logger.warning(f"Downloaded clip too small: {url}")
                        continue
                    return dest_with_ext
            except Exception as e:
                logger.warning(f"Download attempt {attempt+1} failed for {url}: {e}")
                if attempt < self.MAX_DOWNLOAD_RETRIES - 1:
                    time.sleep(2 ** attempt)
        return None

    def _normalize_clip(
        self, input_path: Path, output_path: Path, profile: Dict, target_duration: float
    ) -> Optional[Path]:
        """Scale/crop clip to output profile and trim or loop to target duration."""
        try:
            # If input file is an image, delegate directly to _image_to_video_clip
            if input_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return self._image_to_video_clip(input_path, output_path, profile, target_duration)

            # Probe clip duration
            clip_duration = self._get_media_duration(input_path)

            # If clip duration is 0, it may be an image mislabeled as mp4
            if clip_duration <= 0.0:
                logger.info(f"Clip {input_path.name} has duration 0; processing as static image")
                return self._image_to_video_clip(input_path, output_path, profile, target_duration)

            # If clip is shorter than scene duration, loop it
            if 0 < clip_duration < target_duration:
                loop_count = int(target_duration / clip_duration) + 2
                input_flag = ["-stream_loop", str(loop_count), "-i", str(input_path)]
            else:
                input_flag = ["-i", str(input_path)]

            vf = profile["vf"]
            fps = profile["fps"]

            self._run_ffmpeg([
                "ffmpeg", "-y",
                *input_flag,
                "-t", str(target_duration),
                "-vf", f"{vf},fps={fps}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-an",
                str(output_path),
            ])
            return output_path if output_path.exists() and output_path.stat().st_size > 0 else None
        except Exception as e:
            logger.error(f"Clip normalization failed: {e}")
            return None

    def _generate_placeholder(
        self, output_path: Path, profile: Dict, duration: float
    ) -> Optional[Path]:
        """Generate a styled cinematic ambient backdrop (never an empty black screen)."""
        w, h = profile["width"], profile["height"]
        fps = profile["fps"]
        try:
            # Deep slate-indigo cinematic backdrop with subtle vignette
            lavfi_desc = (
                f"color=c=0x0f172a:s={w}x{h}:r={fps}:d={duration},"
                f"drawbox=y=0:h={h}:color=0x1e293b@0.5:t=fill,"
                f"vignette=PI/4,format=yuv420p"
            )
            self._run_ffmpeg([
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", lavfi_desc,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-an",
                str(output_path),
            ])
            return output_path if output_path.exists() and output_path.stat().st_size > 0 else None
        except Exception as e:
            logger.warning(f"Styled backdrop failed ({e}), using solid fallback")
            try:
                self._run_ffmpeg([
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", f"color=c=0x111827:s={w}x{h}:r={fps}:d={duration}",
                    "-t", str(duration),
                    "-c:v", "libx264", "-preset", self.preset, "-crf", "26",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    str(output_path),
                ])
                return output_path if output_path.exists() else None
            except Exception as e2:
                logger.error(f"Fallback generation failed: {e2}")
                return None

    def _analyze_clip_luma_stats(self, clip_path: Path) -> Dict[str, float]:
        """Analyze representative frame luminance, contrast, and saturation."""
        import io
        from PIL import Image, ImageStat
        try:
            # Extract 1 representative middle frame via ffmpeg image pipe
            cmd = [
                "ffmpeg", "-y", "-ss", "0.5", "-i", str(clip_path),
                "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "-"
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=12)
            if proc.returncode == 0 and len(proc.stdout) > 500:
                img = Image.open(io.BytesIO(proc.stdout)).convert("RGB")
            else:
                img = Image.open(clip_path).convert("RGB")

            # Luminance & contrast
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            luma = float(stat.mean[0])
            contrast = float(stat.stddev[0])

            # Saturation
            hsv = img.convert("HSV")
            hsv_stat = ImageStat.Stat(hsv)
            sat = float(hsv_stat.mean[1]) / 255.0

            return {"luma": luma, "contrast": contrast, "saturation": sat}
        except Exception as e:
            logger.warning(f"Could not analyze luma stats for {clip_path.name}: {e}")
            return {"luma": 128.0, "contrast": 50.0, "saturation": 0.4}

    def _apply_color_consistency_stage(
        self, scenes: List[Dict], scene_clips: List[Path], profile: Dict, tmp_dir: Path
    ) -> List[Path]:
        """
        Analyze and apply restrained per-clip colour and brightness normalization
        to achieve visual consistency across mixed stock and AI sources.
        Preserves intentional dramatic lighting (e.g. night, sunset).
        """
        if len(scenes) != len(scene_clips):
            return scene_clips

        # 1. Analyze all clips
        stats = []
        for i, (sc, clip) in enumerate(zip(scenes, scene_clips)):
            meta_light = (str(sc.get("lighting", "")) + " " + str(sc.get("mood", ""))).lower()
            is_intentional_dark = any(
                k in meta_light for k in ["night", "dark", "nocturnal", "sunset", "dusk", "candlelight", "dim", "shadow"]
            )
            s = self._analyze_clip_luma_stats(clip)
            s["is_intentional_dark"] = is_intentional_dark
            stats.append(s)

        # 2. Compute non-dark target baseline
        non_dark_lumas = [s["luma"] for s in stats if not s["is_intentional_dark"]]
        if non_dark_lumas:
            target_luma = max(110.0, min(145.0, sum(non_dark_lumas) / len(non_dark_lumas)))
        else:
            target_luma = 125.0

        target_contrast = 48.0
        target_sat = 0.42

        # 3. Apply restrained corrections
        normalized_clips = []
        for i, (sc, clip, s) in enumerate(zip(scenes, scene_clips, stats)):
            luma = s["luma"]
            contrast = s["contrast"]
            sat = s["saturation"]

            # If scene is intentionally night or sunset, preserve the mood
            if s["is_intentional_dark"]:
                logger.info(f"Scene {i+1} has intentional {sc.get('lighting', 'dark')} lighting; preserving mood")
                sc["color_normalization"] = {
                    "original_luma": round(luma, 1),
                    "target_luma": round(luma, 1),
                    "correction_applied": False,
                    "reason": "intentional_dramatic_lighting",
                }
                normalized_clips.append(clip)
                continue

            # Gentle, restrained adjustments
            delta_luma = target_luma - luma
            b_adjust = max(-0.06, min(0.06, (delta_luma / 255.0) * 0.35))

            delta_contrast = target_contrast - contrast
            c_adjust = max(0.94, min(1.06, 1.0 + (delta_contrast / 100.0) * 0.20))

            delta_sat = target_sat - sat
            s_adjust = max(0.94, min(1.06, 1.0 + delta_sat * 0.25))

            needs_correction = abs(b_adjust) > 0.015 or abs(c_adjust - 1.0) > 0.02 or abs(s_adjust - 1.0) > 0.02

            if needs_correction:
                norm_clip = tmp_dir / f"color_norm_{i:04d}.mp4"
                try:
                    eq_filter = f"eq=brightness={b_adjust:.3f}:contrast={c_adjust:.3f}:saturation={s_adjust:.3f}"
                    self._run_ffmpeg([
                        "ffmpeg", "-y",
                        "-i", str(clip),
                        "-vf", f"{eq_filter},format=yuv420p",
                        "-c:v", "libx264", "-preset", self.preset, "-crf", "22",
                        "-an",
                        str(norm_clip),
                    ])
                    if norm_clip.exists() and norm_clip.stat().st_size > 0:
                        normalized_clips.append(norm_clip)
                        sc["color_normalization"] = {
                            "original_luma": round(luma, 1),
                            "target_luma": round(target_luma, 1),
                            "applied_brightness": round(b_adjust, 3),
                            "applied_contrast": round(c_adjust, 3),
                            "applied_saturation": round(s_adjust, 3),
                            "correction_applied": True,
                        }
                        logger.info(
                            f"Scene {i+1}: Normalized luma {luma:.1f} -> target {target_luma:.1f} "
                            f"(eq brightness={b_adjust:.3f}, contrast={c_adjust:.3f}, sat={s_adjust:.3f})"
                        )
                        continue
                except Exception as ne:
                    logger.warning(f"Color normalization encode failed for scene {i+1} ({ne}); using original clip")

            sc["color_normalization"] = {
                "original_luma": round(luma, 1),
                "target_luma": round(target_luma, 1),
                "correction_applied": False,
            }
            normalized_clips.append(clip)

        return normalized_clips

    def _burn_captions(
        self, video_path: Path, srt_path: Path, output_path: Path, profile: Dict, duration: Optional[float] = None
    ) -> None:
        """Burn SRT captions into video using libass with safe path escaping and Unicode font support."""
        try:
            font_family = getattr(settings, "subtitle_font_family", "Nirmala UI")
            srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
            burn_timeout = max(600, int((duration or 60.0) * 4))
            self._run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-vf", (
                    f"subtitles='{srt_escaped}':"
                    f"force_style='FontName={font_family},FontSize=24,PrimaryColour=&Hffffff&,"
                    f"OutlineColour=&H000000&,Outline=2,Alignment=2'"
                ),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                str(output_path),
            ], timeout=burn_timeout)
        except Exception as e:
            logger.warning(f"Caption burn-in failed ({e}); using uncaptioned video")
            shutil.copy2(video_path, output_path)

    def _get_media_duration(self, path: Path) -> float:
        """Get exact duration of a media file via ffprobe."""
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", str(path)],
                capture_output=True, text=True, timeout=25
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return float(data.get("format", {}).get("duration", 0.0))
        except Exception as e:
            logger.warning(f"Failed to probe duration for {path}: {e}")
        return 0.0

    @staticmethod
    def _run_ffmpeg(cmd: List[str], timeout: Optional[int] = None) -> str:
        """Run an FFmpeg command, raising on failure with dynamic timeout."""
        cmd_timeout = timeout or 600
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=cmd_timeout)
        if result.returncode != 0:
            error_text = result.stderr[-2000:] if result.stderr else "unknown error"
            raise RuntimeError(f"FFmpeg failed (code {result.returncode}): {error_text}")
        return result.stdout + result.stderr

    def generate_srt(
        self,
        scenes: List[Dict[str, Any]],
        output_path: Path,
    ) -> Path:
        """Generate an SRT subtitle file from scene transcript data."""
        lines = []
        seq = 1

        for scene in scenes:
            start = float(scene.get("start_time", 0.0))
            end = float(scene.get("end_time", start + 1.0))
            text = (scene.get("subtitle_text") or scene.get("transcript_text") or scene.get("narration_text") or "").strip()
            if not text:
                continue

            # Split long text into 2-line captions
            words = text.split()
            chunks = self._chunk_words(words, max_words=10)
            total_chunks = len(chunks)
            chunk_dur = (end - start) / total_chunks if total_chunks > 0 else (end - start)

            for ci, chunk in enumerate(chunks):
                chunk_start = start + ci * chunk_dur
                chunk_end = min(start + (ci + 1) * chunk_dur, end)
                lines.append(str(seq))
                lines.append(
                    f"{self._seconds_to_srt(chunk_start)} --> {self._seconds_to_srt(chunk_end)}"
                )
                lines.append(chunk)
                lines.append("")
                seq += 1

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    @staticmethod
    def _chunk_words(words: List[str], max_words: int = 10) -> List[str]:
        chunks = []
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i:i + max_words]))
        return chunks if chunks else [""]

    @staticmethod
    def _seconds_to_srt(seconds: float) -> str:
        """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
        seconds = max(0.0, seconds)
        total_ms = round(seconds * 1000)
        ms = total_ms % 1000
        total_s = total_ms // 1000
        s = total_s % 60
        total_m = total_s // 60
        m = total_m % 60
        h = total_m // 60
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
