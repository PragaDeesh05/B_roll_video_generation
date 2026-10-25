"""
Phase 5 tests: OpenCLIP candidate retrieval ranking (Stage 2 shortlist).
"""
from __future__ import annotations

import pytest
from app.services.openclip_ranker import DeterministicMockCLIPRanker, OpenCLIPRanker


def test_mock_clip_ranker_scores():
    ranker = DeterministicMockCLIPRanker()
    scene = {
        "semantic_description": "A close-up of a digital bank balance steadily growing through automatic recurring deposits.",
        "primary_search_query": "digital banking balance increase",
    }
    candidates = [
        {"id": "cand_01", "tags": "digital banking, bank balance, automatic deposit, growth"},
        {"id": "cand_02", "tags": "piggy bank, coins, cash currency"},
        {"id": "cand_03", "tags": "tropical beach, ocean sunset, sunny clouds"},
    ]

    shortlist = ranker.rank_candidates(scene, candidates, top_k=2)
    assert len(shortlist) == 2

    top_candidate = shortlist[0]
    # cand_01 has strong semantic match for digital banking / deposits
    assert top_candidate["id"] == "cand_01"

    # Distinct metrics recorded
    assert "clip_score" in top_candidate
    assert "semantic_similarity" in top_candidate
    assert "query_similarity" in top_candidate
    assert "relevance_score" in top_candidate

    # Verify score scales
    assert 0.0 <= top_candidate["clip_score"] <= 1.0
    assert 1.0 <= top_candidate["relevance_score"] <= 5.0

    # Ensure cand_01 ranked higher than beach
    cand_01_score = top_candidate["clip_score"]
    cand_02 = shortlist[1]
    assert cand_01_score >= cand_02["clip_score"]


def test_openclip_lazy_load_interface():
    # Model instantiation is lazy; shouldn't fail or load weights on init
    real_ranker = OpenCLIPRanker(model_name="ViT-B-32")
    assert real_ranker._model is None
    assert real_ranker.device in ("cpu", "cuda")
