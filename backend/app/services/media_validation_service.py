"""
Media Validation Service
Uses FFprobe and FFmpeg analysis filters to validate rendered outputs.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

# Output profiles: (width, height, fps)
OUTPUT_PROFILES = {
    "16:9": (1920, 1080, 30),
    "9:16": (1080, 1920, 30),
    "1:1": (1080, 1080, 30),
}

DURATION_TOLERANCE = 1.5   # seconds
FPS_TOLERANCE = 2.0         # fps
RESOLUTION_TOLERANCE = 4    # pixels (allow minor rounding)


class MediaValidationService:
    """FFprobe-based validation of rendered MP4 outputs."""

    def validate_output(
        self,
        mp4_path: Path,
        aspect_ratio: str,
        expected_duration: float,
        job_id: str,
        scenes: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Full validation of a rendered MP4 file.

        Returns a dict with overall_passed, checks, warnings, errors.
        """
        checks = []
        warnings = []
        errors = []

        if not mp4_path.exists():
            return {
                "aspect_ratio": aspect_ratio,
                "file_path": str(mp4_path),
                "overall_passed": False,
                "checks": [],
                "warnings": [],
                "errors": [f"Output file does not exist: {mp4_path}"],
            }

        # 1. Probe the file
        probe = self._probe(mp4_path)
        if probe is None:
            errors.append("FFprobe failed: file may be corrupted or unreadable")
            return {
                "aspect_ratio": aspect_ratio,
                "file_path": str(mp4_path),
                "overall_passed": False,
                "checks": checks,
                "warnings": warnings,
                "errors": errors,
            }

        # 2. Extract stream info
        video_stream = next(
            (s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None
        )
        audio_stream = next(
            (s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None
        )
        fmt = probe.get("format", {})
        actual_duration = float(fmt.get("duration", 0))

        # ── Check: video stream exists ───────────────────────────────────────
        checks.append({
            "check": "video_stream_exists",
            "passed": video_stream is not None,
            "value": video_stream is not None,
            "detail": "H.264 video stream present" if video_stream else "No video stream found",
        })
        if not video_stream:
            errors.append("No video stream found in output")

        # ── Check: audio stream exists ───────────────────────────────────────
        checks.append({
            "check": "audio_stream_exists",
            "passed": audio_stream is not None,
            "value": audio_stream is not None,
            "detail": "Audio stream present" if audio_stream else "No audio stream found",
        })
        if not audio_stream:
            errors.append("No audio stream found in output")

        # ── Check: duration matches narration ────────────────────────────────
        dur_ok = abs(actual_duration - expected_duration) <= DURATION_TOLERANCE
        checks.append({
            "check": "duration_matches_narration",
            "passed": dur_ok,
            "value": round(actual_duration, 2),
            "threshold": f"{expected_duration:.2f} ± {DURATION_TOLERANCE}s",
            "detail": f"Actual: {actual_duration:.2f}s, Expected: {expected_duration:.2f}s",
        })
        if not dur_ok:
            errors.append(
                f"Duration mismatch: {actual_duration:.2f}s vs {expected_duration:.2f}s"
            )

        # ── Check: resolution ────────────────────────────────────────────────
        if video_stream and aspect_ratio in OUTPUT_PROFILES:
            expected_w, expected_h, expected_fps = OUTPUT_PROFILES[aspect_ratio]
            actual_w = int(video_stream.get("width", 0))
            actual_h = int(video_stream.get("height", 0))
            res_ok = (
                abs(actual_w - expected_w) <= RESOLUTION_TOLERANCE
                and abs(actual_h - expected_h) <= RESOLUTION_TOLERANCE
            )
            checks.append({
                "check": "resolution",
                "passed": res_ok,
                "value": f"{actual_w}x{actual_h}",
                "threshold": f"{expected_w}x{expected_h}",
                "detail": f"Actual: {actual_w}x{actual_h}",
            })
            if not res_ok:
                warnings.append(
                    f"Resolution {actual_w}x{actual_h} != expected {expected_w}x{expected_h}"
                )

            # ── Check: frame rate ────────────────────────────────────────────
            fps_str = video_stream.get("avg_frame_rate", "0/1")
            try:
                num, den = fps_str.split("/")
                actual_fps = float(num) / float(den) if float(den) != 0 else 0
            except Exception:
                actual_fps = 0.0
            fps_ok = abs(actual_fps - expected_fps) <= FPS_TOLERANCE
            checks.append({
                "check": "frame_rate",
                "passed": fps_ok,
                "value": round(actual_fps, 2),
                "threshold": f"{expected_fps} ± {FPS_TOLERANCE}",
            })
            if not fps_ok:
                warnings.append(f"FPS {actual_fps:.1f} != expected {expected_fps}")

        # ── Check: video codec ───────────────────────────────────────────────
        if video_stream:
            codec = video_stream.get("codec_name", "")
            codec_ok = codec in ("h264", "libx264")
            checks.append({
                "check": "video_codec",
                "passed": codec_ok,
                "value": codec,
                "threshold": "h264",
            })

        # ── Check: audio codec ───────────────────────────────────────────────
        if audio_stream:
            acodec = audio_stream.get("codec_name", "")
            acodec_ok = acodec in ("aac",)
            checks.append({
                "check": "audio_codec",
                "passed": acodec_ok,
                "value": acodec,
                "threshold": "aac",
            })

        # ── Check: pixel format ──────────────────────────────────────────────
        if video_stream:
            pix_fmt = video_stream.get("pix_fmt", "")
            pix_ok = pix_fmt in ("yuv420p", "yuvj420p")
            checks.append({
                "check": "pixel_format",
                "passed": pix_ok,
                "value": pix_fmt,
                "threshold": "yuv420p",
            })

        # ── Check: black frames (using FFmpeg blackdetect) ──────────────────
        black_result = self._detect_black_frames(mp4_path)
        if black_result["excessive_black"]:
            warnings.append(
                f"Excessive black frames detected: {black_result['black_duration']:.1f}s"
            )
        checks.append({
            "check": "black_frame_detection",
            "passed": not black_result["excessive_black"],
            "value": black_result,
            "detail": "Black frame analysis (threshold: >10% of video)",
        })

        # ── Check: frozen frames ─────────────────────────────────────────────
        frozen_result = self._detect_frozen_frames(mp4_path)
        if frozen_result["has_frozen"]:
            warnings.append("Frozen/static frames detected — may indicate rendering issue")
        checks.append({
            "check": "frozen_frame_detection",
            "passed": not frozen_result["has_frozen"],
            "value": frozen_result,
        })

        # ── Check: silent audio ──────────────────────────────────────────────
        if audio_stream:
            silence_result = self._detect_silence(mp4_path)
            audio_ok = not silence_result.get("all_silent", False)
            checks.append({
                "check": "audio_not_silent",
                "passed": audio_ok,
                "value": silence_result,
                "detail": "Checks audio is not completely silent",
            })
            if not audio_ok:
                errors.append("Audio track appears to be completely silent")

        # ── Check: minimum scene duration & shot pacing ──────────────────────
        if scenes:
            min_target = getattr(settings, "min_scene_duration_seconds", 1.5)
            short_scenes = [
                s.get("scene_id", f"scene_{idx+1}")
                for idx, s in enumerate(scenes)
                if float(s.get("duration", 0.0) or 0.0) < min_target
            ]
            has_short = len(short_scenes) > 0 and actual_duration >= min_target * len(scenes)
            checks.append({
                "check": "scene_pacing_and_durations",
                "passed": not has_short,
                "value": len(short_scenes),
                "threshold": f">= {min_target}s per shot",
                "detail": f"{len(short_scenes)} shots under {min_target}s" if has_short else "All shots meet pacing criteria",
            })
            if has_short:
                warnings.append(f"Scenes {short_scenes} below target duration of {min_target}s")

        # ── Check: adjacent scene luminance jumps ────────────────────────────
        if scenes and len(scenes) > 1:
            jump_thresh = getattr(settings, "max_luminance_jump_threshold", 45.0)
            luma_jumps = self._check_adjacent_luminance_jumps(mp4_path, scenes, jump_thresh)
            excessive_jumps = [j for j in luma_jumps if j["is_excessive"] and not j["is_intentional"]]
            checks.append({
                "check": "luminance_continuity",
                "passed": len(excessive_jumps) == 0,
                "value": len(excessive_jumps),
                "threshold": f"<= {jump_thresh} Y-delta",
                "detail": (
                    f"{len(excessive_jumps)} unexplained luminance jumps detected"
                    if excessive_jumps
                    else "Visual luminance smooth across transitions"
                ),
            })
            if excessive_jumps:
                warnings.append(f"Large luminance jumps across cuts: {[j['cut'] for j in excessive_jumps]}")

        # ── Overall result ───────────────────────────────────────────────────
        overall_passed = len(errors) == 0

        return {
            "aspect_ratio": aspect_ratio,
            "file_path": str(mp4_path),
            "overall_passed": overall_passed,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
        }

    def validate_srt(self, srt_path: Path) -> Tuple[bool, Optional[str]]:
        """SRT validation: check timestamp ordering, validity, and Unicode integrity."""
        if not srt_path.exists():
            return False, "SRT file does not exist"
        try:
            content = srt_path.read_text(encoding="utf-8")
            if "\ufffd" in content:
                return False, "SRT contains Unicode replacement character (corrupted glyphs)"

            blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
            if not blocks:
                return False, "SRT file is empty"

            prev_end = -1.0
            for i, block in enumerate(blocks):
                lines = block.splitlines()
                if len(lines) < 3:
                    return False, f"Block {i+1} has fewer than 3 lines"
                time_line = lines[1]
                parts = time_line.split(" --> ")
                if len(parts) != 2:
                    return False, f"Block {i+1} has invalid time line: {time_line}"
                start = self._srt_time_to_seconds(parts[0])
                end = self._srt_time_to_seconds(parts[1])
                if start > end:
                    return False, f"Block {i+1}: start > end ({start:.3f} > {end:.3f})"
                if start < prev_end - 0.01:
                    return False, f"Block {i+1}: start {start:.3f} < previous end {prev_end:.3f}"
                prev_end = end

            return True, None
        except Exception as e:
            return False, str(e)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _probe(self, path: Path) -> Optional[Dict]:
        """Run ffprobe on a file and return parsed JSON."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams", "-show_format",
                    str(path),
                ],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        except Exception as e:
            logger.error(f"ffprobe error on {path}: {e}")
            return None

    def _detect_black_frames(self, path: Path) -> Dict:
        """Detect excessive black frames using FFmpeg blackdetect filter."""
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-i", str(path),
                    "-vf", "blackdetect=d=0.5:pix_th=0.1",
                    "-an", "-f", "null", "-"
                ],
                capture_output=True, text=True, timeout=120
            )
            output = result.stderr
            total_black = 0.0
            for line in output.splitlines():
                if "black_duration" in line:
                    import re
                    m = re.search(r"black_duration:([\d.]+)", line)
                    if m:
                        total_black += float(m.group(1))

            # Get video duration
            probe = self._probe(path)
            vid_duration = float(probe.get("format", {}).get("duration", 1)) if probe else 1.0

            excessive = (total_black / vid_duration) > 0.1 if vid_duration > 0 else False
            return {
                "black_duration": total_black,
                "video_duration": vid_duration,
                "black_fraction": total_black / vid_duration if vid_duration > 0 else 0,
                "excessive_black": excessive,
            }
        except Exception as e:
            logger.warning(f"Black frame detection failed: {e}")
            return {"black_duration": 0, "excessive_black": False, "error": str(e)}

    def _detect_frozen_frames(self, path: Path) -> Dict:
        """Detect excessive frozen frames using FFmpeg freezedetect filter."""
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-i", str(path),
                    "-vf", "freezedetect=n=-50dB:d=3.0",
                    "-an", "-f", "null", "-"
                ],
                capture_output=True, text=True, timeout=120
            )
            output = result.stderr
            total_frozen = 0.0
            max_single_freeze = 0.0
            import re
            for line in output.splitlines():
                if "freeze_duration" in line:
                    m = re.search(r"freeze_duration:([\d.]+)", line)
                    if m:
                        dur = float(m.group(1))
                        total_frozen += dur
                        if dur > max_single_freeze:
                            max_single_freeze = dur

            probe = self._probe(path)
            vid_duration = float(probe.get("format", {}).get("duration", 1)) if probe else 1.0

            # Excessive freezing occurs only if a single freeze lasts > 5.0s or total frozen fraction > 20%
            excessive = (max_single_freeze > 5.0) or ((total_frozen / vid_duration) > 0.20 if vid_duration > 0 else False)
            return {
                "has_frozen": excessive,
                "total_frozen_duration": round(total_frozen, 2),
                "max_single_freeze": round(max_single_freeze, 2),
                "excessive_freeze": excessive,
                "raw": output[-400:] if excessive else "",
            }
        except Exception as e:
            logger.warning(f"Frozen frame detection failed: {e}")
            return {"has_frozen": False, "error": str(e)}

    def _detect_silence(self, path: Path) -> Dict:
        """Detect complete silence using FFmpeg silencedetect."""
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-i", str(path),
                    "-af", "silencedetect=n=-60dB:d=0.5",
                    "-f", "null", "-"
                ],
                capture_output=True, text=True, timeout=60
            )
            output = result.stderr
            has_silence = "silence_start" in output
            all_silent = has_silence and "silence_end" not in output
            return {"has_silence": has_silence, "all_silent": all_silent}
        except Exception as e:
            logger.warning(f"Silence detection failed: {e}")
            return {"has_silence": False, "all_silent": False, "error": str(e)}

    def _check_adjacent_luminance_jumps(
        self, mp4_path: Path, scenes: List[Dict], threshold: float = 45.0
    ) -> List[Dict[str, Any]]:
        """Check for large unexplained luminance shifts between consecutive scenes."""
        jumps = []
        scene_lumas = []

        for i, sc in enumerate(scenes):
            # 1. Use color normalization metadata if already computed
            norm_meta = sc.get("color_normalization")
            if norm_meta and "target_luma" in norm_meta:
                scene_lumas.append(float(norm_meta["target_luma"]))
                continue

            # 2. Or sample frame from video at scene midpoint
            start = float(sc.get("start_time", 0.0))
            end = float(sc.get("end_time", start + 2.0))
            mid = (start + end) / 2.0

            try:
                cmd = [
                    "ffmpeg", "-y", "-ss", f"{mid:.2f}", "-i", str(mp4_path),
                    "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "-"
                ]
                proc = subprocess.run(cmd, capture_output=True, timeout=8)
                if proc.returncode == 0 and len(proc.stdout) > 500:
                    import io
                    from PIL import Image, ImageStat
                    img = Image.open(io.BytesIO(proc.stdout)).convert("L")
                    stat = ImageStat.Stat(img)
                    scene_lumas.append(float(stat.mean[0]))
                else:
                    scene_lumas.append(128.0)
            except Exception:
                scene_lumas.append(128.0)

        for i in range(len(scene_lumas) - 1):
            delta = abs(scene_lumas[i + 1] - scene_lumas[i])
            is_excessive = delta > threshold

            # Check if either scene is intentional night / dark / sunset
            light_curr = (str(scenes[i].get("lighting", "")) + " " + str(scenes[i].get("mood", ""))).lower()
            light_next = (str(scenes[i + 1].get("lighting", "")) + " " + str(scenes[i + 1].get("mood", ""))).lower()
            is_intentional = any(
                k in (light_curr + " " + light_next)
                for k in ["night", "dark", "nocturnal", "sunset", "dusk", "candlelight", "dim", "shadow"]
            )

            jumps.append({
                "cut": f"scene_{i+1}->scene_{i+2}",
                "delta": round(delta, 1),
                "is_excessive": is_excessive,
                "is_intentional": is_intentional,
            })

        return jumps

    @staticmethod
    def _srt_time_to_seconds(t: str) -> float:
        """Convert SRT timestamp HH:MM:SS,mmm to seconds."""
        t = t.strip().replace(",", ".")
        parts = t.split(":")
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s
