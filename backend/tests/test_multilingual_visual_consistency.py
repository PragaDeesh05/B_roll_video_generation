"""
Unit and integration tests for:
- FEATURE 1: Multilingual Narration (English, Hindi, Tamil)
- FEATURE 2: Visual Consistency ("Looks Like One Video")
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from app.config import settings
from app.schemas import JobCreateRequest, JobCreateV1Request, JobStatusResponse
from app.services.tts_service import (
    TTSService,
    DeterministicMockTTSAdapter,
    LANGUAGE_VOICE_MAP,
    LANGUAGE_GTTS_MAP,
)
from app.services.transcription_service import (
    TranscriptionService,
    TranscriptionResult,
    DeterministicMockSTTAdapter,
)
from app.services.gemini_scene_planner import GeminiScenePlanner
from app.services.timeline_service import TimelineService
from app.services.rendering_service import RenderingService
from app.services.media_validation_service import MediaValidationService


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 1: MULTILINGUAL NARRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestLanguageSelectionAndValidation:
    """Test language parameter validation, defaults, and unsupported code rejection."""

    def test_default_language_is_english(self):
        req = JobCreateV1Request(script_text="Managing personal finance requires steady discipline.")
        assert req.language == "en"
        assert req.target_language is None

    def test_valid_languages_accepted(self):
        for lang in ["en", "hi", "ta"]:
            req = JobCreateV1Request(
                script_text="Test script",
                language=lang,
            )
            assert req.language == lang

    def test_unsupported_language_rejected_v1(self):
        with pytest.raises(ValidationError) as exc_info:
            JobCreateV1Request(
                script_text="Bonjour le monde",
                language="fr",
            )
        assert "Unsupported language code" in str(exc_info.value)

    def test_unsupported_target_language_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            JobCreateV1Request(
                script_text="Hello world",
                language="en",
                target_language="de",
            )
        assert "Unsupported target language code" in str(exc_info.value)

    def test_legacy_request_language_support(self):
        req = JobCreateRequest(
            script_text="नमस्ते भारत",
            language="hi",
        )
        assert req.language == "hi"

    def test_legacy_request_unsupported_language_rejected(self):
        with pytest.raises(ValidationError):
            JobCreateRequest(
                script_text="Guten Tag",
                language="de",
            )


class TestSpeechGenerationMultilingual:
    """Test TTS voice selection, language mapping, and natural audio synthesis."""

    def test_language_voice_mapping_exists(self):
        assert "en" in LANGUAGE_VOICE_MAP
        assert "hi" in LANGUAGE_VOICE_MAP
        assert "ta" in LANGUAGE_VOICE_MAP
        assert "Madhur" in LANGUAGE_VOICE_MAP["hi"]
        assert "Valluvar" in LANGUAGE_VOICE_MAP["ta"]

    def test_tts_service_rejects_unsupported_language(self, tmp_path):
        tts = TTSService()
        out = tmp_path / "test.mp3"
        with pytest.raises(ValueError) as exc_info:
            tts.synthesize("Bonjour", out, language="fr")
        assert "Unsupported TTS language" in str(exc_info.value)

    def test_mock_tts_duration_pacing(self, tmp_path):
        mock_tts = DeterministicMockTTSAdapter()
        # English: approx 0.38s per word
        en_out = mock_tts.synthesize("Managing personal finance requires steady discipline.", tmp_path / "en.wav", language="en")
        assert en_out.exists()
        assert en_out.stat().st_size > 0

        # Hindi: approx 0.45s per word
        hi_out = mock_tts.synthesize("व्यक्तिगत वित्त का प्रबंधन निरंतर अनुशासन मांगता है।", tmp_path / "hi.wav", language="hi")
        assert hi_out.exists()
        assert hi_out.stat().st_size > 0


class TestTranscriptionAndTranslation:
    """Test transcription language detection and explicit translation requirements."""

    def test_mock_stt_language_heuristics(self, tmp_path):
        # Create silent dummy wav
        audio_file = tmp_path / "dummy.wav"
        DeterministicMockTTSAdapter().synthesize("test", audio_file)

        # Devanagari detection
        stt_hi = DeterministicMockSTTAdapter(mock_text="किसान खेतों में फसलें उगाते हैं।")
        res_hi = stt_hi.transcribe(audio_file)
        assert res_hi.language == "hi"
        assert "किसान" in res_hi.text

        # Tamil detection
        stt_ta = DeterministicMockSTTAdapter(mock_text="விவசாயி வயலில் பயிர்களை வளர்க்கிறார்.")
        res_ta = stt_ta.transcribe(audio_file)
        assert res_ta.language == "ta"
        assert "விவசாயி" in res_ta.text

    def test_explicit_translation_not_performed_without_target_request(self):
        svc = TranscriptionService()
        # Same language: never translated
        text = "Managing personal finance effectively."
        out = svc.translate_text(text, source_lang="en", target_lang="en")
        assert out == text


class TestLanguageAwareScenePlanning:
    """Test scene planning understanding Hindi & Tamil scripts and generating English stock queries."""

    def test_hindi_script_understanding_and_stock_queries(self):
        planner = GeminiScenePlanner()
        hindi_script = "भारत में किसान खेतों में हरी फसलें उगाते हैं। मेहनती अन्नदाता देश का पोषण करते हैं।"
        scenes = planner.plan_scenes(
            transcript=hindi_script,
            narration_duration=8.0,
            language="hi",
        )
        assert len(scenes) >= 1
        scene = scenes[0]
        # Original narration preserved in Hindi Devanagari script
        assert "किसान" in scene["narration_text"] or "फसलें" in scene["narration_text"]
        # Stock search queries generated in concise English
        queries = scene.get("search_queries", [])
        assert len(queries) > 0
        # Check queries are English (ASCII characters)
        assert all(all(ord(c) < 128 for c in q) for q in queries)
        assert any("farmer" in q.lower() or "agriculture" in q.lower() or "field" in q.lower() or "crop" in q.lower() for q in queries)

    def test_tamil_script_understanding_and_stock_queries(self):
        planner = GeminiScenePlanner()
        tamil_script = "தனிப்பட்ட நிதியை ஒழுக்கமாக சேமிப்பது எதிர்காலத்திற்கு பாதுகாப்பு அளிக்கிறது. வங்கி கணக்கில் முதலீடு வளர்கிறது."
        scenes = planner.plan_scenes(
            transcript=tamil_script,
            narration_duration=8.0,
            language="ta",
        )
        assert len(scenes) >= 1
        scene = scenes[0]
        # Original narration preserved in Tamil script
        assert any("\u0B80" <= c <= "\u0BFF" for c in scene["narration_text"])
        # Stock queries in English
        queries = scene.get("search_queries", [])
        assert len(queries) > 0
        assert all(all(ord(c) < 128 for c in q) for q in queries)

    def test_cultural_festival_concept_preservation(self):
        planner = GeminiScenePlanner()
        diwali_script = "दीवाली के पावन त्योहार पर घरों में दीप जलाए जाते हैं और खुशियां मनाई जाती हैं।"
        scenes = planner.plan_scenes(
            transcript=diwali_script,
            narration_duration=6.0,
            language="hi",
        )
        assert len(scenes) >= 1
        scene = scenes[0]
        # Visual subject reflects oil lamps / celebration
        subject = scene.get("visual_subject", "").lower()
        queries = " ".join(scene.get("search_queries", [])).lower()
        assert "oil lamps" in subject or "lamp" in queries or "festival" in queries or "celebration" in queries


class TestSubtitleUnicodePreservation:
    """Test SRT caption generation with native Indic Unicode characters and validation."""

    def test_srt_preserves_hindi_and_tamil_unicode(self, tmp_path):
        renderer = RenderingService()
        validator = MediaValidationService()
        scenes = [
            {
                "scene_id": "scene_001",
                "start_time": 0.0,
                "end_time": 3.0,
                "transcript_text": "नमस्ते भारत, आपका स्वागत है।",
            },
            {
                "scene_id": "scene_002",
                "start_time": 3.0,
                "end_time": 6.0,
                "transcript_text": "வணக்கம் நண்பர்களே, நல்வரவு.",
            },
        ]
        srt_path = tmp_path / "captions.srt"
        renderer.generate_srt(scenes, srt_path)
        assert srt_path.exists()
        content = srt_path.read_text(encoding="utf-8")

        # Verify Unicode preserved
        assert "नमस्ते" in content
        assert "வணக்கம்" in content
        # Verify valid timestamps
        is_valid, err = validator.validate_srt(srt_path)
        assert is_valid is True
        assert err is None


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 2: VISUAL CONSISTENCY ("LOOKS LIKE ONE VIDEO") TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestSensiblePacingAndSceneDurations:
    """Test scene duration consolidation and prevention of 0.5s flashes."""

    def test_consolidate_short_scenes_merges_rapid_shots(self):
        timeline_svc = TimelineService()
        # 4 scenes in 3 seconds = 0.75s per scene, which is < min_scene_duration (1.5s)
        scenes = [
            {"scene_id": "scene_001", "start_time": 0.0, "end_time": 0.75, "duration": 0.75, "narration_text": "One."},
            {"scene_id": "scene_002", "start_time": 0.75, "end_time": 1.50, "duration": 0.75, "narration_text": "Two."},
            {"scene_id": "scene_003", "start_time": 1.50, "end_time": 2.25, "duration": 0.75, "narration_text": "Three."},
            {"scene_id": "scene_004", "start_time": 2.25, "end_time": 3.00, "duration": 0.75, "narration_text": "Four."},
        ]
        aligned = timeline_svc.align_scenes(scenes, narration_duration=3.0)
        # Max allowed scenes for 3.0s with min_duration 1.5s is 2 scenes
        assert len(aligned) <= 2
        for sc in aligned:
            assert sc["duration"] >= 1.4  # meets pacing requirement
        # All narration content preserved
        combined_text = " ".join(s["narration_text"] for s in aligned)
        assert "One" in combined_text and "Four" in combined_text

    def test_duration_coverage_and_no_gaps(self):
        timeline_svc = TimelineService()
        scenes = [
            {"scene_id": "scene_001", "start_time": 0.0, "end_time": 4.0, "duration": 4.0, "narration_text": "Scene A"},
            {"scene_id": "scene_002", "start_time": 4.0, "end_time": 8.0, "duration": 4.0, "narration_text": "Scene B"},
        ]
        aligned = timeline_svc.align_scenes(scenes, narration_duration=8.0)
        assert aligned[0]["start_time"] == 0.0
        assert aligned[-1]["end_time"] == 8.0
        assert aligned[0]["end_time"] == aligned[1]["start_time"]


class TestColourAndBrightnessNormalization:
    """Test restrained per-clip colour analysis and night/sunset scene preservation."""

    def test_clip_luminance_analysis(self, tmp_path):
        from PIL import Image
        renderer = RenderingService()

        # Create a bright synthetic test image (white)
        bright_img = tmp_path / "bright.png"
        Image.new("RGB", (320, 240), color=(220, 220, 220)).save(bright_img)
        stats_bright = renderer._analyze_clip_luma_stats(bright_img)
        assert stats_bright["luma"] > 200.0

        # Create a dark synthetic test image
        dark_img = tmp_path / "dark.png"
        Image.new("RGB", (320, 240), color=(40, 40, 40)).save(dark_img)
        stats_dark = renderer._analyze_clip_luma_stats(dark_img)
        assert stats_dark["luma"] < 60.0

    def test_preserves_intentional_night_and_sunset_scenes(self, tmp_path):
        from PIL import Image
        renderer = RenderingService()

        clip1 = tmp_path / "clip1.png"
        Image.new("RGB", (320, 240), color=(140, 140, 140)).save(clip1)
        clip2 = tmp_path / "clip2.png"
        Image.new("RGB", (320, 240), color=(30, 30, 35)).save(clip2)

        scenes = [
            {"scene_id": "scene_001", "lighting": "natural daylight", "mood": "optimistic"},
            {"scene_id": "scene_002", "lighting": "night time moonlit", "mood": "nocturnal dark"},
        ]
        profile = {"width": 320, "height": 240, "fps": 30}

        normalized = renderer._apply_color_consistency_stage(scenes, [clip1, clip2], profile, tmp_path)
        assert len(normalized) == 2

        # Scene 2 must NOT be washed out or brightened because it's an intentional night scene
        scene2_meta = scenes[1].get("color_normalization", {})
        assert scene2_meta.get("correction_applied") is False
        assert scene2_meta.get("reason") == "intentional_dramatic_lighting"


class TestAutomatedPostRenderValidation:
    """Test MediaValidationService visual consistency and quality checks."""

    def test_pacing_and_luminance_jump_check_in_validation(self, tmp_path, monkeypatch):
        validator = MediaValidationService()
        monkeypatch.setattr(
            validator,
            "_probe",
            lambda p: {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": "yuv420p",
                        "width": 1920,
                        "height": 1080,
                        "avg_frame_rate": "30/1",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "5.8"},
            },
        )
        monkeypatch.setattr(
            validator,
            "_detect_black_frames",
            lambda p: {"excessive_black": False, "black_duration": 0},
        )
        monkeypatch.setattr(
            validator,
            "_detect_frozen_frames",
            lambda p: {"has_frozen": False, "excessive_freeze": False},
        )
        monkeypatch.setattr(
            validator,
            "_detect_silence",
            lambda p: {"has_silence": False, "all_silent": False},
        )
        monkeypatch.setattr(
            validator,
            "_check_adjacent_luminance_jumps",
            lambda p, s, t: [],
        )

        scenes = [
            {"scene_id": "scene_001", "duration": 5.0, "start_time": 0.0, "end_time": 5.0, "lighting": "day"},
            {"scene_id": "scene_002", "duration": 0.8, "start_time": 5.0, "end_time": 5.8, "lighting": "day"},
        ]
        dummy_mp4 = tmp_path / "dummy.mp4"
        dummy_mp4.write_bytes(b"dummy")

        report = validator.validate_output(
            mp4_path=dummy_mp4,
            aspect_ratio="16:9",
            expected_duration=5.8,
            job_id="test_job",
            scenes=scenes,
        )
        # Should flag a warning for scene under 1.5s
        pacing_check = next((c for c in report["checks"] if c["check"] == "scene_pacing_and_durations"), None)
        assert pacing_check is not None
        assert pacing_check["passed"] is False
