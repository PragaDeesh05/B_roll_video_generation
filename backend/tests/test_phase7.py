"""
Phase 7 tests: Calibrated rejection policy & evidence-based acceptance.
"""
from __future__ import annotations

import pytest
from app.services.calibrated_relevance_policy import CalibratedRelevancePolicy


def test_all_candidates_can_be_rejected():
    policy = CalibratedRelevancePolicy(min_relevance_score=3.0, min_verification_score=3.0)
    scene = {"narration_text": "Advanced cloud computing servers processing transactions."}

    # Low-scoring candidates (e.g. raw clip 0.65 but low verification or contradiction)
    candidates = [
        {"id": "cand_01", "relevance_score": 2.1, "verification_score": 1.5, "contradiction_detected": True, "rejection_reason": "Literal sky"},
        {"id": "cand_02", "relevance_score": 2.4, "verification_score": 2.2, "contradiction_detected": False},
    ]

    accepted, rejected = policy.rank_and_filter_candidates(candidates, scene)
    assert len(accepted) == 0  # ALL rejected!
    assert len(rejected) == 2
    assert "contradiction" in rejected[0]["policy_reason"].lower()


def test_high_clip_rejected_if_contradictory():
    policy = CalibratedRelevancePolicy()
    scene = {"narration_text": "Avoiding dangerous debt."}
    high_clip_contradictory = {
        "id": "cand_high_clip",
        "clip_score": 0.88,
        "relevance_score": 4.5,
        "verification_score": 1.2,
        "contradiction_detected": True,
        "rejection_reason": "Shows lavish reckless spending spree",
    }
    is_ok, composite, reason = policy.evaluate_candidate(high_clip_contradictory, scene)
    assert is_ok is False
    assert "REJECTED" in reason
    assert "contradiction" in reason.lower() or "lavish" in reason.lower()


def test_promotion_of_faithful_candidate():
    policy = CalibratedRelevancePolicy()
    scene = {"narration_text": "Consistent daily savings compound over time."}

    cand_moderate_clip_high_ver = {
        "id": "cand_faithful",
        "clip_score": 0.22,
        "relevance_score": 3.8,
        "verification_score": 4.6,
        "temporal_score": 0.9,
        "visual_quality": 4.5,
        "contradiction_detected": False,
    }

    is_ok, composite, reason = policy.evaluate_candidate(cand_moderate_clip_high_ver, scene)
    assert is_ok is True
    assert composite >= 3.5
    assert "ACCEPTED" in reason


def test_calibration_dataset_persists(tmp_path):
    dataset_path = tmp_path / "test_calib.json"
    policy = CalibratedRelevancePolicy(calibration_dataset_path=dataset_path)
    assert dataset_path.exists()
    import json
    data = json.loads(dataset_path.read_text())
    assert len(data) >= 5
    assert "human_rating" in data[0]
