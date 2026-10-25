"""
Application configuration using pydantic-settings.
All values are read from environment variables / .env file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    groq_api_key: str = ""
    pixabay_api_key: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./storage/broll.db"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Storage ───────────────────────────────────────────────────────────────
    output_dir: Path = Path("./storage/jobs")
    upload_dir: Path = Path("./storage/uploads")
    cache_dir: Path = Path("./storage/cache")
    fallback_library_dir: Path = Path("./storage/fallback_library")

    # ── MinIO / S3 Storage ────────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "incubrix-broll"
    minio_secure: bool = False
    use_minio: bool = True

    # ── Model & Provider Settings ─────────────────────────────────────────────
    openclip_model_name: str = "ViT-B-32"
    openclip_pretrained: str = "laion2b_s34b_b79k"
    visual_verifier_provider: str = "gemini"  # "gemini" | "llava" | "groq" | "mock"
    visual_verifier_model: str = "gemini-3.5-flash-lite"
    image_gen_provider: str = "gemini"  # "gemini" | "vertexai" | "mock"
    image_gen_model: str = "gemini-2.5-flash-image"
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    stt_provider: str = "whisper"  # "whisper" | "groq" | "mock"
    tts_provider: str = "edge-tts"  # "edge-tts" | "gtts" | "pyttsx3" | "mock"

    # ── Multilingual Narration ────────────────────────────────────────────────
    supported_languages: list[str] = ["en", "hi", "ta"]
    default_language: str = "en"
    default_tts_voices: dict[str, str] = {
        "en": "en-US-ChristopherNeural",
        "hi": "hi-IN-MadhurNeural",
        "ta": "ta-IN-ValluvarNeural",
    }
    subtitle_font_family: str = "Nirmala UI"

    # ── Visual Consistency & Pacing ───────────────────────────────────────────
    enable_color_normalization: bool = False  # Disabled by default for ultra-fast rendering (saves 15-20s)
    min_scene_duration_seconds: float = 1.5
    max_luminance_jump_threshold: float = 45.0

    # ── Scoring & Calibration ─────────────────────────────────────────────────
    scoring_formula_version: str = "v1.0"
    min_relevance_threshold: float = 3.5
    min_verification_threshold: float = 2.8
    diversity_similarity_threshold: float = 0.85
    max_upload_size_mb: int = 200
    max_audio_duration_seconds: int = 600

    @property
    def min_relevance_score(self) -> float:
        return self.min_relevance_threshold

    @property
    def min_verification_score(self) -> float:
        return self.min_verification_threshold

    # ── Video defaults ────────────────────────────────────────────────────────
    default_frame_rate: int = 30
    default_aspect_ratio: str = "16:9"
    ffmpeg_preset: str = "ultrafast"  # "ultrafast" | "veryfast" | "fast"

    # ── Feature flags & Optimizations ─────────────────────────────────────────
    enable_ai_image_fallback: bool = True
    enable_clip_ranking: bool = False
    use_in_process_worker: bool = True
    enable_early_exit_verification: bool = True
    enable_lazy_downloads: bool = True
    enable_unified_scene_planning: bool = True
    enable_vlm_confidence_gating: bool = True  # Gating: bypass remote VLM if lexical score >= 4.0 (saves 60-80s)
    vlm_max_keyframes: int = 1  # Verify with 1 keyframe/thumbnail instead of 3 (cuts payload by 66%)

    # ── App ───────────────────────────────────────────────────────────────────
    app_version: str = "1.0.0"
    log_level: str = "INFO"

    # ── Computed helpers ──────────────────────────────────────────────────────
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        """Create storage directories if they don't exist."""
        for d in [self.output_dir, self.upload_dir, self.cache_dir, self.fallback_library_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def missing_keys(self) -> list[str]:
        missing = []
        if not self.gemini_api_key and not self.groq_api_key:
            missing.append("GEMINI_API_KEY (or GROQ_API_KEY)")
        if not self.pixabay_api_key:
            missing.append("PIXABAY_API_KEY")
        return missing


# Singleton instance
settings = Settings()
settings.ensure_dirs()
