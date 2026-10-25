"""
Artifact Service
Generates timeline.json, manifest.json, and the validation report.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class ArtifactService:
    """Generates and saves job artifacts."""

    def generate_timeline(
        self,
        job_id: str,
        scenes: List[Dict[str, Any]],
        narration_duration: float,
        aspect_ratio: str,
        output_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """Build and save timeline.json."""
        timeline = {
            "job_id": job_id,
            "narration_duration": narration_duration,
            "output_profile": aspect_ratio,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "scenes": [self._scene_to_timeline_entry(s) for s in scenes],
        }
        output_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        return timeline

    def generate_manifest(
        self,
        job_id: str,
        input_type: str,
        input_metadata: Dict,
        output_files: List[Dict],
        scenes: List[Dict],
        validation_results: List[Dict],
        output_path: Path,
    ) -> Dict:
        """Build and save manifest.json."""
        manifest = {
            "job_id": job_id,
            "app_version": settings.app_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_type": input_type,
            "input_metadata": input_metadata,
            "output_files": output_files,
            "scenes_count": len(scenes),
            "scenes": [self._scene_to_manifest_entry(s) for s in scenes],
            "validation_summary": {
                "outputs_validated": len(validation_results),
                "all_passed": all(v.get("overall_passed", False) for v in validation_results),
                "results": validation_results,
            },
        }
        output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def generate_validation_report(
        self,
        job_id: str,
        validation_results: List[Dict],
        srt_valid: bool,
        srt_error: Optional[str],
        output_path: Path,
    ) -> Dict:
        """Build and save validation_report.json."""
        report = {
            "job_id": job_id,
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "overall_passed": all(v.get("overall_passed", False) for v in validation_results) and srt_valid,
            "outputs": validation_results,
            "srt_valid": srt_valid,
            "srt_error": srt_error,
        }
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    # ── Private helpers ───────────────────────────────────────────────────────

    def _scene_to_timeline_entry(self, scene: Dict) -> Dict:
        return {
            "scene_id": scene.get("scene_id"),
            "scene_index": scene.get("scene_index", 0),
            "start_time": scene.get("start_time"),
            "end_time": scene.get("end_time"),
            "duration": scene.get("duration"),
            "narration_text": scene.get("narration_text") or scene.get("transcript_text", ""),
            "transcript_text": scene.get("transcript_text") or scene.get("narration_text", ""),
            "scene_summary": scene.get("scene_summary", ""),
            "narrative_beat": scene.get("narrative_beat"),
            "narrative_role": scene.get("narrative_role"),
            "semantic_description": scene.get("semantic_description") or scene.get("visual_description", ""),
            "visual_description": scene.get("visual_description") or scene.get("semantic_description", ""),
            "visual_subject": scene.get("visual_subject"),
            "visual_action": scene.get("visual_action"),
            "primary_search_queries": scene.get("primary_search_queries") or [scene.get("primary_search_query", "")],
            "primary_search_query": scene.get("primary_search_query", ""),
            "alternative_search_queries": scene.get("alternative_search_queries", []),
            "image_generation_prompt": scene.get("image_generation_prompt"),
            "selected_asset_id": scene.get("selected_asset_id"),
            "selected_asset_url": scene.get("selected_asset_url"),
            "provenance": scene.get("provenance"),
            "clip_score": scene.get("clip_score"),
            "query_similarity": scene.get("query_similarity"),
            "semantic_similarity": scene.get("semantic_similarity"),
            "relevance_score": scene.get("relevance_score"),
            "verification_score": scene.get("verification_score"),
            "temporal_evidence": scene.get("temporal_evidence"),
            "selection_reason": scene.get("selection_reason"),
            "rejection_reason": scene.get("rejection_reason"),
            "relevance_explanation": scene.get("relevance_explanation"),
            "safety_flags": scene.get("safety_flags", []),
            "ai_generated": scene.get("ai_generated", False),
            "color_normalization": scene.get("color_normalization"),
            "validation_status": scene.get("validation_status"),
        }

    def _scene_to_manifest_entry(self, scene: Dict) -> Dict:
        entry = self._scene_to_timeline_entry(scene)
        prov = scene.get("provenance", {}) or {}
        # Ensure no internal filesystem paths in manifest
        entry["provenance"] = {
            k: v for k, v in prov.items()
            if k not in ("media_url",)  # Exclude direct media URL from public manifest
        } if prov else None
        return entry
