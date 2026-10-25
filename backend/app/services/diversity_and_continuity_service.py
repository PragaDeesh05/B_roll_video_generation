"""
Story-level Visual Diversity Tracker & Narrative Continuity Validator (Phase 8, Sections 13 & 14).
Prevents accidental visual repetition (e.g. repeated piggy banks) using perceptual hashing,
subject tracking, and validates end-to-end story continuity before rendering.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


def compute_dhash(image_path: Path, hash_size: int = 8) -> str:
    """Compute difference hash (dHash) of an image for perceptual deduplication."""
    try:
        with Image.open(image_path) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            diff = []
            for row in range(hash_size):
                for col in range(hash_size):
                    pixel_left = img.getpixel((col, row))
                    pixel_right = img.getpixel((col + 1, row))
                    diff.append(pixel_left > pixel_right)
            # Convert boolean list to hex string
            decimal_val = 0
            hex_str = []
            for idx, val in enumerate(diff):
                if val:
                    decimal_val += 2 ** (idx % 4)
                if idx % 4 == 3:
                    hex_str.append(f"{decimal_val:x}")
                    decimal_val = 0
            return "".join(hex_str)
    except Exception as e:
        logger.debug(f"Could not compute dHash for {image_path}: {e}")
        return ""


def hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate hamming distance between two hex hash strings."""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 999
    try:
        bin1 = bin(int(hash1, 16))[2:].zfill(len(hash1) * 4)
        bin2 = bin(int(hash2, 16))[2:].zfill(len(hash2) * 4)
        return sum(c1 != c2 for c1, c2 in zip(bin1, bin2))
    except Exception:
        return 999


class VisualDiversityTracker:
    """Tracks visual assets across scenes to guarantee story-level diversity."""

    def __init__(self, repetition_threshold: float = 0.70):
        self.repetition_threshold = repetition_threshold
        self.used_asset_ids: Set[str] = set()
        self.file_hashes: Set[str] = set()
        self.perceptual_hashes: List[str] = []
        self.selected_subjects: List[str] = []
        self.selected_actions: List[str] = []
        self.scene_records: List[Dict[str, Any]] = []

    def check_candidate_diversity(
        self,
        candidate: Dict[str, Any],
        scene: Dict[str, Any],
        frame_paths: Optional[List[Path]] = None,
    ) -> Tuple[float, float, bool, str]:
        """
        Evaluate candidate against previously selected scenes.

        Returns:
            (diversity_score: float (1.0-5.0), repetition_risk: float (0.0-1.0),
             is_excessive_repetition: bool, evidence: str)
        """
        asset_id = str(candidate.get("id", ""))
        tags = (candidate.get("tags") or "").lower()
        cand_subject = (scene.get("visual_subject") or "").lower()

        # 1. Exact asset ID duplication
        if asset_id in self.used_asset_ids:
            return 1.0, 1.0, True, f"Exact asset ID duplication ({asset_id})"

        # 2. Perceptual image hash comparison
        cand_dhash = ""
        if frame_paths and len(frame_paths) > 0 and frame_paths[0].exists():
            cand_dhash = compute_dhash(frame_paths[0])
            for prev_hash in self.perceptual_hashes:
                dist = hamming_distance(cand_dhash, prev_hash)
                if dist < 6:  # Near identical image
                    return 1.2, 0.95, True, f"Perceptually near-identical image to prior scene (dHash distance={dist})"

        # 3. Subject and Visual Metaphor Cliché Tracking
        # Example: repeated piggy bank / coin shots in consecutive scenes
        cliche_categories = [
            ("piggy_bank_coins", ["piggy", "piggy bank", "stack of coins", "cash pile"]),
            ("handshake_deal", ["handshake", "shaking hands", "business deal"]),
            ("lightbulb_idea", ["lightbulb", "glowing bulb", "idea bulb"]),
        ]

        repetition_risk = 0.1
        evidence = []

        for category_name, category_keywords in cliche_categories:
            is_cand_category = any(kw in tags for kw in category_keywords)
            if is_cand_category:
                prev_hits = sum(
                    1 for s in self.selected_subjects if any(kw in s.lower() for kw in category_keywords)
                )
                if prev_hits >= 1:
                    repetition_risk += 0.5 * prev_hits
                    evidence.append(
                        f"Repeated motif category '{category_name}' used {prev_hits} time(s) in earlier scenes."
                    )

        # Check if subject is verbatim duplicate of immediate previous scene
        if self.selected_subjects and cand_subject:
            last_subject = self.selected_subjects[-1]
            if cand_subject == last_subject and not scene.get("visual_continuity_requirements"):
                repetition_risk += 0.4
                evidence.append(f"Verbatim subject repeat from previous scene: '{cand_subject}'")

        repetition_risk = min(1.0, round(repetition_risk, 2))
        diversity_score = round(max(1.0, 5.0 - 4.0 * repetition_risk), 2)
        is_excessive = repetition_risk >= self.repetition_threshold

        reason = "; ".join(evidence) if evidence else "Visually distinct composition and subject."
        return diversity_score, repetition_risk, is_excessive, reason

    def record_selection(
        self,
        candidate: Dict[str, Any],
        scene: Dict[str, Any],
        frame_paths: Optional[List[Path]] = None,
    ) -> None:
        """Commit selected visual to memory."""
        asset_id = str(candidate.get("id", ""))
        self.used_asset_ids.add(asset_id)
        if scene.get("visual_subject"):
            self.selected_subjects.append(str(scene["visual_subject"]))
        if scene.get("visual_action"):
            self.selected_actions.append(str(scene["visual_action"]))

        if frame_paths and len(frame_paths) > 0 and frame_paths[0].exists():
            h = compute_dhash(frame_paths[0])
            if h:
                self.perceptual_hashes.append(h)

        self.scene_records.append({"scene_id": scene.get("scene_id"), "asset_id": asset_id})


class NarrativeContinuityValidator:
    """Validates full-video story progression and narrative coherence before rendering."""

    def validate_video_continuity(
        self,
        scenes: List[Dict[str, Any]],
        narration_duration: float,
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate full-sequence continuity.

        Returns:
            (is_valid: bool, issues: List[str], warnings: List[str])
        """
        issues = []
        warnings = []

        if not scenes:
            return False, ["Video has no planned scenes."], []

        # 1. Monotonic ordering and full narration coverage
        for i, s in enumerate(scenes):
            start = s.get("start_time", 0.0)
            end = s.get("end_time", 0.0)
            if end <= start:
                issues.append(f"Scene {i} ({s.get('scene_id')}) has invalid non-positive duration: {start} -> {end}")

            if i > 0:
                prev_end = scenes[i - 1].get("end_time", 0.0)
                gap = start - prev_end
                if abs(gap) > 1.0:
                    issues.append(f"Temporal gap of {gap:.2f}s between scene {i-1} and scene {i}")

        # 2. Check full duration coverage
        first_start = scenes[0].get("start_time", 0.0)
        last_end = scenes[-1].get("end_time", 0.0)
        if abs(first_start) > 0.5:
            issues.append(f"First scene does not start at 0.0s (starts at {first_start}s)")
        if abs(last_end - narration_duration) > 1.5:
            warnings.append(
                f"Total scene duration ({last_end}s) differs from narration ({narration_duration}s) by >1.5s"
            )

        # 3. Check narrative beat diversity
        roles = [s.get("narrative_role") for s in scenes if s.get("narrative_role")]
        if len(scenes) >= 3 and len(set(roles)) < 2:
            warnings.append(
                "Low narrative beat progression: all scenes share the same functional narrative role."
            )

        # 4. Check subject diversity
        subjects = [s.get("visual_subject", "").lower() for s in scenes if s.get("visual_subject")]
        if len(subjects) >= 4 and len(set(subjects)) <= len(subjects) // 2:
            warnings.append(
                "Excessive visual idea repetition: over 50% of scenes share identical visual subjects."
            )

        # 5. Ending role resolution check
        ending_role = (scenes[-1].get("narrative_role") or "").lower()
        ending_beat = (scenes[-1].get("narrative_beat") or "").lower()
        if "resolution" not in ending_role and "conclusion" not in ending_role and "security" not in ending_beat and "resolution" not in ending_beat:
            warnings.append("Ending scene does not explicitly indicate narrative resolution or conclusion.")

        is_valid = len(issues) == 0
        return is_valid, issues, warnings
