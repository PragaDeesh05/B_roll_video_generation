# Phase 0 Audit: Incubrix Context-Aware B-Roll Video Engine

## 1. Executive Summary & Baseline State

- **Workspace**: `c:\Users\praga\OneDrive\Documents\Downloads\video_gen_incubrix`
- **Baseline Test Suite**: `38 passed, 1 failed` in 79.27s (`test_gemini_fallback_on_error` failed due to calling `_call_gemini` instead of `_call_llm`).
- **Core Technology Stack Availability**:
  - Python 3.13.7
  - FFmpeg & FFprobe 9.0.2 (libx264, aac, yuv420p, libass all enabled and verified)
  - `open_clip_torch` 3.3.0, `torch` 2.14.1, `torchvision` 0.29.1+cpu
  - `openai-whisper`, `edge-tts`, `gTTS`, `pyttsx3`
  - `fastapi` 0.135.0, `pydantic` 2.12.5, `pydantic-settings` 2.16.0
  - `redis` 8.1.0, `fakeredis` 2.40.0
  - `pillow` 11.3.0, `opencv-python` 4.13.0
  - `diffusers`, `google-generativeai` 0.7.2

## 2. Root Cause Analysis of Visual Relevance Failures

| Failure Mode | Current Code Behavior | Root Cause | Affected Modules | Proposed Architecture Correction |
|---|---|---|---|---|
| **1. Narrow query losing narration meaning** | `GeminiScenePlanner` generates only `primary_search_query` and 2 alt queries per sentence chunk. | Conflation of semantic description and provider search query. Lack of Stage A (Global Narrative Analysis) and Stage B (Beat Planning). | `app/services/gemini_scene_planner.py`, `app/workers/video_pipeline.py` | Implement 3 distinct representations: `semantic_description`, `search_queries`, `image_generation_prompt`. Implement 3-stage LLM narrative planning (Global, Beat, Context-Aware Scene). |
| **2. Treating raw OpenCLIP threshold as proof of relevance** | `ENABLE_CLIP_RANKING=false` in `.env`. Ranking was purely heuristic tag keyword overlap count (`len(query_words & tags)`). | OpenCLIP was never actually integrated into candidate ranking in `video_pipeline.py`. | `app/workers/video_pipeline.py`, `app/services/pixabay_provider.py` | Add `OpenCLIPRanker` service computing separate `clip_score`, `query_similarity`, `semantic_similarity`, and calibrated `relevance_score`. |
| **3. Static frame selection for dynamic actions** | Pixabay provider picks the first metadata match without downloading or inspecting video frames. | No multi-frame extraction or temporal action verification. | `app/services/pixabay_provider.py`, `app/services/rendering_service.py` | Add `TemporalActionVerifier` that samples distributed frames across video candidate using FFmpeg and verifies action progression. |
| **4. Visual verification only after final selection or missing** | No independent vision-language verification exists in the codebase. | LLaVA / vision-language verifier was omitted. | Missing service module (`app/services/visual_verifier.py`) | Build `VisualVerifier` (LLaVA / Gemini Multimodal / local VLM adapter with deterministic mock) running **BEFORE** final selection to verify subject, action, context, and contradiction. |
| **5. Unique asset IDs as proof of diversity** | Simple `used_ids: Set[str]` set membership check. | No perceptual image hashing (dHash/pHash), embedding distance, or visual motif progression tracking. | `app/workers/video_pipeline.py` | Implement `VisualDiversityTracker` tracking exact hashes, perceptual hashes, OpenCLIP embedding distances, and motif repetition risk. |
| **6. Forgetting previous scenes in later scenes** | Scene planner asks for all scenes at once without passing preceding scenes, rolling summary, or established entities. | Stateless one-shot prompt without narrative memory. | `app/services/gemini_scene_planner.py` | Context-aware scene planning with rolling previous scene summary, established entities, recurring visual motifs, and continuity constraints. |
| **7. Generating technically valid images that do not match the intended scene** | `ENABLE_AI_IMAGE_FALLBACK=false` was set; no image generation adapter was integrated. | Missing context-aware image generation with visual reference constraints. | `app/services/image_generation_service.py` | Context-aware image generation (Gemini Imagen / Diffusion / mock adapter) taking narrative context, continuity reference, and avoid constraints. |
| **8. Individually plausible scenes failing to form a coherent story** | No full-video narrative continuity validation pass. | Missing post-planning validator. | `app/services/narrative_validator.py` | Full-video narrative continuity validator checking chronological progression, object continuity, contradiction detection, and repetition reduction before rendering. |

## 3. Database & Storage Architecture Audit

- **Current Database**: Single `Job` table in SQLite (`storage/broll.db`) containing serialized JSON strings for timeline and manifest.
- **Required Database**: Normalized relational records for `jobs`, `scenes`, `candidates`, `scores`, `provenance`, and `evaluation_ratings`.
- **Current Storage**: Direct local file writes.
- **Required Storage**: MinIO S3-compatible media storage adapter with deterministic local fallback, plus Redis queue with worker retry safety and idempotency.

## 4. API & Interface Contract Audit

- **Current Endpoints**: `/jobs` (text) and `/jobs/upload` (audio) with non-standard error codes.
- **Required Endpoints**:
  - `POST /api/v1/broll/jobs` (Audio file, audio URL, text script, or structured scene list `[{"text": "...", "visual_hint": "..."}]`)
  - `GET /api/v1/jobs/{job_id}`
  - `GET /health` & `GET /ready`
  - Uppercase error codes (`INVALID_INPUT_MODE`, `MEDIA_DECODE_ERROR`, `ALL_CANDIDATES_REJECTED`, etc.), retryability flag, `X-Correlation-Id`, and structured logging.
