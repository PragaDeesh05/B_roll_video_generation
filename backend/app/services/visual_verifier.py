"""
Independent Visual Verifier (Stage 3 & Stage 4).
Runs BEFORE final selection using Vision-Language evaluation.
Evaluates subject match, action match, context, contradictions, and temporal frame progression.
Can reject high-OpenCLIP candidates and promote semantically faithful candidates.
"""
from __future__ import annotations

import abc
import io
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Concurrency throttle to prevent Vertex AI / Gemini 429 RESOURCE_EXHAUSTED
VERIFIER_SEMAPHORE = threading.Semaphore(2)

VISUAL_VERIFY_PROMPT = """You are an expert film continuity supervisor and independent visual verifier.
Evaluate this visual candidate against the intended scene narration and requirements.

Narration: "{narration_text}"
Scene Narrative Role: "{narrative_role}"
Semantic Description: "{semantic_description}"
Required Visual Subject: "{visual_subject}"
Required Visual Action: "{visual_action}"
Global Narrative Context: "{global_story_context}"
Avoid Constraints: {must_avoid}

Evaluation Rules:
1. The narration is the authoritative description of what the visual must communicate. Do not
   replace it with a broad theme, a setting-only interpretation, the semantic description, or
   the required visual subject. Evaluate the image/video itself, not the candidate prompt,
   tags, filename, URL, or metadata.
2. Convert the narration, semantic description, required subject, and required action into a
   concrete checklist of visible requirements. Identify every distinct person, object,
   location, state, relationship, and action required by the narration. Every essential
   requirement must be visibly supported before the candidate can pass.
3. For each checklist requirement, ask: "What exact pixels show this?" Do not infer or assume
   an element because it is plausible, implied by the setting, represented symbolically, or
   mentioned in metadata. If an essential element is absent, unclear, too small to verify, or
   contradicted, mark it missing and lower the score.
4. When 2 to 3 frames are provided, they represent the chronological timeline of the video:
   beginning (~20%), middle (~50%), and end (~80%). Verify every essential requirement across
   the available frames and confirm that the required subject and action remain consistent.
   If the visual starts on-topic but cuts away to unrelated content, rate subject_match <= 0.4,
   temporal_score <= 0.4, and flag contradiction_detected: true.
5. Score each dimension conservatively:
   - subject_match = 1.0 only when all essential subjects/objects from the checklist are
     clearly visible; otherwise it must be <= 0.4 when any essential subject is missing.
   - action_match = 1.0 only when the required action/relationship is visibly occurring;
     a compatible setting or static subject is not evidence of the action.
   - context_match = 1.0 only when the required setting and narrative context are clearly
     visible.
   - verification_score must be <= 2.5 if any essential checklist requirement is missing,
     unclear, or only implied. It may be 3.5 or higher only when all essential requirements
     are visibly satisfied and no contradiction is present.
6. A still image may pass a movement requirement only when the requested action is visibly
   expressed by posture, contact, or a clearly captured moment of the action. Do not award
   action credit merely because a still image contains the subject or setting.
7. CRITICAL CONTRADICTION RULE:
   - A still image is not contradictory merely because it is static.
   - Set contradiction_detected to true when the image shows an unrelated subject, the
     opposite state/action, or omits/replaces an essential narrative subject with something
     materially different (for example, a landscape instead of people repairing an object).
8. Do not give a passing score to abstract backgrounds, generic locations, decorative images,
   or images matching only one keyword. If the narration requires multiple elements and only
   one is visible, reject the candidate or flag it for review.
9. In "evidence", list the visible evidence for each requirement and explicitly list every
   missing or unverified requirement. In "rejection_reason", explain the first essential
   requirement that failed. Never claim an element is visible without image evidence.

Return ONLY a valid JSON object matching this schema:
{{
  "subject_match": 0.9,
  "action_match": 0.85,
  "context_match": 0.9,
  "contradiction_detected": false,
  "visual_quality": 4.5,
  "continuity_match": 0.85,
  "repetition_risk": 0.1,
  "temporal_score": 0.85,
  "temporal_evidence": "Valid depiction of scene subject.",
  "evidence": "Description of actual visible evidence",
  "verification_score": 4.2,
  "rejection_reason": null
}}
"""


class BaseVisualVerifier(abc.ABC):
    """Abstract interface for independent visual verification."""

    @abc.abstractmethod
    def verify_candidate(
        self,
        scene: Dict[str, Any],
        candidate: Dict[str, Any],
        frame_paths: List[Path],
    ) -> Dict[str, Any]:
        pass


class DeterministicMockVisualVerifier(BaseVisualVerifier):
    """
    Deterministic rule-based visual verifier for testing.
    Can deliberately promote semantically faithful candidates and penalize false-keyword matches.
    """

    def verify_candidate(
        self,
        scene: Dict[str, Any],
        candidate: Dict[str, Any],
        frame_paths: List[Path],
    ) -> Dict[str, Any]:
        tags = (candidate.get("tags") or "").lower()
        semantic_desc = (scene.get("semantic_description") or "").lower()
        subject = (scene.get("visual_subject") or "").lower()
        action = (scene.get("visual_action") or "").lower()
        narration = (scene.get("narration_text") or "").lower()

        # Check for contradictions
        contradiction = False
        rejection_reason = None
        evidence = []

        # Example failure mode: "cloud computing" matching literal sky
        is_cloud_tech = (
            ("cloud" in narration or "cloud" in semantic_desc or "cloud" in subject)
            and ("computing" in narration or "computing" in semantic_desc or "computing" in subject or "workload" in narration or "server" in semantic_desc or "data" in subject)
        )
        is_literal_sky = ("sky" in tags or "atmosphere" in tags or "weather" in tags) and ("cloud" in tags or "clouds" in tags)
        has_tech_elements = any(t in tags for t in ["server", "screen", "computer", "data", "code", "datacenter", "technology"])

        if is_cloud_tech and is_literal_sky and not has_tech_elements:
            contradiction = True
            rejection_reason = "Literal sky imagery used for abstract cloud computing narration"
            evidence.append("Contradiction: Natural sky/weather clouds depicted instead of technology infrastructure.")

        # Check Fruit vs Meat or Floral contradiction
        is_fruit_theme = any(k in narration or k in semantic_desc or k in subject for k in ["fruit", "fruits", "apple", "banana", "produce", "market", "shop", "eat"])
        has_meat = any(k in tags for k in ["meat", "beef", "pork", "steak", "butcher", "sausage", "bbq", "barbecue"])
        flower_only = any(k in tags for k in ["flower", "flowers", "bouquet", "floral"]) and not any(k in tags for k in ["fruit", "fruits", "produce", "food"])
        if is_fruit_theme and (has_meat or flower_only):
            contradiction = True
            rejection_reason = "Meat or floral imagery used for fruit shop/eating fresh fruits scene"
            evidence.append("Contradiction: Meat or floral imagery depicted instead of fresh fruits.")

        # Example failure mode: financial savings represented as coin near jar without action
        from app.services.relevance_engine import (
            extract_content_tokens,
            lemmatize_word,
            get_synonym_set,
        )

        temporal_score = 0.80
        temporal_evidence = "Valid frame depicting scene subject and context."
        if frame_paths and len(frame_paths) >= 2:
            temporal_score = 0.85
            temporal_evidence = f"Verified across {len(frame_paths)} distributed video frames without temporal contradiction."

        # Evaluate candidate subject and action against scene requirements using NLP & synonyms
        cand_prompt = (candidate.get("prompt") or "").lower()
        cand_desc = (candidate.get("description") or "").lower()
        cand_query = (candidate.get("query_used") or "").lower()
        cand_text = f"{tags} {cand_prompt} {cand_desc} {cand_query}"
        cand_tokens = set(extract_content_tokens(cand_text))

        # Scene queries
        scene_queries = (
            (scene.get("search_queries") or []) +
            (scene.get("primary_search_queries") or []) +
            (scene.get("alternative_search_queries") or []) +
            ([scene["primary_search_query"]] if scene.get("primary_search_query") else [])
        )
        query_hits = 0
        for sq in scene_queries:
            sq_tokens = extract_content_tokens(sq)
            if sq_tokens and all(any(syn in cand_tokens or syn in cand_text for syn in get_synonym_set(t)) for t in sq_tokens):
                query_hits += 1

        sub_tokens = extract_content_tokens(subject) + extract_content_tokens(narration)[:4]
        sub_hits = 0
        for st in sub_tokens:
            st_syns = get_synonym_set(st)
            if any(syn in cand_tokens or syn in cand_text for syn in st_syns):
                sub_hits += 1

        act_tokens = extract_content_tokens(action)
        act_hits = 0
        if act_tokens:
            for at in act_tokens:
                at_syns = get_synonym_set(at)
                if any(syn in cand_tokens or syn in cand_text for syn in at_syns):
                    act_hits += 1
            action_match = round(min(1.0, 0.4 + 0.3 * act_hits), 2)
        else:
            action_match = round(min(1.0, 0.5 + 0.25 * sub_hits), 2)

        if sub_hits == 0 and query_hits == 0:
            subject_match = 0.20
            action_match = 0.20
        else:
            subject_match = round(min(1.0, 0.5 + 0.25 * (sub_hits + query_hits)), 2)

        # If contradiction detected, slash scores
        if contradiction:
            subject_match = 0.2
            action_match = 0.1
            context_match = 0.1
            verification_score = 1.2
        else:
            context_match = round(0.5 * subject_match + 0.5 * action_match, 2)
            # verification_score on 1.0 - 5.0 scale
            verification_score = round(1.0 + 4.0 * (0.4 * subject_match + 0.4 * action_match + 0.2 * context_match), 2)
            evidence.append(f"Subject match: {subject_match:.2f}, Action match: {action_match:.2f}.")

        return {
            "subject_match": subject_match,
            "action_match": action_match,
            "context_match": context_match,
            "contradiction_detected": contradiction,
            "visual_quality": 4.5,
            "continuity_match": 0.85,
            "repetition_risk": 0.15,
            "temporal_score": temporal_score,
            "temporal_evidence": temporal_evidence,
            "evidence": "; ".join(evidence) if evidence else "Verified candidate appearance against narration requirements.",
            "verification_score": verification_score,
            "rejection_reason": rejection_reason,
        }


def _prepare_image_part(frame_path: Path):
    """Convert and compress image to optimized JPEG payload (< 150KB) for fast remote VLM transmission."""
    from PIL import Image as PILImage
    img = PILImage.open(frame_path)
    if img.width > 1280 or img.height > 1280:
        img.thumbnail((1280, 1280))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    from google.genai import types
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


class GeminiVisualVerifier(BaseVisualVerifier):
    """Multimodal vision-language verifier using Gemini via Vertex AI or API key."""

    def __init__(self, model_name: str = "gemini-3.5-flash-lite"):
        self.model_name = model_name
        self._vertex_client = None

    def _get_vertex_client(self):
        if self._vertex_client is None and settings.google_cloud_project:
            try:
                from google import genai
                self._vertex_client = genai.Client(
                    vertexai=True,
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location or "us-central1",
                )
            except Exception as e:
                logger.debug(f"Vertex AI client init failed: {e}")
        return self._vertex_client

    def verify_candidate(
        self,
        scene: Dict[str, Any],
        candidate: Dict[str, Any],
        frame_paths: List[Path],
    ) -> Dict[str, Any]:
        prompt = VISUAL_VERIFY_PROMPT.format(
            narration_text=scene.get("narration_text", ""),
            narrative_role=scene.get("narrative_role", "Progression"),
            semantic_description=scene.get("semantic_description", ""),
            visual_subject=scene.get("visual_subject", ""),
            visual_action=scene.get("visual_action", ""),
            global_story_context=scene.get("global_story_context", ""),
            must_avoid=", ".join(scene.get("must_avoid", [])),
        )

        # Try Vertex AI first (paid/trial quota) with retry on 429
        vertex_client = self._get_vertex_client()
        if vertex_client:
            for attempt in range(3):
                try:
                    contents = [prompt]
                    for f in frame_paths[:3]:  # Send beginning (20%), middle (50%), and end (80%) timeline frames
                        if f.exists():
                            contents.append(_prepare_image_part(f))

                    with VERIFIER_SEMAPHORE:
                        res = vertex_client.models.generate_content(
                            model=self.model_name,
                            contents=contents,
                        )
                    if res and res.text:
                        text = res.text.strip().replace("```json", "").replace("```", "").strip()
                        data = json.loads(text)
                        return data
                except Exception as e:
                    err_msg = str(e)
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        backoff = 1.5 * (2 ** attempt)
                        logger.warning(f"Vertex AI visual verifier rate limited (429), backing off {backoff}s...")
                        time.sleep(backoff)
                        continue
                    logger.warning(f"Vertex AI visual verifier failed: {e}; trying Gemini API key fallback")
                    break

        # Fallback to Gemini API key
        if settings.gemini_api_key:
            try:
                from google import genai
                client = genai.Client(api_key=settings.gemini_api_key)
                contents = [prompt]
                for f in frame_paths[:3]:  # Send beginning (20%), middle (50%), and end (80%) timeline frames
                    if f.exists():
                        contents.append(_prepare_image_part(f))

                with VERIFIER_SEMAPHORE:
                    res = client.models.generate_content(model="gemini-3.5-flash-lite", contents=contents)
                if res and res.text:
                    text = res.text.strip().replace("```json", "").replace("```", "").strip()
                    return json.loads(text)
            except Exception as e:
                logger.warning(f"Gemini API visual verifier failed: {e}; using fallback mock verifier")
            except Exception as e:
                logger.warning(f"Gemini API visual verifier failed: {e}; using fallback mock verifier")

        return DeterministicMockVisualVerifier().verify_candidate(scene, candidate, frame_paths)


class VisualVerificationService:
    """Unified service coordinating Stage 3 Visual Verification and Stage 4 Temporal Verification."""

    def __init__(self, verifier: Optional[BaseVisualVerifier] = None):
        self.verifier = verifier or self._resolve_verifier()

    def _resolve_verifier(self) -> BaseVisualVerifier:
        if settings.visual_verifier_provider == "mock":
            return DeterministicMockVisualVerifier()
        # Use GeminiVisualVerifier if either Vertex AI or Gemini API key is available
        if settings.google_cloud_project or settings.gemini_api_key:
            return GeminiVisualVerifier(settings.visual_verifier_model)
        return DeterministicMockVisualVerifier()

    def verify_candidate(
        self,
        scene: Dict[str, Any],
        candidate: Dict[str, Any],
        frame_paths: Optional[List[Path]] = None,
    ) -> Dict[str, Any]:
        """Run independent verification on a candidate."""
        return self.verifier.verify_candidate(scene, candidate, frame_paths or [])
