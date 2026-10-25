"""
Phase 12 tests: Evaluation sheet generation, audit metrics, and master semantic tests.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, init_db
from app.models.job import Job, SceneModel, EvaluationRatingModel
from app.services.evaluation_service import EvaluationService, EVALUATION_COLUMNS
from app.services.visual_verifier import VisualVerificationService, DeterministicMockVisualVerifier
from app.services.openclip_ranker import DeterministicMockCLIPRanker
from app.services.diversity_and_continuity_service import VisualDiversityTracker


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_30_column_evaluation_sheet_generation(tmp_path):
    init_db()
    db = SessionLocal()
    eval_svc = EvaluationService()

    try:
        # Clean up any existing job-eval-test-001
        existing = db.query(Job).filter(Job.id == "job-eval-test-001").first()
        if existing:
            db.query(SceneModel).filter(SceneModel.job_id == "job-eval-test-001").delete()
            db.query(EvaluationRatingModel).filter(EvaluationRatingModel.job_id == "job-eval-test-001").delete()
            db.delete(existing)
            db.commit()

        # Create a test job and scene
        job = Job(
            id="job-eval-test-001",
            input_type="text",
            script_text="Saving regularly increases accumulated wealth.",
            audio_duration=5.0,
            status="completed",
        )
        scene = SceneModel(
            job_id="job-eval-test-001",
            scene_id="scene-001",
            scene_index=0,
            narration_text="Saving regularly increases accumulated wealth.",
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            semantic_description="Demonstration of gradual capital expansion",
            narrative_role="Progression",
            visual_subject="digital balance ledger",
            visual_action="increasing steadily",
            primary_search_queries='["digital banking balance"]',
            selected_asset_id="asset_mock_001",
            selection_reason="Verified by independent VLM and diverse",
            clip_score=0.28,
            relevance_score=4.2,
            verification_score=4.5,
        )
        db.add(job)
        db.add(scene)
        db.commit()

        # Record human rating
        eval_svc.record_human_rating(
            job_id="job-eval-test-001",
            scene_id="scene-001",
            human_rating=5.0,
            human_notes="Excellent match for narration.",
            db=db,
        )

        csv_path, json_path = eval_svc.generate_evaluation_sheet("job-eval-test-001", db, output_dir=tmp_path)

        assert csv_path.exists()
        assert json_path.exists()

        # Check all 30 columns in CSV
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == EVALUATION_COLUMNS
            assert len(header) == 30

            row = next(reader)
            assert len(row) == 30
            assert row[0] == "job-eval-test-001"
            assert row[1] == "scene-001"
            assert row[28] == "5.0"  # human_rating
            assert row[29] == "Excellent match for narration."  # human_notes

        # Check audit metrics
        metrics = eval_svc.compute_audit_metrics("job-eval-test-001", db)
        assert metrics["total_scenes"] == 1
        assert metrics["average_human_relevance"] == 5.0
        assert metrics["percentage_rated_4_or_5"] == 100.0
        assert metrics["narration_coverage_percentage"] == 100.0

    finally:
        db.close()


def test_cloud_computing_sky_contradiction_rejected():
    """Section 20 semantic requirement: 'Cloud computing' must not default to sky footage."""
    verifier = VisualVerificationService(verifier=DeterministicMockVisualVerifier())
    scene = {
        "narration_text": "Enterprises run modern workloads in the cloud.",
        "semantic_description": "Data center servers processing cloud computation.",
        "visual_subject": "cloud computing data infrastructure",
        "visual_action": "processing network traffic",
        "narrative_role": "Exposition",
    }
    sky_candidate = {
        "id": "cand_sky",
        "tags": "sky, cumulus clouds, blue weather, atmosphere",
    }
    result = verifier.verify_candidate(scene, sky_candidate)
    assert result["contradiction_detected"] is True
    assert result["verification_score"] < 2.0


def test_repeated_piggy_bank_diversity_blocked():
    """Section 20 diversity requirement: repeated piggy bank imagery triggers diversity rejection."""
    tracker = VisualDiversityTracker()
    scene1 = {"scene_id": "s1", "visual_subject": "piggy bank"}
    cand1 = {"id": "c1", "tags": "piggy bank, coins"}
    tracker.record_selection(cand1, scene1)

    scene2 = {"scene_id": "s2", "visual_subject": "piggy bank"}
    cand2 = {"id": "c2", "tags": "piggy bank, savings"}
    div_score, rep_risk, is_excessive, reason = tracker.check_candidate_diversity(cand2, scene2)

    assert is_excessive is True
    assert rep_risk >= 0.70


def test_api_evaluation_routes(client):
    res = client.get("/api/v1/jobs/job-eval-test-001/evaluation")
    assert res.status_code == 200
    data = res.json()
    assert "metrics" in data
    assert "rows" in data
    assert len(data["rows"]) >= 1

    # Test submitting a human rating via API
    rate_res = client.post(
        "/api/v1/jobs/job-eval-test-001/evaluation/rate",
        json={"scene_id": "scene-001", "rating": 4.5, "notes": "Audited via test"},
    )
    assert rate_res.status_code == 200
    assert rate_res.json()["human_rating"] == 4.5
