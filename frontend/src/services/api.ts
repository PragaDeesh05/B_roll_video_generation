import {
  JobStatus,
  Timeline,
  Scene,
  CandidateScore,
  CandidatesResponse,
  EvaluationResponse,
  EvaluationRow,
  JobLogsResponse,
  HealthResponse,
  ReadyResponse,
  ClipSwapRequest,
  ClipSwapResponse,
} from '../types'

export type {
  JobStatus,
  Timeline,
  Scene,
  CandidateScore,
  CandidatesResponse,
  EvaluationResponse,
  EvaluationRow,
  JobLogsResponse,
  HealthResponse,
  ReadyResponse,
  ClipSwapRequest,
  ClipSwapResponse,
}

const API_JOBS = '/api/v1/jobs'
const LEGACY_JOBS = '/jobs'

export async function listJobs(limit: number = 50): Promise<JobStatus[]> {
  const resp = await fetch(`${API_JOBS}?limit=${limit}`)
  if (!resp.ok) {
    const fallback = await fetch(`${LEGACY_JOBS}?limit=${limit}`)
    if (!fallback.ok) throw new Error(`Failed to list jobs: ${resp.status}`)
    return fallback.json()
  }
  return resp.json()
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const resp = await fetch(`${API_JOBS}/${jobId}`)
  if (!resp.ok) {
    const fallback = await fetch(`${LEGACY_JOBS}/${jobId}`)
    if (!fallback.ok) throw new Error(`Job not found: ${jobId}`)
    return fallback.json()
  }
  return resp.json()
}

export async function cancelJob(jobId: string): Promise<any> {
  const resp = await fetch(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' })
  if (!resp.ok) {
    return { status: 'cancelled', job_id: jobId }
  }
  return resp.json()
}

export async function retryJob(jobId: string): Promise<JobStatus> {
  const resp = await fetch(`/api/v1/jobs/${jobId}/retry`, { method: 'POST' })
  if (!resp.ok) {
    return getJobStatus(jobId)
  }
  return resp.json()
}

export async function submitTextJob(
  scriptText: string,
  aspectRatios: string[] = ['16:9'],
  language: string = 'en',
  targetLanguage?: string | null,
  stylePreferences?: string,
  avoidConstraints?: string[],
  narrationLanguage?: string | null,
  subtitleLanguage: string = 'en'
): Promise<JobStatus> {
  const payload = {
    input_type: 'text',
    script_text: scriptText,
    aspect_ratios: aspectRatios,
    language,
    target_language: targetLanguage || null,
    narration_language: narrationLanguage || null,
    subtitle_language: subtitleLanguage || 'en',
    style_preferences: stylePreferences || null,
    avoid_constraints: avoidConstraints || [],
  }

  // Try v1 unified endpoint first
  const resp = await fetch('/api/v1/broll/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (resp.ok) {
    return resp.json()
  }

  // Fallback to legacy
  const fallback = await fetch(LEGACY_JOBS, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!fallback.ok) {
    const err = await fallback.json().catch(() => ({ detail: 'Failed to create job' }))
    throw new Error(err.message || err.detail || `HTTP ${fallback.status}`)
  }

  return fallback.json()
}

export async function submitAudioJob(
  file: File,
  aspectRatios: string[] = ['16:9'],
  language: string = 'en',
  targetLanguage?: string | null,
  stylePreferences?: string,
  avoidConstraints?: string[],
  narrationLanguage?: string | null,
  subtitleLanguage: string = 'en'
): Promise<JobStatus> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('aspect_ratios', JSON.stringify(aspectRatios))
  formData.append('language', language)
  if (targetLanguage) formData.append('target_language', targetLanguage)
  if (narrationLanguage) formData.append('narration_language', narrationLanguage)
  if (subtitleLanguage) formData.append('subtitle_language', subtitleLanguage)
  if (stylePreferences) formData.append('style_preferences', stylePreferences)
  if (avoidConstraints && avoidConstraints.length > 0) {
    formData.append('avoid_constraints', JSON.stringify(avoidConstraints))
  }

  const resp = await fetch(`${LEGACY_JOBS}/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to upload audio' }))
    throw new Error(err.message || err.detail || `HTTP ${resp.status}`)
  }

  return resp.json()
}

export async function getTimeline(jobId: string): Promise<Timeline> {
  const resp = await fetch(`${LEGACY_JOBS}/${jobId}/timeline`)
  if (!resp.ok) throw new Error(`Timeline not available: HTTP ${resp.status}`)
  return resp.json()
}
export const getJobTimeline = getTimeline

export async function getManifest(jobId: string): Promise<any> {
  const resp = await fetch(`${LEGACY_JOBS}/${jobId}/manifest`)
  if (!resp.ok) throw new Error(`Manifest not available: HTTP ${resp.status}`)
  return resp.json()
}

export async function getValidation(jobId: string): Promise<any> {
  const resp = await fetch(`${LEGACY_JOBS}/${jobId}/validation`)
  if (!resp.ok) throw new Error(`Validation report not available: HTTP ${resp.status}`)
  return resp.json()
}

export async function getCandidates(jobId: string): Promise<CandidatesResponse> {
  const resp = await fetch(`/api/v1/jobs/${jobId}/candidates`)
  if (!resp.ok) throw new Error(`Candidates not available: HTTP ${resp.status}`)
  return resp.json()
}
export const getJobCandidates = getCandidates

export async function getEvaluation(jobId: string): Promise<EvaluationResponse> {
  const resp = await fetch(`/api/v1/jobs/${jobId}/evaluation`)
  if (!resp.ok) throw new Error(`Evaluation sheet not available: HTTP ${resp.status}`)
  return resp.json()
}
export const getJobEvaluation = getEvaluation

export async function rateScene(
  jobId: string,
  sceneId: string,
  rating: number,
  notes: string = ''
): Promise<any> {
  const resp = await fetch(`/api/v1/jobs/${jobId}/evaluation/rate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scene_id: sceneId, rating, notes }),
  })
  if (!resp.ok) throw new Error(`Rating failed: HTTP ${resp.status}`)
  return resp.json()
}

export async function getJobLogs(jobId: string): Promise<JobLogsResponse> {
  const resp = await fetch(`/api/v1/jobs/${jobId}/logs`)
  if (!resp.ok) throw new Error(`Logs not available: HTTP ${resp.status}`)
  return resp.json()
}

export async function getHealth(): Promise<HealthResponse> {
  const resp = await fetch('/health')
  if (!resp.ok) throw new Error(`Health check failed: HTTP ${resp.status}`)
  return resp.json()
}

export async function getReady(): Promise<ReadyResponse> {
  const resp = await fetch('/ready')
  if (!resp.ok) throw new Error(`Readiness check failed: HTTP ${resp.status}`)
  return resp.json()
}
export const getReadiness = getReady

export function getVideoDownloadUrl(jobId: string, filename: string = 'output_16x9.mp4'): string {
  return `${LEGACY_JOBS}/${jobId}/download/${filename}`
}

export function getCaptionsDownloadUrl(jobId: string): string {
  return `${LEGACY_JOBS}/${jobId}/download/captions.srt`
}

export function getTimelineDownloadUrl(jobId: string): string {
  return `${LEGACY_JOBS}/${jobId}/timeline`
}

export function getManifestDownloadUrl(jobId: string): string {
  return `${LEGACY_JOBS}/${jobId}/manifest`
}

export function getEvaluationCsvDownloadUrl(jobId: string): string {
  return `${LEGACY_JOBS}/${jobId}/download/evaluation_sheet.csv`
}

export function getArtifactDownloadUrl(jobId: string, artifactType: string): string {
  if (artifactType === 'captions') return `${LEGACY_JOBS}/${jobId}/captions`
  if (artifactType === 'timeline') return `${LEGACY_JOBS}/${jobId}/timeline`
  if (artifactType === 'manifest') return `${LEGACY_JOBS}/${jobId}/manifest`
  if (artifactType === 'evaluation_csv') return `${LEGACY_JOBS}/${jobId}/download/evaluation_sheet.csv`
  if (artifactType === 'validation') return `${LEGACY_JOBS}/${jobId}/validation`
  return `${LEGACY_JOBS}/${jobId}/download/${artifactType}`
}

export async function swapSceneClip(
  jobId: string,
  sceneId: string,
  data: {
    candidateId?: string
    mediaUrl?: string
    generatePrompt?: string
    file?: File
  }
): Promise<ClipSwapResponse> {
  if (data.file) {
    const formData = new FormData()
    formData.append('file', data.file)
    if (data.candidateId) formData.append('candidate_id', data.candidateId)
    if (data.mediaUrl) formData.append('media_url', data.mediaUrl)
    if (data.generatePrompt) formData.append('generate_prompt', data.generatePrompt)

    const res = await fetch(`${API_JOBS}/${jobId}/scenes/${sceneId}/swap-clip`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to swap clip')
    }
    return res.json()
  } else {
    const res = await fetch(`${API_JOBS}/${jobId}/scenes/${sceneId}/swap-clip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        candidate_id: data.candidateId,
        media_url: data.mediaUrl,
        generate_prompt: data.generatePrompt,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to swap clip')
    }
    return res.json()
  }
}
