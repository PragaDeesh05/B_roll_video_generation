"""
Phase 4 tests: Pixabay retrieval, media validation, hard constraints, and rights checks.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

from app.services.pixabay_provider import PixabayProvider
from app.utils.media import extract_video_frames


def test_retrieve_candidates_returns_multiple(mock_scene):
    prov = PixabayProvider()
    used = set()
    candidates = prov.retrieve_candidates(mock_scene, used, max_candidates=3)
    assert len(candidates) == 3
    ids = [c["id"] for c in candidates]
    assert len(set(ids)) == 3  # Distinct candidate IDs

    # Check provenance
    for c in candidates:
        prov_record = c["provenance"]
        assert prov_record["commercial_use_eligible"] is True
        assert "Pixabay" in prov_record["licence_name"]
        assert prov_record["ai_generated"] is False


def test_hard_constraint_watermark_rejection():
    prov = PixabayProvider()
    fake_asset = {
        "id": "12345",
        "tags": "nature, watermark, stock footage",
        "user": "test_user",
        "videos": {"large": {"url": "https://example.com/video.mp4"}},
    }
    scene = {"must_avoid": [], "excluded_visual_elements": []}
    passed, reason = prov._check_hard_constraints(fake_asset, scene)
    assert passed is False
    assert "watermark" in reason.lower()


def test_hard_constraint_avoid_rejection():
    prov = PixabayProvider()
    fake_asset = {
        "id": "12346",
        "tags": "celebration, beer, party, alcohol",
        "user": "test_user",
        "videos": {"large": {"url": "https://example.com/video.mp4"}},
    }
    scene = {"must_avoid": ["alcohol"], "excluded_visual_elements": []}
    passed, reason = prov._check_hard_constraints(fake_asset, scene)
    assert passed is False
    assert "alcohol" in reason.lower()


def test_extract_video_frames(tmp_path):
    test_video = tmp_path / "test_clip.mp4"
    # Create a 3-second test MP4
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
            "-pix_fmt", "yuv420p",
            str(test_video)
        ],
        check=True, capture_output=True, timeout=20,
    )

    frames_dir = tmp_path / "frames"
    frames = extract_video_frames(test_video, frames_dir, num_frames=3)
    assert len(frames) == 3
    for f in frames:
        assert f.exists()
        assert f.stat().st_size > 500
