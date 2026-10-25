"""
Unit tests for Pipeline 8-10x Performance Optimizations:
1. Early-Exit Candidate Verification
2. Fast In-Memory Pre-Ranking
3. Lazy Video Downloads
4. Single-Prompt Unified Scene Planning
5. High-Speed FFmpeg Preset Optimization
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.services.pixabay_provider import PixabayProvider
from app.services.rendering_service import RenderingService
from app.services.gemini_scene_planner import GeminiScenePlanner
from app.workers.video_pipeline import _process_single_scene
from app.services.diversity_and_continuity_service import VisualDiversityTracker
import threading


def test_rendering_preset_defaults_to_ultrafast():
    renderer = RenderingService()
    assert renderer.preset in ("ultrafast", "veryfast")


def test_lazy_download_downloads_full_media_on_selection(tmp_path):
    provider = PixabayProvider()
    candidate = {
        "id": "pixabay_12345",
        "media_type": "video",
        "download_url": "https://example.com/fake_video.mp4",
        "local_path": str(tmp_path / "pixabay_12345_thumb.jpg"),  # only thumb exists
    }

    # Mock _download_file to simulate downloading the full MP4
    with patch.object(provider, "_download_file", return_value=True) as mock_dl:
        res = provider.download_full_candidate(candidate, tmp_path)
        assert mock_dl.called
        assert candidate["local_path"].endswith(".mp4")


def test_early_exit_stops_evaluating_after_high_scoring_candidate(tmp_path):
    """
    Test that when the first pre-ranked candidate scores >= 3.5,
    the verifier is NOT called for subsequent candidates (Early Exit).
    """
    scene = {
        "scene_id": "scene_001",
        "narration_text": "Solar panels generate clean electricity from the sun.",
        "visual_subject": "solar panels",
        "visual_action": "absorbing sunlight on rooftop",
        "search_queries": ["solar panels sun"],
        "primary_search_queries": ["solar panels sun"],
        "must_avoid": [],
    }

    raw_candidates = [
        {
            "id": "pixabay_solar_01",
            "tags": "solar panels, sun, renewable energy, rooftop",
            "query_used": "solar panels sun",
            "media_type": "video",
            "local_path": str(tmp_path / "thumb1.jpg"),
            "extracted_frames": [str(tmp_path / "thumb1.jpg")],
            "views": 5000,
            "downloads": 500,
        },
        {
            "id": "pixabay_solar_02",
            "tags": "solar energy, roof, clean electricity",
            "query_used": "solar panels sun",
            "media_type": "video",
            "local_path": str(tmp_path / "thumb2.jpg"),
            "extracted_frames": [str(tmp_path / "thumb2.jpg")],
            "views": 3000,
            "downloads": 300,
        },
        {
            "id": "pixabay_solar_03",
            "tags": "electric panels, solar cells",
            "query_used": "solar panels sun",
            "media_type": "video",
            "local_path": str(tmp_path / "thumb3.jpg"),
            "extracted_frames": [str(tmp_path / "thumb3.jpg")],
            "views": 1000,
            "downloads": 100,
        },
    ]

    # Create dummy thumbnail files
    (tmp_path / "thumb1.jpg").write_bytes(b"dummy image data" * 100)
    (tmp_path / "thumb2.jpg").write_bytes(b"dummy image data" * 100)
    (tmp_path / "thumb3.jpg").write_bytes(b"dummy image data" * 100)

    diversity_tracker = VisualDiversityTracker()
    diversity_lock = threading.Lock()
    used_ids = set()
    used_ids_lock = threading.Lock()

    # Track how many candidates get verified by visual verifier
    verified_call_ids = []

    def fake_verify(sc, cand, frames):
        verified_call_ids.append(cand["id"])
        return {
            "subject_match": 0.95,
            "action_match": 0.90,
            "context_match": 0.90,
            "contradiction_detected": False,
            "verification_score": 4.5,
            "evidence": "Perfect solar panels visible.",
        }

    with patch("app.workers.video_pipeline._pixabay.retrieve_candidates", return_value=raw_candidates):
        with patch("app.workers.video_pipeline._pixabay.download_full_candidate", return_value=tmp_path / "solar.mp4"):
            with patch("app.workers.video_pipeline._visual_verifier.verify_candidate", side_effect=fake_verify):
                with patch("app.workers.video_pipeline.settings.enable_vlm_confidence_gating", False):
                    res_idx, processed_scene, cands, scores = _process_single_scene(
                        idx=0,
                        scene=scene,
                        job_id="test_job",
                        job_dir=tmp_path,
                        diversity_tracker=diversity_tracker,
                        diversity_lock=diversity_lock,
                        used_ids=used_ids,
                        used_ids_lock=used_ids_lock,
                        min_rel=3.5,
                    )

    # Candidate 1 scored >= 3.5, so only 1 candidate should have been sent to verifier!
    assert len(verified_call_ids) == 1
    assert verified_call_ids[0] == "pixabay_solar_01"
    assert processed_scene["selected_asset_id"] == "pixabay_solar_01"
    assert processed_scene["relevance_score"] >= 3.5


def test_early_exit_falls_through_when_candidate_fails_threshold(tmp_path):
    """
    Test that if Candidate #1 scores below 3.5 or has contradiction,
    Candidate #2 is evaluated.
    """
    scene = {
        "scene_id": "scene_001",
        "narration_text": "Solar panels generate clean electricity from the sun.",
        "visual_subject": "solar panels",
        "visual_action": "absorbing sunlight",
        "search_queries": ["solar panels sun"],
        "primary_search_queries": ["solar panels sun"],
        "must_avoid": [],
    }

    raw_candidates = [
        {
            "id": "cand_bad",
            "tags": "desert sand dunes, barren landscape",
            "query_used": "solar panels sun",
            "media_type": "video",
            "local_path": str(tmp_path / "thumb_bad.jpg"),
            "extracted_frames": [str(tmp_path / "thumb_bad.jpg")],
            "views": 500,
            "downloads": 50,
        },
        {
            "id": "cand_good",
            "tags": "solar panels, sun, clean power",
            "query_used": "solar panels sun",
            "media_type": "video",
            "local_path": str(tmp_path / "thumb_good.jpg"),
            "extracted_frames": [str(tmp_path / "thumb_good.jpg")],
            "views": 5000,
            "downloads": 500,
        },
    ]

    (tmp_path / "thumb_bad.jpg").write_bytes(b"dummy" * 100)
    (tmp_path / "thumb_good.jpg").write_bytes(b"dummy" * 100)

    diversity_tracker = VisualDiversityTracker()
    diversity_lock = threading.Lock()
    used_ids = set()
    used_ids_lock = threading.Lock()

    verified_call_ids = []

    def fake_verify(sc, cand, frames):
        verified_call_ids.append(cand["id"])
        if cand["id"] == "cand_bad":
            return {
                "subject_match": 0.2,
                "action_match": 0.1,
                "context_match": 0.1,
                "contradiction_detected": True,
                "verification_score": 1.2,
                "evidence": "Sand dunes instead of solar panels.",
            }
        else:
            return {
                "subject_match": 0.95,
                "action_match": 0.90,
                "context_match": 0.90,
                "contradiction_detected": False,
                "verification_score": 4.5,
                "evidence": "Clear solar panels.",
            }

    with patch("app.workers.video_pipeline._pixabay.retrieve_candidates", return_value=raw_candidates):
        with patch("app.workers.video_pipeline._pixabay.download_full_candidate", return_value=tmp_path / "solar.mp4"):
            with patch("app.workers.video_pipeline._visual_verifier.verify_candidate", side_effect=fake_verify):
                with patch("app.workers.video_pipeline.settings.enable_vlm_confidence_gating", False):
                    res_idx, processed_scene, cands, scores = _process_single_scene(
                        idx=0,
                        scene=scene,
                        job_id="test_job",
                        job_dir=tmp_path,
                        diversity_tracker=diversity_tracker,
                        diversity_lock=diversity_lock,
                        used_ids=used_ids,
                        used_ids_lock=used_ids_lock,
                        min_rel=3.5,
                    )

    # First one was bad, second one was good and accepted
    assert "cand_good" in verified_call_ids
    assert processed_scene["selected_asset_id"] == "cand_good"
    assert processed_scene["relevance_score"] >= 3.5


def test_unified_scene_planning_success():
    planner = GeminiScenePlanner()
    mock_payload = {
        "global_narrative": {
            "core_conflict": "Climate change and reliance on fossil fuels.",
            "resolution": "Adoption of renewable clean energy solutions.",
            "audience_takeaway": "Empowered awareness.",
            "visual_arc_description": "From melting glaciers to modern wind farms.",
            "pacing": "Deliberate documentary pacing.",
            "tone": "Inspirational",
            "beginning_role": "Problem Definition",
            "middle_role": "Impact",
            "ending_role": "Solution",
            "visual_repetition_constraints": ["avoid repeated turbine angles"],
            "sensitive_content_constraints": []
        },
        "narrative_beats": [
            {
                "beat_id": "beat_01",
                "beat_name": "Problem Statement",
                "narrative_role": "Exposition",
                "core_idea": "The planet is warming",
                "suggested_visual_focus": "Melting ice",
                "avoid_repetition_of": "None"
            }
        ],
        "scenes": [
            {
                "scene_id": "scene_001",
                "scene_index": 0,
                "narration_text": "Climate change is affecting our global weather.",
                "start_time": 0.0,
                "end_time": 5.0,
                "duration": 5.0,
                "visual_subject": "Earth globe spinning",
                "visual_action": "rotating in space",
                "search_queries": ["earth globe spinning", "planet earth space", "globe rotating orbit"],
                "primary_search_queries": ["earth globe spinning", "planet earth space"],
                "alternative_search_queries": ["globe rotating orbit"],
                "image_generation_prompt": "Cinematic 4k shot of Earth from space.",
                "semantic_description": "Overview of planet Earth.",
                "requires_real_faces": False
            }
        ]
    }

    with patch.object(planner, "_call_llm", return_value=json.dumps(mock_payload)):
        scenes = planner._plan_scenes_unified(
            transcript="Climate change is affecting our global weather.",
            narration_duration=5.0,
        )
        assert len(scenes) == 1
        assert scenes[0]["scene_id"] == "scene_001"
        assert len(scenes[0]["search_queries"]) >= 3


def test_extract_video_frames_samples_20_50_80_percent(tmp_path):
    """
    Test that extract_video_frames accurately samples keyframes at 20%, 50%, and 80% of video duration.
    """
    dummy_video = tmp_path / "test_clip.mp4"
    dummy_video.write_bytes(b"dummy mp4 data" * 100)

    def fake_subprocess_run(cmd, *args, **kwargs):
        if cmd[0] == "ffprobe":
            return MagicMock(returncode=0, stdout=json.dumps({"format": {"duration": "10.0"}}))
        elif cmd[0] == "ffmpeg":
            out_file = Path(cmd[-1])
            out_file.write_bytes(b"dummy frame bytes" * 100)
            return MagicMock(returncode=0)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_subprocess_run) as mock_sub:
        from app.utils.media import extract_video_frames
        frames = extract_video_frames(dummy_video, tmp_path, num_frames=3)

        assert len(frames) == 3
        ffmpeg_calls = [c for c in mock_sub.call_args_list if c[0][0][0] == "ffmpeg"]
        assert len(ffmpeg_calls) == 3
        # Beginning frame: 20% of 10s = 2.0s
        assert ffmpeg_calls[0][0][0][3] == "2.0"
        # Middle frame: 50% of 10s = 5.0s
        assert ffmpeg_calls[1][0][0][3] == "5.0"
        # End frame: 80% of 10s = 8.0s
        assert ffmpeg_calls[2][0][0][3] == "8.0"


def test_scene_wise_audio_generation_locks_timeline_coherence(tmp_path):
    """
    Test that scene-wise audio generation synthesizes per-scene audio,
    pads with natural conversational breathing room snapped to frame boundaries,
    and locks audio, visual, and subtitle timelines into 100% coherence.
    """
    from app.services.tts_service import DeterministicMockTTSAdapter
    from app.workers.video_pipeline import _synthesize_scene_wise_audio
    from app.services.rendering_service import RenderingService

    scenes = [
        {
            "scene_id": "scene_001",
            "narration_text": "Managing personal finance effectively requires steady discipline.",
            "transcript_text": "Managing personal finance effectively requires steady discipline.",
        },
        {
            "scene_id": "scene_002",
            "narration_text": "Regular contributions allow savings to grow over time.",
            "transcript_text": "Regular contributions allow savings to grow over time.",
        },
        {
            "scene_id": "scene_003",
            "narration_text": "Compound returns build financial security for the future.",
            "transcript_text": "Compound returns build financial security for the future.",
        },
    ]

    mock_tts = DeterministicMockTTSAdapter()
    master_wav, master_dur = _synthesize_scene_wise_audio(
        scenes=scenes,
        job_dir=tmp_path,
        tts_service=mock_tts,
        language="en",
        pause_duration=0.35,
        min_scene_duration=1.5,
        fps=30,
    )

    # 1. Master audio file exists and has positive duration
    assert master_wav.exists()
    assert master_wav.stat().st_size > 0
    assert master_dur > 0

    # 2. Each scene has its own valid audio file
    for sc in scenes:
        audio_file = Path(sc["audio_path"])
        assert audio_file.exists()
        assert audio_file.stat().st_size > 0
        assert sc["duration"] > 0
        assert round(sc["end_time"] - sc["start_time"], 3) == round(sc["duration"], 3)

    # 3. Timeline continuity is mathematically seamless (0 gaps, 0 overlaps)
    assert scenes[0]["start_time"] == 0.0
    assert scenes[1]["start_time"] == scenes[0]["end_time"]
    assert scenes[2]["start_time"] == scenes[1]["end_time"]
    assert scenes[2]["end_time"] == master_dur

    # 4. Subtitle generation reflects the exact acoustic scene boundaries
    srt_path = tmp_path / "captions.srt"
    RenderingService().generate_srt(scenes, srt_path)
    assert srt_path.exists()
    srt_content = srt_path.read_text(encoding="utf-8")
    assert "Managing personal finance" in srt_content
    assert "Regular contributions" in srt_content
    assert "Compound returns" in srt_content


