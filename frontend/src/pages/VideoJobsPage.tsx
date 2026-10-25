import React, { useState, useMemo } from 'react'
import { JobStatus } from '../types'
import { StatusBadge } from '../components/StatusBadge'
import { cancelJob, retryJob } from '../services/api'
import './VideoJobsPage.css'

export interface VideoJobsPageProps {
  jobs: JobStatus[]
  activeJobId: string | null
  onSelectJob: (jobId: string) => void
  onNavigate: (tab: any) => void
  onRefresh: () => void
}

export const VideoJobsPage: React.FC<VideoJobsPageProps> = ({
  jobs,
  activeJobId,
  onSelectJob,
  onNavigate,
  onRefresh,
}) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      // Status filter
      if (statusFilter !== 'all' && job.status !== statusFilter) {
        return false
      }
      // Search query (job_id, prompt snippet, language)
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim()
        const idMatch = job.job_id.toLowerCase().includes(q)
        const textMatch = job.input_text?.toLowerCase().includes(q) || false
        const langMatch = job.language?.toLowerCase().includes(q) || false
        const stageMatch = job.current_stage?.toLowerCase().includes(q) || false
        if (!idMatch && !textMatch && !langMatch && !stageMatch) {
          return false
        }
      }
      return true
    })
  }, [jobs, statusFilter, searchQuery])

  const copyToClipboard = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(id)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const handleCancel = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm(`Cancel running job ${jobId.slice(0, 8)}...?`)) return
    setActionLoading(jobId)
    try {
      await cancelJob(jobId)
      onRefresh()
    } catch (err) {
      alert(`Failed to cancel job: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setActionLoading(null)
    }
  }

  const handleRetry = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm(`Retry failed job ${jobId.slice(0, 8)}...?`)) return
    setActionLoading(jobId)
    try {
      const newJob = await retryJob(jobId)
      onSelectJob(newJob.job_id)
      onRefresh()
    } catch (err) {
      alert(`Failed to retry job: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setActionLoading(null)
    }
  }

  const navigateToView = (jobId: string, tab: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onSelectJob(jobId)
    onNavigate(tab)
  }

  const formatDuration = (start?: string | null, end?: string | null) => {
    if (!start) return '—'
    const s = new Date(start).getTime()
    const e = end ? new Date(end).getTime() : Date.now()
    const sec = Math.round((e - s) / 1000)
    if (sec < 60) return `${sec}s`
    const m = Math.floor(sec / 60)
    const rem = sec % 60
    return `${m}m ${rem}s`
  }

  return (
    <div className="video-jobs-page">
      <div className="jobs-header-row">
        <div>
          <h2>Video Jobs Registry</h2>
          <p>Full audit trail of all generation runs, background pipelines, and rendered assets.</p>
        </div>
        <div className="jobs-header-actions">
          <button className="primary-action-btn" onClick={() => onNavigate('create')}>
            + Create New Video
          </button>
          <button className="refresh-btn" onClick={onRefresh} title="Refresh jobs">
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="jobs-filter-bar">
        <div className="search-input-wrapper">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            className="jobs-search-input"
            placeholder="Search by Job ID, narration script text, or language..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search-btn" onClick={() => setSearchQuery('')}>
              ✕
            </button>
          )}
        </div>

        <div className="status-filter-pills">
          {[
            { id: 'all', label: `All (${jobs.length})` },
            { id: 'completed', label: `Completed (${jobs.filter((j) => j.status === 'completed').length})` },
            { id: 'processing', label: `Processing (${jobs.filter((j) => j.status === 'processing').length})` },
            { id: 'queued', label: `Queued (${jobs.filter((j) => j.status === 'queued').length})` },
            { id: 'failed', label: `Failed (${jobs.filter((j) => j.status === 'failed').length})` },
          ].map((pill) => (
            <button
              key={pill.id}
              className={`filter-pill ${statusFilter === pill.id ? 'active' : ''}`}
              onClick={() => setStatusFilter(pill.id)}
            >
              {pill.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table of Jobs */}
      <div className="jobs-table-card">
        {filteredJobs.length === 0 ? (
          <div className="empty-jobs-state">
            <span className="empty-icon">📂</span>
            <h3>No matching video jobs found</h3>
            <p>Try adjusting your search criteria or create a new video generation job.</p>
            <button className="create-first-btn" onClick={() => onNavigate('create')}>
              Create Video Job
            </button>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Job ID</th>
                  <th>Script / Input Preview</th>
                  <th>Lang</th>
                  <th>Scenes</th>
                  <th>Progress</th>
                  <th>Duration</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredJobs.map((job) => {
                  const isActive = job.job_id === activeJobId
                  return (
                    <tr
                      key={job.job_id}
                      className={`job-row ${isActive ? 'active-job-row' : ''}`}
                      onClick={() => onSelectJob(job.job_id)}
                    >
                      <td>
                        <StatusBadge status={job.status} stage={job.current_stage} />
                      </td>
                      <td>
                        <div className="job-id-cell">
                          <code className="id-code" title={job.job_id}>
                            {job.job_id.slice(0, 8)}...
                          </code>
                          <button
                            className="copy-mini-btn"
                            title="Copy full Job ID"
                            onClick={(e) => copyToClipboard(job.job_id, e)}
                          >
                            {copiedId === job.job_id ? '✓' : '📋'}
                          </button>
                        </div>
                      </td>
                      <td className="script-cell">
                        <span className="script-snippet">
                          {job.input_text
                            ? job.input_text.slice(0, 75) + (job.input_text.length > 75 ? '...' : '')
                            : 'Audio voiceover file job'}
                        </span>
                      </td>
                      <td>
                        <span className="lang-tag">{(job.language || 'en').toUpperCase()}</span>
                      </td>
                      <td>
                        <span className="scenes-count">{job.scenes_count || '—'}</span>
                      </td>
                      <td>
                        <div className="progress-cell">
                          <div className="mini-progress-track">
                            <div
                              className={`mini-progress-bar ${job.status}`}
                              style={{ width: `${job.progress_pct || (job.status === 'completed' ? 100 : 0)}%` }}
                            />
                          </div>
                          <span className="mini-pct">{Math.round(job.progress_pct || (job.status === 'completed' ? 100 : 0))}%</span>
                        </div>
                      </td>
                      <td className="duration-cell">
                        {formatDuration(job.created_at, job.completed_at)}
                      </td>
                      <td className="date-cell">
                        {job.created_at
                          ? new Date(job.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                          : '—'}
                      </td>
                      <td className="actions-cell">
                        <div className="action-buttons-group">
                          {/* Monitor Link */}
                          <button
                            className="table-action-btn"
                            title="View Pipeline Monitor"
                            onClick={(e) => navigateToView(job.job_id, 'monitor', e)}
                          >
                            ⚡
                          </button>

                          {/* Inspector Link */}
                          <button
                            className="table-action-btn"
                            title="Inspect Scene Relevance"
                            onClick={(e) => navigateToView(job.job_id, 'scenes', e)}
                          >
                            🔬
                          </button>

                          {/* Video Library Link */}
                          {job.status === 'completed' && (
                            <button
                              className="table-action-btn highlight"
                              title="Watch Video & Assets"
                              onClick={(e) => navigateToView(job.job_id, 'library', e)}
                            >
                              ▶
                            </button>
                          )}

                          {/* Evaluation Link */}
                          <button
                            className="table-action-btn"
                            title="Audit 30-col Evaluation"
                            onClick={(e) => navigateToView(job.job_id, 'evaluation', e)}
                          >
                            📊
                          </button>

                          {/* Cancel if processing */}
                          {job.status === 'processing' && (
                            <button
                              className="table-action-btn danger"
                              title="Cancel Job"
                              disabled={actionLoading === job.job_id}
                              onClick={(e) => handleCancel(job.job_id, e)}
                            >
                              ⛔
                            </button>
                          )}

                          {/* Retry if failed */}
                          {job.status === 'failed' && (
                            <button
                              className="table-action-btn warning"
                              title="Retry Job"
                              disabled={actionLoading === job.job_id}
                              onClick={(e) => handleRetry(job.job_id, e)}
                            >
                              ↺
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
export default VideoJobsPage
