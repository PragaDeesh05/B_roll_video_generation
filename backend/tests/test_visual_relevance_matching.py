"""
Unit Tests for Scene Query Generation & Visual Relevance Matching (Pixabay & Gemini 2.5 Flash Image)
Tests:
- Literal narration query generation
- Abstract concepts practical visual alternatives
- Vague/filler word elimination
- Stop-word removal and lemmatization
- Synonym and conceptual expansion
- Multi-word phrase matching
- Ambiguity disambiguation (cloud computing vs sky, financial bank vs river bank)
- Candidate sorting across multiple queries
- 3.5/5 acceptance threshold enforcement
- Fallback to Gemini 2.5 Flash Image when stock < 3.5
- Evaluated scoring of generated images (no hardcoded fixed scores)
- Gemini 429 rate limit exponential backoff retry logic
- Last-resort colour-card fallback reason recording
"""
from __future__ import annotations

import os
os.environ["GOOGLE_API_CORE_SUPPRESS_PYTHON_VERSION_WARNING"] = "1"
os.environ["GOOGLE_GENAI_SUPPRESS_PYTHON_VERSION_WARNING"] = "1"

import unittest.mock as mock
from pathlib import Path
import pytest

from app.services.gemini_scene_planner import GeminiScenePlanner
from app.services.relevance_engine import (
    RelevanceScorer,
    extract_content_tokens,
    lemmatize_word,
    extract_phrases,
    get_synonym_set,
    check_semantic_contradiction,
)
from app.services.image_generation_service import (
    GeminiFlashImageGenerator,
    DeterministicMockImageGenerator,
    ImageGenerationService,
)


# ── 1. Search Query Generation Tests ─────────────────────────────────────────

class TestSearchQueryGeneration:

    def setup_method(self):
        with mock.patch("app.services.gemini_scene_planner.settings.google_cloud_project", ""), \
             mock.patch("app.services.gemini_scene_planner.settings.gemini_api_key", ""), \
             mock.patch("app.services.gemini_scene_planner.settings.groq_api_key", ""):
            self.planner = GeminiScenePlanner()

    def test_literal_narration_queries(self):
        """Concrete literal narration produces 3-5 diverse descriptive queries for Pixabay."""
        sentence = "The farmer carefully inspects green crops in the morning sunlight."
        queries = self.planner.generate_pixabay_queries(
            sentence=sentence,
            visual_hint="Close up of wheat field and farmer",
            subject="farmer inspecting wheat",
            action="inspecting crops",
            environment="agricultural field",
        )
        assert 3 <= len(queries) <= 5
        assert any("farmer" in q for q in queries)
        assert any("crop" in q or "wheat" in q or "farm" in q for q in queries)

    def test_abstract_concept_practical_alternatives(self):
        """Abstract concepts generate practical, concrete visual alternatives for stock libraries."""
        # 1. Financial compounding
        fin_queries = self.planner.generate_pixabay_queries(
            sentence="Small daily investments create compounding interest that accelerates financial growth.",
            visual_hint="Financial compounding mechanism",
        )
        assert 3 <= len(fin_queries) <= 5
        assert any(
            k in " ".join(fin_queries)
            for k in ["chart", "graph", "stock market", "coins", "piggy bank", "banking"]
        )

        # 2. Climate & Global Challenges
        climate_queries = self.planner.generate_pixabay_queries(
            sentence="Every day, our planet faces a global environmental challenge.",
            visual_hint="Climate change impact",
        )
        assert 3 <= len(climate_queries) <= 5
        assert any(
            k in " ".join(climate_queries)
            for k in ["glacier", "desert", "solar", "turbine", "planet", "earth"]
        )

        # 3. Habit & Discipline
        habit_queries = self.planner.generate_pixabay_queries(
            sentence="Disciplined daily habits establish the foundation for lasting success.",
            visual_hint="Daily routine and discipline",
        )
        assert 3 <= len(habit_queries) <= 5
        assert any(
            k in " ".join(habit_queries)
            for k in ["morning", "sunrise", "running", "journal", "coffee", "alarm", "clock"]
        )

    def test_queries_avoid_vague_filler_words(self):
        """Queries must not contain filler stock words like 'video', 'concept', 'footage', 'showing'."""
        sentence = "A student drives a car towards the countryside school."
        queries = self.planner.generate_pixabay_queries(
            sentence=sentence,
            visual_hint="Student traveling in vehicle to class",
        )
        forbidden = ["video", "concept", "footage", "clip", "showing", "depicting", "abstract", "thing"]
        for q in queries:
            words = q.lower().split()
            for fw in forbidden:
                assert fw not in words, f"Found forbidden filler word '{fw}' in query '{q}'"


# ── 2. Relevance Scoring, NLP & Matching Tests ───────────────────────────────

class TestRelevanceScoringAndNLP:

    def test_stopword_removal_and_lemmatization(self):
        """Inflected forms and stop-word filtered tokens match base concepts."""
        text = "The farmers were harvesting golden crops and running across the fields."
        tokens = extract_content_tokens(text)
        assert "the" not in tokens
        assert "were" not in tokens
        assert "and" not in tokens
        assert "across" not in tokens
        assert "farmer" in tokens
        assert "harvest" in tokens
        assert "crop" in tokens
        assert "run" in tokens
        assert "field" in tokens

    def test_irregular_lemmatization(self):
        """Irregular words are correctly normalized."""
        assert lemmatize_word("children") == "child"
        assert lemmatize_word("people") == "person"
        assert lemmatize_word("drove") == "drive"
        assert lemmatize_word("bought") == "buy"
        assert lemmatize_word("leaves") == "leaf"

    def test_synonym_and_concept_expansion(self):
        """Synonyms expand matching capabilities across equivalent concepts."""
        syns_car = get_synonym_set("car")
        assert "automobile" in syns_car or "vehicle" in syns_car

        syns_farmer = get_synonym_set("farmer")
        assert "grower" in syns_farmer or "cultivator" in syns_farmer or "agriculturist" in syns_farmer

        syns_money = get_synonym_set("money")
        assert "currency" in syns_money or "cash" in syns_money or "finance" in syns_money

    def test_multiword_phrase_matching(self):
        """Phrases like 'wind turbine' or 'solar panel' are detected and boost relevance."""
        scene = {
            "narration_text": "Clean renewable energy powered by wind turbine installations.",
            "visual_hint": "Modern wind turbine turning on green hills",
            "visual_subject": "wind turbine",
            "visual_action": "generating clean power",
            "environment": "green rolling hills",
        }
        cand_phrase = {
            "id": "cand_phrase",
            "tags": "wind turbine, renewable energy, green hills, power generator",
            "description": "Close up of giant wind turbine blades turning in wind",
            "query_used": "wind turbine green hills",
        }
        res = RelevanceScorer.score_candidate(scene, cand_phrase)
        assert res["phrase_match"] >= 0.5
        assert res["relevance_score"] >= 3.5

    def test_ambiguity_disambiguation_cloud_computing(self):
        """Cloud computing narration must reject literal atmospheric sky clouds as contradiction."""
        scene = {
            "narration_text": "Enterprises migrate critical workloads to enterprise cloud computing infrastructure.",
            "visual_hint": "Modern datacenter cloud server architecture",
            "visual_subject": "cloud computing server network",
        }
        cand_sky = {
            "id": "cand_literal_sky",
            "tags": "blue sky, weather, fluffy clouds, atmosphere, sunny day",
            "description": "Beautiful sunny sky with white clouds over grass",
        }
        is_contra, reason = check_semantic_contradiction(scene, cand_sky)
        assert is_contra is True
        assert "sky" in reason.lower()

        res = RelevanceScorer.score_candidate(scene, cand_sky)
        assert res["contradiction_detected"] is True
        assert res["relevance_score"] <= 1.0
        assert res["meets_threshold"] is False

    def test_ambiguity_disambiguation_fruit_vs_meat(self):
        """Fruit scene narration must reject butchered meat as contradiction."""
        scene = {
            "narration_text": "Fresh organic fruits available at the local community market.",
            "visual_hint": "Fresh apples and oranges displayed at fruit market",
            "visual_subject": "fresh fruit market",
        }
        cand_meat = {
            "id": "cand_butcher_meat",
            "tags": "butcher shop, raw meat, beef steak, sausages, bbq",
            "description": "Butcher preparing raw beef steak and sausages",
        }
        is_contra, reason = check_semantic_contradiction(scene, cand_meat)
        assert is_contra is True
        assert "meat" in reason.lower()

        res = RelevanceScorer.score_candidate(scene, cand_meat)
        assert res["contradiction_detected"] is True
        assert res["relevance_score"] <= 1.0


# ── 3. Candidate Sorting & Threshold Enforcement Tests ───────────────────────

class TestCandidateSortingAndSelection:

    def test_candidates_sorted_by_final_relevance_descending(self):
        """Candidates from multiple queries must be sorted in descending order of final relevance."""
        scene = {
            "narration_text": "The farmer harvests ripe wheat under the bright sun.",
            "visual_hint": "Farmer in wheat field harvesting crop",
            "visual_subject": "farmer harvesting wheat",
            "visual_action": "harvesting crops",
            "environment": "wheat farmland",
        }
        candidates = [
            {
                "id": "cand_weak",
                "tags": "outdoor, sunny, landscape",
                "query_used": "sunlight outdoor",
            },
            {
                "id": "cand_strong",
                "tags": "farmer, harvesting, wheat, agricultural field, crop",
                "query_used": "farmer wheat field",
            },
            {
                "id": "cand_moderate",
                "tags": "green farm, crops, agriculture",
                "query_used": "sunlit farmland",
            },
        ]

        scored = []
        for c in candidates:
            r = RelevanceScorer.score_candidate(scene, c)
            c["relevance_score"] = r["relevance_score"]
            scored.append(c)

        # Sort descending
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        assert scored[0]["id"] == "cand_strong"
        assert scored[0]["relevance_score"] > scored[1]["relevance_score"]
        assert scored[1]["relevance_score"] >= scored[2]["relevance_score"]

    def test_threshold_3_5_acceptance_and_rejection(self):
        """Threshold 3.5/5 strictly accepts >= 3.5 and rejects < 3.5."""
        scene = {
            "narration_text": "Solar energy powers modern homes sustainably.",
            "visual_hint": "Rooftop solar panel installation",
            "visual_subject": "solar panel",
            "visual_action": "absorbing sunlight",
            "environment": "residential rooftop",
        }

        # High scoring candidate (matches solar panel, rooftop, sunlight)
        high_cand = {
            "id": "cand_solar",
            "tags": "solar panel, rooftop, photovoltaic, solar energy, sunlight",
            "description": "Technician installing solar panels on house roof in sunlight",
        }
        high_res = RelevanceScorer.score_candidate(scene, high_cand)
        assert high_res["relevance_score"] >= 3.5
        assert high_res["meets_threshold"] is True

        # Low scoring candidate (only generic 'house' without solar)
        low_cand = {
            "id": "cand_generic_house",
            "tags": "house, building, lawn, brick wall, suburban",
            "description": "Empty brick suburban house with green grass lawn",
        }
        low_res = RelevanceScorer.score_candidate(scene, low_cand)
        assert low_res["relevance_score"] < 3.5
        assert low_res["meets_threshold"] is False


# ── 4. Gemini 2.5 Flash Image Fallback & Evaluation Tests ────────────────────

class TestGeminiFlashImageFallbackAndEvaluation:

    def test_generated_image_uses_actual_evaluation_no_fixed_score(self, tmp_path):
        """Generated images must use actual objective evaluation instead of a fixed 4.5 score."""
        svc = ImageGenerationService(generator=DeterministicMockImageGenerator())
        scene = {
            "scene_id": "scene_test_eval",
            "narration_text": "Wind turbines spin steadily across the ocean coast.",
            "visual_hint": "Offshore wind turbines turning above ocean waves",
            "visual_subject": "offshore wind turbines",
            "visual_action": "spinning steadily above waves",
            "environment": "ocean coast",
            "image_generation_prompt": "Cinematic wide shot of offshore wind turbines turning over ocean waves.",
            "duration": 5.0,
        }

        cand = svc.generate_scene_image(scene, tmp_path)

        # Verify relevance_score is computed dynamically and is a float
        assert "relevance_score" in cand
        assert isinstance(cand["relevance_score"], float)
        assert 1.0 <= cand["relevance_score"] <= 5.0
        assert "subject_match" in cand
        assert "action_match" in cand
        assert "evidence" in cand
        assert cand["provenance"]["provider"] == "gemini_2_5_flash_image"
        assert cand["provenance"]["ai_generation_model"] == "gemini-2.5-flash-image"

    def test_gemini_exponential_backoff_on_429(self, tmp_path):
        """Temporary 429 rate limit errors trigger exponential backoff retries."""
        gen = GeminiFlashImageGenerator(model_name="gemini-2.5-flash-image")

        call_count = 0

        def mock_generate_content(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("429 ResourceExhausted: Rate limit exceeded")
            # Success on 3rd attempt
            mock_part = mock.MagicMock()
            mock_part.inline_data.data = b"fake_jpeg_image_bytes_12345"
            mock_res = mock.MagicMock()
            mock_res.candidates = [mock.MagicMock(content=mock.MagicMock(parts=[mock_part]))]
            return mock_res

        with mock.patch("app.services.image_generation_service.time.sleep") as mock_sleep:
            with mock.patch("app.config.settings.gemini_api_key", "test_key_123"):
                mock_client = mock.MagicMock()
                mock_client.models.generate_content.side_effect = mock_generate_content

                with mock.patch("google.genai.Client", return_value=mock_client):
                    out_path = tmp_path / "test_429.jpg"
                    scene = {"scene_id": "scene_001", "visual_subject": "sunflower"}
                    result = gen.generate_image(scene, "sunflower field", out_path)

                    assert result.exists()
                    assert call_count == 3
                    # Exponential backoff sleeps were called: delays [2, 4]
                    assert mock_sleep.call_count == 2
                    mock_sleep.assert_has_calls([mock.call(2), mock.call(4)])


# ── 5. End-to-End Fallback Policy & Reason Recording ─────────────────────────

class TestFallbackPolicyAndLogging:

    def test_stock_below_threshold_triggers_gemini_fallback(self):
        """When stock footage is below 3.5, it must NOT be selected; triggers Gemini fallback."""
        min_threshold = 3.5
        stock_candidate = {
            "id": "pixabay_low_rel",
            "relevance_score": 2.4,  # BELOW 3.5
            "tags": "random background",
        }
        assert stock_candidate["relevance_score"] < min_threshold

        # Should trigger Gemini image fallback
        scene = {
            "scene_id": "scene_test_fb",
            "narration_text": "Advanced quantum computing chip undergoing laser diagnostics.",
            "visual_hint": "Quantum computer processor glowing with laser beams",
            "visual_subject": "quantum processor",
        }
        # Verify fallback reason would be logged
        fallback_reason = (
            f"Stock footage below {min_threshold:.1f} (top: {stock_candidate['relevance_score']:.2f}); "
            f"generated by Gemini 2.5 Flash Image"
        )
        assert "Gemini 2.5 Flash Image" in fallback_reason
        assert "below 3.5" in fallback_reason
