"""
Phase 6 tests: Independent visual verification & temporal evaluation (Stage 3 & 4).
"""
from __future__ import annotations

import pytest
from app.services.visual_verifier import VisualVerificationService, DeterministicMockVisualVerifier


def test_contradiction_detection():
    verifier = VisualVerificationService(verifier=DeterministicMockVisualVerifier())
    scene = {
        "narration_text": "Modern enterprises rely heavily on cloud computing infrastructure.",
        "semantic_description": "Data centers and digital cloud architecture.",
        "visual_subject": "cloud computing server network",
        "visual_action": "processing high throughput data",
        "narrative_role": "Exposition",
    }
    # Candidate with literal sky clouds (false keyword match)
    false_keyword_candidate = {
        "id": "cand_sky_01",
        "tags": "sky, weather, fluffy clouds, blue atmosphere",
    }
    result = verifier.verify_candidate(scene, false_keyword_candidate)

    assert result["contradiction_detected"] is True
    assert result["verification_score"] < 2.0
    assert "rejection_reason" in result
    assert result["rejection_reason"] is not None


def test_faithful_candidate_promoted():
    verifier = VisualVerificationService(verifier=DeterministicMockVisualVerifier())
    scene = {
        "narration_text": "Regular monthly contributions allow capital reserves to expand.",
        "semantic_description": "Digital banking ledger showing automatic recurring savings contribution.",
        "visual_subject": "automatic savings contribution",
        "visual_action": "transferring into an interest-bearing account",
        "narrative_role": "Action",
    }
    faithful_candidate = {
        "id": "cand_banking_01",
        "tags": "savings, contribution, transferring, automatic deposit, account",
    }
    result = verifier.verify_candidate(scene, faithful_candidate)

    assert result["contradiction_detected"] is False
    assert result["verification_score"] >= 3.5
    assert result["subject_match"] >= 0.7
    assert result["action_match"] >= 0.6


def test_temporal_verification_evidence(tmp_path):
    verifier = VisualVerificationService(verifier=DeterministicMockVisualVerifier())
    scene = {
        "narration_text": "The savings balance increases steadily over time.",
        "visual_subject": "savings balance",
        "visual_action": "increasing",
    }
    candidate = {"id": "cand_growth_01", "tags": "balance, increasing, growth"}

    # Simulate 3 extracted frame paths
    frame1 = tmp_path / "frame1.jpg"
    frame2 = tmp_path / "frame2.jpg"
    frame3 = tmp_path / "frame3.jpg"
    frame1.touch()
    frame2.touch()
    frame3.touch()

    res = verifier.verify_candidate(scene, candidate, [frame1, frame2, frame3])
    assert res["temporal_score"] >= 0.8
    assert "verified across 3 distributed video frames" in res["temporal_evidence"].lower()
