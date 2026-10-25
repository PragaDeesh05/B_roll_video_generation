from app.database import SessionLocal
from app.models.job import ScoreRecordModel, SceneModel

db = SessionLocal()
scores = db.query(ScoreRecordModel).filter(
    ScoreRecordModel.job_id == 'job_7183c367',
    ScoreRecordModel.candidate_id.like('%pixabay%')
).all()

scenes = {s.scene_id: s for s in db.query(SceneModel).filter(SceneModel.job_id == 'job_7183c367').all()}

print(f"Total Pixabay candidates evaluated: {len(scores)}\n")
for s in scores:
    sc = scenes.get(s.scene_id)
    scene_text = sc.narration_text if sc else ''
    pixabay_id = s.candidate_id.replace('job_7183c367_', '')
    print(f"[{s.scene_id}] Narration: \"{scene_text}\"")
    print(f"  Asset: {pixabay_id}")
    print(f"  Relevance Score:      {s.relevance_score:.2f} / 5.00  (Threshold: 3.50)")
    print(f"  OpenCLIP Score:       {s.clip_score}")
    print(f"  Verification Score:   {s.verification_score:.2f} / 5.00")
    print(f"  Subject Match:        {s.subject_match:.2f}")
    print(f"  Action Match:         {s.action_match:.2f}")
    print(f"  Contradiction:        {s.contradiction_detected}")
    print(f"  Decision:             BELOW THRESHOLD (< 3.5) -> Fallback to gemini-2.5-flash-image")
    print("-" * 75)
