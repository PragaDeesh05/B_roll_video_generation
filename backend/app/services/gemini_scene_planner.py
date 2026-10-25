"""
Gemini Context-Aware Scene Planner.
Implements the 3-Stage Full-Video Narrative Understanding Pipeline:
  - Stage A: Global Narrative Analysis (theme, tone, entities, motifs, constraints)
  - Stage B: Narrative Beat Planning (logical progression through distinct story functions)
  - Stage C: Context-Aware Scene Planning (full Section 7 schema, rolling memory, continuity)
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_genai = None


def _get_genai():
    global _genai
    if _genai is None:
        import google.generativeai as genai
        _genai = genai
    return _genai


GLOBAL_NARRATIVE_PROMPT = """You are a senior documentary film director and narrative analyst.
Analyze the following video narration script and extract its full narrative architecture.

Return ONLY a valid JSON object matching this schema:
{{
  "overall_topic": "string",
  "central_message": "string",
  "intended_audience": "string",
  "narrative_structure": "string",
  "tone": "string",
  "chronology": "string",
  "major_claims": ["string"],
  "named_entities": ["string"],
  "important_objects": ["string"],
  "recurring_visual_motifs": ["string"],
  "visual_style": "string",
  "established_facts": ["string"],
  "causal_relationships": ["string"],
  "emotional_progression": ["string"],
  "beginning_role": "string",
  "middle_role": "string",
  "ending_role": "string",
  "visual_repetition_constraints": ["string"],
  "sensitive_content_constraints": ["string"]
}}

Style preferences: {style_preferences}
Avoid constraints: {avoid_constraints}

Script:
\"\"\"{transcript}\"\"\"
"""


BEAT_PLANNING_PROMPT = """You are a story editor. Given this global narrative analysis and transcript,
divide the video into logical narrative beats representing the story progression.
Each beat must perform a distinct narrative function (e.g. Problem Definition, Daily Recurring Mechanism,
Long-term Accumulation, Compounding Acceleration, Final Security / Resolution).

Global Narrative Summary:
{global_summary_json}

Return ONLY a valid JSON array of beat objects:
[
  {{
    "beat_id": "beat_01",
    "beat_name": "string",
    "narrative_role": "string",
    "core_idea": "string",
    "suggested_visual_focus": "string",
    "avoid_repetition_of": "string"
  }}
]

Script:
\"\"\"{transcript}\"\"\"
"""


SCENE_PLAN_PROMPT = """You are a master cinematographer and scene planner.
Given the timed narration transcript, global narrative analysis, and beat plan,
produce a JSON array of scene objects matching the mandatory Section 7 schema.

Style preferences: {style_preferences}
Avoid constraints: {avoid_constraints}

Rules:
1. STRICT 1-TO-1 SCENE CORRESPONDENCE (ABSOLUTELY ZERO NARRATION DUPLICATION):
   - Every scene MUST correspond to a unique, distinct sentence or clause of the narration transcript.
   - The number of scenes must match the number of logical sentences/segments in the transcript (e.g. 4 sentences in transcript = EXACTLY 4 scenes; 5 sentences = 5 scenes).
   - NEVER create multiple scenes for the same sentence. NEVER repeat, clone, or duplicate narration_text across scenes.
   - Each sentence must appear in narration_text ONCE and ONLY ONCE.
   - Concatenating all scene narration_text values in order MUST reconstruct the transcript verbatim, with ZERO duplicate sentences, ZERO repeated clauses, and ZERO repeated words.
   - Timestamps and durations must cover [0.0, {narration_duration}s] with no gaps or overlaps, strictly matching the timed transcript intervals.
2. NARRATION-FIRST VISUAL DECOMPOSITION (MANDATORY):
   - Treat each scene's narration_text as the authoritative source of visual requirements.
   - Before choosing a setting or search query, identify every concrete entity, character, object,
     quantity, state, relationship, and action explicitly stated or unambiguously required by the
     narration segment.
   - Preserve all essential narrative elements in the same scene. Do not replace a required
     character or event with a related location, mood, symbol, or broad theme. For example,
     narration about Humpty Dumpty falling requires a visible egg character on a wall and a
     visually communicable fall or aftermath; a wall by itself is insufficient.
   - For narration describing an interaction or event, the visual_action must describe the
     visible interaction, not merely camera movement. The environment is secondary context.
   - Populate must_include with one literal, checkable item for every essential requirement.
     Populate relevant_objects with the concrete entities that must appear on screen.
   - If an abstract concept cannot be shown literally, choose a practical real-world depiction
     that preserves the exact meaning, and state any unavoidable limitation in warnings. Never
     invent an unrelated metaphor or silently omit a required element.
   - Ensure image_generation_prompt, visual_subject, visual_action, search_queries, and
     semantic_description all agree with narration_text and must_include.
2. Search Queries & Representations:
   - search_queries: Provide 3 to 5 diverse, concrete, descriptive 2-to-4 word search queries describing real, physical visible subjects for Pixabay stock library (e.g. "glacier melting waterfall", "farmer inspecting wheat field", "stock market chart screen"). For abstract concepts, generate practical visual alternatives. Never use vague terms like 'video' or 'concept'.
   - primary_search_queries: The first 2 queries from search_queries.
   - alternative_search_queries: The remaining 1 to 3 queries from search_queries.
   - semantic_description: Explain what visual communicates in context of narration (NOT a search keyword).
   - alternative_visual_descriptions: Array of 2 alternative visual angles / compositions for the scene.
   - visual_subject: The primary physical visible subject in the shot. Must be directly, practically, and realistically relevant to the real-world topic of the scene narration (e.g. for finance/money: "smartphone budgeting app", "savings jar and coins", "investment growth chart", "clean home office desk with financial documents"), NOT an obscure or unrelated metaphor.
   - image_generation_prompt: Rich, photorealistic or cinematic composition instructions for AI image generation (Gemini 2.5 Flash Image / Imagen).
     * MANDATORY DIRECT RELEVANCE: The scene prompt MUST realistically, practically, and directly reflect the real-world domain and specific meaning of the narration.
     * FOR FINANCE & MONEY MANAGEMENT: Depict modern digital banking dashboards, budgeting apps on sleek smartphones or laptops, clean office desks with calculators, organized savings jars with coins, upward-trending growth charts, debit cards, and realistic financial planning tools.
     * PROHIBITED ODD METAPHORS: NEVER generate bizarre, strained, or irrelevant allegorical metaphors (e.g., NEVER use tree roots in soil for money savings, bricklaying masonry for investing, antique pirate compasses for income, medieval bank vaults for emergency funds, or balance scales with rustic bread for budgeting). The visual MUST feel natural, modern, and directly related to the narration topic.
     * COMPOSITION: Specify framing (e.g. close-up flat lay, macro shot, over-the-shoulder), lighting (soft natural morning sunlight, clean diffused lighting), depth of field, and crisp 4k aesthetic. No watermarks, no logos, no distorted elements.
   - requires_real_faces: Set to true only if this scene specifically depicts human faces, portraits, characters, students, children, or workers. Set to false if it depicts objects, devices, technology, nature, or hands without human faces.
3. Prevent visual repetition: Do NOT use the same visual metaphor across multiple scenes unless required for motif continuity.
   - Treat the complete scene list as one continuous film, not as independent prompts.
   - Create a global visual uniqueness ledger before finalizing: record each scene's main subject,
     setting, action, camera composition, and narrative purpose, then compare every scene against
     all earlier scenes.
   - No two scenes may reuse the same primary visual subject plus the same action, setting, or
     composition. Do not reuse the opening scene's visual at the end as a recap, summary, or
     decorative closing shot unless the narration explicitly requires a literal return.
   - The final scene MUST introduce a distinct conclusion-specific visual that represents the
     final narration segment. It must not repeat, closely paraphrase, or visually substitute for
     scene 1 or any earlier scene.
   - If the narration revisits an earlier topic, show a new state, consequence, result, scale,
     or point of view that is visibly different; never copy the earlier scene's subject/action
     combination.
   - Set visual_diversity_role to a unique function in the story (for example: introduction,
     mechanism, evidence, consequence, comparison, or conclusion), and do not assign the same
     role and visual treatment to multiple scenes.
4. For action-based scenes, specify temporal_requirements (visible movement, progression over time).
5. NON-HUMAN & REAL FACES ENFORCEMENT:
   If avoid_constraints includes "human", "people", "faces", "human faces", or similar:
   - Strictly avoid visible human faces, portraits, or identifiable people.
   - You CAN and SHOULD show hands performing purposeful actions (e.g., hands typing on a laptop, hands holding a pen, hands organizing savings jars, hands using a smartphone app) or clean inanimate objects, modern technology, devices, and workspaces.
   - DO NOT replace modern topics with primitive nature or ancient metaphors (like tree roots, rocks, or antique compasses) unless the narration is actually about nature or history.
   - Set "requires_real_faces": false for ALL scenes so that Pixabay stock footage is used as the primary footage provider!

6. MULTILINGUAL & CULTURAL CONSISTENCY (English, Hindi, Tamil):
   - Language of narration: {narration_language}
   - Original Script: Keep "narration_text" in the EXACT original language and native script (Hindi Devanagari, Tamil, or English). Do NOT translate narration text.
   - Subtitle Integrity: Ensure native Unicode characters are preserved accurately for subtitles and caption rendering.
   - English Visual Search Queries: Even if narration is in Hindi or Tamil, ALL "search_queries", "primary_search_queries", and "alternative_search_queries" MUST be concise 2-3 word ENGLISH terms describing literal visible physical objects for stock engines (e.g., "clay cooking pot", "sunlit paddy field", "farmer inspecting crops", "market fruits stall"). Stock footage engines index in English.
   - Cultural Preservation: Preserve cultural context, intent, and authentic visual meaning. For Tamil Pongal, focus on traditional clay pots boiling sweet pongal, fresh sugarcane, and floor kolam. For Diwali, focus on warm glowing clay diyas and festive illumination. Do NOT incorrectly map Indian cultural concepts to generic Western tropes.

7. SENSIBLE PACING & SHOT DURATIONS:
   - Each shot duration is defined by its corresponding narration segment (typically 4 to 12 seconds per scene).
   - Enforce MINIMUM shot duration of {min_scene_duration} seconds. Avoid rapid 0.5s clips or flashing cuts.
   - Do NOT artificially split a single sentence into multiple redundant scenes. One scene per sentence provides optimal documentary pacing.
8. FINAL SCENE-BY-SCENE SELF-CHECK:
   - For every scene, mentally read only narration_text and must_include. Confirm that the
     proposed visual would let an independent reviewer point to visible evidence for every item.
   - Reject your own scene plan and regenerate that scene if it contains only a generic location
     while the narration requires a named character, object, action, failure, transformation,
     or relationship.
   - Do not claim that a camera movement, atmosphere, or visual mood represents a narrative
     event unless the event itself is visibly depicted.
   - Perform a final global duplicate audit after the per-scene checks: compare scene 1 with
     every later scene, especially the last scene, and reject/regenerate any scene whose main
     subject, action, setting, and composition substantially repeat an earlier scene.
   - Confirm that the ending advances or concludes the story rather than restarting the
     introduction. If the last scene resembles the first scene, redesign the last scene before
     returning JSON.

Global Narrative Context:
{global_summary_json}

Narrative Beats:
{beat_plan_json}

Timed Transcript:
{timed_transcript}

Return ONLY a valid JSON array matching this schema:
[
  {{
    "scene_id": "scene_001",
    "scene_index": 0,
    "narration_text": "...",
    "start_time": 0.0,
    "end_time": 5.0,
    "duration": 5.0,
    "previous_scene_summary": "...",
    "global_story_context": "...",
    "narrative_beat": "...",
    "narrative_role": "...",
    "semantic_description": "...",
    "alternative_visual_descriptions": ["description 1", "description 2"],
    "intended_visual_meaning": "...",
    "visual_subject": "...",
    "visual_action": "...",
    "requires_real_faces": false,
    "environment": "...",
    "relevant_objects": ["..."],
    "object_state": "...",
    "composition": "...",
    "shot_type": "wide",
    "camera_angle": "eye-level",
    "camera_movement": "subtle push-in",
    "lighting": "natural warm",
    "mood": "optimistic",
    "style": "cinematic documentary",
    "temporal_requirements": "continuous steady motion demonstrating growth",
    "visual_continuity_requirements": "...",
    "visual_diversity_role": "...",
    "must_include": ["..."],
    "must_avoid": ["brand logos", "watermarks"],
    "primary_search_queries": ["query1", "query2"],
    "alternative_search_queries": ["query3"],
    "search_queries": ["query1", "query2", "query3"],
    "image_generation_prompt": "Clean documentary shot of ...",
    "warnings": []
  }}
]
"""

UNIFIED_SCENE_PLAN_PROMPT = """You are a master story editor, cinematographer, and scene planner.
Given the timed narration transcript, produce a unified, comprehensive plan covering:
1. Global Narrative Analysis
2. Narrative Beat Progression
3. Per-Scene Cinematographic Plan with Tag-Optimized Pixabay Search Queries

Style preferences: {style_preferences}
Avoid constraints: {avoid_constraints}

Rules:
1. STRICT 1-TO-1 SCENE CORRESPONDENCE (ABSOLUTELY ZERO NARRATION DUPLICATION):
   - Every scene MUST correspond to a unique, distinct sentence or clause of the narration transcript.
   - The number of scenes must match the number of logical sentences/segments in the transcript (e.g. 4 sentences in transcript = EXACTLY 4 scenes; 5 sentences = 5 scenes).
   - NEVER create multiple scenes for the same sentence. NEVER repeat, clone, or duplicate narration_text across scenes.
   - Each sentence must appear in narration_text ONCE and ONLY ONCE.
   - Concatenating all scene narration_text values in order MUST reconstruct the transcript verbatim, with ZERO duplicate sentences, ZERO repeated clauses, and ZERO repeated words.
   - Timestamps and durations must cover [0.0, {narration_duration}s] with no gaps or overlaps, strictly matching the timed transcript intervals.
2. NARRATION-FIRST VISUAL DECOMPOSITION (MANDATORY):
   - Treat each scene's narration_text as the authoritative source of visual requirements.
   - Before choosing a setting or search query, identify every concrete entity, character, object,
     quantity, state, relationship, and action explicitly stated or unambiguously required by the
     narration segment.
   - Preserve all essential narrative elements in the same scene. Do not replace a required
     character or event with a related location, mood, symbol, or broad theme. For example,
     narration about Humpty Dumpty falling requires a visible egg character on a wall and a
     visually communicable fall or aftermath; a wall by itself is insufficient.
   - For narration describing an interaction or event, the visual_action must describe the
     visible interaction, not merely camera movement. The environment is secondary context.
   - Populate must_include with one literal, checkable item for every essential requirement.
     Populate relevant_objects with the concrete entities that must appear on screen.
   - If an abstract concept cannot be shown literally, choose a practical real-world depiction
     that preserves the exact meaning, and state any unavoidable limitation in warnings. Never
     invent an unrelated metaphor or silently omit a required element.
   - Ensure image_generation_prompt, visual_subject, visual_action, search_queries, and
     semantic_description all agree with narration_text and must_include.
2. Search Queries & Representations:
   - search_queries: Provide 3 to 5 diverse, concrete, descriptive 2-to-4 word search queries describing real, physical visible subjects for Pixabay stock library (e.g. "glacier melting waterfall", "farmer inspecting wheat field", "stock market chart screen"). For abstract concepts, generate practical visual alternatives. Never use vague terms like 'video' or 'concept'.
   - primary_search_queries: The first 2 queries from search_queries.
   - alternative_search_queries: The remaining 1 to 3 queries from search_queries.
   - semantic_description: Explain what visual communicates in context of narration (NOT a search keyword).
   - alternative_visual_descriptions: Array of 2 alternative visual angles / compositions for the scene.
   - visual_subject: The primary physical visible subject in the shot. Must be directly, practically, and realistically relevant to the real-world topic of the scene narration (e.g. for finance/money: "smartphone budgeting app", "savings jar and coins", "investment growth chart", "clean home office desk with financial documents"), NOT an obscure or unrelated metaphor.
   - image_generation_prompt: Rich, photorealistic or cinematic composition instructions for AI image generation (Gemini 2.5 Flash Image / Imagen).
     * MANDATORY DIRECT RELEVANCE: The scene prompt MUST realistically, practically, and directly reflect the real-world domain and specific meaning of the narration.
     * FOR FINANCE & MONEY MANAGEMENT: Depict modern digital banking dashboards, budgeting apps on sleek smartphones or laptops, clean office desks with calculators, organized savings jars with coins, upward-trending growth charts, debit cards, and realistic financial planning tools.
     * PROHIBITED ODD METAPHORS: NEVER generate bizarre, strained, or irrelevant allegorical metaphors (e.g., NEVER use tree roots in soil for money savings, bricklaying masonry for investing, antique pirate compasses for income, medieval bank vaults for emergency funds, or balance scales with rustic bread for budgeting). The visual MUST feel natural, modern, and directly related to the narration topic.
     * COMPOSITION: Specify framing (e.g. close-up flat lay, macro shot, over-the-shoulder), lighting (soft natural morning sunlight, clean diffused lighting), depth of field, and crisp 4k aesthetic. No watermarks, no logos, no distorted elements.
   - requires_real_faces: Set to true only if this scene specifically depicts human faces, portraits, characters, students, children, or workers. Set to false if it depicts objects, devices, technology, nature, or hands without human faces.
3. Prevent visual repetition: Do NOT use the same visual metaphor across multiple scenes unless required for motif continuity.
   - Treat the complete scene list as one continuous film, not as independent prompts.
   - Create a global visual uniqueness ledger before finalizing: record each scene's main subject,
     setting, action, camera composition, and narrative purpose, then compare every scene against
     all earlier scenes.
   - No two scenes may reuse the same primary visual subject plus the same action, setting, or
     composition. Do not reuse the opening scene's visual at the end as a recap, summary, or
     decorative closing shot unless the narration explicitly requires a literal return.
   - The final scene MUST introduce a distinct conclusion-specific visual that represents the
     final narration segment. It must not repeat, closely paraphrase, or visually substitute for
     scene 1 or any earlier scene.
   - If the narration revisits an earlier topic, show a new state, consequence, result, scale,
     or point of view that is visibly different; never copy the earlier scene's subject/action
     combination.
   - Set visual_diversity_role to a unique function in the story (for example: introduction,
     mechanism, evidence, consequence, comparison, or conclusion), and do not assign the same
     role and visual treatment to multiple scenes.
4. For action-based scenes, specify temporal_requirements (visible movement, progression over time).
5. NON-HUMAN & REAL FACES ENFORCEMENT:
   If avoid_constraints includes "human", "people", "faces", "human faces", or similar:
   - Strictly avoid visible human faces, portraits, or identifiable people.
   - You CAN and SHOULD show hands performing purposeful actions (e.g., hands typing on a laptop, hands holding a pen, hands organizing savings jars, hands using a smartphone app) or clean inanimate objects, modern technology, devices, and workspaces.
   - Set "requires_real_faces": false for ALL scenes so that Pixabay stock footage is used as the primary footage provider!
6. MULTILINGUAL & CULTURAL CONSISTENCY (English, Hindi, Tamil):
   - Language of narration: {narration_language}
   - Original Script: Keep "narration_text" in the EXACT original language and native script (Hindi Devanagari, Tamil, or English). Do NOT translate narration text.
   - English Visual Search Queries: Even if narration is in Hindi or Tamil, ALL "search_queries", "primary_search_queries", and "alternative_search_queries" MUST be concise 2-3 word ENGLISH terms describing literal visible physical objects for stock engines.
7. SENSIBLE PACING & SHOT DURATIONS:
   - Each shot duration is defined by its corresponding narration segment (typically 4 to 12 seconds per scene).
   - Enforce MINIMUM shot duration of {min_scene_duration} seconds.
   - Do NOT artificially split a single sentence into multiple redundant scenes. One scene per sentence provides optimal documentary pacing.
8. FINAL SCENE-BY-SCENE SELF-CHECK:
   - For every scene, mentally read only narration_text and must_include. Confirm that the
     proposed visual would let an independent reviewer point to visible evidence for every item.
   - Reject your own scene plan and regenerate that scene if it contains only a generic location
     while the narration requires a named character, object, action, failure, transformation,
     or relationship.
   - Do not claim that a camera movement, atmosphere, or visual mood represents a narrative
     event unless the event itself is visibly depicted.
   - Perform a final global duplicate audit after the per-scene checks: compare scene 1 with
     every later scene, especially the last scene, and reject/regenerate any scene whose main
     subject, action, setting, and composition substantially repeat an earlier scene.
   - Confirm that the ending advances or concludes the story rather than restarting the
     introduction. If the last scene resembles the first scene, redesign the last scene before
     returning JSON.

Timed Transcript:
{timed_transcript}

Return ONLY a valid JSON object matching this schema:
{{
  "global_narrative": {{
    "core_conflict": "string",
    "resolution": "string",
    "audience_takeaway": "string",
    "visual_arc_description": "string",
    "pacing": "string",
    "tone": "string",
    "beginning_role": "string",
    "middle_role": "string",
    "ending_role": "string",
    "visual_repetition_constraints": ["string"],
    "sensitive_content_constraints": ["string"]
  }},
  "narrative_beats": [
    {{
      "beat_id": "beat_01",
      "beat_name": "string",
      "narrative_role": "string",
      "core_idea": "string",
      "suggested_visual_focus": "string",
      "avoid_repetition_of": "string"
    }}
  ],
  "scenes": [
    {{
      "scene_id": "scene_001",
      "scene_index": 0,
      "narration_text": "...",
      "start_time": 0.0,
      "end_time": 5.0,
      "duration": 5.0,
      "previous_scene_summary": "...",
      "global_story_context": "...",
      "narrative_beat": "...",
      "narrative_role": "...",
      "semantic_description": "...",
      "alternative_visual_descriptions": ["description 1", "description 2"],
      "intended_visual_meaning": "...",
      "visual_subject": "...",
      "visual_action": "...",
      "requires_real_faces": false,
      "environment": "...",
      "relevant_objects": ["..."],
      "object_state": "...",
      "composition": "...",
      "shot_type": "wide",
      "camera_angle": "eye-level",
      "camera_movement": "subtle push-in",
      "lighting": "natural warm",
      "mood": "optimistic",
      "style": "cinematic documentary",
      "temporal_requirements": "continuous steady motion demonstrating growth",
      "visual_continuity_requirements": "...",
      "visual_diversity_role": "...",
      "must_include": ["..."],
      "must_avoid": ["brand logos", "watermarks"],
      "primary_search_queries": ["query1", "query2"],
      "alternative_search_queries": ["query3"],
      "search_queries": ["query1", "query2", "query3"],
      "image_generation_prompt": "Clean documentary shot of ...",
      "warnings": []
    }}
  ]
}}
"""

RETRY_CORRECTION_PROMPT = (
    "Your previous response was not valid JSON or failed schema validation.\n"
    "Error: {error}\n\n"
    "Please return ONLY a valid JSON array or object matching the schema. No markdown fences.\n"
    "Previous attempt excerpt:\n{previous}\n"
)


class GeminiScenePlanner:
    """Context-aware scene planner implementing Stages A, B, and C."""

    MAX_RETRIES = 3
    RETRY_DELAY = 1.5

    def __init__(self) -> None:
        self._provider = None
        self._mock_mode = True
        self._vertex_client = None

        # Try Vertex AI first (uses gcloud ADC — paid/trial quota, more reliable)
        if settings.google_cloud_project:
            try:
                from google import genai
                self._vertex_client = genai.Client(
                    vertexai=True,
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location or "us-central1",
                )
                self._provider = "vertexai"
                self._mock_mode = False
                logger.info("Using Vertex AI (gcloud ADC) for scene planning")
            except Exception as e:
                logger.warning(f"Vertex AI init failed: {e}")

        # Fallback to Gemini API key
        if self._mock_mode and settings.gemini_api_key:
            try:
                genai = _get_genai()
                genai.configure(api_key=settings.gemini_api_key)
                self._model = genai.GenerativeModel("gemini-3.8-flash")
                self._provider = "gemini"
                self._mock_mode = False
                logger.info("Using Gemini API for scene planning")
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")

        if self._mock_mode and settings.groq_api_key:
            self._provider = "groq"
            self._mock_mode = False
            logger.info("Using Groq API for scene planning")

        if self._mock_mode:
            logger.info("Scene planner initialized in deterministic mock mode.")

    # ── Stage A: Global Narrative Analysis ─────────────────────────────────────

    def analyze_global_narrative(
        self,
        transcript: str,
        style_preferences: Optional[str] = None,
        avoid_constraints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Stage A: Understand full-video context before planning scenes."""
        if self._mock_mode:
            return self._mock_global_analysis(transcript, style_preferences, avoid_constraints)

        prompt = GLOBAL_NARRATIVE_PROMPT.format(
            transcript=transcript,
            style_preferences=style_preferences or "Cinematic documentary, realistic lighting",
            avoid_constraints=", ".join(avoid_constraints or ["watermarks", "brand logos"]),
        )
        try:
            raw = self._call_llm(prompt)
            data = self._clean_and_parse_json(raw)
            if isinstance(data, dict) and "overall_topic" in data:
                if not data.get("visual_repetition_constraints"):
                    data["visual_repetition_constraints"] = [
                        "Do not repeat identical visual subjects across consecutive scenes",
                        "Vary shot types between wide, medium, and close-up views",
                    ]
                return data
        except Exception as e:
            logger.warning(f"Stage A Global analysis failed: {e}; using deterministic fallback")

        return self._mock_global_analysis(transcript, style_preferences, avoid_constraints)

    # ── Stage B: Narrative Beat Planning ───────────────────────────────────────

    def plan_narrative_beats(
        self,
        transcript: str,
        global_summary: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Stage B: Plan functional story progression across beats."""
        if self._mock_mode:
            return self._mock_beat_plan(transcript, global_summary)

        prompt = BEAT_PLANNING_PROMPT.format(
            global_summary_json=json.dumps(global_summary, indent=2),
            transcript=transcript,
        )
        try:
            raw = self._call_llm(prompt)
            data = self._clean_and_parse_json(raw)
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception as e:
            logger.warning(f"Stage B Beat planning failed: {e}; using deterministic fallback")

        return self._mock_beat_plan(transcript, global_summary)

    # ── Stage C: Context-Aware Scene Planning ─────────────────────────────────

    def plan_scenes(
        self,
        transcript: str,
        narration_duration: float,
        segments: Optional[List[Dict]] = None,
        style_preferences: Optional[str] = None,
        avoid_constraints: Optional[List[str]] = None,
        structured_scenes: Optional[List[Dict]] = None,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """
        Complete 3-Stage Pipeline:
          1. Global narrative analysis
          2. Beat plan
          3. Context-aware scene generation with rolling memory
        """
        # If structured scenes provided, adapt them directly with constraints
        if structured_scenes and len(structured_scenes) > 0:
            return self._plan_structured_scenes(
                structured_scenes, narration_duration, style_preferences, avoid_constraints
            )

        # High-Speed Optimization: Single-Prompt Consolidated Narrative & Scene Planning (~20s vs ~90s)
        if not self._mock_mode and getattr(settings, "enable_unified_scene_planning", True):
            try:
                unified_scenes = self._plan_scenes_unified(
                    transcript=transcript,
                    narration_duration=narration_duration,
                    segments=segments,
                    style_preferences=style_preferences,
                    avoid_constraints=avoid_constraints,
                    language=language,
                )
                if unified_scenes and len(unified_scenes) > 0:
                    logger.info(f"Unified scene planning succeeded ({len(unified_scenes)} scenes generated in 1 LLM pass)")
                    return unified_scenes
            except Exception as ue:
                logger.warning(f"Unified scene planning failed ({ue}); falling back to 3-stage sequential planning")

        # Stage A: Global Narrative Analysis
        global_summary = self.analyze_global_narrative(
            transcript, style_preferences, avoid_constraints
        )

        # Stage B: Narrative Beat Planning
        beat_plan = self.plan_narrative_beats(transcript, global_summary)

        if self._mock_mode:
            return self._mock_plan_context_aware(
                transcript, narration_duration, segments, global_summary, beat_plan, avoid_constraints, language=language
            )

        # Stage C: LLM Scene Planning
        timed_transcript = self._build_timed_transcript(transcript, segments)
        prompt = SCENE_PLAN_PROMPT.format(
            narration_duration=narration_duration,
            global_summary_json=json.dumps(global_summary, indent=2),
            beat_plan_json=json.dumps(beat_plan, indent=2),
            timed_transcript=timed_transcript,
            style_preferences=style_preferences or "cinematic documentary",
            avoid_constraints=json.dumps(avoid_constraints) if avoid_constraints else "[]",
            narration_language=language or "en",
            min_scene_duration=getattr(settings, "min_scene_duration_seconds", 1.5),
        )

        previous_response = ""
        last_error = ""

        for attempt in range(self.MAX_RETRIES):
            try:
                if attempt == 0:
                    raw = self._call_llm(prompt)
                else:
                    correction_prompt = RETRY_CORRECTION_PROMPT.format(
                        error=last_error,
                        previous=previous_response[:1500],
                    )
                    raw = self._call_llm(correction_prompt)

                previous_response = raw
                scenes = self._parse_and_validate(raw, narration_duration)
                return scenes
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Scene planning attempt {attempt+1} failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY * (2 ** attempt))

        logger.error("All LLM scene planning attempts failed, using fallback")
        return self._mock_plan_context_aware(
            transcript, narration_duration, segments, global_summary, beat_plan, avoid_constraints
        )

    def _plan_scenes_unified(
        self,
        transcript: str,
        narration_duration: float,
        segments: Optional[List[Dict]] = None,
        style_preferences: Optional[str] = None,
        avoid_constraints: Optional[List[str]] = None,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """
        Consolidated Single-Prompt Narrative & Scene Planning.
        Combines Global Narrative Analysis, Beat Breakdown, and Scene Planning into 1 LLM request.
        """
        timed_transcript = self._build_timed_transcript(transcript, segments)
        prompt = UNIFIED_SCENE_PLAN_PROMPT.format(
            narration_duration=narration_duration,
            timed_transcript=timed_transcript,
            style_preferences=style_preferences or "cinematic documentary",
            avoid_constraints=json.dumps(avoid_constraints) if avoid_constraints else "[]",
            narration_language=language or "en",
            min_scene_duration=getattr(settings, "min_scene_duration_seconds", 1.5),
        )

        raw = self._call_llm(prompt)
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        scenes_raw = data.get("scenes") if isinstance(data, dict) else data
        if not scenes_raw or not isinstance(scenes_raw, list):
            raise ValueError("Unified response missing valid 'scenes' array")

        scenes = self._parse_and_validate(json.dumps(scenes_raw), narration_duration)
        if not scenes:
            raise ValueError("No valid scenes produced after validation")
        return scenes

    # ── Backward Compatibility Aliases ────────────────────────────────────────

    def _call_groq(self, prompt: str) -> str:
        """Call Groq API with robust model fallback and strict JSON output."""
        import httpx
        for model in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]:
            try:
                resp = httpx.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a professional video director and scene planner. "
                                    "You MUST return ONLY valid JSON — no markdown fences, no explanations, "
                                    "no extra text before or after the JSON. "
                                    "Start your response with either { or [ and end with } or ]."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 4096,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.debug(f"Groq model {model} attempt failed: {e}")
                continue
        raise RuntimeError("All Groq model attempts failed")

    def _call_gemini(self, prompt: str) -> str:
        """Alias for _call_llm for backwards compatibility with tests."""
        return self._call_llm(prompt)

    def _call_llm(self, prompt: str) -> str:
        """Call configured LLM (Vertex AI → Gemini API key → Groq fallback) and return raw text."""
        if self._provider == "vertexai":
            try:
                response = self._vertex_client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=prompt,
                )
                if response and response.text:
                    return response.text
                raise RuntimeError("Vertex AI returned empty response")
            except Exception as e:
                logger.warning(f"Vertex AI LLM call failed: {e}; falling back to Groq")
                if settings.groq_api_key:
                    return self._call_groq(prompt)
                raise
        elif self._provider == "gemini":
            try:
                genai = _get_genai()
                response = self._model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=8192,
                    ),
                )
                return response.text
            except Exception as e:
                logger.warning(f"Gemini LLM call failed: {e}; falling back to Groq")
                if settings.groq_api_key:
                    return self._call_groq(prompt)
                raise
        elif settings.groq_api_key:
            return self._call_groq(prompt)
        else:
            raise RuntimeError("No LLM provider available")

    # ── Deterministic Mock / Fallback Logic ────────────────────────────────────

    def _mock_global_analysis(
        self,
        transcript: str,
        style_preferences: Optional[str] = None,
        avoid_constraints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Deterministic Stage A narrative analysis."""
        words = transcript.lower().split()
        is_finance = any(w in words for w in ["money", "savings", "interest", "finance", "invest", "wealth", "account", "bank"])
        topic = "Financial Growth & Disciplined Savings" if is_finance else "Documentary Overview"
        return {
            "overall_topic": topic,
            "central_message": "Disciplined progress creates compounding, sustainable results over time.",
            "intended_audience": "General audience seeking informative visual explanations",
            "narrative_structure": "Linear problem-mechanism-growth-resolution progression",
            "tone": "Authoritative, educational, reassuring",
            "chronology": "Present to future progression",
            "major_claims": [
                "Small recurring actions compound significantly over time",
                "Long-term accumulation provides security and tangible value",
            ],
            "named_entities": [],
            "important_objects": ["balance graph", "digital savings account", "financial ledger", "asset reserve"],
            "recurring_visual_motifs": ["gradual upward progression", "accumulating resources"],
            "visual_style": style_preferences or "Cinematic documentary, clean lighting, clear composition",
            "established_facts": ["Initial contributions start small", "Growth accelerates with duration"],
            "causal_relationships": ["Recurring deposits -> increasing capital balance -> financial peace of mind"],
            "emotional_progression": ["Concern / deliberation", "Focused action", "Reassurance & confidence"],
            "beginning_role": "Introduce context and baseline situation",
            "middle_role": "Demonstrate recurring mechanism and gradual growth",
            "ending_role": "Conclude with established security and realized goals",
            "visual_repetition_constraints": [
                "Do not repeat identical coin or piggy bank shots across consecutive scenes",
                "Vary shot types between wide conceptual, medium action, and close analytical views",
            ],
            "sensitive_content_constraints": avoid_constraints or ["no watermarks", "no misleading imagery"],
        }

    def _mock_beat_plan(
        self,
        transcript: str,
        global_summary: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Deterministic Stage B beat plan."""
        return [
            {
                "beat_id": "beat_01",
                "beat_name": "Context & Challenge",
                "narrative_role": "Exposition",
                "core_idea": "The initial state and importance of understanding resource allocation",
                "suggested_visual_focus": "Person reviewing accounts or planning financial horizon",
                "avoid_repetition_of": "Generic piggy banks",
            },
            {
                "beat_id": "beat_02",
                "beat_name": "Recurring Mechanism",
                "narrative_role": "Action",
                "core_idea": "Steady, recurring actions performed consistently over time",
                "suggested_visual_focus": "Recurring deposit interface or steady accumulation action",
                "avoid_repetition_of": "Static coins",
            },
            {
                "beat_id": "beat_03",
                "beat_name": "Compounding Accumulation",
                "narrative_role": "Progression",
                "core_idea": "Accumulated balance expanding through compounding progression",
                "suggested_visual_focus": "Dynamic upward growth chart or expanding asset reserve",
                "avoid_repetition_of": "Single coin drops",
            },
            {
                "beat_id": "beat_04",
                "beat_name": "Realized Security",
                "narrative_role": "Resolution",
                "core_idea": "The final financial resilience and stability achieved",
                "suggested_visual_focus": "Confident individual looking toward the future in a secure home",
                "avoid_repetition_of": "Cash piles",
            },
        ]

    def _mock_plan_context_aware(
        self,
        transcript: str,
        narration_duration: float,
        segments: Optional[List[Dict]],
        global_summary: Dict[str, Any],
        beat_plan: List[Dict[str, Any]],
        avoid_constraints: Optional[List[str]],
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """Stage C: Deterministic, fully populated Section 7 scene records with pacing & multilingual awareness."""
        # Split sentences across English punctuation (. ! ?) and Indic danda (।)
        raw_sentences = re.split(r"(?<=[.!?।])\s+", transcript.strip())
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        if not sentences:
            sentences = [transcript.strip()] if transcript.strip() else ["Essential narrative concept."]

        # Enforce sensible pacing: merge rapid sentences if duration per sentence < min_scene_duration_seconds
        min_dur = getattr(settings, "min_scene_duration_seconds", 1.5)
        if len(sentences) > 1 and narration_duration > 0:
            avg_dur = narration_duration / len(sentences)
            if avg_dur < min_dur:
                merged = []
                buf = ""
                for s in sentences:
                    if not buf:
                        buf = s
                    elif (len(buf.split()) * 0.45) < min_dur:
                        buf += " " + s
                    else:
                        merged.append(buf)
                        buf = s
                if buf:
                    if merged and (len(buf.split()) * 0.45 < min_dur):
                        merged[-1] += " " + buf
                    else:
                        merged.append(buf)
                sentences = merged

        n = len(sentences)
        scene_dur = max(min_dur, narration_duration / n if n > 0 else narration_duration)

        scenes = []
        rolling_summary = ""

        shot_types = ["wide", "medium", "close-up", "aerial", "medium-close-up"]
        camera_movements = ["slow push-in", "gentle pan right", "steady tracking", "subtle tilt-up", "static stable"]

        for i, sentence in enumerate(sentences):
            start = round(i * scene_dur, 2)
            end = round(narration_duration if i == n - 1 else (i + 1) * scene_dur, 2)
            if end <= start:
                end = round(start + min_dur, 2)

            beat = beat_plan[min(i, len(beat_plan) - 1)]
            role = beat.get("narrative_role", "Progression")
            beat_name = beat.get("beat_name", "Progression Beat")

            # Determine distinct visual subject and action based on sentence content
            subject, action, env = self._infer_visual_subject_action(sentence, i)

            # Generate 3-5 diverse, descriptive queries optimized for Pixabay (no vague filler words)
            clean_queries = self.generate_pixabay_queries(
                sentence=sentence,
                visual_hint=sentence,
                subject=subject,
                action=action,
                environment=env,
            )

            primary_queries = clean_queries[:2]
            alt_queries = clean_queries[2:]

            semantic_desc = (
                f"Visual depiction of {sentence.lower().rstrip('.')}: "
                f"Shows {subject} actively {action} within a {env}. "
                f"Communicates {beat.get('core_idea', 'narrative progress')} without relying on superficial clichés."
            )

            # Multiple descriptions
            multi_descriptions = [
                semantic_desc,
                f"Authentic visual representation: {subject} in {env}.",
                f"Detailed focus on {action}.",
            ]

            gen_prompt = (
                f"Cinematic illustration frame, {shot_types[i % len(shot_types)]} shot: "
                f"A {subject} {action} in a {env}. Lighting: natural, soft warm contrast. "
                f"Style: clean, vibrant digital art, non-photorealistic. Avoid: {', '.join(avoid_constraints or ['watermarks', 'logos', 'meat', 'distorted faces'])}."
            )

            scene = {
                "scene_id": f"scene_{i+1:03d}",
                "scene_index": i,
                "narration_text": sentence,
                "start_time": start,
                "end_time": end,
                "duration": round(end - start, 2),
                "previous_scene_summary": rolling_summary[:120] if rolling_summary else "Beginning of video.",
                "global_story_context": global_summary.get("central_message", ""),
                "narrative_beat": beat_name,
                "narrative_role": role,
                "semantic_description": semantic_desc,
                "intended_visual_meaning": f"Demonstrates {role.lower()} for {beat_name}",
                "visual_subject": subject,
                "visual_action": action,
                "environment": env,
                "relevant_objects": [subject, "financial ledger", "digital interface"],
                "object_state": "in steady progress",
                "composition": "Rule of thirds, subject clearly centered with depth of field",
                "shot_type": shot_types[i % len(shot_types)],
                "camera_angle": "eye-level",
                "camera_movement": camera_movements[i % len(camera_movements)],
                "lighting": "natural diffuse morning light",
                "mood": "calm, focused, purposeful",
                "style": "cinematic documentary",
                "temporal_requirements": f"Visible {action} progression across the clip duration",
                "visual_continuity_requirements": "Maintain cohesive cool-blue and warm-neutral documentary color grading",
                "visual_diversity_role": f"Presents distinct facet: {beat.get('suggested_visual_focus', subject)}",
                "must_include": [subject],
                "must_avoid": avoid_constraints or ["watermarks", "brand logos"],
                "primary_search_queries": primary_queries,
                "alternative_search_queries": alt_queries,
                "search_queries": clean_queries,
                "semantic_description": semantic_desc,
                "semantic_descriptions": multi_descriptions,
                "alternative_visual_descriptions": multi_descriptions[1:],
                "image_generation_prompt": gen_prompt,
                "requires_real_faces": False if any(
                    h in str(avoid_constraints).lower() for h in ["human", "people", "face"]
                ) else any(
                    kw in (sentence + " " + subject + " " + action).lower()
                    for kw in ["boy", "girl", "child", "person", "people", "man", "woman", "face", "student", "family"]
                ),
                "candidate_asset_ids": [],
                "warnings": [],

                # Backwards-compatibility fields for existing modules & tests
                "transcript_text": sentence,
                "scene_summary": sentence[:80],
                "visual_description": semantic_desc,
                "primary_search_query": primary_queries[0] if primary_queries else "",
                "sentence_start": start,
                "sentence_end": end,
                "required_visual_elements": [subject],
                "excluded_visual_elements": avoid_constraints or ["watermarks", "brand logos"],
                "safety_flags": [],
                "preferred_shot_type": shot_types[i % len(shot_types)],
            }

            rolling_summary = f"{sentence[:60]}... Visual: {subject} {action}"
            scenes.append(scene)

        self._check_coverage(scenes, narration_duration)
        return scenes

    def generate_pixabay_queries(
        self,
        sentence: str,
        visual_hint: Optional[str] = None,
        subject: Optional[str] = None,
        action: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> List[str]:
        """
        Analyze scene narration and visual hint to identify subject, action, setting,
        and objects, generating 3-5 diverse, descriptive search queries optimized for Pixabay.
        For abstract concepts, generates practical visual alternatives.
        Avoids overly literal, vague ('concept', 'video'), or repetitive queries.
        """
        if not subject or not action or not environment:
            sub, act, env = self._infer_visual_subject_action(sentence, 0)
            subject = subject or sub
            action = action or act
            environment = environment or env

        s_low = f"{sentence} {visual_hint or ''}".lower()
        tokens = set(re.findall(r"\b[a-zA-Z0-9_\-\u0900-\u097F\u0B80-\u0BFF]+\b", s_low))

        def matches_any(keywords: List[str]) -> bool:
            for kw in keywords:
                if " " in kw:
                    if kw in s_low:
                        return True
                else:
                    if kw in tokens or kw in s_low:
                        # For Indic scripts without clear ASCII word boundaries, fallback to substring
                        if any(ord(c) > 127 for c in kw):
                            if kw in s_low:
                                return True
                        elif kw in tokens:
                            return True
            return False

        queries: List[str] = []

        # 1. Cultural Concepts (Pongal, Diwali, Indic Festivals)
        if matches_any(["பொங்கல்", "அறுவடை", "pongal", "harvest festival"]):
            queries = [
                "traditional clay pot cooking",
                "harvest festival sugarcane celebration",
                "colorful kolam rangoli floor",
                "south indian festive village",
                "traditional clay pot",
            ]
        elif matches_any(["दीवाली", "दिवाली", "diwali", "diya", "दीये", "दीप"]):
            queries = [
                "lit clay diyas",
                "diwali oil lamps",
                "golden candle glow",
                "diwali street lights",
                "festival lamps celebration",
            ]
        # 2. Agriculture & Farming
        elif matches_any(["farmer", "farming", "crop", "wheat", "field", "harvest", "agriculture", "farmland", "कृषि", "किसान", "வயல்", "விவசாயி"]):
            queries = [
                "indian farmer wheat field",
                "farmer inspecting green crops",
                "sunlit agriculture farmland",
                "golden wheat harvest closeup",
                "rural farm tractor field",
            ]
        # 3. Fruits, Fresh Food & Markets
        elif matches_any(["fruit", "fruits", "apple", "banana", "produce", "market", "shop", "eat", "eating", "फल", "பழம்"]):
            queries = [
                "fresh fruit market stall",
                "organic fruits market display",
                "farmer picking fresh apples",
                "colorful fruits shop counter",
                "eating fresh organic fruit",
            ]
        # 4. Transportation & Commute
        elif matches_any(["car", "vehicle", "drive", "driving", "road", "commute", "travel", "गाड़ी", "சாலை"]):
            queries = [
                "passenger car driving road",
                "morning commute highway traffic",
                "car driving countryside road",
                "student traveling car commute",
                "vehicle moving road sunset",
            ]
        # 5. Daily Habits, Discipline & Routines
        elif matches_any(["habit", "habits", "discipline", "routine", "daily routine", "daily habit"]):
            queries = [
                "morning sunrise running path",
                "person writing journal coffee",
                "focused person working laptop",
                "alarm clock morning bed",
                "fresh morning coffee steam",
            ]
        # 6. Financial Management, Budgeting, Income & Expenses
        elif matches_any(["budget", "budgeting", "expense", "expenses", "spending", "salary", "income", "divide", "essential", "essentials", "financial freedom", "debt", "money", "पैसा", "धन", "பணம்", "செலவு"]):
            queries = [
                "person budgeting finances desk",
                "calculating expenses and budget",
                "organizing cash and savings",
                "financial planning notebook desk",
                "hands organizing monthly budget",
            ]
        # 7. Abstract Concept: Financial Growth & Compounding
        elif matches_any(["compound", "compounding", "interest", "wealth", "invest", "investment", "investments", "growth", "savings", "balance", "बचत", "சேமி"]):
            queries = [
                "stock market chart screen",
                "financial growth upward graph",
                "digital banking app screen",
                "piggy bank savings coins",
                "coins stacking growth",
            ]
        # 8. Abstract Concept: Resilience, Peace of Mind, Stability & Emergency Fund
        elif matches_any(["resilience", "stability", "peace of mind", "security", "protect", "protection", "emergency fund", "financial foundation", "सुरक्षा", "பாதுகாப்ப"]):
            queries = [
                "person reviewing financial plan",
                "calm person working home desk",
                "family relaxing sunny living room",
                "piggy bank secure savings",
                "solid oak tree sunny field",
            ]
        # 7. Abstract Concept: Global Challenges, Climate & Planet
        elif matches_any(["climate", "planet", "challenge", "challenges", "global", "earth", "warming", "environment"]):
            queries = [
                "glacier melting waterfall",
                "dry cracked desert soil",
                "solar panels sunny field",
                "wind turbine green hills",
                "earth globe planet space",
            ]
        # 8. Science, Technology & Innovation
        elif matches_any(["science", "scientific", "innovation", "technology", "research", "data", "code", "ai"]):
            queries = [
                "scientist laboratory microscope",
                "modern datacenter server lights",
                "hands typing computer code",
                "robotics engineering lab",
                "digital tech network infographic",
            ]
        # 9. Clean Energy & Sustainability
        elif matches_any(["clean energy", "sustainability", "renewable", "solar", "wind turbine"]):
            queries = [
                "wind turbines rolling hills",
                "solar panel field sunlight",
                "green forest canopy aerial",
                "clear mountain river rocks",
                "electric vehicle charging station",
            ]
        # 10. Daily Habits & Discipline
        elif matches_any(["habit", "habits", "discipline", "routine", "daily", "morning", "every day"]):
            queries = [
                "morning sunrise running path",
                "person writing journal coffee",
                "focused person working laptop",
                "alarm clock morning bed",
                "fresh morning coffee steam",
            ]
        # 11. Generic Synthesized Diverse Fallback
        else:
            from app.services.relevance_engine import extract_content_tokens
            sub_toks = extract_content_tokens(subject)[:3]
            act_toks = extract_content_tokens(action)[:2]
            env_toks = extract_content_tokens(environment)[:2]

            sub_str = " ".join(sub_toks) if sub_toks else "subject"
            act_str = " ".join(act_toks) if act_toks else "motion"
            env_str = " ".join(env_toks) if env_toks else "setting"

            queries = [
                f"{sub_str} {act_str}".strip(),
                f"{env_str} {sub_str}".strip(),
                f"{sub_str} close up".strip(),
                f"{env_str} {sub_str} sunlight".strip(),
                f"{sub_str} {env_str}".strip(),
            ]

        # Clean, filter vague words, deduplicate while preserving 3-5 items
        vague_terms = {"concept", "video", "footage", "clip", "photo", "image", "showing", "abstract", "thing"}
        clean_list = []
        seen = set()
        for q in queries:
            words = [w for w in q.lower().split() if w not in vague_terms]
            if len(words) >= 2:
                q_clean = " ".join(words[:4]).strip()
                if q_clean and q_clean not in seen:
                    seen.add(q_clean)
                    clean_list.append(q_clean)

        # Guarantee between 3 and 5 queries
        if len(clean_list) < 3:
            first = clean_list[0] if clean_list else "scenic nature"
            clean_list.append(f"{first} outdoor")
            clean_list.append(f"{first} landscape")

        return clean_list[:5]

    def _infer_visual_subject_action(self, sentence: str, index: int) -> tuple[str, str, str]:
        """Infer non-repetitive subjects and actions from sentence semantics."""
        s = sentence.lower()

        # Multilingual & Cultural Concepts (Hindi & Tamil)
        # Indian Agriculture & Farmers
        if any(w in s for w in ["किसान", "खेत", "फसल", "कृषि", "விவசாயி", "வயல்", "பயிர்", "விவசாயம்"]):
            return (
                "indian farmer in fertile agricultural field",
                "inspecting healthy green crops under warm morning sunlight",
                "authentic lush rural farmland landscape",
            )

        # Tamil Harvest Festival (Pongal / அறுவடை)
        if any(w in s for w in ["பொங்கல்", "அறுவடை", "தைப்பொங்கல்", "உழவர்"]):
            if any(w in s for w in ["கோலம்", "வணக்கம்", "வரவேற்பு", "நண்ப"]):
                return (
                    "traditional tamil home entrance with colorful floor kolam",
                    "showcasing intricate rice flour rangoli design and fresh mango leaf decor",
                    "festive traditional south indian courtyard bathed in bright morning sun",
                )
            return (
                "traditional pongal clay pot cooking celebration",
                "boiling fresh harvest rice and milk with sugarcane stalks in joyous community",
                "authentic rural tamil harvest festival celebration setting",
            )

        # Diwali / Deepavali (Festival of Lights)
        if any(w in s for w in ["दीवाली", "दिवाली", "त्योहार", "दीप", "दीये", "दीपक", "தீபாவளி", "விளக்கு"]):
            return (
                "traditional diwali festival of lights",
                "illuminating hand-crafted clay diyas with warm glowing flames",
                "festive decorated courtyard glowing with warm golden ambient light",
            )

        # Heritage & Architecture (Temples, Monuments)
        if any(w in s for w in ["मंदिर", "धरोहर", "कोவில்", "பாரம்பரியம்"]):
            return (
                "historic stone temple architecture",
                "showcasing intricate carved pillars in warm morning sunlight",
                "serene sacred temple courtyard",
            )

        # Indic Finance & Savings
        if any(w in s for w in ["बचत", "धन", "पैसे", "बैंक", "वित्तीय", "वित्त", "சேமி", "பண", "வங்க", "நிதி", "பாதுகாப்ப"]):
            return (
                "disciplined savings accumulation",
                "growing savings balance steadily in secure account",
                "modern financial planning setting",
            )
        if any(w in s for w in ["निवेश", "मुதலீ", "வளர்"]):
            return (
                "investment growth chart",
                "progressing steadily upward with compounding returns",
                "clean professional financial workspace",
            )

        # Boy / student / school / travel (English, Hindi, Tamil)
        if any(w in s for w in ["boy", "girl", "child", "student", "kid", "छात्र", "विद्यार्थी", "बच्चा", "மாணவர்", "குழந்தை"]):
            if any(w in s for w in ["school", "class", "study", "learn", "विद्यालय", "स्कूल", "पढ़ाई", "பள்ளி", "கல்வி"]):
                if any(w in s for w in ["car", "vehicle", "drive", "travel", "road", "village", "गाड़ी", "कार", "மகிழுந்து"]):
                    return (
                        "student traveling in car to school",
                        "looking out car window on morning commute from village",
                        "picturesque morning countryside road",
                    )
                return (
                    "school student walking with backpack",
                    "heading enthusiastically towards school entrance",
                    "pleasant outdoor school morning atmosphere",
                )

        # Fruits / food / shop / market (English, Hindi, Tamil)
        if any(w in s for w in ["fruit", "shop", "market", "eat", "food", "fresh", "apple", "banana", "orange", "produce", "फल", "बाजार", "दुकान", "ताजा", "பழம்", "சந்தை", "கடை", "புதிய"]):
            return (
                "vibrant fresh fruit market stand",
                "displaying colorful fresh organic fruits and refreshing snacks",
                "bright sunlit outdoor market street",
            )

        # Vehicles / transport (English, Hindi, Tamil)
        if any(w in s for w in ["car", "vehicle", "automobile", "drive", "road", "travel", "गाड़ी", "कार", "यात्रा", "सड़क", "மகிழுந்து", "கார்", "பயணம்", "சாலை"]):
            return (
                "passenger car driving on road",
                "traveling smoothly through scenic countryside",
                "sunlit rural highway",
            )

        # Countryside / nature
        if any(w in s for w in ["village", "rural", "countryside", "field", "farm"]):
            return (
                "peaceful rural village landscape",
                "showing authentic morning countryside scenery",
                "open natural green countryside",
            )

        # Technology & cloud
        if any(w in s for w in ["cloud", "datacenter", "server", "computing", "network", "technology"]):
            return (
                "enterprise datacenter server racks",
                "processing high-speed data communications",
                "modern secure technology facility",
            )

        # Robotics & automation
        if any(w in s for w in ["robot", "industrial", "factory", "automation", "edge"]):
            return (
                "smart industrial robotic arm",
                "assembling precision components in automated facility",
                "high-tech smart manufacturing floor",
            )

        # Finance & savings domain
        if any(w in s for w in ["problem", "uncontrolled", "spend", "cost", "review"]):
            return ("household financial accounts", "being carefully reviewed on a digital spreadsheet", "modern home office")
        elif any(w in s for w in ["deposit", "contribute", "regular", "recurring", "monthly"]):
            return ("automatic savings contribution", "transferring into an interest-bearing account", "clean banking interface")
        elif any(w in s for w in ["accumulate", "grow", "balance", "steady", "over time"]):
            return ("savings account balance graph", "rising steadily through an animated financial chart", "bright modern studio")
        elif any(w in s for w in ["interest", "compound", "accelerate", "dividend"]):
            return ("compound return projection chart", "expanding upward with clear milestone indicators", "professional analytics workstation")
        elif any(w in s for w in ["security", "benefit", "future", "stability", "freedom"]):
            return ("individual enjoying financial security", "looking forward calmly and confidently", "warm sunlit living space")
        else:
            is_non_ascii = any(ord(c) >= 128 for c in s)
            if is_non_ascii:
                return ("cinematic visual concept", "demonstrating key concept", "natural daylight setting")
            stop_words = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from", "up", "about", "into", "over", "after", "is", "are", "was", "were", "be", "been", "he", "she", "it", "they", "and", "but", "or", "so"}
            words = [re.sub(r"[^\w]", "", w) for w in s.split()]
            content = [w for w in words if w and w not in stop_words]
            subject_str = f"{' '.join(content[:2])}" if content else "cinematic visual"
            action_str = f"progressing through {' '.join(content[2:4])}" if len(content) > 2 else "demonstrating key concept"
            return (subject_str, action_str, "cinematic natural daylight environment")

    def _plan_structured_scenes(
        self,
        structured_scenes: List[Dict],
        narration_duration: float,
        style_preferences: Optional[str],
        avoid_constraints: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Directly map structured scene inputs into Section 7 schema."""
        n = len(structured_scenes)
        scene_dur = max(1.0, narration_duration / n if n > 0 else narration_duration)
        scenes = []

        for i, item in enumerate(structured_scenes):
            text = item.get("text", "").strip()
            hint = item.get("visual_hint", "").strip()
            start = round(i * scene_dur, 2)
            end = round(narration_duration if i == n - 1 else (i + 1) * scene_dur, 2)
            if end <= start:
                end = round(start + 1.0, 2)

            query = hint if hint else " ".join(text.split()[:4])
            semantic_desc = (
                f"Visual illustrating: '{text}'. "
                f"Target composition: {hint if hint else 'Contextually faithful representation of the spoken narration'}."
            )

            clean_queries = self.generate_pixabay_queries(
                sentence=text,
                visual_hint=hint,
            )
            primary_queries = clean_queries[:2]
            alt_queries = clean_queries[2:]

            scene = {
                "scene_id": f"scene_{i+1:03d}",
                "scene_index": i,
                "narration_text": text,
                "start_time": start,
                "end_time": end,
                "duration": round(end - start, 2),
                "previous_scene_summary": f"Previous: Scene {i}" if i > 0 else "Start of sequence.",
                "global_story_context": "Structured narrative sequence",
                "narrative_beat": f"Beat {i+1}",
                "narrative_role": "Structured Beat",
                "semantic_description": semantic_desc,
                "intended_visual_meaning": f"Visual hint constraint: {hint}" if hint else text,
                "visual_subject": hint or "narrative subject",
                "visual_action": "illustrating narration concept",
                "environment": "documentary setting",
                "relevant_objects": [hint] if hint else [],
                "object_state": "active",
                "composition": "cinematic framing",
                "shot_type": "medium",
                "camera_angle": "eye-level",
                "camera_movement": "slow push-in",
                "lighting": "natural",
                "mood": "educational",
                "style": style_preferences or "cinematic",
                "temporal_requirements": "continuous motion",
                "visual_continuity_requirements": "consistent grading",
                "visual_diversity_role": f"Structured scene {i+1}",
                "must_include": [hint] if hint else [],
                "must_avoid": avoid_constraints or ["watermarks", "brand logos"],
                "primary_search_queries": primary_queries,
                "alternative_search_queries": alt_queries,
                "search_queries": clean_queries,
                "image_generation_prompt": f"Cinematic documentary shot: {hint or text}. Style: natural lighting.",
                "candidate_asset_ids": [],
                "warnings": [],

                # Backwards compatibility
                "transcript_text": text,
                "scene_summary": text[:80],
                "visual_description": semantic_desc,
                "primary_search_query": query,
                "sentence_start": start,
                "sentence_end": end,
                "required_visual_elements": [hint] if hint else [],
                "excluded_visual_elements": avoid_constraints or ["watermarks", "brand logos"],
                "safety_flags": [],
                "preferred_shot_type": "medium",
            }
            scenes.append(scene)

        self._check_coverage(scenes, narration_duration)
        return scenes

    # ── Helpers & Parsers ─────────────────────────────────────────────────────

    def _clean_and_parse_json(self, raw: str) -> Any:
        text = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object or array found in LLM output: {raw[:200]}")
        return json.loads(match.group(1))

    def _parse_and_validate(self, raw: str, narration_duration: float) -> List[Dict]:
        scenes = self._clean_and_parse_json(raw)
        if not isinstance(scenes, list) or len(scenes) == 0:
            raise ValueError("Scene output must be a non-empty JSON array")

        required_fields = [
            "scene_id", "start_time", "end_time", "duration",
            "semantic_description", "primary_search_queries",
        ]
        validated = []
        for i, s in enumerate(scenes):
            s.setdefault("scene_index", i)
            s.setdefault("narration_text", s.get("transcript_text", ""))
            s.setdefault("transcript_text", s.get("narration_text", ""))
            s.setdefault("visual_description", s.get("semantic_description", ""))
            s.setdefault("semantic_description", s.get("visual_description", ""))

            # Deduplicate and build complete search_queries list
            all_q = (
                (s.get("search_queries") or []) +
                (s.get("primary_search_queries") or []) +
                (s.get("alternative_search_queries") or []) +
                ([s["primary_search_query"]] if s.get("primary_search_query") else [])
            )
            seen_q = set()
            deduped_q = []
            for q in all_q:
                if q and isinstance(q, str):
                    q_str = q.strip()
                    if q_str and q_str.lower() not in seen_q:
                        seen_q.add(q_str.lower())
                        deduped_q.append(q_str)
            s["search_queries"] = deduped_q[:5]
            if deduped_q:
                s["primary_search_queries"] = deduped_q[:2]
                s["primary_search_query"] = deduped_q[0]
                s["alternative_search_queries"] = deduped_q[2:5]
            else:
                s.setdefault("primary_search_queries", ["scenic nature"])
                s.setdefault("primary_search_query", "scenic nature")
                s.setdefault("alternative_search_queries", [])

            for f in required_fields:
                if f not in s:
                    raise ValueError(f"Scene {i} missing mandatory field '{f}'")

            s["start_time"] = float(s["start_time"])
            s["end_time"] = float(s["end_time"])
            s["duration"] = float(s["duration"])
            s["sentence_start"] = float(s.get("sentence_start", s["start_time"]))
            s["sentence_end"] = float(s.get("sentence_end", s["end_time"]))
            s.setdefault("required_visual_elements", [])
            s.setdefault("excluded_visual_elements", ["watermarks", "brand logos"])
            s.setdefault("safety_flags", [])
            s.setdefault("preferred_shot_type", s.get("shot_type", "wide"))
            validated.append(s)

        validated = self._consolidate_duplicate_scenes(validated, narration_duration)
        self._check_coverage(validated, narration_duration)
        return validated

    def _consolidate_duplicate_scenes(self, scenes: List[Dict], narration_duration: float) -> List[Dict]:
        """
        Detects and merges consecutive duplicate or redundant scenes that share identical or
        heavily overlapping narration text, preventing 'original, duplicate' repetition.
        """
        if not scenes or len(scenes) <= 1:
            return scenes

        deduped = []
        for s in scenes:
            cur_text = (s.get("narration_text") or s.get("transcript_text") or "").strip().lower()
            cur_clean = re.sub(r"[^\w\s]", "", cur_text).strip()

            if deduped:
                prev = deduped[-1]
                prev_text = (prev.get("narration_text") or prev.get("transcript_text") or "").strip().lower()
                prev_clean = re.sub(r"[^\w\s]", "", prev_text).strip()

                is_duplicate = False
                if cur_clean and prev_clean:
                    if cur_clean == prev_clean:
                        is_duplicate = True
                    elif cur_clean in prev_clean or prev_clean in cur_clean:
                        ratio = min(len(cur_clean), len(prev_clean)) / max(len(cur_clean), len(prev_clean))
                        if ratio > 0.6:
                            is_duplicate = True

                if is_duplicate:
                    logger.info(
                        f"Consolidating duplicate scene {s.get('scene_id')} into {prev.get('scene_id')} "
                        f"(repeated narration detected: '{cur_clean[:40]}...')"
                    )
                    prev["end_time"] = max(float(prev.get("end_time", 0.0)), float(s.get("end_time", 0.0)))
                    prev["duration"] = round(prev["end_time"] - float(prev.get("start_time", 0.0)), 3)

                    sq_prev = prev.get("search_queries", []) or []
                    sq_curr = s.get("search_queries", []) or []
                    merged_sq = list(dict.fromkeys(sq_prev + sq_curr))
                    prev["search_queries"] = merged_sq[:5]
                    prev["primary_search_queries"] = merged_sq[:2]
                    prev["alternative_search_queries"] = merged_sq[2:5]

                    obj_prev = prev.get("relevant_objects", []) or []
                    obj_curr = s.get("relevant_objects", []) or []
                    prev["relevant_objects"] = list(dict.fromkeys(obj_prev + obj_curr))
                    continue

            deduped.append(s)

        for idx, sc in enumerate(deduped):
            sc["scene_index"] = idx
            sc["scene_id"] = f"scene_{idx+1:03d}"

        return deduped

    def _check_coverage(self, scenes: List[Dict], duration: float) -> None:
        if not scenes:
            raise ValueError("Empty scene list")
        scenes_sorted = sorted(scenes, key=lambda s: s["start_time"])
        if abs(scenes_sorted[0]["start_time"]) > 0.5:
            raise ValueError(f"First scene doesn't start at 0.0 (got {scenes_sorted[0]['start_time']})")

        for i in range(len(scenes_sorted) - 1):
            gap = scenes_sorted[i + 1]["start_time"] - scenes_sorted[i]["end_time"]
            if abs(gap) > 1.0:
                raise ValueError(f"Gap of {gap:.2f}s between scenes {i} and {i+1}")

        final_end = scenes_sorted[-1]["end_time"]
        if abs(final_end - duration) > 1.0:
            scenes_sorted[-1]["end_time"] = duration
            scenes_sorted[-1]["duration"] = duration - scenes_sorted[-1]["start_time"]

    def _build_timed_transcript(self, transcript: str, segments: Optional[List[Dict]]) -> str:
        if not segments:
            return transcript
        lines = []
        for seg in segments:
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "").strip()
            lines.append(f"[{start:.2f}s - {end:.2f}s] {text}")
        return "\n".join(lines)

    def _fallback_plan(self, transcript: str, narration_duration: float, segments: Optional[List[Dict]]) -> List[Dict]:
        """Fallback scene generation method."""
        global_summary = self._mock_global_analysis(transcript)
        beat_plan = self._mock_beat_plan(transcript, global_summary)
        return self._mock_plan_context_aware(transcript, narration_duration, segments, global_summary, beat_plan, None)

    def _mock_plan(self, transcript: str, narration_duration: float) -> List[Dict]:
        return self._fallback_plan(transcript, narration_duration, None)
