"""
API routes: Health and readiness checks.
"""
from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


def _check_ffmpeg() -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_ffprobe() -> bool:
    try:
        result = subprocess.run(
            ["ffprobe", "-version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
@router.get("/api/v1/health", response_model=HealthResponse)
def health():
    """Basic health check."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        ffmpeg=_check_ffmpeg(),
        ffprobe=_check_ffprobe(),
    )


@router.get("/ready", response_model=ReadyResponse)
@router.get("/api/v1/ready", response_model=ReadyResponse)
def readiness(db: Session = Depends(get_db)):
    """Readiness check: validates API keys and tool availability."""
    db_connected = False
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_connected = True
    except Exception:
        pass

    ffmpeg_ok = _check_ffmpeg()
    ffprobe_ok = _check_ffprobe()
    missing = settings.missing_keys()

    ready = db_connected and ffmpeg_ok and ffprobe_ok

    return ReadyResponse(
        ready=ready,
        missing_keys=missing,
        ffmpeg_available=ffmpeg_ok,
        ffprobe_available=ffprobe_ok,
        db_connected=db_connected,
    )
