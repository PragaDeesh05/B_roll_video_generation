"""
API routes: Artifact downloads (timeline, manifest, captions, video files).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.job import Job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["artifacts"])


def _get_job_or_404(job_id: str, db: Session) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


def _require_completed(job: Job) -> None:
    if job.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Job {job.id} is still in progress (status: {job.status})",
        )


def _job_dir(job_id: str) -> Path:
    return settings.output_dir / job_id


# ── Timeline ──────────────────────────────────────────────────────────────────

@router.get("/{job_id}/timeline")
def get_timeline(job_id: str, db: Session = Depends(get_db)):
    """Return timeline.json for a completed job."""
    job = _get_job_or_404(job_id, db)
    _require_completed(job)

    if job.timeline_json:
        return JSONResponse(json.loads(job.timeline_json))

    path = _job_dir(job_id) / "timeline.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Timeline not found")
    return JSONResponse(json.loads(path.read_text()))


# ── Manifest ──────────────────────────────────────────────────────────────────

@router.get("/{job_id}/manifest")
def get_manifest(job_id: str, db: Session = Depends(get_db)):
    """Return manifest.json for a completed job."""
    job = _get_job_or_404(job_id, db)
    _require_completed(job)

    if job.manifest_json:
        return JSONResponse(json.loads(job.manifest_json))

    path = _job_dir(job_id) / "manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    return JSONResponse(json.loads(path.read_text()))


# ── Captions ──────────────────────────────────────────────────────────────────

@router.get("/{job_id}/captions")
def get_captions(job_id: str, db: Session = Depends(get_db)):
    """Return captions.srt for a completed job."""
    job = _get_job_or_404(job_id, db)
    _require_completed(job)

    path = _job_dir(job_id) / "captions.srt"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Captions not found")
    return FileResponse(
        path=str(path),
        media_type="text/plain",
        filename="captions.srt",
    )


# ── Validation report ─────────────────────────────────────────────────────────

@router.get("/{job_id}/validation")
def get_validation(job_id: str, db: Session = Depends(get_db)):
    """Return validation_report.json for a completed job."""
    job = _get_job_or_404(job_id, db)
    _require_completed(job)

    if job.validation_json:
        return JSONResponse(json.loads(job.validation_json))

    path = _job_dir(job_id) / "validation_report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Validation report not found")
    return JSONResponse(json.loads(path.read_text()))


# ── Artifact list ─────────────────────────────────────────────────────────────

@router.get("/{job_id}/artifacts")
def list_artifacts(job_id: str, db: Session = Depends(get_db)):
    """List all artifacts for a completed job."""
    job = _get_job_or_404(job_id, db)
    _require_completed(job)

    artifacts_info = {}
    if job.artifacts_json:
        raw = json.loads(job.artifacts_json)
        videos = raw.get("videos", [])
        artifacts_info = {
            "timeline": f"/jobs/{job_id}/timeline",
            "manifest": f"/jobs/{job_id}/manifest",
            "captions": f"/jobs/{job_id}/captions",
            "validation": f"/jobs/{job_id}/validation",
            "videos": [f"/jobs/{job_id}/download/{v}" for v in videos],
        }
    return JSONResponse(artifacts_info)


# ── Video download ────────────────────────────────────────────────────────────

@router.get("/{job_id}/video")
def get_primary_video(job_id: str, db: Session = Depends(get_db)):
    """Serve the primary rendered video for a completed job."""
    job = _get_job_or_404(job_id, db)
    _require_completed(job)

    job_dir = _job_dir(job_id)
    mp4s = list(job_dir.glob("*.mp4"))
    if not mp4s:
        raise HTTPException(status_code=404, detail="No rendered video found for this job")

    # Prefer 16x9 if multiple, else first available
    primary = next((f for f in mp4s if "16x9" in f.name), mp4s[0])
    return FileResponse(path=str(primary), media_type="video/mp4", filename=primary.name)


@router.get("/artifacts/download/{filename}")
def download_artifact_file(filename: str):
    """
    Direct artifact/media download by filename across all jobs in output_dir.
    Serves AI generated scene visuals and other artifacts referenced by filename:
    /jobs/artifacts/download/{filename}
    """
    safe_name = Path(filename).name
    allowed_extensions = {".mp4", ".srt", ".json", ".csv", ".jpg", ".jpeg", ".png", ".webp", ".wav", ".mp3"}
    if Path(safe_name).suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid file type")

    matching = list(settings.output_dir.glob(f"**/{safe_name}"))
    if not matching:
        raise HTTPException(status_code=404, detail=f"Artifact {safe_name} not found")

    target = matching[0]
    media_types = {
        ".mp4": "video/mp4",
        ".srt": "text/plain",
        ".json": "application/json",
        ".csv": "text/csv",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }
    media_type = media_types.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(path=str(target), media_type=media_type, filename=safe_name)


@router.get("/{job_id}/download/{filename}")
def download_file(job_id: str, filename: str, db: Session = Depends(get_db)):
    """Download a generated video or artifact file."""
    job = _get_job_or_404(job_id, db)
    _require_completed(job)

    # Security: only allow safe filenames — no path traversal
    safe_name = Path(filename).name  # strips any directory components
    allowed_extensions = {".mp4", ".srt", ".json", ".csv", ".jpg", ".jpeg", ".png", ".webp", ".wav", ".mp3"}
    if Path(safe_name).suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid file type")

    file_path = _job_dir(job_id) / safe_name
    if not file_path.exists():
        if safe_name.endswith(".mp4"):
            # Check for any available mp4 in job directory (e.g. 1x1 or 9x16)
            available_mp4s = list(_job_dir(job_id).glob("*.mp4"))
            if available_mp4s:
                file_path = available_mp4s[0]
                safe_name = file_path.name
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File {safe_name} not found")

    media_types = {
        ".mp4": "video/mp4",
        ".srt": "text/plain",
        ".json": "application/json",
        ".csv": "text/csv",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }
    media_type = media_types.get(file_path.suffix.lower(), "application/octet-stream")
    return FileResponse(path=str(file_path), media_type=media_type, filename=safe_name)


@router.get("/{job_id}/media/{file_path:path}")
def get_media_file(job_id: str, file_path: str, db: Session = Depends(get_db)):
    """Serve nested media assets (candidate frames, generated visuals) safely."""
    job = _get_job_or_404(job_id, db)
    job_dir = _job_dir(job_id)

    target_path = (job_dir / file_path).resolve()
    # Path traversal check
    if not str(target_path).startswith(str(job_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Media not found")

    ext = target_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }
    return FileResponse(path=str(target_path), media_type=media_types.get(ext, "application/octet-stream"))
