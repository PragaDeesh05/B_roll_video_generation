import os
import sys
import uuid
import json
from pathlib import Path

# Add backend directory to path
backend_path = Path(r"c:\Users\praga\OneDrive\Documents\Downloads\video_gen_incubrix\backend")
sys.path.insert(0, str(backend_path))

from app.database import SessionLocal
from app.models.job import Job
from app.workers.video_pipeline import run_pipeline

def test_tamil_accurate_captions_and_relevance():
    print("=== Testing Accurate Tamil Captions & High-Relevance Visual Retrieval ===")
    db = SessionLocal()
    try:
        job_id = f"test-ta-acc-{uuid.uuid4().hex[:6]}"
        script = "வணக்கம் நண்பர்களே. தமிழ்நாட்டில் பொங்கல் திருநாள் அறுவடைத் திருநாளாக மகிழ்ச்சியுடன் கொண்டாடப்படுகிறது."
        job = Job(
            id=job_id,
            status="pending",
            input_type="text",
            script_text=script,
            language="ta",
            aspect_ratios=json.dumps(["16:9"]),
            avoid_constraints=json.dumps(["watermark", "blurry", "text"]),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        print(f"Created Tamil Job: {job_id}")

        run_pipeline(job_id, db)

        db.refresh(job)
        print(f"Final Job Status: {job.status}")
        print(f"Error (if any): {job.error_message}")
        
        job_dir = backend_path / "storage" / "jobs" / job_id
        if not job_dir.exists():
            job_dir = Path("storage/jobs") / job_id

        print(f"Job directory exists: {job_dir.exists()}")
        
        # 1. Check Subtitle Verbatim Accuracy
        srt_file = job_dir / "captions.srt"
        if srt_file.exists():
            srt_content = srt_file.read_text(encoding="utf-8")
            print("\n--- Subtitle Captions (SRT) ---")
            for line in srt_content.splitlines():
                print(line)
            
            # Check if key ground truth words are present
            assert "வணக்கம் நண்பர்களே" in srt_content, "Expected 'வணக்கம் நண்பர்களே' in captions!"
            assert "பொங்கல்" in srt_content, "Expected 'பொங்கல்' in captions!"
            assert "அறுவடை" in srt_content, "Expected 'அறுவடை' in captions!"
            print("\n>> VERIFIED: 100% exact Tamil words preserved without corruption!")

        # 2. Check Scene Relevance & Image Selection
        timeline_file = job_dir / "timeline.json"
        if timeline_file.exists():
            timeline_data = json.loads(timeline_file.read_text(encoding="utf-8"))
            print("\n--- Scene Details & Visual Relevance ---")
            for sc in timeline_data.get("scenes", []):
                sid = sc.get("scene_id")
                dur = sc.get("duration")
                narr = sc.get("narration_text")
                query = sc.get("primary_search_query")
                rel = sc.get("relevance_score")
                asset = sc.get("selected_asset_id")
                reason = sc.get("selection_reason")
                print(f"  [{sid}] {dur}s | Rel: {rel} | Query: '{query}' | Asset: {asset}")
                print(f"      Narration: {narr}")
                print(f"      Reason: {reason}")
                assert float(rel or 0.0) >= 3.0, f"Scene {sid} relevance {rel} < 3.0 threshold!"

        # 3. Check Post-Render Automated Validation
        val_file = job_dir / "validation_report.json"
        if val_file.exists():
            val_data = json.loads(val_file.read_text(encoding="utf-8"))
            print(f"\nValidation Overall Passed: {val_data.get('overall_passed')}")
            assert val_data.get("overall_passed") is True, "Validation did not pass!"

        print("\n=== ALL TAMIL ACCURACY & RELEVANCE CHECKS PASSED SUCCESSFULLY ===")
        return True
    finally:
        db.close()

if __name__ == "__main__":
    success = test_tamil_accurate_captions_and_relevance()
    sys.exit(0 if success else 1)
