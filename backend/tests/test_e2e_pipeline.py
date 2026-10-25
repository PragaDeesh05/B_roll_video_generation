"""
End-to-end integration test for Incubrix Context-Aware B-Roll Video Engine.
Validates the entire journey from input ingestion to final artifact delivery.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, init_db
from app.models.job import Job, SceneModel, CandidateModel
from app.workers.video_pipeline import run_pipeline


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_full_e2e_pipeline_execution(client):
    """
    Submit a text script job, execute the pipeline synchronously in test mode,
    and verify that all artifacts, provenance records, and evaluation sheets are generated.
    """
    script = (
        "Cloud computing connects distributed servers across modern global enterprise datacenters. "
        "Secure microservices process continuous data streams reliably and securely."
    )

    # 1. Ingest via API
    response = client.post(
        "/api/v1/broll/jobs",
        json={
            "input_type": "text",
            "script_text": script,
            "aspect_ratios": ["16:9"],
            "style_preferences": "modern cinematic technology",
            "avoid_constraints": ["sky", "natural weather clouds", "watermark"],
        },
    )
    assert response.status_code in (200, 202), response.text
    data = response.json()
    job_id = data["job_id"]
    assert job_id is not None

    # 2. Run pipeline synchronously
    db = SessionLocal()
    try:
        run_pipeline(job_id, db)
        db.expire_all()

        # 3. Verify Job Completion
        job = db.query(Job).filter(Job.id == job_id).first()
        assert job is not None
        assert job.status == "completed", f"Job failed: {job.error_message}"
        assert job.progress == 100

        # Verify artifacts
        artifacts = json.loads(job.artifacts_json) if job.artifacts_json else {}
        assert "captions" in artifacts
        assert "timeline" in artifacts
        assert "manifest" in artifacts
        assert "validation_report" in artifacts
        assert "evaluation_csv" in artifacts
        assert "evaluation_json" in artifacts
        assert len(artifacts.get("videos", [])) >= 1

        # Verify scenes in database
        scenes = db.query(SceneModel).filter(SceneModel.job_id == job_id).all()
        assert len(scenes) >= 1
        for scene in scenes:
            assert scene.semantic_description is not None
            assert scene.selected_asset_id is not None
            assert scene.verification_score is not None

        # 4. Verify API Endpoints for Job
        status_res = client.get(f"/api/v1/jobs/{job_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["status"] == "completed"
        assert "artifacts" in status_data

        # 5. Verify Evaluation API Endpoint
        eval_res = client.get(f"/api/v1/jobs/{job_id}/evaluation")
        assert eval_res.status_code == 200
        eval_data = eval_res.json()
        assert "metrics" in eval_data
        assert "rows" in eval_data
        assert len(eval_data["rows"]) == len(scenes)

        # 6. Verify Human Rating API Endpoint
        first_scene_id = scenes[0].scene_id
        rate_res = client.post(
            f"/api/v1/jobs/{job_id}/evaluation/rate",
            json={
                "scene_id": first_scene_id,
                "rating": 5.0,
                "notes": "End-to-end verified with high narrative fidelity",
            },
        )
        assert rate_res.status_code == 200
        assert rate_res.json()["human_rating"] == 5.0

    finally:
        db.close()
