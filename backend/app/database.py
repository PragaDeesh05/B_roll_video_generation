"""SQLAlchemy database setup."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# SQLite needs check_same_thread=False for multi-threaded use
connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency for DB sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables and migrate missing columns (used for local SQLite dev)."""
    from app.models import job  # noqa: F401 – import triggers table registration
    Base.metadata.create_all(bind=engine)

    # SQLite column migration helper for jobs table
    if "sqlite" in settings.database_url:
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(jobs)"))
            existing_cols = {row[1] for row in result.fetchall()}
            
            new_columns = [
                ("idempotency_key", "VARCHAR(128)"),
                ("input_audio_url", "VARCHAR(2048)"),
                ("structured_scenes_json", "TEXT"),
                ("upload_filename", "VARCHAR(512)"),
                ("upload_path", "VARCHAR(1024)"),
                ("audio_duration", "FLOAT"),
                ("style_preferences", "TEXT"),
                ("avoid_constraints", "TEXT"),
                ("language", "VARCHAR(16)"),
                ("target_language", "VARCHAR(16)"),
                ("narration_language", "VARCHAR(8)"),
                ("subtitle_language", "VARCHAR(8)"),
                ("error_code", "VARCHAR(64)"),
                ("error_message", "TEXT"),
                ("error_detail", "TEXT"),
                ("retry_count", "INTEGER DEFAULT 0"),
                ("artifacts_json", "TEXT"),
                ("timeline_json", "TEXT"),
                ("manifest_json", "TEXT"),
                ("validation_json", "TEXT"),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}"))
            conn.commit()
