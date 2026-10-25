export interface JobStatus {
  job_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed' | string
  input_type: 'text' | 'audio' | 'structured_scenes' | string
  input_text?: string | null
  script_text?: string | null
  progress: number
  progress_pct?: number | null
  scenes_count?: number | null
  current_stage: string | null
  stage_detail: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_code: string | null
  error_message: string | null
  error_detail: string | null
  retry_count: number
  aspect_ratios: string[]
  language: string
  target_language?: string | null
  narration_language?: string | null
  subtitle_language?: string | null
  style_preferences?: string | null
  avoid_constraints?: string[]
  artifacts: {
    timeline?: string
    manifest?: string
    captions?: string
    validation_report?: string
    videos?: string[]
    video_urls?: string[]
    evaluation_csv?: string
    evaluation_json?: string
    minio_storage?: Record<string, any>
  } | null
}

export interface SceneProvenance {
  provider: string
  asset_id: string
  original_url?: string | null
  media_url?: string | null
  licence_name?: string
  licence_url?: string
  attribution_required?: boolean
  attribution_text?: string
  commercial_use_eligible?: boolean
  verification_status?: string
  verification_method?: string
  retrieved_at?: string
  ai_generated?: boolean
  ai_generation_provider?: string
  ai_generation_model?: string
  mock_fallback?: boolean
}

export interface Scene {
  scene_id: string
  scene_index: number
  start_time: number
  end_time: number
  duration: number
  narration_text: string
  transcript_text?: string
  scene_summary?: string
  narrative_beat?: string
  narrative_role?: string
  semantic_description?: string
  visual_description?: string
  visual_subject: string
  visual_action?: string
  primary_search_queries?: string[]
  primary_search_query?: string
  alternative_search_queries?: string[]
  image_generation_prompt?: string
  selected_asset_id?: string
  selected_asset_url?: string
  provenance?: SceneProvenance | string
  clip_score?: number
  query_similarity?: number
  semantic_similarity?: number
  relevance_score?: number
  verification_score?: number
  temporal_score?: number
  temporal_evidence?: any
  selection_reason?: string
  rejection_reason?: string
  relevance_explanation?: string
  safety_flags?: string[]
  ai_generated?: boolean
  color_normalization?: boolean
  validation_status?: string
}

export interface Timeline {
  job_id: string
  narration_duration: number
  output_profile: string
  generated_at: string
  metadata?: {
    input_type?: string
    language?: string
    target_language?: string | null
    narration_duration?: number
    color_normalization_enabled?: boolean
    min_scene_duration_seconds?: number
    script_length_chars?: number
    script_preview?: string
  }
  scenes: Scene[]
}

export interface CandidateScore {
  candidate_id: string
  clip_score: number | null
  query_similarity?: number | null
  semantic_similarity?: number | null
  relevance_score: number | null
  verification_score: number | null
  subject_match: number | null
  action_match: number | null
  context_match?: number | null
  contradiction_detected: boolean
  repetition_risk: number | null
  temporal_score?: number | null
  diversity_score?: number | null
  final_rank?: number | null
  is_selected: boolean
}

export interface CandidatesResponse {
  job_id: string
  scenes: Record<string, CandidateScore[]>
}

export interface EvaluationRow {
  job_id?: string
  scene_id: string
  narration_text: string
  semantic_description?: string
  narrative_role?: string
  visual_subject?: string
  visual_action?: string
  query?: string
  selected_asset_id?: string
  provider?: string
  licence_status?: string
  attribution?: string
  clip_score?: any
  query_similarity?: any
  semantic_similarity?: any
  relevance_score?: any
  verification_score?: any
  subject_match?: any
  action_match?: any
  temporal_evidence?: any
  diversity_score?: any
  repetition_risk?: any
  selection_reason?: string
  rejection_reason?: string
  is_ai_generated?: boolean
  ai_generated?: boolean
  start_time?: number
  end_time?: number
  duration?: number
  human_rating?: any
  human_notes?: string
  contradiction_detected?: boolean
}

export interface EvaluationResponse {
  job_id: string
  metrics: Record<string, any>
  csv_download_url: string
  rows: EvaluationRow[]
}

export interface JobLog {
  timestamp: string
  level: 'INFO' | 'WARNING' | 'ERROR' | string
  stage: string
  progress: number
  message: string
}

export interface JobLogsResponse {
  job_id: string
  logs: JobLog[]
}

export interface HealthResponse {
  status: string
  version: string
  ffmpeg: boolean
  ffprobe: boolean
}

export interface ReadyResponse {
  ready: boolean
  missing_keys: string[]
  ffmpeg_available?: boolean
  ffprobe_available?: boolean
  db_connected?: boolean
  database?: boolean
  ffmpeg?: boolean
  ffprobe?: boolean
}

export interface ClipSwapRequest {
  candidateId?: string
  mediaUrl?: string
  generatePrompt?: string
  file?: File
}

export interface ClipSwapResponse {
  status: string
  job_id: string
  scene_id: string
  scene_index: number
  swapped_asset: string
  is_image: boolean
  duration_seconds: number
  render_duration_seconds: number
  output_videos: Array<{
    aspect_ratio: string
    filename: string
    download_url: string
    file_size_bytes: number
    updated_at?: string
  }>
  output_path?: string
  video_url?: string
  message?: string
  updated_scene: Record<string, any>
}

export interface ActiveSwapTask {
  jobId: string
  sceneId: string
  sceneIndex: number
  targetSceneSubject?: string
  status: 'uploading' | 'processing' | 'success' | 'failed'
  progressStep: string
  details: string[]
  error?: string | null
  durationSeconds?: number
  swappedAsset?: string
  outputPath?: string
  videoUrl?: string
  startTime: number
  finishTime?: number
}
