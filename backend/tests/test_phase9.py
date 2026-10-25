"""
Phase 9 tests: Context-aware image generation and fallback behavior.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image
import pytest

from app.services.image_generation_service import (
    ImageGenerationService,
    DeterministicMockImageGenerator,
)
from app.services.visual_verifier import VisualVerificationService


def test_mock_image_generation_dimensions(tmp_path):
    svc = ImageGenerationService(generator=DeterministicMockImageGenerator())
    scene = {
        "scene_id": "scene_001",
        "semantic_description": "A financial balance graph steadily climbing.",
        "visual_subject": "growth balance graph",
        "image_generation_prompt": "Cinematic shot of upward line chart in modern office.",
        "duration": 5.0,
    }

    # Test 16:9
    cand_16x9 = svc.generate_scene_image(scene, tmp_path, aspect_ratio="16:9")
    img_path = Path(cand_16x9["local_path"])
    assert img_path.exists()
    with Image.open(img_path) as im:
        assert im.size == (1920, 1080)

    # Test 9:16
    cand_9x16 = svc.generate_scene_image(scene, tmp_path, aspect_ratio="9:16")
    img_9x16_path = Path(cand_9x16["local_path"])
    assert img_9x16_path.exists()
    with Image.open(img_9x16_path) as im:
        assert im.size == (1080, 1920)


def test_standalone_image_generation_for_clip_swap(tmp_path):
    svc = ImageGenerationService(generator=DeterministicMockImageGenerator())
    output_path = tmp_path / "swap.jpg"

    result = svc.generate_image(
        prompt="A modern solar farm at sunset",
        output_path=output_path,
        style="cinematic photo",
    )

    assert result == output_path
    assert output_path.exists()
    with Image.open(output_path) as im:
        assert im.size == (1920, 1080)


def test_image_generation_provenance_flag(tmp_path):
    svc = ImageGenerationService(generator=DeterministicMockImageGenerator())
    scene = {
        "scene_id": "scene_002",
        "semantic_description": "Person calculating monthly savings.",
        "visual_subject": "budget planner",
    }
    cand = svc.generate_scene_image(scene, tmp_path)
    prov = cand["provenance"]

    assert prov["ai_generated"] is True
    assert prov["commercial_use_eligible"] is True
    assert prov["verification_status"] == "ai_generated_verified"
    assert "ai_gen_" in cand["id"]


def test_generated_image_verified_by_vlm(tmp_path):
    svc = ImageGenerationService(generator=DeterministicMockImageGenerator())
    verifier = VisualVerificationService()
    scene = {
        "scene_id": "scene_003",
        "narration_text": "Compound returns build lasting security.",
        "semantic_description": "Visualizing compound return growth.",
        "visual_subject": "growth returns",
        "visual_action": "increasing capital",
        "narrative_role": "Resolution",
    }
    cand = svc.generate_scene_image(scene, tmp_path)
    img_path = Path(cand["local_path"])

    # Independent verifier runs on generated image
    ver_res = verifier.verify_candidate(scene, cand, [img_path])
    assert "verification_score" in ver_res
    assert ver_res["verification_score"] >= 2.5
