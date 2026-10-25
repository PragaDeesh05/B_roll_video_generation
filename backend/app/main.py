"""
FastAPI Application Entry Point
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info(f"Starting B-Roll Video Engine v{settings.app_version}")

    # Initialize DB
    init_db()
    logger.info("Database initialized")

    # Check dependencies
    missing = settings.missing_keys()
    if missing:
        logger.warning(f"Missing API keys: {missing} — running in limited mode")
    else:
        logger.info("All API keys present")

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="B-Roll Video Engine",
    description="Converts text scripts or voiceover audio into B-roll videos using Gemini AI and Pixabay stock footage.",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_artifacts import router as artifacts_router

app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(artifacts_router)

# Serve frontend static files if built
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
