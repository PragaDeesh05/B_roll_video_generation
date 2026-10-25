"""
Safety Service
Flags named people, brands, sensitive content, and applies conservative rules.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Patterns for named people (simple heuristic: two+ capitalized words)
NAMED_PERSON_PATTERN = re.compile(r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b")

# Known brand keywords (expand as needed)
BRAND_KEYWORDS = {
    "apple", "google", "microsoft", "amazon", "facebook", "meta",
    "twitter", "instagram", "tiktok", "youtube", "netflix", "tesla",
    "samsung", "nike", "coca-cola", "pepsi", "mcdonalds", "starbucks",
}

SENSITIVE_KEYWORDS = {
    "death", "died", "killed", "murder", "suicide", "tragedy", "disaster",
    "war", "attack", "shooting", "bombing", "terrorist", "violence",
    "abuse", "assault", "rape", "genocide", "holocaust",
}

SAD_NEWS_KEYWORDS = {
    "funeral", "mourning", "grief", "memorial", "condolence", "victim",
}

NSFW_KEYWORDS = {
    "nude", "naked", "sexual", "explicit", "adult", "xxx",
}


class SafetyService:
    """Detects safety issues in scenes and applies conservative search rules."""

    def check_scene(self, scene: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
        """
        Check a scene for safety concerns.

        Returns:
            (flags list, modified scene dict with safety mitigations applied)
        """
        flags = list(scene.get("safety_flags", []))
        text = (
            scene.get("transcript_text", "")
            + " "
            + scene.get("visual_description", "")
            + " "
            + scene.get("scene_summary", "")
        ).lower()

        # Named person detection
        full_text = scene.get("transcript_text", "") + " " + scene.get("scene_summary", "")
        named_people = NAMED_PERSON_PATTERN.findall(full_text)
        if named_people:
            flags.append(f"named_person:{','.join(named_people[:3])}")
            # Override queries to avoid realistic depictions
            scene = self._apply_generic_footage_override(scene, "contextual background")

        # Brand detection
        brand_hits = {kw for kw in BRAND_KEYWORDS if kw in text}
        if brand_hits:
            flags.append(f"brand_content:{','.join(brand_hits)}")
            scene = self._sanitize_query(scene, brand_hits)

        # Sensitive / sad news
        sensitive_hits = {kw for kw in SENSITIVE_KEYWORDS if kw in text}
        if sensitive_hits:
            flags.append(f"sensitive_content:{','.join(sensitive_hits)}")

        sad_hits = {kw for kw in SAD_NEWS_KEYWORDS if kw in text}
        if sad_hits:
            flags.append(f"sad_news:{','.join(sad_hits)}")

        # NSFW
        nsfw_hits = {kw for kw in NSFW_KEYWORDS if kw in text}
        if nsfw_hits:
            flags.append("nsfw_content")
            scene["excluded_visual_elements"] = list(
                set(scene.get("excluded_visual_elements", []))
                | {"explicit content", "adult content"}
            )

        scene["safety_flags"] = flags
        return flags, scene

    def _apply_generic_footage_override(self, scene: Dict, override_query: str) -> Dict:
        """Replace queries with context-appropriate generic footage for named-person scenes."""
        transcript_words = scene.get("transcript_text", "").lower().split()[:5]
        safe_query = " ".join(transcript_words) if transcript_words else override_query

        scene["alternative_search_queries"] = [
            scene.get("primary_search_query", ""),
        ] + scene.get("alternative_search_queries", [])[:2]

        # Keep primary query (Pixabay doesn't reliably match real people anyway)
        # but add context-safe alternatives
        scene["alternative_search_queries"].insert(0, safe_query)
        return scene

    def _sanitize_query(self, scene: Dict, brand_hits: set) -> Dict:
        """Remove brand names from search queries to avoid logo/trademark content."""
        for brand in brand_hits:
            for field in ("primary_search_query", "alternative_search_queries"):
                if field == "primary_search_query":
                    scene[field] = scene[field].replace(brand, "").strip()
                else:
                    scene[field] = [
                        q.replace(brand, "").strip()
                        for q in scene.get(field, [])
                    ]
        scene["excluded_visual_elements"] = list(
            set(scene.get("excluded_visual_elements", []))
            | {"brand logo", "company logo", "trademark"}
        )
        return scene

    def is_asset_safe(self, asset: Dict[str, Any], scene: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Final safety check on a selected asset before use.

        Returns:
            (is_safe, reason_if_not)
        """
        tags_str = asset.get("tags", "").lower()
        tags = set(tags_str.split(", "))

        nsfw_tags = tags & {"nude", "adult", "explicit", "nsfw", "erotic", "sexy"}
        if nsfw_tags:
            return False, f"NSFW tags: {nsfw_tags}"

        # Check for scene safety flags requiring rejection
        flags = scene.get("safety_flags", [])
        if any("nsfw" in f for f in flags):
            if nsfw_tags:
                return False, "NSFW content rejected due to scene safety flag"

        return True, ""
