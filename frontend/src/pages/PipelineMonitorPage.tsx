import React, { useState, useEffect, useRef } from 'react'
import { JobStatus, JobLog } from '../types'
import { getJobLogs, getJobStatus, cancelJob } from '../services/api'
import { StatusBadge } from '../components/StatusBadge'
import './PipelineMonitorPage.css'

export interface PipelineMonitorPageProps {
  jobId: string | null
  job: JobStatus | null
  allJobs: JobStatus[]
  onSelectJob: (jobId: string) => void
  onNavigate: (tab: any) => void
  onRefreshJob: () => void
}

// Complete 11 architectural stages from video_pipeline.py
export const PIPELINE_STAGES = [
  { key: 'input_validation', label: '1. Validation', desc: 'Validates script, inputs, aspect ratios' },
  { key: 'audio_processing', label: '2. Audio / TTS', desc: 'Generates scene-wise speech & timestamps' },
  { key: 'scene_planning', label: '3. Scene Planner', desc: 'Gemini plans beats, visual subjects & queries' },
  { key: 'candidate_retrieval', label: '4. Pixabay Fetch', desc: 'Queries stock API for candidates' },
  { key: 'candidate_evaluation', label: '5. Relevance & VLM', desc: 'Ranks candidates; samples 20/50/80% keyframes' },
  { key: 'visual_generation', label: '6. AI Fallback', desc: 'Generates high-res image if score < 3.5' },
  { key: 'timeline_assembly', label: '7. Timeline Assembly', desc: 'Locks cuts, transitions & aspect ratio scaling' },
  { key: 'narration_alignment', label: '8. Audio Alignment', desc: 'Stitches scene audio with zero drift' },
  { key: 'subtitle_generation', label: '9. Subtitles', desc: 'Generates synchronized SRT & WebVTT' },
  { key: 'video_rendering', label: '10. FFmpeg Render', desc: 'Single-pass ultrafast H.264 encode' },
  { key: 'cleanup_and_export', label: '11. MinIO Export', desc: 'Persists artifacts & 30-col audit metrics' },
]

export const PipelineMonitorPage: React.FC<PipelineMonitorPageProps> = ({
  jobId,
  job,
  allJobs,
  onSelectJob,
  onNavigate,
  onRefreshJob,
}) => {
  const [logs, setLogs] = useState<JobLog[]>([])
  const [isLoadingLogs, setIsLoadingLogs] = useState(false)
  const [logFilter, setLogFilter] = useState<'all' | 'INFO' | 'WARNING' | 'ERROR'>('all')
  const [logSearch, setLogSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [copiedLogs, setCopiedLogs] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)

  // Fetch logs whenever jobId changes or job progress changes
  useEffect(() => {
    if (!jobId) {
      setLogs([])
      return
    }

    let isMounted = true
    const fetchLogs = async () => {
      try {
        const data = await getJobLogs(jobId)
        if (isMounted) {
          setLogs(data.logs || [])
        }
      } catch (err) {
        console.warn('Could not fetch logs:', err)
      }
    }

    fetchLogs()

    // Polling logs if job is actively processing
    let interval: any = null
    if (job?.status === 'processing' || job?.status === 'queued') {
      interval = setInterval(() => {
        fetchLogs()
        onRefreshJob()
      }, 2500)
    }

    return () => {
      isMounted = false
      if (interval) clearInterval(interval)
    }
  }, [jobId, job?.status, job?.current_stage])

  // Auto-scroll logs
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  // Filtered logs
  const filteredLogs = logs.filter((log) => {
    if (logFilter !== 'all' && log.level.toUpperCase() !== logFilter) {
      return false
    }
    if (logSearch.trim()) {
      const q = logSearch.toLowerCase().trim()
      const matchMsg = log.message.toLowerCase().includes(q)
      const matchStage = log.stage?.toLowerCase().includes(q) || false
      if (!matchMsg && !matchStage) return false
    }
    return true
  })

  const handleCopyLogs = () => {
    const text = logs
      .map((l) => `[${l.timestamp}] [${l.level}] [${l.stage || 'GLOBAL'}] ${l.message}`)
      .join('\n')
    navigator.clipboard.writeText(text)
    setCopiedLogs(true)
    setTimeout(() => setCopiedLogs(false), 2000)
  }

  const handleCancel = async () => {
    if (!jobId) return
    if (!confirm('Are you sure you want to cancel this running pipeline job?')) return
    setIsCancelling(true)
    try {
      await cancelJob(jobId)
      onRefreshJob()
    } catch (err) {
      alert(`Error cancelling job: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsCancelling(false)
    }
  }

  // Find current stage index in our 11 stages
  const currentStageIndex = PIPELINE_STAGES.findIndex(
    (s) => s.key === job?.current_stage
  )

  const getStageStatus = (index: number) => {
    if (!job) return 'pending'
    if (job.status === 'completed') return 'completed'
    if (job.status === 'failed' && currentStageIndex === index) return 'failed'
    if (currentStageIndex > index) return 'completed'
    if (currentStageIndex === index) return job.status === 'processing' ? 'active' : 'pending'
    return 'pending'
  }

  if (!jobId || !job) {
    return (
      <div className="pipeline-monitor-page empty-selection">
        <div className="empty-card">
          <span className="empty-icon">⚡</span>
          <h2>No Job Selected for Monitoring</h2>
          <p>Please select an existing video job from the list or create a new one to monitor its live pipeline execution.</p>
          <div className="empty-actions">
            {allJobs.length > 0 ? (
              <div className="quick-job-picker">
                <span>Select a job:</span>
                <select
                  className="job-select-dropdown"
                  onChange={(e) => onSelectJob(e.target.value)}
                  defaultValue=""
                >
                  <option value="" disabled>Choose job to monitor...</option>
                  {allJobs.map((j) => (
                    <option key={j.job_id} value={j.job_id}>
                      {j.job_id.slice(0, 8)} — [{j.status.toUpperCase()}] {j.input_text?.slice(0, 40) || 'Audio Job'}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <button className="primary-btn" onClick={() => onNavigate('create')}>
                Create First Video
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="pipeline-monitor-page">
      {/* Header bar with Job Status & Quick Switcher */}
      <div className="monitor-header">
        <div className="monitor-title-meta">
          <div className="title-row">
            <h2>Pipeline Execution Monitor</h2>
            <StatusBadge status={job.status} stage={job.current_stage} />
          </div>
          <div className="job-id-subtitle">
            <span>Job ID: <code>{job.job_id}</code></span>
            <span>•</span>
            <span>Created: {new Date(job.created_at).toLocaleTimeString()}</span>
            {job.completed_at && (
              <>
                <span>•</span>
                <span>Finished: {new Date(job.completed_at).toLocaleTimeString()}</span>
              </>
            )}
          </div>
        </div>

        <div className="monitor-actions">
          {job.status === 'processing' && (
            <button
              className="cancel-job-btn"
              onClick={handleCancel}
              disabled={isCancelling}
            >
              ⛔ Cancel Pipeline
            </button>
          )}

          {job.status === 'completed' && (
            <>
              <button className="view-btn outline" onClick={() => onNavigate('scenes')}>
                🔬 Inspect Scenes
              </button>
              <button className="view-btn primary" onClick={() => onNavigate('library')}>
                ▶ Watch Video
              </button>
            </>
          )}

          <button className="refresh-logs-btn" onClick={onRefreshJob} title="Refresh pipeline state">
            ↻
          </button>
        </div>
      </div>

      {/* Progress & Stats Bar */}
      <div className="progress-hero-card">
        <div className="progress-hero-header">
          <div className="hero-status-text">
            <span className="current-stage-title">
              Current Stage: <strong>{job.current_stage || 'Initializing pipeline...'}</strong>
            </span>
            <span className="hero-message">{job.error_message || 'Pipeline executing normally'}</span>
          </div>
          <div className="hero-pct">
            {Math.round(job.progress_pct || (job.status === 'completed' ? 100 : 0))}%
          </div>
        </div>

        <div className="progress-bar-container">
          <div
            className={`progress-bar-fill ${job.status}`}
            style={{ width: `${job.progress_pct || (job.status === 'completed' ? 100 : 0)}%` }}
          />
        </div>

        <div className="pipeline-metrics-grid">
          <div className="metric-box">
            <span className="metric-lbl">Target Resolution</span>
            <span className="metric-val">1080p (Full HD)</span>
          </div>
          <div className="metric-box">
            <span className="metric-lbl">Language</span>
            <span className="metric-val">{(job.language || 'en').toUpperCase()}</span>
          </div>
          <div className="metric-box">
            <span className="metric-lbl">Total Scenes</span>
            <span className="metric-val">{job.scenes_count || 'Pending planning'}</span>
          </div>
          <div className="metric-box">
            <span className="metric-lbl">VLM Min Threshold</span>
            <span className="metric-val">3.5 / 5.0 (Passed)</span>
          </div>
        </div>
      </div>

      {/* 11-Stage Pipeline Stepper */}
      <div className="stepper-card">
        <div className="stepper-header">
          <h3>Architectural Pipeline Stages</h3>
          <span className="stepper-subtitle">11-stage autonomous synthesis & rendering pipeline</span>
        </div>

        <div className="pipeline-stepper-grid">
          {PIPELINE_STAGES.map((stage, idx) => {
            const status = getStageStatus(idx)
            return (
              <div key={stage.key} className={`stepper-node ${status}`}>
                <div className="node-indicator">
                  {status === 'completed' && <span className="icon-check">✓</span>}
                  {status === 'active' && <span className="icon-spinner" />}
                  {status === 'failed' && <span className="icon-fail">✕</span>}
                  {status === 'pending' && <span className="icon-num">{idx + 1}</span>}
                </div>
                <div className="node-details">
                  <div className="node-label">{stage.label}</div>
                  <div className="node-desc">{stage.desc}</div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Live Structured Logs Viewer */}
      <div className="logs-card">
        <div className="logs-header">
          <div className="logs-title-wrap">
            <h3>Structured Execution Logs</h3>
            <span className="logs-count">({filteredLogs.length} events)</span>
          </div>

          <div className="logs-controls">
            {/* Search Input */}
            <input
              type="text"
              className="log-search-input"
              placeholder="Filter logs by keyword..."
              value={logSearch}
              onChange={(e) => setLogSearch(e.target.value)}
            />

            {/* Level filter */}
            <div className="level-filters">
              {(['all', 'INFO', 'WARNING', 'ERROR'] as const).map((lvl) => (
                <button
                  key={lvl}
                  className={`lvl-pill ${logFilter === lvl ? 'active' : ''}`}
                  onClick={() => setLogFilter(lvl)}
                >
                  {lvl}
                </button>
              ))}
            </div>

            {/* Auto-scroll toggle */}
            <label className="autoscroll-toggle">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
              />
              <span>Auto-scroll</span>
            </label>

            {/* Copy button */}
            <button className="copy-logs-btn" onClick={handleCopyLogs}>
              {copiedLogs ? '✓ Copied' : '📋 Copy All'}
            </button>
          </div>
        </div>

        <div className="logs-terminal">
          {filteredLogs.length === 0 ? (
            <div className="empty-logs">
              {logs.length === 0 ? (
                <span>No logs emitted yet for this job. Check back in a moment...</span>
              ) : (
                <span>No logs match current filter criteria.</span>
              )}
            </div>
          ) : (
            filteredLogs.map((log, i) => {
              const lvl = log.level.toLowerCase()
              return (
                <div key={i} className={`log-entry ${lvl}`}>
                  <span className="log-time">
                    {new Date(log.timestamp).toLocaleTimeString([], {
                      hour12: false,
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                  <span className={`log-badge ${lvl}`}>{log.level}</span>
                  {log.stage && <span className="log-stage">[{log.stage}]</span>}
                  <span className="log-msg">{log.message}</span>
                </div>
              )
            })
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  )
}
export default PipelineMonitorPage
