"""
Phase 8 tests: Story-level visual diversity and narrative continuity validation.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image
import pytest

from app.services.diversity_and_continuity_service import (
    VisualDiversityTracker,
    NarrativeContinuityValidator,
    compute_dhash,
    hamming_distance,
)


def test_dhash_and_hamming_distance(tmp_path):
    img1_path = tmp_path / "img1.png"
    img2_path = tmp_path / "img2.png"

    # Create solid image and slightly altered image
    Image.new("RGB", (64, 64), color="blue").save(img1_path)
    Image.new("RGB", (64, 64), color="blue").save(img2_path)

    h1 = compute_dhash(img1_path)
    h2 = compute_dhash(img2_path)
    assert len(h1) > 0
    assert hamming_distance(h1, h2) == 0


def test_repeated_cliche_triggers_diversity_rejection():
    tracker = VisualDiversityTracker()

    scene1 = {
        "scene_id": "s1",
        "visual_subject": "piggy bank and coins",
        "visual_continuity_requirements": None,
    }
    cand1 = {"id": "asset_101", "tags": "piggy bank, coins, savings"}
    tracker.record_selection(cand1, scene1)

    # Next scene also tries to pick piggy bank / coins
    scene2 = {
        "scene_id": "s2",
        "visual_subject": "piggy bank and coins",
        "visual_continuity_requirements": None,
    }
    cand2 = {"id": "asset_102", "tags": "piggy bank, savings"}

    diversity_score, repetition_risk, is_excessive, reason = tracker.check_candidate_diversity(cand2, scene2)

    assert repetition_risk >= 0.70
    assert is_excessive is True
    assert "repeated motif" in reason.lower() or "verbatim subject" in reason.lower()


def test_narrative_continuity_validator():
    validator = NarrativeContinuityValidator()

    # Valid sequence
    valid_scenes = [
        {"scene_id": "s1", "start_time": 0.0, "end_time": 5.0, "narrative_role": "Exposition", "visual_subject": "budget spreadsheet"},
        {"scene_id": "s2", "start_time": 5.0, "end_time": 10.0, "narrative_role": "Progression", "visual_subject": "digital deposit"},
        {"scene_id": "s3", "start_time": 10.0, "end_time": 15.0, "narrative_role": "Resolution", "visual_subject": "homeowner peaceful"},
    ]
    is_valid, issues, warnings = validator.validate_video_continuity(valid_scenes, 15.0)
    assert is_valid is True
    assert len(issues) == 0

    # Sequence with 3s gap
    broken_scenes = [
        {"scene_id": "s1", "start_time": 0.0, "end_time": 5.0, "narrative_role": "Exposition"},
        {"scene_id": "s2", "start_time": 8.0, "end_time": 15.0, "narrative_role": "Progression"},  # 3s gap
    ]
    is_valid, issues, warnings = validator.validate_video_continuity(broken_scenes, 15.0)
    assert is_valid is False
    assert any("gap" in err.lower() for err in issues)
