"""
Timeline Service
Aligns scene plans with the actual narration audio duration.
Enforces no-gap, no-overlap, and correct boundary rules.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class TimelineService:
    """Validates and corrects scene timing to match narration duration."""

    GAP_TOLERANCE = 0.05  # seconds
    DURATION_TOLERANCE = 0.5  # seconds

    def align_scenes(
        self,
        scenes: List[Dict[str, Any]],
        narration_duration: float,
        segments: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ensure scenes cover [0, narration_duration] with no gaps/overlaps and sensible pacing.

        If Whisper segments are available, refine scene boundaries to align
        with actual speech timing. Otherwise, distribute proportionally.
        Enforces min_scene_duration_seconds to avoid unintended short 0.5s flashes.
        """
        if not scenes:
            raise ValueError("Empty scene list cannot be aligned")
        if narration_duration <= 0:
            raise ValueError(f"Invalid narration duration: {narration_duration}")

        min_duration = getattr(settings, "min_scene_duration_seconds", 1.5)
        scenes = self.consolidate_duplicate_narration_scenes(scenes)
        scenes = self.consolidate_short_scenes(scenes, narration_duration, min_duration=min_duration)
        scenes = sorted(scenes, key=lambda s: s["start_time"])

        # If we have meaningful Whisper segments covering multiple intervals
        valid_segments = (
            segments is not None
            and len(segments) >= len(scenes)
            and any(s.get("end", 0) > s.get("start", 0) for s in segments)
        )

        if valid_segments:
            scenes = self._align_to_segments(scenes, segments, narration_duration)
        else:
            scenes = self._distribute_proportionally(scenes, narration_duration)

        # Final consistency pass
        scenes = self._enforce_coverage(scenes, narration_duration, min_duration=min_duration)
        self._validate(scenes, narration_duration)

        return scenes

    def consolidate_short_scenes(
        self,
        scenes: List[Dict[str, Any]],
        narration_duration: float,
        min_duration: float = 1.5,
    ) -> List[Dict[str, Any]]:
        """
        Merge excessively short scenes (< min_duration) with adjacent scenes
        to prevent unintended rapid 0.5s flashes, preserving all narration and metadata.
        """
        if len(scenes) <= 1 or narration_duration <= min_duration:
            return scenes

        max_allowed_scenes = max(1, int(narration_duration / min_duration))
        if len(scenes) > max_allowed_scenes:
            while len(scenes) > max_allowed_scenes and len(scenes) > 1:
                # Find shortest scene
                shortest_idx = min(range(len(scenes)), key=lambda idx: float(scenes[idx].get("duration", 0.0) or 0.0))
                if shortest_idx == 0:
                    scenes = [self._merge_two_scenes(scenes[0], scenes[1])] + scenes[2:]
                else:
                    merged = self._merge_two_scenes(scenes[shortest_idx - 1], scenes[shortest_idx])
                    scenes = scenes[:shortest_idx - 1] + [merged] + scenes[shortest_idx + 1:]

        for i, sc in enumerate(scenes):
            sc["scene_index"] = i
            sc["scene_id"] = f"scene_{i+1:03d}"

        return scenes

    def consolidate_duplicate_narration_scenes(
        self, scenes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge consecutive scenes that share the same or heavily overlapping narration text,
        preventing 'original, duplicate' narration repetition.
        """
        if not scenes or len(scenes) <= 1:
            return scenes

        import re
        deduped = []
        for s in scenes:
            cur_text = (s.get("narration_text") or s.get("transcript_text") or "").strip().lower()
            cur_clean = re.sub(r"[^\w\s]", "", cur_text).strip()
            if deduped:
                prev = deduped[-1]
                prev_text = (prev.get("narration_text") or prev.get("transcript_text") or "").strip().lower()
                prev_clean = re.sub(r"[^\w\s]", "", prev_text).strip()
                if cur_clean and prev_clean:
                    is_dup = (cur_clean == prev_clean) or (
                        (cur_clean in prev_clean or prev_clean in cur_clean)
                        and min(len(cur_clean), len(prev_clean)) / max(len(cur_clean), len(prev_clean)) > 0.6
                    )
                    if is_dup:
                        logger.info(
                            f"TimelineService: Consolidating duplicate scene {s.get('scene_id')} into {prev.get('scene_id')}"
                        )
                        merged = self._merge_two_scenes(prev, s)
                        deduped[-1] = merged
                        continue
            deduped.append(s)

        for i, sc in enumerate(deduped):
            sc["scene_index"] = i
            sc["scene_id"] = f"scene_{i+1:03d}"
        return deduped

    def _merge_two_scenes(self, sc_a: Dict[str, Any], sc_b: Dict[str, Any]) -> Dict[str, Any]:
        """Merge sc_b into sc_a without dropping narration or objects, avoiding duplicate repetition."""
        import re
        merged = dict(sc_a)
        text_a = (sc_a.get("narration_text") or sc_a.get("transcript_text") or "").strip()
        text_b = (sc_b.get("narration_text") or sc_b.get("transcript_text") or "").strip()

        clean_a = re.sub(r"[^\w\s]", "", text_a.lower()).strip()
        clean_b = re.sub(r"[^\w\s]", "", text_b.lower()).strip()
        if clean_a == clean_b or clean_b in clean_a:
            merged_text = text_a
        elif clean_a in clean_b:
            merged_text = text_b
        else:
            merged_text = f"{text_a} {text_b}".strip()

        merged["narration_text"] = merged_text
        merged["transcript_text"] = merged_text

        objs_a = sc_a.get("relevant_objects", []) or []
        objs_b = sc_b.get("relevant_objects", []) or []
        merged["relevant_objects"] = list(dict.fromkeys(objs_a + objs_b))

        sq_a = sc_a.get("search_queries", []) or []
        sq_b = sc_b.get("search_queries", []) or []
        merged["search_queries"] = list(dict.fromkeys(sq_a + sq_b))

        merged["duration"] = round(float(sc_a.get("duration", 0.0) or 0.0) + float(sc_b.get("duration", 0.0) or 0.0), 3)
        merged["end_time"] = sc_b.get("end_time", sc_a.get("end_time", 0.0))
        return merged

    def _align_to_segments(
        self,
        scenes: List[Dict],
        segments: List[Dict],
        duration: float,
    ) -> List[Dict]:
        """Snap scene boundaries to nearest Whisper segment boundaries."""
        if not segments or len(segments) < len(scenes):
            return self._distribute_proportionally(scenes, duration)

        seg_starts = sorted([s["start"] for s in segments if "start" in s])
        seg_ends = sorted([s["end"] for s in segments if "end" in s])

        min_dur = min(0.5, duration / (len(scenes) * 2))

        for i, scene in enumerate(scenes):
            # Find nearest segment start
            if i == 0:
                scene["start_time"] = 0.0
            else:
                prev_end = scenes[i - 1]["end_time"]
                candidates = [t for t in seg_starts if t >= prev_end]
                if candidates:
                    scene["start_time"] = min(candidates, key=lambda t: abs(t - scene["start_time"]))
                else:
                    scene["start_time"] = prev_end

            # Find nearest segment end
            if i == len(scenes) - 1:
                scene["end_time"] = duration
            else:
                min_end = scene["start_time"] + min_dur
                candidates = [t for t in seg_ends if t >= min_end]
                if candidates:
                    scene["end_time"] = min(candidates, key=lambda t: abs(t - scene["end_time"]))
                else:
                    scene["end_time"] = min_end

            scene["duration"] = round(scene["end_time"] - scene["start_time"], 3)

        return scenes

    def _distribute_proportionally(
        self, scenes: List[Dict], duration: float
    ) -> List[Dict]:
        """Distribute scene durations proportionally based on words/duration."""
        weights = []
        for s in scenes:
            text = s.get("transcript_text", "") or s.get("narration_text", "")
            words = len(text.split()) if text else 0
            if words > 0:
                weights.append(float(words))
            else:
                weights.append(float(s.get("duration", 1.0) or 1.0))

        total_weight = sum(weights)
        if total_weight <= 0:
            weights = [1.0] * len(scenes)
            total_weight = float(len(scenes))

        cursor = 0.0
        for i, scene in enumerate(scenes):
            scene["start_time"] = round(cursor, 3)
            if i == len(scenes) - 1:
                scene["end_time"] = round(duration, 3)
            else:
                dur = (weights[i] / total_weight) * duration
                scene["end_time"] = round(cursor + dur, 3)
            scene["duration"] = round(scene["end_time"] - scene["start_time"], 3)
            cursor = scene["end_time"]

        return scenes

    def _enforce_coverage(
        self, scenes: List[Dict], duration: float, min_duration: float = 1.5
    ) -> List[Dict]:
        """Fix small gaps/overlaps between consecutive scenes while ensuring sensible shot pacing."""
        n = len(scenes)
        if n == 1:
            scenes[0]["start_time"] = 0.0
            scenes[0]["end_time"] = round(duration, 3)
            scenes[0]["duration"] = round(duration, 3)
            return scenes

        scenes[0]["start_time"] = 0.0
        min_scene_dur = min(min_duration, duration / n if n > 0 else min_duration)

        for i in range(n - 1):
            target_boundary = scenes[i + 1]["start_time"]
            min_bound = scenes[i]["start_time"] + min_scene_dur
            max_bound = duration - (n - 1 - i) * min_scene_dur

            if min_bound > max_bound:
                boundary = (min_bound + max_bound) / 2
            else:
                boundary = max(min_bound, min(target_boundary, max_bound))

            scenes[i]["end_time"] = round(boundary, 3)
            scenes[i]["duration"] = round(scenes[i]["end_time"] - scenes[i]["start_time"], 3)
            scenes[i + 1]["start_time"] = scenes[i]["end_time"]

        scenes[-1]["end_time"] = round(duration, 3)
        scenes[-1]["duration"] = round(scenes[-1]["end_time"] - scenes[-1]["start_time"], 3)

        return scenes

    def _validate(self, scenes: List[Dict], duration: float) -> None:
        """Raise if scenes are still invalid after alignment."""
        for i, scene in enumerate(scenes):
            if scene["duration"] <= 0:
                raise ValueError(
                    f"Scene {scene.get('scene_id', i)} has non-positive duration: {scene['duration']}"
                )

        if abs(scenes[0]["start_time"]) > 0.1:
            raise ValueError(f"First scene starts at {scenes[0]['start_time']}, not 0")

        final_end = scenes[-1]["end_time"]
        if abs(final_end - duration) > self.DURATION_TOLERANCE:
            raise ValueError(
                f"Last scene ends at {final_end:.2f}s but narration duration is {duration:.2f}s"
            )

        for i in range(len(scenes) - 1):
            gap = scenes[i + 1]["start_time"] - scenes[i]["end_time"]
            if abs(gap) > self.GAP_TOLERANCE:
                raise ValueError(
                    f"Gap of {gap:.3f}s between scene {i} and {i+1}"
                )
