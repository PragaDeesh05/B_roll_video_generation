"""
Phase 3 tests: Full-video narrative understanding and context-aware scene planning.
"""
from __future__ import annotations

import pytest
from app.services.gemini_scene_planner import GeminiScenePlanner


def test_stage_a_global_narrative_analysis():
    planner = GeminiScenePlanner()
    script = (
        "Uncontrolled spending quickly drains household financial stability. "
        "Setting aside recurring monthly contributions creates an expanding capital reserve. "
        "Compounding interest accelerates the accumulated balance. "
        "Ultimately, consistent saving yields lasting financial peace and resilience."
    )
    global_meta = planner.analyze_global_narrative(
        transcript=script,
        style_preferences="Documentary photorealism",
        avoid_constraints=["alcohol", "realistic human faces"],
    )

    assert "overall_topic" in global_meta
    assert "central_message" in global_meta
    assert "recurring_visual_motifs" in global_meta
    assert "visual_repetition_constraints" in global_meta
    assert len(global_meta["visual_repetition_constraints"]) > 0


def test_stage_b_beat_planning():
    planner = GeminiScenePlanner()
    script = "Problem definition. Regular savings. Compounding growth. Final resolution."
    global_meta = planner.analyze_global_narrative(script)
    beats = planner.plan_narrative_beats(script, global_meta)

    assert isinstance(beats, list)
    assert len(beats) >= 3
    beat_roles = [b.get("narrative_role") for b in beats]
    # Verify beats represent progressive functional roles
    assert len(set(beat_roles)) >= 2


def test_stage_c_scene_schema_and_distinctions():
    planner = GeminiScenePlanner()
    script = (
        "High household expenses create financial stress. "
        "Automated monthly deposits accumulate steadily over time. "
        "Compound returns increase the balance exponentially. "
        "Financial freedom is achieved for the family."
    )
    duration = 20.0
    scenes = planner.plan_scenes(transcript=script, narration_duration=duration)

    assert len(scenes) == 4

    # Verify Section 7 mandatory fields on every scene
    mandatory_fields = [
        "scene_id", "scene_index", "narration_text", "start_time", "end_time", "duration",
        "previous_scene_summary", "global_story_context", "narrative_beat", "narrative_role",
        "semantic_description", "visual_subject", "visual_action", "environment",
        "shot_type", "temporal_requirements", "primary_search_queries",
        "alternative_search_queries", "image_generation_prompt",
    ]
    for s in scenes:
        for field in mandatory_fields:
            assert field in s, f"Missing Section 7 field: {field}"

    # Verify distinct representations (Section 8)
    s1 = scenes[1]
    # Semantic description is explanatory
    assert len(s1["semantic_description"]) > len(s1["primary_search_queries"][0])
    # Search query is concise
    assert len(s1["primary_search_queries"][0].split()) <= 10
    # Image prompt contains lighting/style composition guidance
    assert "lighting" in s1["image_generation_prompt"].lower() or "style" in s1["image_generation_prompt"].lower() or "shot" in s1["image_generation_prompt"].lower()

    # Verify rolling memory: later scenes remember previous scene summary
    assert scenes[1]["previous_scene_summary"] != "Beginning of video."
    assert len(scenes[1]["previous_scene_summary"]) > 0

    # Verify visual diversity: different scenes do not use identical subjects
    subjects = [s["visual_subject"] for s in scenes]
    assert len(set(subjects)) > 1, f"Expected distinct visual subjects, got: {subjects}"


def test_structured_scenes_input_handling():
    planner = GeminiScenePlanner()
    structured = [
        {"text": "A person checking a banking dashboard.", "visual_hint": "smartphone banking app display"},
        {"text": "The savings balance increasing gradually.", "visual_hint": "climbing bar graph visual"},
    ]
    scenes = planner.plan_scenes(
        transcript="",
        narration_duration=10.0,
        structured_scenes=structured,
    )
    assert len(scenes) == 2
    assert "smartphone banking app display" in scenes[0]["visual_subject"]
    assert "climbing bar graph visual" in scenes[1]["visual_subject"]
