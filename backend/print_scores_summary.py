import json
from pathlib import Path

def print_scores(job_id: str = "job_0afbd8b6"):
    job_dir = Path("backend/storage/jobs") / job_id
    manifest_path = job_dir / "manifest.json"
    eval_path = job_dir / "evaluation_sheet.json"

    if not eval_path.exists() or not manifest_path.exists():
        print(f"Error: Job files not found in {job_dir}")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    with open(eval_path, "r", encoding="utf-8") as f:
        eval_rows = {r["scene_id"]: r for r in json.load(f)}

    print("=" * 90)
    print(f"INCUBRIX VIDEO ENGINE - SCENE & ASSET EVALUATION SUMMARY (Job: {job_id})")
    print("=" * 90)
    print(f"Minimum Relevance Threshold: 3.50 / 5.00")
    print(f"Target Aspect Ratio: 16:9 (1920x1080), Duration: {manifest['input_metadata']['narration_duration']:.2f}s")
    print("-" * 90)

    for sc in manifest["scenes"]:
        scene_id = sc["scene_id"]
        ev = eval_rows.get(scene_id, {})
        prov = sc.get("provenance") or {}
        is_pixabay = prov.get("provider") == "pixabay"
        
        all_queries = sc.get("primary_search_queries", []) + sc.get("alternative_search_queries", [])
        
        print(f"\n[Scene {scene_id}] Time: {sc['start_time']:.1f}s - {sc['end_time']:.1f}s")
        print(f"  Narration: \"{sc['narration_text']}\"")
        print(f"  Narrative Beat: {sc.get('narrative_beat')}")
        print(f"  Visual Subject: {sc.get('visual_subject')}")
        print(f"  Search Queries (3 Generated): {all_queries}")
        print(f"  Selected Asset ID: {sc.get('selected_asset_id')} ({'PIXABAY STOCK' if is_pixabay else 'GEMINI-2.5-FLASH-IMAGE'})")
        if is_pixabay:
            print(f"  Pixabay Source URL: {prov.get('original_url')}")
        rel_score = float(ev.get('relevance_score') or 0)
        clip_sc = float(ev.get('clip_score') or 0)
        ver_sc = float(ev.get('verification_score') or 0)
        subj_sc = float(ev.get('subject_match') or 0)
        act_sc = float(ev.get('action_match') or 0)

        print(f"  Scores:")
        print(f"    - Relevance Score:        {rel_score:.2f} / 5.00  (Threshold: >= 3.50 -> {'PASSED' if rel_score >= 3.5 else 'FAILED'})")
        print(f"    - OpenCLIP Cosine Score:  {clip_sc:.4f}")
        print(f"    - VLM Verification Score: {ver_sc:.2f} / 5.00")
        print(f"    - Subject Match:          {subj_sc:.2f}")
        print(f"    - Action Match:           {act_sc:.2f}")
        print(f"  Selection Reason: {ev.get('selection_reason')}")

    print("\n" + "=" * 90)

if __name__ == "__main__":
    print_scores()
