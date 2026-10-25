import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.workers.video_pipeline import _process_single_scene
from app.services.diversity_and_continuity_service import VisualDiversityTracker
import threading


def test_best_effort_stock_fallback_when_below_threshold(tmp_path):
    job_id = "test_fallback_job"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True)

    scene = {
        "scene_id": "scene_001",
        "scene_index": 0,
        "narration_text": "Examining intricate logistics manifests at the security reception.",
        "semantic_description": "Office desk with delivery list",
        "visual_subject": "delivery list",
        "visual_action": "checking list",
        "environment": "office desk",
        "must_avoid": [],
    }

    diversity_tracker = VisualDiversityTracker()
    diversity_lock = threading.Lock()
    used_ids = set()
    used_ids_lock = threading.Lock()

    # Create dummy candidate image
    cand_img = tmp_path / "cand_123.jpg"
    cand_img.write_bytes(b"dummy image data" * 200)

    mock_candidates = [
        {
            "id": "123",
            "media_type": "image",
            "local_path": str(cand_img),
            "download_url": "http://example.com/123.jpg",
            "tags": "delivery, office",
            "extracted_frames": [str(cand_img)],
            "relevance_score": 2.8,  # Below 3.5 threshold!
            "verification_score": 2.8,
            "contradiction_detected": False,
            "provenance": {"provider": "pixabay"},
        }
    ]

    with patch("app.workers.video_pipeline._pixabay.retrieve_candidates", return_value=mock_candidates), \
         patch("app.workers.video_pipeline._visual_verifier.verify_candidate", return_value={"verification_score": 2.8, "contradiction_detected": False}), \
         patch("app.services.relevance_engine.RelevanceScorer.score_candidate", return_value={"relevance_score": 2.8, "contradiction_detected": False, "evidence": "Partial match"}), \
         patch("app.workers.video_pipeline._pixabay.download_full_candidate", return_value=cand_img), \
         patch("app.workers.video_pipeline._image_generator.generate_scene_candidates", return_value=[]), \
         patch("app.workers.video_pipeline._image_generator.generate_scene_image", return_value=None):

        idx, processed_scene, cands, scores = _process_single_scene(
            idx=0,
            scene=scene,
            job_id=job_id,
            job_dir=job_dir,
            diversity_tracker=diversity_tracker,
            diversity_lock=diversity_lock,
            used_ids=used_ids,
            used_ids_lock=used_ids_lock,
            min_rel=3.5,
        )

        # Candidate 123 should be chosen via Best-Effort Stock Fallback instead of dropping to None!
        assert processed_scene.get("selected_asset_id") == "123"
        assert processed_scene.get("local_path") is not None
        assert "Best-effort stock fallback" in processed_scene.get("selection_reason", "")
        assert processed_scene.get("validation_status") == "review_required"
        assert processed_scene.get("low_relevance_flag") is True
        print("PASS: Best-effort fallback successfully selected candidate 123 with score 2.8 < 3.5!")


def test_requery_gemini_when_pixabay_returns_nothing(tmp_path):
    job_id = "test_empty_pixabay_job"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True)

    scene = {
        "scene_id": "scene_002",
        "scene_index": 1,
        "narration_text": "A futuristic holographic scanner analyzing encrypted packages.",
        "semantic_description": "Futuristic scanner hologram",
        "visual_subject": "scanner hologram",
        "visual_action": "scanning package",
        "environment": "laboratory",
        "must_avoid": [],
    }

    diversity_tracker = VisualDiversityTracker()
    diversity_lock = threading.Lock()
    used_ids = set()
    used_ids_lock = threading.Lock()

    retry_img = tmp_path / "gen_scene_002_requery.jpg"
    retry_img.write_bytes(b"ai image data" * 200)

    ai_retry_candidate = {
        "id": "ai_gen_scene_002_requery",
        "media_type": "image",
        "local_path": str(retry_img),
        "download_url": "/jobs/artifacts/download/gen_scene_002_requery.jpg",
        "tags": "hologram, scanner, ai_generated",
        "relevance_score": 4.5,
        "verification_score": 4.5,
        "contradiction_detected": False,
        "provenance": {"provider": "gemini_2_5_flash_image", "ai_generated": True},
    }

    # Pixabay returns nothing, primary generate_scene_candidates returns empty, but requery succeeds!
    with patch("app.workers.video_pipeline._pixabay.retrieve_candidates", return_value=[]), \
         patch("app.workers.video_pipeline._image_generator.generate_scene_candidates", return_value=[]), \
         patch("app.workers.video_pipeline._image_generator.generate_scene_image", return_value=ai_retry_candidate), \
         patch("app.workers.video_pipeline._visual_verifier.verify_candidate", return_value={"verification_score": 4.5, "contradiction_detected": False}), \
         patch("app.services.relevance_engine.RelevanceScorer.score_candidate", return_value={"relevance_score": 4.5, "contradiction_detected": False, "evidence": "High match"}):

        idx, processed_scene, cands, scores = _process_single_scene(
            idx=1,
            scene=scene,
            job_id=job_id,
            job_dir=job_dir,
            diversity_tracker=diversity_tracker,
            diversity_lock=diversity_lock,
            used_ids=used_ids,
            used_ids_lock=used_ids_lock,
            min_rel=3.5,
        )

        assert processed_scene.get("selected_asset_id") == "ai_gen_scene_002_requery"
        assert processed_scene.get("local_path") == str(retry_img)
        assert processed_scene.get("ai_generated") is True
        assert "targeted requery" in processed_scene.get("selection_reason", "")
        print("PASS: Gemini requery successfully generated and selected AI visual when Pixabay returned nothing!")


def test_gemini_image_used_as_final_even_when_score_less_than_3_5(tmp_path):
    """
    CRITICAL USER DIRECTIVE TEST:
    Even when both Pixabay and Gemini relevance scores are less than the 3.5 threshold,
    do NOT drop to ambient colour card.
    Flag as review_required and use the Gemini image as final to generate the video!
    """
    job_id = "test_low_score_gemini_job"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True)

    scene = {
        "scene_id": "scene_003",
        "scene_index": 2,
        "narration_text": "An esoteric micro-electronic device operating at quantum thresholds.",
        "semantic_description": "Micro-electronic quantum chip",
        "visual_subject": "quantum micro-chip",
        "visual_action": "operating quantum pulses",
        "environment": "cleanroom lab",
        "must_avoid": [],
    }

    diversity_tracker = VisualDiversityTracker()
    diversity_lock = threading.Lock()
    used_ids = set()
    used_ids_lock = threading.Lock()

    # Pixabay candidate scores 2.1 (< 3.5)
    stock_img = tmp_path / "stock_chip.jpg"
    stock_img.write_bytes(b"stock data" * 200)
    stock_candidate = {
        "id": "pix_chip",
        "media_type": "image",
        "local_path": str(stock_img),
        "tags": "chip, electronics",
        "extracted_frames": [str(stock_img)],
        "relevance_score": 2.1,
        "verification_score": 2.1,
        "contradiction_detected": False,
        "provenance": {"provider": "pixabay"},
    }

    # Gemini image is generated, but verifier scores it 2.9 (< 3.5)
    gemini_img = tmp_path / "gen_scene_003_cand_1.jpg"
    gemini_img.write_bytes(b"gemini ai image" * 300)
    gemini_candidate = {
        "id": "ai_gen_scene_003_cand_1",
        "media_type": "image",
        "local_path": str(gemini_img),
        "download_url": "/jobs/artifacts/download/gen_scene_003_cand_1.jpg",
        "tags": "quantum, chip, ai_generated",
        "relevance_score": 2.9,  # < 3.5 threshold!
        "verification_score": 2.9,
        "contradiction_detected": False,
        "provenance": {"provider": "gemini_2_5_flash_image", "ai_generated": True},
    }

    with patch("app.workers.video_pipeline._pixabay.retrieve_candidates", return_value=[stock_candidate]), \
         patch("app.workers.video_pipeline._image_generator.generate_scene_candidates", return_value=[gemini_candidate]), \
         patch("app.workers.video_pipeline._visual_verifier.verify_candidate", return_value={"verification_score": 2.9, "contradiction_detected": False}), \
         patch("app.services.relevance_engine.RelevanceScorer.score_candidate", return_value={"relevance_score": 2.9, "contradiction_detected": False, "evidence": "Evaluated generated visual"}):

        idx, processed_scene, cands, scores = _process_single_scene(
            idx=2,
            scene=scene,
            job_id=job_id,
            job_dir=job_dir,
            diversity_tracker=diversity_tracker,
            diversity_lock=diversity_lock,
            used_ids=used_ids,
            used_ids_lock=used_ids_lock,
            min_rel=3.5,
        )

        # 1. Must NOT drop to colour card!
        assert processed_scene.get("selected_asset_id") == "ai_gen_scene_003_cand_1"
        assert processed_scene.get("local_path") == str(gemini_img)
        assert processed_scene.get("ai_generated") is True

        # 2. Must be flagged in metadata for frontend
        assert processed_scene.get("validation_status") == "review_required"
        assert processed_scene.get("low_relevance_flag") is True
        assert "flagged for review" in processed_scene.get("selection_reason", "")
        print("PASS: Gemini image used as final asset and flagged for review when score < 3.5 (zero ambient colour card)!")


def test_low_relevance_triggers_efficient_prompt_requery_and_top_pick(tmp_path):
    """
    Test user directive:
    If relevance score of generated image is low (< 3.5), re-generate using efficient prompt.
    If still low, select the top pick among all candidates without dropping to coloured cards.
    """
    job_id = "test_efficient_prompt_job"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True)

    scene = {
        "scene_id": "scene_006",
        "scene_index": 5,
        "narration_text": "Humpty decided to climb onto a tall stone wall overlooking the royal gardens.",
        "semantic_description": "Tall stone garden wall overlooking flowers",
        "visual_subject": "Tall stone garden wall",
        "visual_action": "standing prominently overlooking royal gardens",
        "environment": "royal garden morning",
        "primary_search_queries": ["sunlit garden wall"],
        "must_avoid": [],
    }

    diversity_tracker = VisualDiversityTracker()
    diversity_lock = threading.Lock()
    used_ids = set()
    used_ids_lock = threading.Lock()

    # Stock candidate scores 2.0 (< 3.5)
    stock_img = tmp_path / "stock_wall.mp4"
    stock_img.write_bytes(b"stock footage video" * 200)
    stock_candidate = {
        "id": "pix_wall",
        "media_type": "video",
        "local_path": str(stock_img),
        "tags": "stone wall, ruins",
        "extracted_frames": [str(stock_img)],
        "relevance_score": 2.0,
        "verification_score": 2.0,
        "contradiction_detected": False,
        "provenance": {"provider": "pixabay"},
    }

    # Initial AI image has low score 2.3 (< 3.5)
    cand1_img = tmp_path / "gen_scene_006_cand_1.jpg"
    cand1_img.write_bytes(b"initial ai visual" * 200)
    cand1 = {
        "id": "ai_gen_scene_006_cand_1",
        "media_type": "image",
        "local_path": str(cand1_img),
        "tags": "stone, wall, ai_generated",
        "relevance_score": 2.3,  # Low!
        "verification_score": 2.3,
        "contradiction_detected": False,
        "provenance": {"provider": "gemini_2_5_flash_image", "ai_generated": True},
    }

    # Requeried AI image with efficient prompt scores 3.1 (or higher)
    retry_img = tmp_path / "gen_scene_006_requery.jpg"
    retry_img.write_bytes(b"retry efficient visual" * 300)
    retry_cand = {
        "id": "ai_gen_scene_006_requery",
        "media_type": "image",
        "local_path": str(retry_img),
        "tags": "stone wall, garden, detailed, ai_generated",
        "relevance_score": 3.1,  # Improved via efficient prompt!
        "verification_score": 3.1,
        "contradiction_detected": False,
        "provenance": {"provider": "gemini_2_5_flash_image", "ai_generated": True},
    }

    prompts_captured = []

    def mock_generate_scene_image(**kwargs):
        prompts_captured.append(kwargs.get("prompt_override", ""))
        return retry_cand

    with patch("app.workers.video_pipeline._pixabay.retrieve_candidates", return_value=[stock_candidate]), \
         patch("app.workers.video_pipeline._image_generator.generate_scene_candidates", return_value=[cand1]), \
         patch("app.workers.video_pipeline._image_generator.generate_scene_image", side_effect=mock_generate_scene_image), \
         patch("app.workers.video_pipeline._visual_verifier.verify_candidate", return_value={"verification_score": 3.1, "contradiction_detected": False}), \
         patch("app.services.relevance_engine.RelevanceScorer.score_candidate", side_effect=lambda sc, c, **kw: {"relevance_score": c.get("relevance_score", 2.0), "contradiction_detected": False, "evidence": "Score"}):

        idx, processed_scene, cands, scores = _process_single_scene(
            idx=5,
            scene=scene,
            job_id=job_id,
            job_dir=job_dir,
            diversity_tracker=diversity_tracker,
            diversity_lock=diversity_lock,
            used_ids=used_ids,
            used_ids_lock=used_ids_lock,
            min_rel=3.5,
        )

        # 1. Requery was triggered with an efficient prompt containing the subject
        assert len(prompts_captured) >= 1
        assert "Tall stone garden wall" in prompts_captured[0]

        # 2. Top pick among candidates (retry_cand with 3.1 > cand1 2.3 > stock 2.0) is selected
        assert processed_scene.get("selected_asset_id") == "ai_gen_scene_006_requery"
        assert processed_scene.get("local_path") == str(retry_img)
        assert processed_scene.get("validation_status") == "review_required"
        assert processed_scene.get("low_relevance_flag") is True
        assert "flagged for review" in processed_scene.get("selection_reason", "")
        print("PASS: Low relevance triggered efficient requery and top pick was selected with real media!")
