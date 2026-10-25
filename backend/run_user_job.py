"""
Script to execute the Incubrix B-Roll video pipeline for the user's custom script.
"""
import json
import logging
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models.job import Job, SceneModel, CandidateModel, ScoreRecordModel
from app.workers.video_pipeline import run_pipeline
from app.utils.media import probe_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_user_job")


def main():
    script_text = (
        "Climate change is one of the biggest challenges facing our planet. "
        "Rising temperatures are melting glaciers, increasing sea levels, and changing weather patterns. "
        "Forests absorb carbon dioxide and help regulate the Earth's climate. "
        "By adopting renewable energy, protecting forests, and reducing waste, we can contribute to a more sustainable future."
    )
    print("=" * 70)
    print("INCUBRIX CONTEXT-AWARE B-ROLL VIDEO ENGINE — JOB EXECUTION")
    print("=" * 70)
    print(f"Input Script: \"{script_text}\"")

    init_db()
    db: Session = SessionLocal()

    from app.config import settings
    settings.google_cloud_project = "incubrix-project1"
    settings.enable_ai_image_fallback = True

    try:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = Job(
            id=job_id,
            input_type="text",
            script_text=script_text,
            aspect_ratios=json.dumps(["16:9"]),
            style_preferences="cinematic documentary style, authentic natural lighting, clear composition",
            avoid_constraints=json.dumps(["watermarks", "distorted visuals", "brand logos", "blurry imagery"]),
            status="queued",
            progress=0,
        )
        db.add(job)
        db.commit()
        print(f"Created Job ID: {job_id}")

        print("\nStarting video generation pipeline...")
        run_pipeline(job_id, db)

        db.expire_all()
        job = db.query(Job).filter(Job.id == job_id).first()
        print(f"\nJob Execution Status: {job.status.upper()}")
        if job.status == "failed":
            print(f"Error Code: {job.error_code}")
            print(f"Error Message: {job.error_message}")
            return

        print(f"Progress: {job.progress}%")
        artifacts = json.loads(job.artifacts_json) if job.artifacts_json else {}
        print("\nGenerated Artifacts:")
        for k, v in artifacts.items():
            print(f" - {k}: {v}")

        # Inspect scenes & candidates
        scenes = db.query(SceneModel).filter(SceneModel.job_id == job_id).order_by(SceneModel.scene_index).all()
        print(f"\nPlanned & Rendered Scenes ({len(scenes)} scenes):")
        for sc in scenes:
            print(f"\n--- Scene {sc.scene_index + 1} ({sc.scene_id}): [{sc.start_time:.1f}s -> {sc.end_time:.1f}s] ---")
            print(f" Narration: \"{sc.narration_text}\"")
            print(f" Narrative Role: {sc.narrative_role}")
            print(f" Visual Subject: {sc.visual_subject}")
            print(f" Visual Action: {sc.visual_action}")
            print(f" Semantic Description: {sc.semantic_description}")
            print(f" Selected Asset ID: {sc.selected_asset_id}")
            print(f" Selection Reason: {sc.selection_reason}")
            print(f" Winning Scores -> CLIP: {sc.clip_score}, Verification: {sc.verification_score}, Relevance: {sc.relevance_score}")

            # Print all candidates evaluated under this scene
            scores = db.query(ScoreRecordModel).filter(
                ScoreRecordModel.job_id == job_id,
                ScoreRecordModel.scene_id == sc.scene_id
            ).all()
            if scores:
                print(f" Candidates Evaluated ({len(scores)} candidates):")
                for scr in scores:
                    sel_flag = " [CHOSEN WINNER]" if scr.is_selected else ""
                    print(f"   * Candidate: {scr.candidate_id}{sel_flag}")
                    print(f"     CLIP: {scr.clip_score}, Verification: {scr.verification_score}, Relevance: {scr.relevance_score}, Subject Match: {scr.subject_match}, Contradiction: {scr.contradiction_detected}")

        # Probe final output video
        job_dir = Path("storage/jobs") / job_id
        rendered_videos = list(job_dir.glob("output_*.mp4")) + list(job_dir.glob("video_*.mp4"))
        if rendered_videos:
            final_video = rendered_videos[0]
            probe = probe_video(final_video)
            print("\n" + "=" * 70)
            print(f"FINAL RENDERED VIDEO: {final_video.resolve()}")
            print(f"Resolution: {probe.get('width')}x{probe.get('height')}")
            print(f"Duration: {probe.get('duration'):.2f} seconds")
            print(f"Video Codec: {probe.get('codec')}, Pixel Format: {probe.get('pix_fmt')}")
            print(f"Audio Stream Present: {probe.get('has_audio')}")
            print("=" * 70)

        eval_csv = job_dir / "evaluation_sheet.csv"
        if eval_csv.exists():
            print(f"\n30-Column Evaluation Sheet: {eval_csv.resolve()}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
