"""
Test configuration and fixtures.
Patches all external services so tests run without API keys or network calls.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Environment setup BEFORE any app import ───────────────────────────────────
os.environ["GOOGLE_API_CORE_SUPPRESS_PYTHON_VERSION_WARNING"] = "1"
os.environ["GOOGLE_GENAI_SUPPRESS_PYTHON_VERSION_WARNING"] = "1"
os.environ.setdefault("DATABASE_URL", "sqlite:///./storage/broll_test.db")
os.environ.setdefault("OUTPUT_DIR", "./storage/test_jobs")
os.environ.setdefault("UPLOAD_DIR", "./storage/test_uploads")
os.environ.setdefault("CACHE_DIR", "./storage/test_cache")
os.environ.setdefault("FALLBACK_LIBRARY_DIR", "./storage/test_fallback")
os.environ["GEMINI_API_KEY"] = ""  # Force mock mode for all tests
os.environ["PIXABAY_API_KEY"] = ""  # Force mock mode
os.environ["GOOGLE_CLOUD_PROJECT"] = ""  # Force mock mode for Vertex AI in tests

from app.config import settings
settings.google_cloud_project = ""
settings.gemini_api_key = ""
settings.pixabay_api_key = ""
settings.groq_api_key = ""


def _mock_run_pipeline(job_id: str, db) -> None:
    """Fast mock pipeline that marks a job completed immediately."""
    from app.models.job import Job
    import json
    from datetime import datetime, timezone

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return

    job_dir = Path(f"./storage/test_jobs/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)

    # Write stub artifacts
    (job_dir / "captions.srt").write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nTest caption.\n\n", encoding="utf-8"
    )
    (job_dir / "timeline.json").write_text(
        json.dumps({
            "job_id": job_id,
            "narration_duration": 5.0,
            "output_profile": "16:9",
            "scenes": [{
                "scene_id": "scene_001",
                "start_time": 0.0,
                "end_time": 5.0,
                "duration": 5.0,
                "transcript_text": "Test narration.",
                "scene_summary": "Test",
                "visual_description": "Test visual",
                "primary_search_query": "nature",
                "selected_asset_id": "mock_001",
                "selected_asset_url": None,
                "provenance": {
                    "provider": "pixabay",
                    "asset_id": "mock_001",
                    "original_url": "https://pixabay.com/mock/",
                    "licence_name": "Pixabay Content License",
                    "licence_url": "https://pixabay.com/service/license-summary/",
                    "attribution_required": False,
                    "commercial_use_eligible": True,
                    "verification_method": "pixabay_api_tos",
                    "retrieved_at": "2026-10-20T12:00:00Z",
                    "ai_generated": False,
                },
                "relevance_score": 3,
                "relevance_explanation": "Mock match",
                "safety_flags": [],
                "ai_generated": False,
                "validation_status": "selected",
            }],
        }),
        encoding="utf-8",
    )
    (job_dir / "manifest.json").write_text(
        json.dumps({
            "job_id": job_id,
            "app_version": "1.0.0",
            "generated_at": "2026-10-20T12:00:00Z",
            "input_type": job.input_type,
            "input_metadata": {"narration_duration": 5.0},
            "output_files": [{
                "aspect_ratio": "16:9",
                "filename": "output_16x9.mp4",
                "download_url": f"/jobs/{job_id}/download/output_16x9.mp4",
                "width": 1920, "height": 1080, "frame_rate": 30,
                "video_codec": "h264", "audio_codec": "aac",
                "duration": 5.0, "file_size_bytes": 100000,
            }],
            "scenes_count": 1,
            "scenes": [],
            "validation_summary": {
                "outputs_validated": 1,
                "all_passed": True,
                "results": [{
                    "aspect_ratio": "16:9",
                    "overall_passed": True,
                    "checks": [],
                    "warnings": [],
                    "errors": [],
                }],
            },
        }),
        encoding="utf-8",
    )
    (job_dir / "validation_report.json").write_text(
        json.dumps({
            "job_id": job_id,
            "validated_at": "2026-10-20T12:00:00Z",
            "overall_passed": True,
            "outputs": [],
            "srt_valid": True,
            "srt_error": None,
        }),
        encoding="utf-8",
    )

    artifacts = {
        "timeline": str(job_dir / "timeline.json"),
        "manifest": str(job_dir / "manifest.json"),
        "captions": str(job_dir / "captions.srt"),
        "validation_report": str(job_dir / "validation_report.json"),
        "videos": [],
    }

    job.status = "completed"
    job.progress = 100
    job.current_stage = "completed"
    job.completed_at = datetime.now(timezone.utc)
    job.artifacts_json = json.dumps(artifacts)
    job.timeline_json = (job_dir / "timeline.json").read_text()
    job.manifest_json = (job_dir / "manifest.json").read_text()
    job.validation_json = (job_dir / "validation_report.json").read_text()
    db.commit()


@pytest.fixture(scope="session", autouse=True)
def patch_pipeline():
    """Patch the background pipeline so API tests don't call real services."""
    with patch("app.api.routes_jobs._run_job_async") as mock_run:
        def _fast_run(job_id: str):
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                _mock_run_pipeline(job_id, db)
            finally:
                db.close()

        mock_run.side_effect = _fast_run
        yield mock_run


@pytest.fixture(scope="session")
def app(patch_pipeline):
    """Create the FastAPI application with test DB."""
    from app.main import app
    from app.database import init_db
    init_db()
    return app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def mock_scene():
    return {
        "scene_id": "scene_001",
        "start_time": 0.0,
        "end_time": 5.0,
        "duration": 5.0,
        "transcript_text": "The quick brown fox jumps over the lazy dog.",
        "sentence_start": 0.0,
        "sentence_end": 5.0,
        "scene_summary": "Fox jumping over a dog",
        "visual_description": "A fox leaping over a resting dog in a meadow",
        "primary_search_query": "fox jumping nature",
        "alternative_search_queries": ["wildlife animals nature", "dog meadow outdoor"],
        "required_visual_elements": ["animal"],
        "excluded_visual_elements": ["watermarks"],
        "safety_flags": [],
        "preferred_shot_type": "wide",
    }
