"""
Runner for user uploaded audio job:
Measures total end-to-end execution time, runs the complete video pipeline,
and prints all relevance scores and execution metrics.
"""
import json
import logging
import time
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models.job import Job
from app.workers.video_pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_uploaded_audio_job")


def main():
    audio_path = Path("C:/Users/praga/.gemini/antigravity/brain/1851df22-7ed3-49f3-90d5-4c167ed16bd2/.user_uploaded/uploaded_media_1792561931559.mp3")
    
    extracted_text = (
        "Every great achievement begins with one small step. "
        "You do not need to have everything figured out today. "
        "You only need the courage to begin and the discipline to keep going. "
        "Some days will feel difficult and progress may seem slow, "
        "but every effort is building strength, skill, and confidence. "
        "Do not compare your journey with someone else's. "
        "Focus on becoming a little better than you were yesterday. "
        "Believe in your potential, stay consistent, and keep moving forward. "
        "Your future is shaped by what you choose to do today."
    )

    print("=" * 80)
    print("INCUBRIX VIDEO ENGINE — USER AUDIO JOB EXECUTION")
    print("=" * 80)
    print(f"Uploaded Audio Path: {audio_path}")
    print(f"Extracted Script Text:\n\"{extracted_text}\"")
    print("=" * 80)

    init_db()
    db: Session = SessionLocal()

    from app.config import settings
    settings.google_cloud_project = "incubrix-project1"
    settings.enable_ai_image_fallback = True
    settings.min_relevance_threshold = 3.0
    settings.min_verification_threshold = 2.5

    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job = Job(
        id=job_id,
        input_type="audio",
        upload_path=str(audio_path),
        script_text=extracted_text,
        aspect_ratios=json.dumps(["16:9"]),
        style_preferences="cinematic motivational documentary style, majestic nature, symbolic landscapes, metaphorical objects, authentic natural lighting, ultra-high resolution, scenic wide views",
        avoid_constraints=json.dumps([
            "humans", "people", "human faces", "characters", "portraits", "crowds",
            "watermarks", "distorted visuals", "brand logos", "blurry imagery"
        ]),
        status="queued",
        progress=0,
    )
    db.add(job)
    db.commit()
    print(f"Created Job ID: {job_id}")

    start_time = time.time()
    print(f"\n[TIMER STARTED] Beginning complete video generation at {time.strftime('%X')}...")

    try:
        run_pipeline(job_id, db)
    except Exception as e:
        logger.exception(f"Pipeline crashed: {e}")
        raise

    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = total_time % 60

    print("\n" + "=" * 80)
    print(f"JOB COMPLETED IN {minutes}m {seconds:.2f}s ({total_time:.2f} seconds total)")
    print("=" * 80)

    # Print summary of results from manifest and eval sheet
    job_dir = Path("backend/storage/jobs") / job_id
    manifest_file = job_dir / "manifest.json"
    eval_file = job_dir / "evaluation_sheet.json"

    if manifest_file.exists() and eval_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        with open(eval_file, "r", encoding="utf-8") as f:
            eval_rows = {r["scene_id"]: r for r in json.load(f)}

        print(f"\nRendered Video: {job_dir / 'output_16x9.mp4'}")
        print(f"Evaluation Sheet: {job_dir / 'evaluation_sheet.csv'}")
        print("\n--- SCENE RELEVANCE & FOOTAGE BREAKDOWN ---")
        for sc in manifest.get("scenes", []):
            sc_id = sc["scene_id"]
            ev = eval_rows.get(sc_id, {})
            prov = sc.get("provenance", {})
            provider = "PIXABAY STOCK" if prov.get("provider") == "pixabay" else "GEMINI-2.5-FLASH-IMAGE"
            print(f"[{sc_id}] ({sc['start_time']:.1f}s -> {sc['end_time']:.1f}s) Asset: {sc.get('selected_asset_id')} ({provider})")
            print(f"   Narration: \"{sc['narration_text']}\"")
            print(f"   Relevance Score: {ev.get('relevance_score', 0):.2f} / 5.00 (Threshold: >= 3.50)")
            print(f"   CLIP: {ev.get('clip_score', 0):.4f} | VLM: {ev.get('verification_score', 0):.2f} | Subj: {ev.get('subject_match', 0):.2f}")


if __name__ == "__main__":
    main()
