"""Media utility helpers."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Any


def probe_audio(path: Path, check_silence: bool = True) -> Dict[str, Any]:
    """
    Use ffprobe to validate and get info about an audio file.
    Detects invalid, corrupted, empty, or silent audio.
    Returns dict with keys: valid, duration, streams, error, is_silent.
    """
    try:
        if not path.exists() or path.stat().st_size == 0:
            return {"valid": False, "error": "File does not exist or is empty", "duration": 0}

        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return {"valid": False, "error": result.stderr[-500:], "duration": 0}

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))

        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if not audio_streams:
            return {"valid": False, "error": "No audio streams found", "duration": 0}

        if duration <= 0:
            return {"valid": False, "error": "Audio duration is 0 seconds", "duration": 0}

        # Silence detection via volumedetect
        if check_silence and duration > 0.5:
            vol_res = subprocess.run(
                ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=30
            )
            vol_output = vol_res.stderr or ""
            max_vol_match = re.search(r"max_volume:\s*([-\d\.]+|-inf)\s*dB", vol_output)
            if max_vol_match:
                max_vol_str = max_vol_match.group(1)
                if max_vol_str == "-inf" or (max_vol_str.replace("-", "").replace(".", "").isdigit() and float(max_vol_str) <= -55.0):
                    return {
                        "valid": False,
                        "error": "Audio file contains only silence",
                        "duration": duration,
                        "is_silent": True,
                    }

        return {
            "valid": True,
            "duration": duration,
            "streams": audio_streams,
            "format": fmt.get("format_name", ""),
            "is_silent": False,
        }
    except Exception as e:
        return {"valid": False, "error": str(e), "duration": 0}


def probe_video(path: Path) -> Dict[str, Any]:
    """
    Use ffprobe to inspect a video file.
    Returns dict with keys: valid, width, height, duration, fps, codec, pix_fmt, has_audio.
    """
    try:
        if not path.exists() or path.stat().st_size == 0:
            return {"valid": False, "error": "File does not exist or is empty"}

        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return {"valid": False, "error": result.stderr[-500:]}

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            return {"valid": False, "error": "No video stream found"}

        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        codec = video_stream.get("codec_name", "")
        pix_fmt = video_stream.get("pix_fmt", "")

        # Frame rate
        r_fps = video_stream.get("r_frame_rate", "30/1")
        try:
            num, den = r_fps.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        except Exception:
            fps = 30.0

        return {
            "valid": True,
            "width": width,
            "height": height,
            "duration": duration,
            "fps": fps,
            "codec": codec,
            "pix_fmt": pix_fmt,
            "has_audio": audio_stream is not None,
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def extract_video_frames(
    video_path: Path,
    output_dir: Path,
    num_frames: int = 3,
) -> List[Path]:
    """
    Extract multiple representative frames distributed across a video clip's timeline
    (specifically at 20% beginning, 50% middle, and 80% end marks).
    Used for temporal action verification and independent Gemini Vision relevance scoring.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if not video_path.exists() or video_path.stat().st_size == 0:
        return []

    # Get duration
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
            capture_output=True, text=True, timeout=15
        )
        duration = float(json.loads(res.stdout).get("format", {}).get("duration", 0))
    except Exception:
        duration = 0.0

    frames = []
    if duration <= 0:
        duration = 3.0

    # Distribute frame timestamps across video timeline (20% beginning, 50% middle, 80% end)
    if num_frames == 3:
        sample_fractions = [0.20, 0.50, 0.80]
        fraction_labels = ["beginning_20pct", "middle_50pct", "end_80pct"]
    elif num_frames == 2:
        sample_fractions = [0.25, 0.75]
        fraction_labels = ["beginning_25pct", "end_75pct"]
    else:
        sample_fractions = [(k + 1) / (num_frames + 1) for k in range(num_frames)]
        fraction_labels = [f"frame_{k:02d}" for k in range(num_frames)]

    timestamps = [
        max(0.05, min(duration - 0.05, round(duration * frac, 3)))
        for frac in sample_fractions
    ]

    stem = video_path.stem
    for idx, (ts, label) in enumerate(zip(timestamps, fraction_labels)):
        out_frame = output_dir / f"{stem}_{label}_{int(ts*1000):06d}ms.jpg"
        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(ts),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(out_frame),
            ]
            subprocess.run(cmd, capture_output=True, timeout=20)
            if out_frame.exists() and out_frame.stat().st_size > 500:
                frames.append(out_frame)
        except Exception:
            pass

    return frames

