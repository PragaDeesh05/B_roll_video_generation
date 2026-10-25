import { useState, useEffect } from 'react'
import {
  getTimeline,
  getManifest,
  getCandidates,
  getEvaluation,
} from '../services/api'
import {
  JobStatus,
  Timeline,
  Scene,
  CandidateScore,
  EvaluationResponse,
} from '../types'
import StepPipelineViewer from './StepPipelineViewer'
import EvaluationSheetTable from './EvaluationSheetTable'
import './JobResults.css'

interface Props {
  job: JobStatus
  onNewJob: () => void
}

type TabKey = 'video' | 'steps' | 'evaluation' | 'minio' | 'manifest'

export default function JobResults({ job, onNewJob }: Props) {
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [manifest, setManifest] = useState<any>(null)
  const [candidateScores, setCandidateScores] = useState<Record<string, CandidateScore[]>>({})
  const [evaluationData, setEvaluationData] = useState<EvaluationResponse | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('steps')
  const [activeScene, setActiveScene] = useState<Scene | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadingDetails, setLoadingDetails] = useState<boolean>(true)

  const loadJobData = async () => {
    setLoadingDetails(true)
    setLoadError(null)

    // Load timeline & manifest
    try {
      const [t, m] = await Promise.all([
        getTimeline(job.job_id).catch(() => null),
        getManifest(job.job_id).catch(() => null),
      ])
      if (t) {
        setTimeline(t)
        if (t.scenes?.length > 0) setActiveScene(t.scenes[0])
      }
      if (m) setManifest(m)
    } catch (err: any) {
      console.warn('Timeline/manifest load error:', err)
    }

    // Load candidate scores
    try {
      const cand = await getCandidates(job.job_id).catch(() => null)
      if (cand && cand.scenes) {
        setCandidateScores(cand.scenes)
      }
    } catch (err: any) {
      console.warn('Candidates load error:', err)
    }

    // Load 30-column evaluation data
    try {
      const evalResp = await getEvaluation(job.job_id).catch(() => null)
      if (evalResp) {
        setEvaluationData(evalResp)
      }
    } catch (err: any) {
      console.warn('Evaluation sheet load error:', err)
    }

    setLoadingDetails(false)
  }

  useEffect(() => {
    loadJobData()
  }, [job.job_id])

  const videoUrls = job.artifacts?.video_urls || []
  const captionsUrl = `/jobs/${job.job_id}/captions`
  const validationUrl = `/jobs/${job.job_id}/validation`
  const evalCsvUrl = `/jobs/${job.job_id}/download/evaluation_sheet.csv`

  return (
    <div className="results-container">
      {/* Top Header Card */}
      <div className="results-header card">
        <div className="results-title">
          <div className="title-row">
            <h2>🎬 B-Roll Video Production Console</h2>
            <span className={`badge ${job.status === 'completed' ? 'badge-success' : 'badge-warning'}`}>
              ● {job.status.toUpperCase()}
            </span>
          </div>
          <div className="job-meta-line">
            <span className="meta-item">
              <strong>Job ID:</strong> <code className="job-id-small">{job.job_id}</code>
            </span>
            <span className="meta-item">
              <strong>Input:</strong> {job.input_type?.toUpperCase()}
            </span>
            <span className="meta-item">
              <strong>Language:</strong>{' '}
              <span className="badge badge-purple" style={{ padding: '2px 8px', fontSize: '11px', verticalAlign: 'middle' }}>
                {job.language === 'hi' ? '🇮🇳 हिंदी (hi)' : job.language === 'ta' ? '🇮🇳 தமிழ் (ta)' : '🇬🇧 English (en)'}
              </span>
            </span>
            <span className="meta-item">
              <strong>Ratios:</strong> {job.aspect_ratios?.join(', ') || '16:9'}
            </span>
            {timeline?.narration_duration && (
              <span className="meta-item">
                <strong>Duration:</strong> {timeline.narration_duration.toFixed(1)}s
              </span>
            )}
            {timeline?.scenes && (
              <span className="meta-item">
                <strong>Scenes:</strong> {timeline.scenes.length}
              </span>
            )}
          </div>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={onNewJob}>
            + New Generation
          </button>
        </div>
      </div>

      {loadError && (
        <div className="error-banner">⚠️ Note: {loadError}</div>
      )}

      {/* Primary Navigation Tabs */}
      <div className="main-tab-bar">
        <button
          className={`main-tab-btn ${activeTab === 'steps' ? 'active' : ''}`}
          onClick={() => setActiveTab('steps')}
        >
          <span className="tab-icon">🔬</span>
          <div className="tab-label-group">
            <span className="tab-title">Step-by-Step Pipeline</span>
            <span className="tab-sub">All 7 Engine Stages & Diagnostics</span>
          </div>
        </button>

        <button
          className={`main-tab-btn ${activeTab === 'video' ? 'active' : ''}`}
          onClick={() => setActiveTab('video')}
        >
          <span className="tab-icon">🎬</span>
          <div className="tab-label-group">
            <span className="tab-title">Output Video Player</span>
            <span className="tab-sub">1080p MP4 & Subtitles</span>
          </div>
        </button>

        <button
          className={`main-tab-btn ${activeTab === 'evaluation' ? 'active' : ''}`}
          onClick={() => setActiveTab('evaluation')}
        >
          <span className="tab-icon">📊</span>
          <div className="tab-label-group">
            <span className="tab-title">30-Col Evaluation Sheet</span>
            <span className="tab-sub">Multi-Factor Scores & Human Ratings</span>
          </div>
        </button>

        <button
          className={`main-tab-btn ${activeTab === 'minio' ? 'active' : ''}`}
          onClick={() => setActiveTab('minio')}
        >
          <span className="tab-icon">📦</span>
          <div className="tab-label-group">
            <span className="tab-title">MinIO & Docker Storage</span>
            <span className="tab-sub">S3 Objects & Web Console</span>
          </div>
        </button>

        <button
          className={`main-tab-btn ${activeTab === 'manifest' ? 'active' : ''}`}
          onClick={() => setActiveTab('manifest')}
        >
          <span className="tab-icon">📋</span>
          <div className="tab-label-group">
            <span className="tab-title">Manifest & Tech Specs</span>
            <span className="tab-sub">FFmpeg & Quality Audit</span>
          </div>
        </button>
      </div>

      {/* TAB 1: STEP-BY-STEP PIPELINE INSPECTOR */}
      {activeTab === 'steps' && (
        <StepPipelineViewer
          jobId={job.job_id}
          timeline={timeline}
          manifest={manifest}
          evaluationData={evaluationData}
          candidateScores={candidateScores}
        />
      )}

      {/* TAB 2: OUTPUT VIDEO PLAYER */}
      {activeTab === 'video' && (
        <div className="video-player-section">
          {videoUrls.length > 0 ? (
            <div className="card video-master-card">
              <div className="card-header-row">
                <h3>🎬 Rendered Video Outputs ({videoUrls.length})</h3>
                <span className="badge badge-success">✓ 1080p H.264 / AAC Normalized</span>
              </div>
              <div className="video-grid">
                {videoUrls.map((url, idx) => {
                  const ratio = job.aspect_ratios[idx] || '16:9'
                  return (
                    <div key={url} className="video-wrapper">
                      <div className="video-label-badge">
                        <span>Aspect Ratio: {ratio}</span>
                        <span className="spec-tag">1920×1080 @ 30fps</span>
                      </div>
                      <video
                        controls
                        className={`video-player ratio-${ratio.replace(':', 'x')}`}
                        src={url}
                        playsInline
                      >
                        Your browser does not support video playback.
                      </video>
                      <div className="video-controls-row">
                        <a
                          href={url}
                          download
                          className="btn btn-primary download-btn"
                        >
                          ⬇ Download {ratio} MP4
                        </a>
                        <a
                          href={`/jobs/${job.job_id}/captions`}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-secondary download-btn"
                        >
                          📝 Download SRT
                        </a>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className="card empty-state">
              <p>⚠️ No video files found for this job yet.</p>
            </div>
          )}

          {/* Quick Scene Scrubber Preview */}
          {timeline && timeline.scenes && (
            <div className="card scene-overview-card">
              <h3>⏱️ Scene Sequence & Visual Footprint</h3>
              <div className="scene-timeline-bar">
                {timeline.scenes.map((s, idx) => {
                  const durPct = timeline.narration_duration
                    ? (s.duration / timeline.narration_duration) * 100
                    : 100 / timeline.scenes.length
                  return (
                    <div
                      key={s.scene_id}
                      className={`timeline-segment ${s.ai_generated ? 'ai' : 'stock'}`}
                      style={{ width: `${durPct}%` }}
                      title={`Scene ${idx + 1}: ${s.duration.toFixed(1)}s (${s.ai_generated ? 'AI' : 'Stock'})`}
                      onClick={() => setActiveScene(s)}
                    >
                      <span className="seg-label">S{idx + 1}</span>
                    </div>
                  )
                })}
              </div>

              {activeScene && (
                <div className="active-scene-banner">
                  <div className="banner-left">
                    <span className="scene-tag">Scene {activeScene.scene_id}</span>
                    <span className="scene-time">
                      {activeScene.start_time.toFixed(1)}s → {activeScene.end_time.toFixed(1)}s ({activeScene.duration.toFixed(1)}s)
                    </span>
                    <span className={`badge ${activeScene.ai_generated ? 'badge-purple' : 'badge-success'}`}>
                      {activeScene.ai_generated ? 'AI Generated' : 'Pixabay Stock'}
                    </span>
                    <span className="badge badge-info">
                      Score: {activeScene.relevance_score ? activeScene.relevance_score.toFixed(1) : 'N/A'}/5.0
                    </span>
                  </div>
                  <div className="banner-right">
                    <p className="scene-narration">"{activeScene.transcript_text}"</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: 30-COLUMN EVALUATION SHEET */}
      {activeTab === 'evaluation' && (
        <div className="evaluation-section">
          <EvaluationSheetTable
            jobId={job.job_id}
            evaluationData={evaluationData}
            onRatingUpdated={loadJobData}
          />
        </div>
      )}

      {/* TAB 4: MINIO & DOCKER STORAGE EXPLORER */}
      {activeTab === 'minio' && (
        <div className="minio-section">
          <div className="card minio-hero-card">
            <div className="minio-header">
              <div className="minio-brand">
                <span className="minio-icon">📦</span>
                <div>
                  <h3>MinIO Object Storage & Docker Deployment</h3>
                  <p className="minio-sub">High-Performance S3-Compatible Storage Layer for Incubrix B-Roll Engine</p>
                </div>
              </div>
              <a
                href="http://localhost:9001"
                target="_blank"
                rel="noreferrer"
                className="btn btn-primary minio-btn"
              >
                🚀 Open MinIO Web Console ↗
              </a>
            </div>

            <div className="minio-status-grid">
              <div className="minio-metric-box">
                <span className="minio-k">Docker Container</span>
                <span className="minio-v text-green">● running (incubrix-minio)</span>
              </div>
              <div className="minio-metric-box">
                <span className="minio-k">S3 API Endpoint</span>
                <span className="minio-v monospace">http://localhost:9000</span>
              </div>
              <div className="minio-metric-box">
                <span className="minio-k">Web UI Port</span>
                <span className="minio-v monospace">http://localhost:9001</span>
              </div>
              <div className="minio-metric-box">
                <span className="minio-k">Target Bucket</span>
                <span className="minio-v monospace">s3://incubrix-broll/</span>
              </div>
              <div className="minio-metric-box">
                <span className="minio-k">Credentials</span>
                <span className="minio-v monospace">minioadmin / minioadmin</span>
              </div>
              <div className="minio-metric-box">
                <span className="minio-k">Job Storage Prefix</span>
                <span className="minio-v monospace">s3://incubrix-broll/{job.job_id}/</span>
              </div>
            </div>
          </div>

          <div className="card">
            <h3>🗂️ Stored S3 Artifacts for Job {job.job_id}</h3>
            <p className="card-sub">
              Every job artifact is replicated directly into MinIO object storage for persistent retrieval, recruiter auditing, and high-speed multi-region streaming.
            </p>
            <div className="minio-files-table-wrapper">
              <table className="minio-files-table">
                <thead>
                  <tr>
                    <th>Asset Name</th>
                    <th>Type</th>
                    <th>S3 URI</th>
                    <th>Presigned Direct Access</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>output_16x9.mp4</strong></td>
                    <td><span className="badge badge-info">Video (1080p)</span></td>
                    <td className="monospace">s3://incubrix-broll/{job.job_id}/output_16x9.mp4</td>
                    <td>
                      <a href={`/jobs/${job.job_id}/download/output_16x9.mp4`} download className="btn btn-small btn-secondary">
                        ⬇ Download MP4
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>timeline.json</strong></td>
                    <td><span className="badge badge-purple">Scene Timeline</span></td>
                    <td className="monospace">s3://incubrix-broll/{job.job_id}/timeline.json</td>
                    <td>
                      <a href={`/jobs/${job.job_id}/timeline`} target="_blank" rel="noreferrer" className="btn btn-small btn-secondary">
                        🔗 View JSON
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>manifest.json</strong></td>
                    <td><span className="badge badge-purple">Job Manifest</span></td>
                    <td className="monospace">s3://incubrix-broll/{job.job_id}/manifest.json</td>
                    <td>
                      <a href={`/jobs/${job.job_id}/manifest`} target="_blank" rel="noreferrer" className="btn btn-small btn-secondary">
                        🔗 View JSON
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>captions.srt</strong></td>
                    <td><span className="badge badge-info">Subtitles (SRT)</span></td>
                    <td className="monospace">s3://incubrix-broll/{job.job_id}/captions.srt</td>
                    <td>
                      <a href={`/jobs/${job.job_id}/captions`} target="_blank" rel="noreferrer" className="btn btn-small btn-secondary">
                        📝 View SRT
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>validation_report.json</strong></td>
                    <td><span className="badge badge-success">Quality Audit</span></td>
                    <td className="monospace">s3://incubrix-broll/{job.job_id}/validation_report.json</td>
                    <td>
                      <a href={`/jobs/${job.job_id}/validation`} target="_blank" rel="noreferrer" className="btn btn-small btn-secondary">
                        🔬 View Report
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>evaluation_sheet.csv</strong></td>
                    <td><span className="badge badge-warning">30-Column CSV</span></td>
                    <td className="monospace">s3://incubrix-broll/{job.job_id}/evaluation_sheet.csv</td>
                    <td>
                      <a href={evalCsvUrl} download className="btn btn-small btn-primary">
                        📥 Download CSV
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>evaluation_sheet.json</strong></td>
                    <td><span className="badge badge-warning">Evaluation JSON</span></td>
                    <td className="monospace">s3://incubrix-broll/{job.job_id}/evaluation_sheet.json</td>
                    <td>
                      <a href={`/jobs/${job.job_id}/download/evaluation_sheet.json`} target="_blank" rel="noreferrer" className="btn btn-small btn-secondary">
                        🔗 View JSON
                      </a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: TECHNICAL MANIFEST & SPECS */}
      {activeTab === 'manifest' && (
        <div className="manifest-section">
          {manifest ? (
            <div className="card">
              <h3>📋 Complete Production Manifest</h3>
              <div className="manifest-meta-grid">
                <div className="meta-box">
                  <span className="meta-label">App Version</span>
                  <span className="meta-val">{manifest.app_version || '1.0.0'}</span>
                </div>
                <div className="meta-box">
                  <span className="meta-label">Engine Framework</span>
                  <span className="meta-val">FastAPI + FFmpeg + OpenCLIP</span>
                </div>
                <div className="meta-box">
                  <span className="meta-label">Scene Planner</span>
                  <span className="meta-val">Gemini 2.5 Flash</span>
                </div>
                <div className="meta-box">
                  <span className="meta-label">Visual Verification</span>
                  <span className="meta-val">Gemini 2.5 Flash VLM</span>
                </div>
                <div className="meta-box">
                  <span className="meta-label">Generated Timestamp</span>
                  <span className="meta-val">
                    {manifest.generated_at ? new Date(manifest.generated_at).toLocaleString() : 'N/A'}
                  </span>
                </div>
                <div className="meta-box">
                  <span className="meta-label">Input Audio / Script</span>
                  <span className="meta-val">{manifest.input_type?.toUpperCase()}</span>
                </div>
              </div>

              <div className="specs-section">
                <h4>Render Outputs & Technical Profile</h4>
                {manifest.output_files?.map((f: any) => (
                  <div key={f.aspect_ratio} className="spec-row">
                    <span className="badge badge-info">{f.aspect_ratio}</span>
                    <span className="spec-item"><strong>Resolution:</strong> {f.width}×{f.height}</span>
                    <span className="spec-item"><strong>Framerate:</strong> {f.frame_rate} fps</span>
                    <span className="spec-item"><strong>Video Codec:</strong> {f.video_codec} (yuv420p)</span>
                    <span className="spec-item"><strong>Audio Codec:</strong> {f.audio_codec} (48kHz Stereo)</span>
                    <span className="spec-item"><strong>File Size:</strong> {(f.file_size_bytes / 1024 / 1024).toFixed(2)} MB</span>
                  </div>
                ))}
              </div>

              {manifest.validation_summary && (
                <div className="validation-checks-box">
                  <h4>Automated Quality Assurance Gates</h4>
                  <div className="checks-grid">
                    {manifest.validation_summary.results?.[0]?.checks?.map((c: any) => (
                      <div key={c.check} className={`check-card ${c.passed ? 'passed' : 'failed'}`}>
                        <div className="check-status-icon">{c.passed ? '✓' : '✗'}</div>
                        <div className="check-info">
                          <span className="check-title">{c.check.replace(/_/g, ' ')}</span>
                          {c.value !== undefined && (
                            <span className="check-val monospace">{String(c.value)}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="raw-json-box">
                <h4>Raw Manifest JSON</h4>
                <pre className="json-pre">{JSON.stringify(manifest, null, 2)}</pre>
              </div>
            </div>
          ) : (
            <div className="card">
              <p>Loading technical manifest...</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
