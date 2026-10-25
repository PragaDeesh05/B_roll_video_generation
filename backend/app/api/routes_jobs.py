"""
API routes: Job submission and status.
Supports both legacy routes (/jobs) and v1 master specification (/api/v1/broll/jobs).
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.job import Job
from app.schemas import (
    APIErrorResponse,
    JobCreateRequest,
    JobCreateV1Request,
    JobStatusResponse,
)
from app.utils.language import detect_script_language
from app.utils.media import probe_audio
from app.utils.security import SSRFValidationError, validate_external_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/m4a",
    "audio/mp4", "audio/x-m4a", "video/mp4",
}
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a"}
VALID_ASPECT_RATIOS = {"16:9", "9:16", "1:1"}


def _error_response(
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Return structured JSON error response."""
    return JSONResponse(
        status_code=status_code,
        content=APIErrorResponse(
            error_code=error_code,
            message=message,
            retryable=retryable,
            details=details or {},
        ).model_dump(),
    )


# ── V1 Master Unified Submission Endpoint ──────────────────────────────────────

@router.post(
    "/api/v1/broll/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobStatusResponse,
    responses={
        400: {"model": APIErrorResponse},
        413: {"model": APIErrorResponse},
        422: {"model": APIErrorResponse},
    },
)
async def create_broll_job_v1(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """
    Master unified endpoint for B-roll video generation jobs.
    Accepts:
      - Plain text script (JSON: script_text)
      - Audio URL (JSON: audio_url)
      - Structured scene list (JSON: structured_scenes)
      - Audio file upload (Multipart form: file)
    """
    if x_correlation_id:
        response.headers["X-Correlation-Id"] = x_correlation_id

    # Check idempotency
    if idempotency_key:
        existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
        if existing:
            logger.info(f"Idempotent hit for key {idempotency_key}: returning job {existing.id}")
            return _job_to_response(existing)

    content_type = request.headers.get("content-type", "")

    # Multipart file upload
    if "multipart/form-data" in content_type:
        form = await request.form()
        file = form.get("file")
        if not file or not isinstance(file, UploadFile):
            return _error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "MISSING_AUDIO_FILE",
                "Multipart request must include a 'file' audio upload.",
            )

        aspect_ratios_raw = form.get("aspect_ratios", '["16:9"]')
        try:
            ratios = json.loads(str(aspect_ratios_raw)) if isinstance(aspect_ratios_raw, str) else list(aspect_ratios_raw)
            if not isinstance(ratios, list):
                ratios = [str(ratios)]
            ratios = [r for r in ratios if r in VALID_ASPECT_RATIOS] or ["16:9"]
        except Exception:
            ratios = ["16:9"]

        style_pref = form.get("style_preferences")
        avoid_raw = form.get("avoid_constraints")
        avoid_list = []
        if avoid_raw:
            try:
                avoid_list = json.loads(str(avoid_raw)) if isinstance(avoid_raw, str) else list(avoid_raw)
            except Exception:
                avoid_list = [str(avoid_raw)]

        language_raw = form.get("language", "en")
        language_val = str(language_raw).strip().lower() if language_raw else "en"
        if language_val not in ("en", "hi", "ta"):
            return _error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "UNSUPPORTED_LANGUAGE",
                f"Unsupported language code '{language_raw}'. Supported languages: en, hi, ta",
            )

        target_lang_raw = form.get("target_language")
        target_lang_val = str(target_lang_raw).strip().lower() if target_lang_raw else None
        if target_lang_val and target_lang_val not in ("en", "hi", "ta"):
            return _error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "UNSUPPORTED_LANGUAGE",
                f"Unsupported target language code '{target_lang_raw}'. Supported languages: en, hi, ta",
            )

        narration_lang_raw = form.get("narration_language")
        narration_lang_val = str(narration_lang_raw).strip().lower() if narration_lang_raw else None
        if narration_lang_val and narration_lang_val not in ("en", "hi", "ta"):
            return _error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "UNSUPPORTED_LANGUAGE",
                f"Unsupported narration language code '{narration_lang_raw}'. Supported languages: en, hi, ta",
            )

        subtitle_lang_raw = form.get("subtitle_language", "en")
        subtitle_lang_val = str(subtitle_lang_raw).strip().lower() if subtitle_lang_raw else "en"
        if subtitle_lang_val not in ("en", "hi", "ta"):
            return _error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "UNSUPPORTED_LANGUAGE",
                f"Unsupported subtitle language code '{subtitle_lang_raw}'. Supported languages: en, hi, ta",
            )

        return await _handle_audio_upload(
            file=file,
            ratios=ratios,
            style_pref=str(style_pref) if style_pref else None,
            avoid_list=avoid_list,
            language=language_val,
            target_language=target_lang_val,
            narration_language=narration_lang_val or target_lang_val or language_val,
            subtitle_language=subtitle_lang_val,
            idempotency_key=idempotency_key,
            background_tasks=background_tasks,
            db=db,
        )

    # JSON payload
    try:
        body = await request.json()
    except Exception as e:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_JSON_BODY",
            f"Failed to parse request JSON: {e}",
        )

    try:
        v1_req = JobCreateV1Request.model_validate(body)
    except Exception as e:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_INPUT_MODE",
            str(e),
            details={"validation_error": str(e)},
        )

    job_id = str(uuid.uuid4())
    input_type = "text"
    script_text = None
    input_audio_url = None
    structured_json = None

    if v1_req.script_text:
        input_type = "text"
        script_text = v1_req.script_text.strip()
    elif v1_req.audio_url:
        input_type = "audio"
        input_audio_url = v1_req.audio_url.strip()
        try:
            validate_external_url(input_audio_url)
        except SSRFValidationError as e:
            return _error_response(
                status.HTTP_400_BAD_REQUEST,
                "SSRF_ATTEMPT_DETECTED",
                f"Invalid or prohibited external audio URL: {e}",
            )
    elif v1_req.structured_scenes:
        input_type = "structured_scenes"
        structured_json = json.dumps([item.model_dump() for item in v1_req.structured_scenes])
        # Reconstruct script text from structured scenes for narration
        script_text = " ".join(s.text.strip() for s in v1_req.structured_scenes)

    # Automatic script language detection & decoupled narration / subtitle defaults
    detected_lang = detect_script_language(script_text)
    script_lang = v1_req.language if (v1_req.language and v1_req.language != "en") else detected_lang
    narration_lang = v1_req.narration_language or v1_req.target_language or script_lang
    subtitle_lang = v1_req.subtitle_language or "en"

    job = Job(
        id=job_id,
        idempotency_key=idempotency_key,
        input_type=input_type,
        script_text=script_text,
        input_audio_url=input_audio_url,
        structured_scenes_json=structured_json,
        aspect_ratios=json.dumps(v1_req.aspect_ratios),
        style_preferences=v1_req.style_preferences,
        avoid_constraints=json.dumps(v1_req.avoid_constraints),
        language=script_lang,
        target_language=v1_req.target_language,
        narration_language=narration_lang,
        subtitle_language=subtitle_lang,
        status="queued",
        progress=0,
        current_stage="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_job_async, job.id)
    logger.info(f"Queued v1 job {job.id} (mode={input_type})")
    return _job_to_response(job)


# ── V1 Status Endpoint ─────────────────────────────────────────────────────────

@router.get(
    "/api/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    responses={404: {"model": APIErrorResponse}},
)
def get_job_v1(
    job_id: str,
    response: Response,
    db: Session = Depends(get_db),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    """Retrieve status, progress, stage, and artifact links for a job."""
    if x_correlation_id:
        response.headers["X-Correlation-Id"] = x_correlation_id

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "JOB_NOT_FOUND",
            f"Job '{job_id}' was not found.",
        )
    return _job_to_response(job)


# ── V1 Evaluation Endpoints ───────────────────────────────────────────────────

@router.get("/api/v1/jobs/{job_id}/evaluation")
def get_job_evaluation(job_id: str, db: Session = Depends(get_db)):
    """Retrieve the 30-column scene evaluation sheet and audit metrics."""
    from app.services.evaluation_service import EvaluationService
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "JOB_NOT_FOUND",
            f"Job '{job_id}' was not found.",
        )
    eval_svc = EvaluationService()
    csv_path, json_path = eval_svc.generate_evaluation_sheet(job_id, db)
    metrics = eval_svc.compute_audit_metrics(job_id, db)
    rows = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else []

    return {
        "job_id": job_id,
        "metrics": metrics,
        "csv_download_url": f"/jobs/{job_id}/download/evaluation_sheet.csv",
        "rows": rows,
    }


@router.post("/api/v1/jobs/{job_id}/evaluation/rate")
async def post_human_rating(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Store human evaluation rating (1-5 scale) for a scene."""
    from app.services.evaluation_service import EvaluationService
    body = await request.json()
    scene_id = body.get("scene_id")
    rating = body.get("rating")
    notes = body.get("notes")

    if not scene_id or rating is None:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "MISSING_RATING_FIELDS",
            "Request must include 'scene_id' and 'rating'.",
        )

    try:
        r_val = float(rating)
        rec = EvaluationService().record_human_rating(job_id, scene_id, r_val, notes, db)
        return {
            "status": "success",
            "job_id": job_id,
            "scene_id": scene_id,
            "human_rating": rec.human_rating,
            "human_notes": rec.human_notes,
        }
    except Exception as e:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_RATING_VALUE",
            str(e),
        )


# ── Legacy Endpoints (Maintained for Backward Compatibility) ───────────────────

@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobStatusResponse)
@router.post("/jobs/", status_code=status.HTTP_202_ACCEPTED, response_model=JobStatusResponse)
async def create_text_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Submit a text script for video generation (legacy)."""
    detected_lang = detect_script_language(request.script_text)
    script_lang = request.language if (request.language and request.language != "en") else detected_lang
    narration_lang = request.narration_language or request.target_language or script_lang
    subtitle_lang = request.subtitle_language or "en"

    job = Job(
        id=str(uuid.uuid4()),
        input_type="text",
        script_text=request.script_text,
        aspect_ratios=json.dumps(request.aspect_ratios),
        language=script_lang,
        target_language=request.target_language,
        narration_language=narration_lang,
        subtitle_language=subtitle_lang,
        status="queued",
        progress=0,
        current_stage="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_job_async, job.id)
    logger.info(f"Queued text job {job.id} (script={job.language}, narration={job.narration_language}, subtitles={job.subtitle_language})")
    return _job_to_response(job)


@router.post("/jobs/upload", status_code=status.HTTP_202_ACCEPTED, response_model=JobStatusResponse)
async def create_audio_job(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    aspect_ratios: str = Form(default='["16:9"]'),
    language: str = Form(default="en"),
    target_language: Optional[str] = Form(default=None),
    narration_language: Optional[str] = Form(default=None),
    subtitle_language: str = Form(default="en"),
):
    """Submit an audio file for video generation (legacy)."""
    try:
        ratios = json.loads(aspect_ratios)
        if not isinstance(ratios, list):
            ratios = [ratios]
        ratios = [r for r in ratios if r in VALID_ASPECT_RATIOS] or ["16:9"]
    except Exception:
        ratios = ["16:9"]

    lang = language.strip().lower() if language else "en"
    if lang not in ("en", "hi", "ta"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported language code '{language}'. Supported: en, hi, ta",
        )

    tgt_lang = target_language.strip().lower() if target_language else None
    if tgt_lang and tgt_lang not in ("en", "hi", "ta"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported target language code '{target_language}'. Supported: en, hi, ta",
        )

    narr_lang = narration_language.strip().lower() if narration_language else None
    if narr_lang and narr_lang not in ("en", "hi", "ta"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported narration language code '{narration_language}'. Supported: en, hi, ta",
        )

    sub_lang = subtitle_language.strip().lower() if subtitle_language else "en"
    if sub_lang not in ("en", "hi", "ta"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported subtitle language code '{subtitle_language}'. Supported: en, hi, ta",
        )

    return await _handle_audio_upload(
        file=file,
        ratios=ratios,
        style_pref=None,
        avoid_list=[],
        language=lang,
        target_language=tgt_lang,
        narration_language=narr_lang or tgt_lang or lang,
        subtitle_language=sub_lang,
        idempotency_key=None,
        background_tasks=background_tasks,
        db=db,
    )


@router.get("/jobs")
@router.get("/api/v1/jobs")
def list_jobs(limit: int = 20, db: Session = Depends(get_db)):
    """List recent video generation jobs."""
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(limit).all()
    return [_job_to_response(j) for j in jobs]


@router.get("/api/v1/jobs/{job_id}/candidates")
def get_job_candidates(job_id: str, db: Session = Depends(get_db)):
    """List all candidate evaluation scores for a job."""
    from app.models.job import ScoreRecordModel
    records = db.query(ScoreRecordModel).filter(ScoreRecordModel.job_id == job_id).all()
    grouped = {}
    for r in records:
        sc = r.scene_id
        if sc not in grouped:
            grouped[sc] = []
        grouped[sc].append({
            "candidate_id": r.candidate_id,
            "clip_score": r.clip_score,
            "query_similarity": r.query_similarity,
            "semantic_similarity": r.semantic_similarity,
            "relevance_score": r.relevance_score,
            "verification_score": r.verification_score,
            "subject_match": r.subject_match,
            "action_match": r.action_match,
            "context_match": r.context_match,
            "temporal_score": r.temporal_score,
            "diversity_score": r.diversity_score,
            "contradiction_detected": bool(r.contradiction_detected),
            "repetition_risk": r.repetition_risk,
            "final_rank": r.final_rank,
            "is_selected": bool(r.is_selected),
        })
    return {"job_id": job_id, "scenes": grouped}


@router.post("/api/v1/jobs/{job_id}/scenes/{scene_id}/swap-clip")
@router.post("/jobs/{job_id}/scenes/{scene_id}/swap-clip")
async def swap_scene_clip_endpoint(
    job_id: str,
    scene_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Swap a scene's visual clip and re-render ONLY that segment.
    Reassembles the output video in ~3-5 seconds without re-rendering other scenes.
    Accepts:
      - JSON: {"candidate_id": "...", "media_url": "...", "generate_prompt": "..."}
      - Multipart form: file (UploadFile), candidate_id, media_url, generate_prompt
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("completed", "partially_completed"):
        raise HTTPException(status_code=400, detail="Cannot swap clip on an unfinished or failed job")

    job_dir = settings.output_dir / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job output directory not found")

    # 1. Parse request content (supports both JSON and Multipart Form)
    content_type = request.headers.get("content-type", "")
    candidate_id = None
    media_url = None
    generate_prompt = None
    file_bytes = None
    filename = None

    if "application/json" in content_type:
        try:
            body = await request.json()
            candidate_id = body.get("candidate_id")
            media_url = body.get("media_url")
            generate_prompt = body.get("generate_prompt")
        except Exception:
            pass
    elif "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "filename"):
            filename = uploaded_file.filename
            file_bytes = await uploaded_file.read()
        candidate_id = form.get("candidate_id")
        media_url = form.get("media_url")
        generate_prompt = form.get("generate_prompt")

    # 2. Load timeline and find the target scene
    timeline_file = job_dir / "timeline.json"
    timeline_data = None
    if timeline_file.exists():
        try:
            timeline_data = json.loads(timeline_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not timeline_data and job.timeline_json:
        try:
            timeline_data = json.loads(job.timeline_json)
        except Exception:
            pass

    if not timeline_data or not timeline_data.get("scenes"):
        raise HTTPException(status_code=400, detail="No scene timeline data available for this job")

    scenes = timeline_data["scenes"]
    scene_index = -1
    target_scene = None

    for idx, sc in enumerate(scenes):
        sc_id = str(sc.get("scene_id", ""))
        if sc_id == scene_id or sc_id == f"scene_{scene_id}":
            scene_index = idx
            target_scene = sc
            break

    if target_scene is None:
        try:
            num = int(re.sub(r"\D", "", scene_id)) - 1
            if 0 <= num < len(scenes):
                scene_index = num
                target_scene = scenes[num]
        except Exception:
            pass

    if target_scene is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found in job timeline")

    # 3. Resolve replacement asset
    t_start = time.time()
    asset_path = None
    is_image = False
    asset_id = None

    # Modality 1: Direct File Upload
    if file_bytes and filename:
        ext = Path(filename).suffix.lower()
        if ext not in (".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".webp"):
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload MP4, MOV, JPG, or PNG.")
        user_swaps_dir = job_dir / "user_swaps"
        user_swaps_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{scene_id}_{int(time.time())}_{Path(filename).name}"
        asset_path = user_swaps_dir / safe_name
        asset_path.write_bytes(file_bytes)
        is_image = ext in (".jpg", ".jpeg", ".png", ".webp")
        asset_id = f"custom_upload_{asset_path.stem}"

    # Modality 2: Candidate ID from Pool
    elif candidate_id:
        from app.models.job import CandidateModel
        cand_rec = db.query(CandidateModel).filter(
            CandidateModel.job_id == job_id,
            CandidateModel.candidate_id == candidate_id
        ).first()

        if cand_rec and cand_rec.local_path and Path(cand_rec.local_path).exists():
            asset_path = Path(cand_rec.local_path)
            is_image = cand_rec.media_type == "image" or asset_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")

        if not asset_path or not asset_path.exists():
            cand_dir = job_dir / "candidate_frames" / scene_id
            for ext in (".mp4", ".jpg", ".png", ".webp"):
                p = cand_dir / f"{candidate_id}{ext}"
                if p.exists() and p.stat().st_size > 1000:
                    asset_path = p
                    is_image = ext != ".mp4"
                    break

        if not asset_path and cand_rec and cand_rec.media_url:
            cand_dir = job_dir / "candidate_frames" / scene_id
            cand_dir.mkdir(parents=True, exist_ok=True)
            is_img_cand = cand_rec.media_type == "image" or any(cand_rec.media_url.lower().endswith(e) for e in (".jpg", ".jpeg", ".png"))
            ext = ".jpg" if is_img_cand else ".mp4"
            asset_path = cand_dir / f"{candidate_id}{ext}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(cand_rec.media_url)
                if resp.status_code == 200:
                    asset_path.write_bytes(resp.content)
                    is_image = is_img_cand

        if not asset_path or not asset_path.exists():
            raise HTTPException(status_code=404, detail=f"Candidate asset '{candidate_id}' could not be located on disk")
        asset_id = candidate_id

    # Modality 3: AI Image Prompt Generation
    elif generate_prompt:
        from app.services.image_generation_service import ImageGenerationService
        gen_svc = ImageGenerationService()
        gen_dir = job_dir / "generated_images" / scene_id
        gen_dir.mkdir(parents=True, exist_ok=True)
        asset_path = gen_dir / f"user_prompt_{int(time.time())}.jpg"
        gen_res = gen_svc.generate_image(
            prompt=generate_prompt,
            output_path=asset_path,
            style=target_scene.get("style") or "cinematic photo",
        )
        if not asset_path.exists() or asset_path.stat().st_size < 1000:
            raise HTTPException(status_code=500, detail="AI image generation failed to produce an image")
        is_image = True
        asset_id = f"ai_gen_{asset_path.stem}"

    # Modality 4: Media URL
    elif media_url:
        validate_external_url(media_url)
        user_swaps_dir = job_dir / "user_swaps"
        user_swaps_dir.mkdir(parents=True, exist_ok=True)
        is_image = any(media_url.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp"))
        ext = ".jpg" if is_image else ".mp4"
        asset_path = user_swaps_dir / f"url_swap_{int(time.time())}{ext}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(media_url)
            if resp.status_code == 200:
                asset_path.write_bytes(resp.content)
            else:
                raise HTTPException(status_code=400, detail=f"Failed to fetch asset from URL: HTTP {resp.status_code}")
        asset_id = f"url_asset_{asset_path.stem}"

    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide one of: candidate_id, file upload, generate_prompt, or media_url"
        )

    # 4. Perform Segment-Only Re-rendering via RenderingService
    from app.services.rendering_service import RenderingService
    renderer = RenderingService()
    aspect_ratios = json.loads(job.aspect_ratios) if job.aspect_ratios else ["16:9"]

    audio_path = None
    for pattern in ("narration.mp3", "narration_master.wav", "narration.wav", "narration_*.wav", "narration_*.mp3", "*.wav", "*.mp3"):
        for cand in job_dir.glob(pattern):
            if cand.is_file() and cand.stat().st_size > 1000:
                audio_path = cand
                break
        if audio_path:
            break

    if not audio_path or not audio_path.exists():
        raise HTTPException(status_code=400, detail="No valid master narration audio file found for this job")

    srt_path = job_dir / "captions.srt"

    updated_output_files = []
    for ar in aspect_ratios:
        out_mp4 = renderer.swap_scene_segment(
            scenes=scenes,
            scene_index=scene_index,
            new_asset_path=asset_path,
            audio_path=audio_path,
            output_dir=job_dir,
            aspect_ratio=ar,
            srt_path=srt_path,
            burn_captions=False,
            is_image=is_image,
        )
        updated_output_files.append({
            "aspect_ratio": ar,
            "filename": out_mp4.name,
            "download_url": f"/jobs/{job_id}/download/{out_mp4.name}",
            "file_size_bytes": out_mp4.stat().st_size,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    render_duration = time.time() - t_start

    # 5. Update scene metadata
    target_scene["selected_asset_id"] = asset_id
    if "candidate_frames" in str(asset_path):
        target_scene["selected_asset_url"] = f"/jobs/{job_id}/media/candidate_frames/{scene_id}/{asset_path.name}"
    elif "generated_images" in str(asset_path):
        target_scene["selected_asset_url"] = f"/jobs/{job_id}/media/generated_images/{scene_id}/{asset_path.name}"
    else:
        target_scene["selected_asset_url"] = f"/jobs/{job_id}/media/user_swaps/{asset_path.name}"
    target_scene["local_path"] = str(asset_path)
    target_scene["relevance_score"] = 5.0
    target_scene["clip_score"] = 5.0
    target_scene["verification_score"] = 5.0
    target_scene["selection_reason"] = "Manually selected by user (clip swap)"
    target_scene["validation_status"] = "manually_verified"
    target_scene["ai_generated"] = is_image and ("gen" in str(asset_path) or "ai" in str(asset_id))

    # 6. Update database models & manifests
    from app.models.job import SceneModel, ScoreRecordModel
    scene_row = db.query(SceneModel).filter(
        SceneModel.job_id == job_id,
        (SceneModel.scene_id == scene_id) | (SceneModel.scene_index == scene_index)
    ).first()
    if scene_row:
        scene_row.selected_asset_id = asset_id
        scene_row.relevance_score = 5.0
        scene_row.clip_score = 5.0
        scene_row.verification_score = 5.0
        scene_row.selection_reason = "Manually selected by user (clip swap)"

    if candidate_id:
        records = db.query(ScoreRecordModel).filter(
            ScoreRecordModel.job_id == job_id,
            ScoreRecordModel.scene_id == scene_id
        ).all()
        for rec in records:
            rec.is_selected = 1 if rec.candidate_id == candidate_id else 0

    timeline_file.write_text(json.dumps(timeline_data, indent=2), encoding="utf-8")
    job.timeline_json = json.dumps(timeline_data)

    manifest_file = job_dir / "manifest.json"
    if manifest_file.exists():
        try:
            man_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            man_data["output_files"] = updated_output_files
            manifest_file.write_text(json.dumps(man_data, indent=2), encoding="utf-8")
            job.manifest_json = json.dumps(man_data)
        except Exception:
            pass

    db.commit()

    primary_output_name = updated_output_files[0]["filename"] if updated_output_files else f"output_{aspect_ratios[0].replace(':', 'x')}.mp4"
    primary_output_path = str(job_dir / primary_output_name)

    return {
        "status": "success",
        "job_id": job_id,
        "scene_id": scene_id,
        "scene_index": scene_index,
        "swapped_asset": asset_path.name,
        "is_image": is_image,
        "duration_seconds": float(target_scene.get("duration", 5.0)),
        "render_duration_seconds": round(render_duration, 2),
        "output_videos": updated_output_files,
        "output_path": primary_output_path,
        "video_url": f"/jobs/{job_id}/video",
        "message": f"Successfully replaced Scene {scene_index + 1} and regenerated video at {primary_output_path} in {round(render_duration, 2)}s",
        "updated_scene": target_scene,
    }


@router.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job_endpoint(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("processing", "queued"):
        job.status = "failed"
        job.error_message = "Job cancelled by user from IncuBrix Studio"
        db.commit()
    return _job_to_response(job)


@router.post("/api/v1/jobs/{job_id}/retry")
def retry_job_endpoint(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = "queued"
    job.progress = 0
    job.current_stage = "queued"
    job.error_message = None
    job.error_code = None
    job.retry_count = (job.retry_count or 0) + 1
    db.commit()
    background_tasks.add_task(_run_job_async, job.id)
    return _job_to_response(job)


@router.get("/api/v1/jobs/{job_id}/logs")
def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    """Retrieve structured real-time pipeline event logs for a job."""
    log_file = settings.output_dir / job_id / "events.jsonl"
    events = []
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        except Exception:
            pass

    # If no jsonl exists yet, construct from database record
    if not events:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            events.append({
                "timestamp": (job.created_at or datetime.now(timezone.utc)).isoformat() if hasattr(job.created_at, "isoformat") else str(job.created_at),
                "level": "INFO",
                "stage": "queued",
                "progress": 0,
                "message": f"Job queued (input_type={job.input_type}, language={job.language})",
            })
            if job.started_at:
                events.append({
                    "timestamp": job.started_at.isoformat() if hasattr(job.started_at, "isoformat") else str(job.started_at),
                    "level": "INFO",
                    "stage": "preparing_audio",
                    "progress": 5,
                    "message": "Pipeline worker claimed job and started execution",
                })
            if job.current_stage and job.current_stage != "queued":
                events.append({
                    "timestamp": (job.completed_at or datetime.now(timezone.utc)).isoformat() if hasattr(job.completed_at, "isoformat") else str(job.completed_at),
                    "level": "ERROR" if job.status == "failed" else "INFO",
                    "stage": job.current_stage,
                    "progress": job.progress,
                    "message": job.stage_detail or f"Current stage: {job.current_stage}",
                })
            if job.error_message:
                events.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "ERROR",
                    "stage": job.current_stage or "failed",
                    "progress": job.progress,
                    "message": f"Error: {job.error_message}",
                })

    return {"job_id": job_id, "logs": events}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get current job status and progress (legacy)."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_to_response(job)


# ── Shared Audio Upload Handler ────────────────────────────────────────────────

async def _handle_audio_upload(
    file: UploadFile,
    ratios: List[str],
    style_pref: Optional[str],
    avoid_list: List[str],
    language: str = "en",
    target_language: Optional[str] = None,
    narration_language: Optional[str] = None,
    subtitle_language: str = "en",
    idempotency_key: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = None,
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    job_id = str(uuid.uuid4())
    upload_dir = settings.upload_dir / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"upload{suffix}"

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb}MB limit",
        )

    upload_path.write_bytes(content)

    probe = probe_audio(upload_path)
    if not probe.get("valid"):
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File is not a valid audio file: {probe.get('error', 'unknown')}",
        )

    duration = probe.get("duration", 0)
    if duration > settings.max_audio_duration_seconds:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Audio duration {duration:.1f}s exceeds {settings.max_audio_duration_seconds}s limit",
        )

    job = Job(
        id=job_id,
        idempotency_key=idempotency_key,
        input_type="audio",
        upload_filename=file.filename,
        upload_path=str(upload_path),
        audio_duration=duration,
        aspect_ratios=json.dumps(ratios),
        style_preferences=style_pref,
        avoid_constraints=json.dumps(avoid_list),
        language=language or "en",
        target_language=target_language,
        narration_language=narration_language or target_language or language or "en",
        subtitle_language=subtitle_language or "en",
        status="queued",
        progress=0,
        current_stage="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_job_async, job.id)
    logger.info(f"Queued audio job {job.id} ({file.filename}, {duration:.1f}s, lang={job.language})")
    return _job_to_response(job)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_to_response(job: Job) -> JobStatusResponse:
    artifacts = None
    if job.artifacts_json:
        try:
            artifacts = json.loads(job.artifacts_json)
            if artifacts.get("videos"):
                artifacts["video_urls"] = [
                    f"/jobs/{job.id}/download/{v}" for v in artifacts["videos"]
                ]
        except Exception:
            pass

    avoid_constraints = []
    if job.avoid_constraints:
        try:
            avoid_constraints = json.loads(job.avoid_constraints)
        except Exception:
            avoid_constraints = [job.avoid_constraints]

    scenes_count = None
    if job.timeline_json:
        try:
            tl = json.loads(job.timeline_json)
            scenes_count = len(tl.get("scenes", []))
        except Exception:
            pass
    elif job.manifest_json:
        try:
            mf = json.loads(job.manifest_json)
            scenes_count = len(mf.get("scenes", []))
        except Exception:
            pass

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        input_type=job.input_type,
        input_text=job.script_text,
        script_text=job.script_text,
        progress=job.progress,
        progress_pct=float(job.progress or (100 if job.status == "completed" else 0)),
        scenes_count=scenes_count,
        current_stage=job.current_stage,
        stage_detail=job.stage_detail,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_code=job.error_code,
        error_message=job.error_message,
        error_detail=job.error_detail,
        retry_count=job.retry_count,
        aspect_ratios=json.loads(job.aspect_ratios) if job.aspect_ratios else ["16:9"],
        style_preferences=job.style_preferences,
        avoid_constraints=avoid_constraints,
        language=job.language or "en",
        target_language=job.target_language,
        narration_language=job.narration_language or job.language or "en",
        subtitle_language=job.subtitle_language or "en",
        artifacts=artifacts,
    )


def _run_job_async(job_id: str) -> None:
    """Run the video pipeline in a background thread."""
    from app.database import SessionLocal
    from app.workers.video_pipeline import run_pipeline

    db = SessionLocal()
    try:
        run_pipeline(job_id, db)
    except Exception as e:
        logger.error(f"Unhandled error in job {job_id}: {e}")
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            job.error_code = "PIPELINE_ERROR"
            db.commit()
    finally:
        db.close()
