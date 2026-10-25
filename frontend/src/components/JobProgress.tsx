import { JobStatus } from '../types'
import './JobProgress.css'

interface Props {
  job: JobStatus
  onViewResults: () => void
  onNewJob: () => void
}

const STAGE_LABELS: Record<string, string> = {
  queued: 'Waiting in queue...',
  transcribing: 'Transcribing audio...',
  planning_scenes: 'Planning scenes with Gemini AI...',
  searching_footage: 'Searching Pixabay for stock footage...',
  validating_assets: 'Validating footage assets...',
  rendering: 'Rendering video with FFmpeg...',
  validating_output: 'Validating output files...',
  completed: 'Completed!',
  failed: 'Failed',
  processing: 'Processing...',
}

const STAGE_ICONS: Record<string, string> = {
  queued: '⏳',
  transcribing: '🎙️',
  planning_scenes: '🧠',
  searching_footage: '🔍',
  validating_assets: '✅',
  rendering: '🎬',
  validating_output: '🔬',
  completed: '🎉',
  failed: '❌',
  processing: '⚙️',
}

export default function JobProgress({ job, onViewResults, onNewJob }: Props) {
  const stage = job.current_stage || job.status
  const stageLabel = STAGE_LABELS[stage] || stage
  const stageIcon = STAGE_ICONS[stage] || '⚙️'
  const isFailed = job.status === 'failed'
  const isCompleted = job.status === 'completed'

  return (
    <div className="progress-container">
      <div className="card">
        <div className="job-header">
          <div>
            <h2>Job Status</h2>
            <code className="job-id">{job.job_id}</code>
          </div>
          <div className={`status-badge status-${job.status}`}>
            {stageIcon} {job.status.toUpperCase()}
          </div>
        </div>

        {/* Progress Bar */}
        <div className="progress-section">
          <div className="progress-bar-container">
            <div
              className={`progress-bar-fill ${isFailed ? 'failed' : ''}`}
              style={{ width: `${job.progress}%` }}
            />
          </div>
          <div className="progress-info">
            <span className="stage-text">
              {stageIcon} {stageLabel}
            </span>
            <span className="progress-pct">{job.progress}%</span>
          </div>
          {job.stage_detail && (
            <p className="stage-detail">{job.stage_detail}</p>
          )}
        </div>

        {/* Stage pipeline */}
        <div className="pipeline">
          {[
            { key: 'queued', label: 'Queue' },
            { key: 'transcribing', label: 'Transcribe' },
            { key: 'planning_scenes', label: 'Plan Scenes' },
            { key: 'searching_footage', label: 'Find Footage' },
            { key: 'rendering', label: 'Render' },
            { key: 'validating_output', label: 'Validate' },
            { key: 'completed', label: 'Done' },
          ].map((s, idx) => {
            const stages = ['queued', 'transcribing', 'planning_scenes',
              'searching_footage', 'rendering', 'validating_output', 'completed']
            const currentIdx = stages.indexOf(stage)
            const isActive = s.key === stage
            const isDone = stages.indexOf(s.key) < currentIdx || isCompleted

            return (
              <div
                key={s.key}
                className={`pipeline-step ${isActive ? 'active' : ''} ${isDone ? 'done' : ''}`}
              >
                <div className="pipeline-dot" />
                <span>{s.label}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Error details */}
      {isFailed && (
        <div className="card error-card">
          <h2>❌ Job Failed</h2>
          <p className="error-message">{job.error_message}</p>
          {job.error_detail && (
            <details className="error-detail">
              <summary>Technical Details</summary>
              <pre>{job.error_detail}</pre>
            </details>
          )}
        </div>
      )}

      {/* Metadata */}
      <div className="card">
        <h2>📋 Job Details</h2>
        <div className="meta-grid">
          <div className="meta-item">
            <span className="meta-key">Input Type</span>
            <span className="meta-val">{job.input_type}</span>
          </div>
          <div className="meta-item">
            <span className="meta-key">Aspect Ratios</span>
            <span className="meta-val">{job.aspect_ratios.join(', ')}</span>
          </div>
          <div className="meta-item">
            <span className="meta-key">Created</span>
            <span className="meta-val">{new Date(job.created_at).toLocaleTimeString()}</span>
          </div>
          {job.started_at && (
            <div className="meta-item">
              <span className="meta-key">Started</span>
              <span className="meta-val">{new Date(job.started_at).toLocaleTimeString()}</span>
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="action-row">
        {isCompleted && (
          <button className="btn btn-success" onClick={onViewResults}>
            🎉 View Results
          </button>
        )}
        <button className="btn btn-secondary" onClick={onNewJob}>
          + New Job
        </button>
      </div>
    </div>
  )
}
