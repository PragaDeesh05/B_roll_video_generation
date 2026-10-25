"""
Phase 1 verification tests:
Configuration, schemas, SQLite persistence, FastAPI routes, errors, and health checks.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.job import Job, SceneModel, CandidateModel, ScoreRecordModel, ProvenanceModel, EvaluationRatingModel
from app.database import SessionLocal, init_db


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_health_and_ready_v1(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res_v1 = client.get("/api/v1/health")
    assert res_v1.status_code == 200
    assert res_v1.json()["status"] == "ok"

    res_ready = client.get("/api/v1/ready")
    assert res_ready.status_code == 200
    assert "ready" in res_ready.json()


def test_v1_create_text_job(client):
    res = client.post(
        "/api/v1/broll/jobs",
        json={
            "script_text": "This is a comprehensive test of narrative finance.",
            "aspect_ratios": ["16:9", "9:16"],
            "avoid_constraints": ["realistic human faces", "alcohol"],
        },
        headers={"X-Correlation-Id": "corr-12345"},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["job_id"]
    assert data["status"] in ("queued", "processing")
    assert data["input_type"] == "text"
    assert "16:9" in data["aspect_ratios"]
    assert "alcohol" in data["avoid_constraints"]
    assert res.headers.get("X-Correlation-Id") == "corr-12345"

    # Status check
    job_id = data["job_id"]
    status_res = client.get(f"/api/v1/jobs/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["job_id"] == job_id


def test_v1_create_structured_scenes_job(client):
    res = client.post(
        "/api/v1/broll/jobs",
        json={
            "structured_scenes": [
                {"text": "A person reviewing household expenses.", "visual_hint": "laptop spreadsheet"},
                {"text": "A small recurring deposit into savings.", "visual_hint": "digital banking notification"},
            ],
            "aspect_ratios": ["1:1"],
        },
    )
    assert res.status_code == 202
    data = res.json()
    assert data["job_id"]
    assert data["input_type"] == "structured_scenes"
    assert data["aspect_ratios"] == ["1:1"]


def test_v1_multiple_inputs_rejected(client):
    res = client.post(
        "/api/v1/broll/jobs",
        json={
            "script_text": "Narration text here.",
            "audio_url": "https://example.com/audio.mp3",
        },
    )
    assert res.status_code == 422
    err = res.json()
    assert err["error_code"] == "INVALID_INPUT_MODE"


def test_v1_no_inputs_rejected(client):
    res = client.post(
        "/api/v1/broll/jobs",
        json={},
    )
    assert res.status_code == 422
    err = res.json()
    assert err["error_code"] == "INVALID_INPUT_MODE"


def test_v1_idempotency(client):
    key = "idemp-test-key-999"
    payload = {
        "script_text": "Idempotent job narration text.",
        "aspect_ratios": ["16:9"],
    }
    res1 = client.post("/api/v1/broll/jobs", json=payload, headers={"Idempotency-Key": key})
    assert res1.status_code == 202
    job1_id = res1.json()["job_id"]

    res2 = client.post("/api/v1/broll/jobs", json=payload, headers={"Idempotency-Key": key})
    assert res2.status_code == 202
    assert res2.json()["job_id"] == job1_id


def test_v1_ssrf_rejected(client):
    res = client.post(
        "/api/v1/broll/jobs",
        json={"audio_url": "http://127.0.0.1:8000/internal-audio.mp3"},
    )
    assert res.status_code == 400
    err = res.json()
    assert err["error_code"] == "SSRF_ATTEMPT_DETECTED"


def test_sqlite_models_persist():
    db = SessionLocal()
    try:
        # Verify all new tables exist and can insert/query
        scene = SceneModel(
            job_id="job-test-persistence",
            scene_id="scene-001",
            scene_index=0,
            narration_text="Saving regularly increases accumulated wealth.",
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            narrative_beat="accumulating_savings",
            narrative_role="exposition",
            semantic_description="Visual demonstration of gradual balance growth",
            visual_subject="bank balance",
            visual_action="increasing",
            clip_score=0.72,
            relevance_score=4.5,
            verification_score=4.0,
        )
        db.add(scene)
        db.commit()

        queried = db.query(SceneModel).filter(SceneModel.job_id == "job-test-persistence").first()
        assert queried is not None
        assert queried.narrative_beat == "accumulating_savings"
        assert queried.clip_score == 0.72
    finally:
        db.close()
