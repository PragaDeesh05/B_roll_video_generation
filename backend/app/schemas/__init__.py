"""Pydantic schemas for API request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Structured Input ─────────────────────────────────────────────────────────

class StructuredSceneInputItem(BaseModel):
    """Single item in structured scene list input mode."""
    text: str = Field(..., min_length=1)
    visual_hint: Optional[str] = None


# ── Job Submission ────────────────────────────────────────────────────────────

class JobCreateRequest(BaseModel):
    """Body for legacy /jobs text-script submissions."""
    input_type: Literal["text"] = "text"
    script_text: str = Field(..., min_length=1, max_length=50_000)
    aspect_ratios: List[Literal["16:9", "9:16", "1:1"]] = Field(default=["16:9"])
    language: Optional[str] = Field(default="en")
    target_language: Optional[str] = None
    narration_language: Optional[str] = None
    subtitle_language: Optional[str] = Field(default="en")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> str:
        if v is None:
            return "en"
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported language code '{v}'. Supported languages: en, hi, ta")
        return val

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported target language code '{v}'. Supported languages: en, hi, ta")
        return val

    @field_validator("narration_language")
    @classmethod
    def validate_narration_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported narration language code '{v}'. Supported languages: en, hi, ta")
        return val

    @field_validator("subtitle_language")
    @classmethod
    def validate_subtitle_language(cls, v: Optional[str]) -> str:
        if v is None or not str(v).strip():
            return "en"
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported subtitle language code '{v}'. Supported languages: en, hi, ta")
        return val

    @field_validator("script_text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("script_text must not be blank")
        return v.strip()


class JobCreateV1Request(BaseModel):
    """
    Unified JSON request body for POST /api/v1/broll/jobs.
    Validates that exactly one primary input mode is provided:
      1. script_text (Text mode)
      2. audio_url (Audio URL mode)
      3. structured_scenes (Structured scene list mode)
    Note: Direct audio file uploads use multipart/form-data on the same endpoint.
    """
    script_text: Optional[str] = Field(None, max_length=50_000)
    audio_url: Optional[str] = None
    structured_scenes: Optional[List[StructuredSceneInputItem]] = None

    aspect_ratios: List[Literal["16:9", "9:16", "1:1"]] = Field(default=["16:9"])
    style_preferences: Optional[str] = None
    avoid_constraints: List[str] = Field(default_factory=list)
    language: Optional[str] = Field(default="en")
    target_language: Optional[str] = None
    narration_language: Optional[str] = None
    subtitle_language: Optional[str] = Field(default="en")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> str:
        if v is None:
            return "en"
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported language code '{v}'. Supported languages: en, hi, ta")
        return val

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported target language code '{v}'. Supported languages: en, hi, ta")
        return val

    @field_validator("narration_language")
    @classmethod
    def validate_narration_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported narration language code '{v}'. Supported languages: en, hi, ta")
        return val

    @field_validator("subtitle_language")
    @classmethod
    def validate_subtitle_language(cls, v: Optional[str]) -> str:
        if v is None or not str(v).strip():
            return "en"
        val = v.strip().lower()
        if val not in ("en", "hi", "ta"):
            raise ValueError(f"Unsupported subtitle language code '{v}'. Supported languages: en, hi, ta")
        return val

    @model_validator(mode="after")
    def validate_exactly_one_input(self) -> JobCreateV1Request:
        inputs_present = 0
        if self.script_text and self.script_text.strip():
            inputs_present += 1
        if self.audio_url and self.audio_url.strip():
            inputs_present += 1
        if self.structured_scenes and len(self.structured_scenes) > 0:
            inputs_present += 1

        if inputs_present == 0:
            raise ValueError(
                "Exactly one primary input mode is required: 'script_text', 'audio_url', or 'structured_scenes'."
            )
        if inputs_present > 1:
            raise ValueError(
                "Multiple input modes provided. Provide exactly one of: 'script_text', 'audio_url', or 'structured_scenes'."
            )
        return self


# ── Error Schema ─────────────────────────────────────────────────────────────

class APIErrorResponse(BaseModel):
    """Standard structured JSON error response."""
    error_code: str
    message: str
    retryable: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


# ── Job Status ────────────────────────────────────────────────────────────────

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    input_type: str
    input_text: Optional[str] = None
    script_text: Optional[str] = None
    progress: int
    progress_pct: Optional[float] = None
    scenes_count: Optional[int] = None
    current_stage: Optional[str] = None
    stage_detail: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_detail: Optional[str] = None
    retry_count: int = 0
    aspect_ratios: List[str] = Field(default_factory=lambda: ["16:9"])
    style_preferences: Optional[str] = None
    avoid_constraints: List[str] = Field(default_factory=list)
    language: str = "en"
    target_language: Optional[str] = None
    narration_language: Optional[str] = None
    subtitle_language: Optional[str] = "en"
    artifacts: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ── Scene / Timeline ──────────────────────────────────────────────────────────

class ProvenanceRecord(BaseModel):
    provider: str = "pixabay"
    asset_id: Optional[str] = None
    original_url: Optional[str] = None
    media_url: Optional[str] = None
    licence_name: str = "Pixabay Content License"
    licence_url: str = "https://pixabay.com/service/license-summary/"
    attribution_required: bool = False
    attribution_text: Optional[str] = None
    commercial_use_eligible: bool = True
    verification_status: str = "provider_policy"
    verification_method: str = "pixabay_api_tos"
    retrieved_at: Optional[str] = None
    ai_generated: bool = False
    ai_generation_provider: Optional[str] = None
    ai_generation_model: Optional[str] = None


class SceneRecord(BaseModel):
    """Complete, mandatory scene schema matching Section 7."""
    scene_id: str
    scene_index: int = 0
    narration_text: str = ""
    start_time: float
    end_time: float
    duration: float

    # Narrative Context
    previous_scene_summary: Optional[str] = None
    global_story_context: Optional[str] = None
    narrative_beat: Optional[str] = None
    narrative_role: Optional[str] = None

    # Visual Meaning & Breakdown
    semantic_description: str = ""
    intended_visual_meaning: Optional[str] = None
    visual_subject: Optional[str] = None
    visual_action: Optional[str] = None
    environment: Optional[str] = None
    relevant_objects: List[str] = Field(default_factory=list)
    object_state: Optional[str] = None
    composition: Optional[str] = None
    shot_type: Optional[str] = "wide"
    camera_angle: Optional[str] = None
    camera_movement: Optional[str] = None
    lighting: Optional[str] = None
    mood: Optional[str] = None
    style: Optional[str] = None
    temporal_requirements: Optional[str] = None
    visual_continuity_requirements: Optional[str] = None
    visual_diversity_role: Optional[str] = None
    must_include: List[str] = Field(default_factory=list)
    must_avoid: List[str] = Field(default_factory=list)

    # Retrieval and Generation
    primary_search_queries: List[str] = Field(default_factory=list)
    alternative_search_queries: List[str] = Field(default_factory=list)
    image_generation_prompt: Optional[str] = None
    candidate_asset_ids: List[str] = Field(default_factory=list)

    # Selection & Verification
    selected_asset_id: Optional[str] = None
    selected_asset_url: Optional[str] = None
    selection_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    clip_score: Optional[float] = None
    relevance_score: Optional[Union[float, int]] = None
    verification_score: Optional[float] = None
    human_rating: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)

    # Backwards-compatibility fields
    transcript_text: Optional[str] = None
    scene_summary: Optional[str] = None
    visual_description: Optional[str] = None
    primary_search_query: Optional[str] = None
    required_visual_elements: List[str] = Field(default_factory=list)
    excluded_visual_elements: List[str] = Field(default_factory=list)
    safety_flags: List[str] = Field(default_factory=list)
    preferred_shot_type: Optional[str] = "wide"
    relevance_explanation: Optional[str] = None
    validation_status: Optional[str] = None
    provenance: Optional[ProvenanceRecord] = None
    ai_generated: bool = False

    @model_validator(mode="before")
    @classmethod
    def sync_backwards_compat(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync narration_text and transcript_text
            if not data.get("narration_text") and data.get("transcript_text"):
                data["narration_text"] = data["transcript_text"]
            elif not data.get("transcript_text") and data.get("narration_text"):
                data["transcript_text"] = data["narration_text"]

            # Sync semantic_description and visual_description
            if not data.get("semantic_description") and data.get("visual_description"):
                data["semantic_description"] = data["visual_description"]
            elif not data.get("visual_description") and data.get("semantic_description"):
                data["visual_description"] = data["semantic_description"]

            # Sync primary_search_query and primary_search_queries
            if not data.get("primary_search_queries") and data.get("primary_search_query"):
                data["primary_search_queries"] = [data["primary_search_query"]]
            elif not data.get("primary_search_query") and data.get("primary_search_queries"):
                data["primary_search_query"] = data["primary_search_queries"][0] if data["primary_search_queries"] else ""
        return data


class TimelineResponse(BaseModel):
    job_id: str
    narration_duration: float
    output_profile: str
    scenes: List[SceneRecord]


# ── Manifest ──────────────────────────────────────────────────────────────────

class OutputFileInfo(BaseModel):
    aspect_ratio: str
    filename: str
    download_url: str
    width: int
    height: int
    frame_rate: int
    video_codec: str
    audio_codec: str
    duration: float
    file_size_bytes: int


class ManifestResponse(BaseModel):
    job_id: str
    app_version: str
    input_type: str
    input_metadata: Dict[str, Any]
    output_files: List[OutputFileInfo]
    scenes: List[SceneRecord]
    validation_summary: Dict[str, Any]
    generated_at: str


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    ffmpeg: bool
    ffprobe: bool


class ReadyResponse(BaseModel):
    ready: bool
    missing_keys: List[str]
    ffmpeg_available: bool
    ffprobe_available: bool
    db_connected: bool


# ── Validation Report ─────────────────────────────────────────────────────────

class ValidationCheck(BaseModel):
    check: str
    passed: bool
    value: Optional[Any] = None
    threshold: Optional[Any] = None
    detail: Optional[str] = None


class AspectRatioValidation(BaseModel):
    aspect_ratio: str
    file_path: str
    overall_passed: bool
    checks: List[ValidationCheck]
    warnings: List[str] = []
    errors: List[str] = []


class ValidationReport(BaseModel):
    job_id: str
    validated_at: str
    overall_passed: bool
    outputs: List[AspectRatioValidation]
    srt_valid: bool
    srt_error: Optional[str] = None


# ── Clip Swap ─────────────────────────────────────────────────────────────

class ClipSwapRequest(BaseModel):
    candidate_id: Optional[str] = None
    media_url: Optional[str] = None
    generate_prompt: Optional[str] = None


class ClipSwapResponse(BaseModel):
    status: str
    job_id: str
    scene_id: str
    scene_index: int
    swapped_asset: str
    is_image: bool
    duration_seconds: float
    render_duration_seconds: float
    output_videos: List[Dict[str, Any]] = Field(default_factory=list)
    updated_scene: Dict[str, Any] = Field(default_factory=dict)
