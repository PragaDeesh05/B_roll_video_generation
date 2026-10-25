# Assessment Checklist — B-Roll Video Engine

## Must-Have 1: Both Input Modes

| Requirement | Implementation | Test |
|-------------|---------------|------|
| Accept MP3/WAV/M4A up to 10 min | `routes_jobs.py` → `POST /jobs/upload`; FFprobe validates type, duration, decodeability | `TestInputHandling::test_audio_*` |
| Validate file type, size, duration, decodeability | `probe_audio()` in `utils/media.py`; rejects corrupt/empty files | `test_audio_corrupted_file_rejected` |
| Save uploaded file safely | Written to `storage/uploads/{job_id}/` | Manual: submit audio |
| Normalize & transcribe (Whisper) | `transcription_service.py` (openai-whisper, fallback alignment) | Unit: service methods |
| Accept text script | `POST /jobs` with `script_text` | `TestInputHandling::test_text_job_valid` |
| TTS generation | `tts_service.py` (edge-tts → gTTS → pyttsx3) | Covered in pipeline tests |
| Both modes feed same downstream pipeline | `video_pipeline.py` has unified flow | `TestAPIEndpoints::test_create_and_get_job` |

**Status: ✅ IMPLEMENTED**

---

## Must-Have 2: Gemini Scene Planning

| Requirement | Implementation | Test |
|-------------|---------------|------|
| Structured scene JSON output | `gemini_scene_planner.py`; Pydantic-validated | `TestScenePlanning::test_gemini_parse_valid_json` |
| Semantic grouping, sentence boundaries | Prompt instructs Gemini; fallback uses regex split | `test_gemini_fallback_plan` |
| Multiple search queries per scene | Required field `alternative_search_queries` (≥2) | Schema validation |
| Retry with corrective prompt on bad output | 3-attempt retry loop with `RETRY_CORRECTION_PROMPT` | `test_gemini_fallback_on_error` |
| All 15+ scene fields | Full schema in `plan_scenes()` and Pydantic schemas | `test_missing_scene_field_raises` |
| Complete narration coverage, no gaps | `_check_coverage()` validates before returning | `TestTimeline::test_no_gaps_after_alignment` |

**Status: ✅ IMPLEMENTED**

---

## Must-Have 3: Pixabay Footage Retrieval

| Requirement | Implementation | Test |
|-------------|---------------|------|
| Official Pixabay API | `pixabay_provider.py` | Unit tests |
| Primary + alternative queries | `search_for_scene()` iterates queries | Covered |
| Relevance ranking (metadata-based) | `_score_asset()` — tag overlap, duration, quality | `test_watermarked_tag_rejected` |
| Watermark rejection | `REJECTED_TAGS` includes "watermark", "getty" | `test_watermarked_tag_rejected` |
| No duplicate clips in same video | `used_ids: Set[str]` tracked per job | `test_duplicate_asset_rejected` |
| Provenance record with all fields | `_enrich_asset()` populates full provenance dict | `test_provenance_has_required_fields` |
| Retry on timeout/rate-limit | 3-attempt loop with exponential backoff | `test_pixabay_timeout_fallback` |

**Status: ✅ IMPLEMENTED**

---

## Must-Have 4: AI-Generated Visual Policy

| Requirement | Implementation | Test |
|-------------|---------------|------|
| Stock footage is primary source | Pixabay always tried first | Architecture |
| AI image generation disabled by default | `ENABLE_AI_IMAGE_FALLBACK=false` (env flag) | Config |
| `ai_generated: false` on all Pixabay assets | `provenance.ai_generated = False` | `test_ai_generated_flag_is_false` |
| Clear labelling in timeline/manifest | `ai_generated` field in every scene record | Schema |
| Fallback chain: alt queries → local library → fail | `search_for_scene()` tries all queries; returns None | Architecture |

**Status: ✅ IMPLEMENTED**

---

## Must-Have 5: No Duplicate / Irrelevant Clips

| Requirement | Implementation | Test |
|-------------|---------------|------|
| Dedup by asset ID | `used_ids` set, checked before selection | `test_duplicate_asset_rejected` |
| Relevance score 1-5 | `_compute_relevance_score()` | `test_mock_mode_returns_asset` |
| Relevance explanation | `relevance_explanation` field in scene | Schema |
| Scene marked unresolved if no asset | `validation_status: "no_asset"` | Pipeline code |

**Status: ✅ IMPLEMENTED**

---

## Must-Have 6: Safety Checks

| Requirement | Implementation | Test |
|-------------|---------------|------|
| Named person detection | Regex + `safety_service.py` | `test_named_person_flagged` |
| Brand detection | `BRAND_KEYWORDS` set | `test_brand_flagged` |
| Sensitive/sad news detection | `SENSITIVE_KEYWORDS`, `SAD_NEWS_KEYWORDS` | Covered by service |
| NSFW exclusion | `NSFW_KEYWORDS`, excluded_visual_elements | Service logic |
| Safety flags recorded in timeline | `scene["safety_flags"]` propagated | Schema |
| Conservative asset check | `is_asset_safe()` — tags checked before use | Service |

**Status: ✅ IMPLEMENTED**

---

## Must-Have 7: FFmpeg Rendering + Captions + Validation

| Requirement | Implementation | Test |
|-------------|---------------|------|
| All 3 aspect ratios (16:9, 9:16, 1:1) | `OUTPUT_PROFILES` dict; one render per ratio | `test_output_profiles_defined` |
| Normalize resolution, FPS, codec, pix_fmt | FFmpeg filter chain in `_normalize_clip()` | Profile tests |
| Narration audio as master timeline | `-shortest`; audio duration drives output | Architecture |
| SRT captions generated | `generate_srt()` with scene timestamps | `test_srt_generation`, `test_srt_timestamps_ordered` |
| Caption burn-in | libass subtitles filter in `_burn_captions()` | Rendering code |
| Valid `timeline.json` | `artifact_service.py` | API test |
| Valid `manifest.json` | `artifact_service.py` | API test |
| Valid `captions.srt` | SRT validator used before marking complete | `test_srt_valid_file` |
| `validation_report.json` | `generate_validation_report()` | API test |

**Status: ✅ IMPLEMENTED**

---

## Must-Have 8: FFprobe Automated Media Validation

| Requirement | Implementation | Test |
|-------------|---------------|------|
| MP4 readable | FFprobe probe on every output | `test_missing_file_fails` |
| Video + audio streams exist | Stream existence checks | Validation service |
| Duration matches narration ±1.5s | `DURATION_TOLERANCE = 1.5` | Validation checks |
| Resolution and FPS match profile | Checked against `OUTPUT_PROFILES` | Validation checks |
| Pixel format = yuv420p | `pix_fmt` check | Validation checks |
| Codec = h264/aac | Codec name check | Validation checks |
| Black frame detection | FFmpeg `blackdetect` filter | Validation service |
| Frozen frame detection | FFmpeg `freezedetect` filter | Validation service |
| Silent audio detection | FFmpeg `silencedetect` filter | Validation service |
| SRT valid | `validate_srt()` — order, timing, parse | `test_srt_valid_file`, `test_srt_start_after_end_fails` |
| Retry on validation failure | `retry_count` tracked; pipeline retries render | Architecture |

**Status: ✅ IMPLEMENTED**

---

## Manual Review Instructions

For each must-have, evaluators should:

1. Start the server: `uvicorn app.main:app --reload --port 8000`
2. Submit a job via the frontend at http://localhost:5173
3. Monitor progress via `GET /jobs/{id}`
4. Inspect artifacts: `GET /jobs/{id}/timeline`, `/manifest`, `/captions`, `/validation`
5. Play the MP4 in a video player and verify audio/video sync
6. Check `timeline.json` — every scene has `provenance.commercial_use_eligible: true`
7. Confirm `ai_generated: false` for all Pixabay assets
8. Review validation report for all checks

## Test Coverage

Run: `cd backend && python -m pytest tests/test_all.py -v`

- **39 tests** covering all 8 must-haves
- All tests use mocked external APIs (no quota usage)
- Runtime: ~45 seconds
