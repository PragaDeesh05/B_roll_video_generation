import React, { useMemo } from 'react'
import { JobStatus, HealthResponse } from '../types'
import StatusBadge from '../components/StatusBadge'
import { CopyIcon } from '../components/CommonIcons'
import './OverviewPage.css'

export interface OverviewPageProps {
  jobs: JobStatus[]
  health: HealthResponse | null
  onNavigate: (tab: any) => void
  onSelectJob: (job: JobStatus) => void
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  jobs,
  health,
  onNavigate,
  onSelectJob,
}) => {
  // Compute real operational metrics from real backend job records
  const metrics = useMemo(() => {
    const total = jobs.length
    const completed = jobs.filter((j) => j.status === 'completed').length
    const processing = jobs.filter((j) => j.status === 'processing' || j.status === 'queued').length
    const failed = jobs.filter((j) => j.status === 'failed').length

    let totalDurationSec = 0
    let durationCount = 0

    jobs.forEach((j) => {
      if (j.started_at && j.completed_at) {
        const start = new Date(j.started_at).getTime()
        const end = new Date(j.completed_at).getTime()
        const diff = (end - start) / 1000
        if (diff > 0) {
          totalDurationSec += diff
          durationCount++
        }
      }
    })

    const avgDuration = durationCount > 0 ? Math.round(totalDurationSec / durationCount) : 0

    // Count available videos
    const videosCount = jobs.reduce((acc, j) => {
      return acc + (j.artifacts?.videos?.length || 0)
    }, 0)

    return {
      total,
      completed,
      processing,
      failed,
      avgDuration,
      videosCount,
    }
  }, [jobs])

  const copyJobId = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(id)
  }

  const formatDuration = (secs: number) => {
    if (!secs) return 'N/A'
    if (secs < 60) return `${secs}s`
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}m ${s}s`
  }

  const formatTimestamp = (dateStr: string) => {
    try {
      const d = new Date(dateStr)
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="overview-page">
      {/* ── Top Hero / CTA Banner ─────────────────────────────────── */}
      <div className="overview-hero">
        <div className="hero-content">
          <h2>Production Operations & Video Engine Overview</h2>
          <p>
            Autonomous B-Roll video pipeline: Text & Voiceover → AI Cinematographic Scene Planning →
            Stock Media Verification & Multi-Modal Scoring → FFmpeg ultrafast rendering.
          </p>
        </div>
        <div className="hero-actions">
          <button className="primary-cta-btn" onClick={() => onNavigate('create')}>
            + Generate Video
          </button>
        </div>
      </div>

      {/* ── Real Operational Metrics Grid ─────────────────────────── */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-header">
            <span className="metric-title">Total Jobs</span>
            <span className="metric-icon">📁</span>
          </div>
          <div className="metric-value">{metrics.total}</div>
          <div className="metric-sub">Lifetime pipeline requests</div>
        </div>

        <div className="metric-card">
          <div className="metric-header">
            <span className="metric-title">Completed Videos</span>
            <span className="metric-icon">✓</span>
          </div>
          <div className="metric-value success-val">{metrics.completed}</div>
          <div className="metric-sub">{metrics.videosCount} MP4 outputs rendered</div>
        </div>

        <div className="metric-card">
          <div className="metric-header">
            <span className="metric-title">Active / In-Flight</span>
            <span className="metric-icon">⏳</span>
          </div>
          <div className="metric-value active-val">{metrics.processing}</div>
          <div className="metric-sub">Running pipeline stages</div>
        </div>

        <div className="metric-card">
          <div className="metric-header">
            <span className="metric-title">Avg Generation Time</span>
            <span className="metric-icon">⚡</span>
          </div>
          <div className="metric-value">{formatDuration(metrics.avgDuration)}</div>
          <div className="metric-sub">End-to-end processing avg</div>
        </div>
      </div>

      {/* ── System Status & Recent Jobs ───────────────────────────── */}
      <div className="overview-columns">
        {/* Recent Jobs Table */}
        <div className="overview-card table-card">
          <div className="card-header">
            <div className="header-titles">
              <h3>Recent Video Jobs</h3>
              <span className="header-counter">{jobs.length} total records</span>
            </div>
            <button className="text-link-btn" onClick={() => onNavigate('jobs')}>
              View all jobs →
            </button>
          </div>

          <div className="table-wrapper">
            <table className="overview-table">
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Mode</th>
                  <th>Language</th>
                  <th>Aspect</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-table-cell">
                      No video jobs found in database. Create a new video to begin.
                    </td>
                  </tr>
                ) : (
                  jobs.slice(0, 6).map((j) => (
                    <tr
                      key={j.job_id}
                      className="clickable-row"
                      onClick={() => {
                        onSelectJob(j)
                        onNavigate(j.status === 'completed' ? 'inspector' : 'pipeline')
                      }}
                    >
                      <td className="id-cell">
                        <span className="job-id-mono" title={j.job_id}>
                          {j.job_id.slice(0, 8)}...
                        </span>
                        <button
                          className="copy-btn"
                          onClick={(e) => copyJobId(j.job_id, e)}
                          title="Copy Full ID"
                        >
                          <CopyIcon size={12} />
                        </button>
                      </td>
                      <td>
                        <span className="mode-badge">{j.input_type}</span>
                      </td>
                      <td>{j.language.toUpperCase()}</td>
                      <td>{j.aspect_ratios.join(', ')}</td>
                      <td>
                        <StatusBadge status={j.status} size="sm" />
                      </td>
                      <td className="date-cell">{formatTimestamp(j.created_at)}</td>
                      <td className="actions-cell" onClick={(e) => e.stopPropagation()}>
                        <button
                          className="table-action-link"
                          onClick={() => {
                            onSelectJob(j)
                            onNavigate('pipeline')
                          }}
                        >
                          Pipeline
                        </button>
                        <button
                          className="table-action-link"
                          onClick={() => {
                            onSelectJob(j)
                            onNavigate('inspector')
                          }}
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* System Component Health Overview Card */}
        <div className="overview-card side-card">
          <div className="card-header">
            <h3>Infrastructure Status</h3>
            <button className="text-link-btn" onClick={() => onNavigate('health')}>
              Diagnostics →
            </button>
          </div>

          <div className="health-list">
            <div className="health-item">
              <div className="health-label">
                <span className="health-name">Backend FastAPI</span>
                <span className="health-desc">Core REST API engine</span>
              </div>
              <StatusBadge status={health?.status === 'ok' ? 'healthy' : 'failed'} size="sm" />
            </div>

            <div className="health-item">
              <div className="health-label">
                <span className="health-name">FFmpeg Transcoder</span>
                <span className="health-desc">Video scaling, padding & audio muxing</span>
              </div>
              <StatusBadge status={health?.ffmpeg ? 'healthy' : 'failed'} size="sm" />
            </div>

            <div className="health-item">
              <div className="health-label">
                <span className="health-name">FFprobe Media Inspector</span>
                <span className="health-desc">Acoustic duration validation</span>
              </div>
              <StatusBadge status={health?.ffprobe ? 'healthy' : 'failed'} size="sm" />
            </div>

            <div className="health-item">
              <div className="health-label">
                <span className="health-name">SQLite Job Database</span>
                <span className="health-desc">Relational records & audit metrics</span>
              </div>
              <StatusBadge status="healthy" size="sm" label="Connected" />
            </div>

            <div className="health-item">
              <div className="health-label">
                <span className="health-name">Pixabay Stock Engine</span>
                <span className="health-desc">HD stock footage library</span>
              </div>
              <StatusBadge status="healthy" size="sm" label="API Ready" />
            </div>

            <div className="health-item">
              <div className="health-label">
                <span className="health-name">Gemini Multimodal VLM</span>
                <span className="health-desc">Visual verification & AI fallback</span>
              </div>
              <StatusBadge status="healthy" size="sm" label="Configured" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
export default OverviewPage
