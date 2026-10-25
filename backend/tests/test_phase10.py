"""
Phase 10 tests: Timing, captions, real FFmpeg rendering, and FFprobe validation.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from PIL import Image
import pytest

from app.services.rendering_service import RenderingService, OUTPUT_PROFILES
from app.services.media_validation_service import MediaValidationService


def test_real_render_and_ffprobe_validation(tmp_path):
    renderer = RenderingService()
    validator = MediaValidationService()

    # 1. Synthesize 4.0s test narration audio
    audio_path = tmp_path / "test_narration.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1",
            str(audio_path),
        ],
        check=True, capture_output=True, timeout=20,
    )

    # 2. Create 2 test scene visuals (images converted to video with motion)
    img1 = tmp_path / "visual1.jpg"
    img2 = tmp_path / "visual2.jpg"
    Image.new("RGB", (1920, 1080), color=(30, 60, 90)).save(img1)
    Image.new("RGB", (1920, 1080), color=(90, 40, 40)).save(img2)

    scenes = [
        {
            "scene_id": "scene_001",
            "start_time": 0.0,
            "end_time": 2.0,
            "duration": 2.0,
            "transcript_text": "First scene introducing recurring savings.",
            "local_path": str(img1),
            "selected_asset_url": None,
        },
        {
            "scene_id": "scene_002",
            "start_time": 2.0,
            "end_time": 4.0,
            "duration": 2.0,
            "transcript_text": "Second scene demonstrating compound balance growth.",
            "local_path": str(img2),
            "selected_asset_url": None,
        },
    ]

    # 3. Generate captions SRT
    srt_path = tmp_path / "captions.srt"
    renderer.generate_srt(scenes, srt_path)
    assert srt_path.exists()
    srt_valid, srt_err = validator.validate_srt(srt_path)
    assert srt_valid is True, f"SRT validation failed: {srt_err}"

    # 4. Render 16:9 video
    out_16x9 = renderer.render_video(
        scenes=scenes,
        audio_path=audio_path,
        output_dir=tmp_path,
        aspect_ratio="16:9",
        srt_path=srt_path,
        burn_captions=False,  # Test base render stream compliance
    )
    assert out_16x9.exists()
    assert out_16x9.stat().st_size > 5000

    # 5. FFprobe automated validation
    val_res = validator.validate_output(
        mp4_path=out_16x9,
        aspect_ratio="16:9",
        expected_duration=4.0,
        job_id="test_render_job",
    )

    assert val_res["overall_passed"] is True, f"Validation failed: {val_res.get('errors')}"
    # Verify stream checks
    check_names = {c["check"]: c["passed"] for c in val_res["checks"]}
    assert check_names.get("video_stream_exists") is True
    assert check_names.get("audio_stream_exists") is True
    assert check_names.get("duration_matches_narration") is True
    assert check_names.get("resolution") is True
    assert check_names.get("pixel_format") is True
