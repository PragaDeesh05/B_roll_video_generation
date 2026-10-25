import pytest
from app.services.gemini_scene_planner import GeminiScenePlanner
from app.services.timeline_service import TimelineService


def test_gemini_scene_planner_consolidates_duplicate_scenes():
    planner = GeminiScenePlanner()
    raw_scenes = [
        {
            "scene_id": "scene_001",
            "scene_index": 0,
            "start_time": 0.0,
            "end_time": 8.367,
            "duration": 8.367,
            "narration_text": "A museum employee notices that a painting near the entrance is hanging unevenly.",
            "semantic_description": "Employee observing painting",
            "primary_search_queries": ["museum employee", "art painting"],
            "search_queries": ["museum employee", "art painting"],
        },
        {
            "scene_id": "scene_002",
            "scene_index": 1,
            "start_time": 8.367,
            "end_time": 16.734,
            "duration": 8.367,
            "narration_text": "A museum employee notices that a painting near the entrance is hanging unevenly.",  # DUPLICATE!
            "semantic_description": "Employee walking to adjust painting",
            "primary_search_queries": ["walking museum", "adjusting artwork"],
            "search_queries": ["walking museum", "adjusting artwork"],
        },
        {
            "scene_id": "scene_003",
            "scene_index": 2,
            "start_time": 16.734,
            "end_time": 28.8,
            "duration": 12.066,
            "narration_text": "She discovers that the identification card belongs to a different painting.",
            "semantic_description": "Examining card",
            "primary_search_queries": ["museum label", "reading plaque"],
            "search_queries": ["museum label", "reading plaque"],
        },
        {
            "scene_id": "scene_004",
            "scene_index": 3,
            "start_time": 28.8,
            "end_time": 40.8,
            "duration": 12.0,
            "narration_text": "She discovers that the identification card belongs to a different painting.",  # DUPLICATE!
            "semantic_description": "Checking tablet records",
            "primary_search_queries": ["digital tablet", "cross referencing"],
            "search_queries": ["digital tablet", "cross referencing"],
        },
    ]

    deduped = planner._consolidate_duplicate_scenes(raw_scenes, narration_duration=40.8)
    # 4 scenes with 2 duplicates must collapse into exactly 2 distinct scenes!
    assert len(deduped) == 2
    assert deduped[0]["scene_id"] == "scene_001"
    assert deduped[0]["end_time"] == 16.734
    assert deduped[0]["duration"] == 16.734
    assert "art painting" in deduped[0]["search_queries"]
    assert "walking museum" in deduped[0]["search_queries"]

    assert deduped[1]["scene_id"] == "scene_002"
    assert deduped[1]["start_time"] == 16.734
    assert deduped[1]["end_time"] == 40.8


def test_timeline_service_consolidate_duplicate_narration_scenes():
    timeline = TimelineService()
    scenes = [
        {
            "scene_id": "scene_001",
            "start_time": 0.0,
            "end_time": 5.0,
            "duration": 5.0,
            "narration_text": "Regular savings compound over time.",
        },
        {
            "scene_id": "scene_002",
            "start_time": 5.0,
            "end_time": 10.0,
            "duration": 5.0,
            "narration_text": "Regular savings compound over time.",  # Duplicate!
        },
        {
            "scene_id": "scene_003",
            "start_time": 10.0,
            "end_time": 15.0,
            "duration": 5.0,
            "narration_text": "Discipline is the foundation of wealth.",
        },
    ]

    result = timeline.consolidate_duplicate_narration_scenes(scenes)
    assert len(result) == 2
    # Verify narration text was not doubled
    assert result[0]["narration_text"] == "Regular savings compound over time."
    assert result[0]["duration"] == 10.0
    assert result[1]["narration_text"] == "Discipline is the foundation of wealth."
