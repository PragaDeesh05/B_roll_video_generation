"""SQLAlchemy ORM model for video generation jobs."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    idempotency_key = Column(String(128), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="queued")
    input_type = Column(String(16), nullable=False)  # "text" | "audio" | "structured_scenes"

    # Input metadata
    script_text = Column(Text, nullable=True)
    input_audio_url = Column(String(2048), nullable=True)
    structured_scenes_json = Column(Text, nullable=True)
    upload_filename = Column(String(512), nullable=True)
    upload_path = Column(String(1024), nullable=True)
    audio_duration = Column(Float, nullable=True)
    aspect_ratios = Column(Text, nullable=False, default='["16:9"]')  # JSON array string
    style_preferences = Column(Text, nullable=True)  # JSON or string
    avoid_constraints = Column(Text, nullable=True)   # JSON array string
    language = Column(String(8), nullable=False, default="en")
    target_language = Column(String(8), nullable=True)
    narration_language = Column(String(8), nullable=True)
    subtitle_language = Column(String(8), nullable=False, default="en")

    # Progress
    progress = Column(Integer, nullable=False, default=0)
    current_stage = Column(String(64), nullable=True)
    stage_detail = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Results / errors
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    error_detail = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    # Artifacts (JSON paths)
    artifacts_json = Column(Text, nullable=True)   # serialized dict
    timeline_json = Column(Text, nullable=True)    # full timeline JSON string
    manifest_json = Column(Text, nullable=True)    # full manifest JSON string
    validation_json = Column(Text, nullable=True)  # full validation report


class SceneModel(Base):
    """Normalized SQLite record for a planned and populated video scene."""
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False, index=True)
    scene_index = Column(Integer, nullable=False)
    narration_text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)

    previous_scene_summary = Column(Text, nullable=True)
    global_story_context = Column(Text, nullable=True)
    narrative_beat = Column(String(256), nullable=True)
    narrative_role = Column(String(256), nullable=True)
    semantic_description = Column(Text, nullable=True)
    intended_visual_meaning = Column(Text, nullable=True)
    visual_subject = Column(String(256), nullable=True)
    visual_action = Column(String(256), nullable=True)
    environment = Column(String(256), nullable=True)
    relevant_objects = Column(Text, nullable=True)  # JSON array
    object_state = Column(String(256), nullable=True)
    composition = Column(String(256), nullable=True)
    shot_type = Column(String(64), nullable=True)
    camera_angle = Column(String(64), nullable=True)
    camera_movement = Column(String(64), nullable=True)
    lighting = Column(String(128), nullable=True)
    mood = Column(String(128), nullable=True)
    style = Column(String(128), nullable=True)
    temporal_requirements = Column(Text, nullable=True)
    visual_continuity_requirements = Column(Text, nullable=True)
    visual_diversity_role = Column(String(256), nullable=True)
    must_include = Column(Text, nullable=True)  # JSON array
    must_avoid = Column(Text, nullable=True)    # JSON array

    primary_search_queries = Column(Text, nullable=True)      # JSON array
    alternative_search_queries = Column(Text, nullable=True)  # JSON array
    image_generation_prompt = Column(Text, nullable=True)
    candidate_asset_ids = Column(Text, nullable=True)         # JSON array
    selected_asset_id = Column(String(128), nullable=True)
    selection_reason = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    clip_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    verification_score = Column(Float, nullable=True)
    human_rating = Column(Float, nullable=True)
    warnings = Column(Text, nullable=True)  # JSON array


class CandidateModel(Base):
    """Downloaded and inspected candidate asset."""
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String(128), nullable=False, index=True)
    job_id = Column(String(36), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    provider_asset_id = Column(String(128), nullable=False)
    source_url = Column(String(2048), nullable=True)
    media_url = Column(String(2048), nullable=True)
    local_path = Column(String(1024), nullable=True)
    media_type = Column(String(32), nullable=False)  # "video" | "image"
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Float, nullable=True)
    fps = Column(Float, nullable=True)
    license_name = Column(String(128), nullable=True)
    license_url = Column(String(512), nullable=True)
    commercial_use_eligible = Column(Integer, nullable=False, default=1)
    attribution_required = Column(Integer, nullable=False, default=0)
    attribution_text = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    is_ai_generated = Column(Integer, nullable=False, default=0)
    hard_constraint_passed = Column(Integer, nullable=False, default=1)
    hard_constraint_rejection_reason = Column(Text, nullable=True)


class ScoreRecordModel(Base):
    """Detailed multi-stage score records for candidate ranking."""
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False, index=True)
    candidate_id = Column(String(64), nullable=False, index=True)
    clip_score = Column(Float, nullable=True)
    query_similarity = Column(Float, nullable=True)
    semantic_similarity = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    verification_score = Column(Float, nullable=True)
    subject_match = Column(Float, nullable=True)
    action_match = Column(Float, nullable=True)
    context_match = Column(Float, nullable=True)
    contradiction_detected = Column(Integer, nullable=False, default=0)
    continuity_match = Column(Float, nullable=True)
    repetition_risk = Column(Float, nullable=True)
    temporal_score = Column(Float, nullable=True)
    temporal_evidence = Column(Text, nullable=True)
    diversity_score = Column(Float, nullable=True)
    final_rank = Column(Integer, nullable=True)
    is_selected = Column(Integer, nullable=False, default=0)
    scoring_formula_version = Column(String(32), nullable=False, default="v1.0")


class ProvenanceModel(Base):
    """Detailed rights, provenance, and license records."""
    __tablename__ = "provenance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False, index=True)
    candidate_id = Column(String(64), nullable=True)
    provider = Column(String(32), nullable=False)
    original_url = Column(String(2048), nullable=True)
    media_url = Column(String(2048), nullable=True)
    license_name = Column(String(128), nullable=True)
    license_url = Column(String(512), nullable=True)
    commercial_use_eligible = Column(Integer, nullable=False, default=1)
    attribution_required = Column(Integer, nullable=False, default=0)
    attribution_text = Column(Text, nullable=True)
    verification_status = Column(String(64), nullable=False, default="provider_policy")
    verification_method = Column(String(64), nullable=False, default="pixabay_api_tos")
    retrieved_at = Column(DateTime, nullable=False, server_default=func.now())
    ai_generated = Column(Integer, nullable=False, default=0)
    ai_provider = Column(String(64), nullable=True)
    ai_model = Column(String(64), nullable=True)


class EvaluationRatingModel(Base):
    """Human evaluation ratings separate from automated model scores."""
    __tablename__ = "evaluation_ratings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False, index=True)
    human_rating = Column(Float, nullable=False)  # 1.0 to 5.0
    human_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
