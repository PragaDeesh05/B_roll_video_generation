import React, { useState, useMemo, useEffect } from 'react'
import { JobStatus } from '../types'
import { VideoPlayer } from '../components/VideoPlayer'
import {
  getVideoDownloadUrl,
  getCaptionsDownloadUrl,
  getTimelineDownloadUrl,
  getManifestDownloadUrl,
  getEvaluationCsvDownloadUrl,
} from '../services/api'
import './VideoLibraryPage.css'

export interface VideoLibraryPageProps {
  jobs: JobStatus[]
  activeJobId: string | null
  onSelectJob: (jobId: string) => void
  onNavigate: (tab: any) => void
}

export const VideoLibraryPage: React.FC<VideoLibraryPageProps> = ({
  jobs,
  activeJobId,
  onSelectJob,
  onNavigate,
}) => {
  const completedJobs = useMemo(() => {
    return jobs.filter((j) => j.status === 'completed')
  }, [jobs])

  const selectedJob = useMemo(() => {
    if (activeJobId) {
      const match = completedJobs.find((j) => j.job_id === activeJobId)
      if (match) return match
    }
    return completedJobs[0] || null
  }, [completedJobs, activeJobId])

  const [selectedAspectRatio, setSelectedAspectRatio] = useState<string>('16:9')

  // Find available aspect ratios for this job
  const availableRatios = useMemo(() => {
    if (!selectedJob) return ['16:9']
    return selectedJob.aspect_ratios && selectedJob.aspect_ratios.length > 0
      ? selectedJob.aspect_ratios
      : ['16:9']
  }, [selectedJob])

  // Automatically sync selected aspect ratio to job's aspect ratio
  useEffect(() => {
    if (selectedJob && availableRatios.length > 0) {
      if (!availableRatios.includes(selectedAspectRatio)) {
        setSelectedAspectRatio(availableRatios[0])
      }
    }
  }, [selectedJob?.job_id, availableRatios])

  // Determine video URL for selected aspect ratio
  const activeVideoUrl = useMemo(() => {
    if (!selectedJob) return ''
    if (selectedJob.artifacts?.videos && selectedJob.artifacts.videos.length > 0) {
      const targetName =
        selectedAspectRatio === '9:16'
          ? 'output_9x16.mp4'
          : selectedAspectRatio === '1:1'
          ? 'output_1x1.mp4'
          : 'output_16x9.mp4'
      const match = selectedJob.artifacts.videos.find((v) =>
        v.toLowerCase().includes(targetName.toLowerCase())
      )
      const filename = match || selectedJob.artifacts.videos[0]
      return `/jobs/${selectedJob.job_id}/download/${filename}`
    }
    const ratioFilename =
      selectedAspectRatio === '9:16'
        ? 'output_9x16.mp4'
        : selectedAspectRatio === '1:1'
        ? 'output_1x1.mp4'
        : 'output_16x9.mp4'
    return `/jobs/${selectedJob.job_id}/download/${ratioFilename}`
  }, [selectedJob, selectedAspectRatio])

  const activeCaptionsUrl = useMemo(() => {
    if (!selectedJob) return undefined
    return `/jobs/${selectedJob.job_id}/download/captions.srt`
  }, [selectedJob])

  if (completedJobs.length === 0) {
    return (
      <div className="video-library-page empty-library">
        <div className="empty-lib-card">
          <span className="icon">🎬</span>
          <h2>No Completed Videos Yet</h2>
          <p>Once you generate a video and the 11-stage pipeline completes, the rendered output, synchronized subtitles, and production assets will appear in this library.</p>
          <button className="primary-btn" onClick={() => onNavigate('create')}>
            Generate Video Now
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="video-library-page">
      <div className="library-header-row">
        <div>
          <h2>Video Production Library</h2>
          <p>Preview rendered videos with synchronized subtitles, inspect timeline cuts, and download production deliverables.</p>
        </div>
        <div className="header-meta-pill">
          <span>{completedJobs.length} Rendered Production Videos</span>
        </div>
      </div>

      <div className="library-layout-grid">
        {/* Left Side: Master Video Player & Deliverables */}
        <div className="player-column">
          {selectedJob ? (
            <div className="master-player-card">
              <div className="player-card-header">
                <div>
                  <h3>
                    {selectedJob.input_text
                      ? selectedJob.input_text.slice(0, 50) + '...'
                      : `Video Run ${selectedJob.job_id.slice(0, 8)}`}
                  </h3>
                  <span className="job-id-subtitle">
                    Job ID: <code>{selectedJob.job_id}</code> • Completed{' '}
                    {selectedJob.completed_at ? new Date(selectedJob.completed_at).toLocaleTimeString() : ''}
                  </span>
                </div>

                {/* Aspect ratio switch buttons */}
                <div className="ratio-switcher">
                  {availableRatios.map((ratio) => (
                    <button
                      key={ratio}
                      className={`ratio-btn ${selectedAspectRatio === ratio ? 'active' : ''}`}
                      onClick={() => setSelectedAspectRatio(ratio)}
                    >
                      {ratio}
                    </button>
                  ))}
                </div>
              </div>

              {/* HTML5 Player */}
              <div className="video-player-wrapper">
                <VideoPlayer
                  src={activeVideoUrl}
                  captionSrc={activeCaptionsUrl}
                  aspectRatio={selectedAspectRatio as any}
                  autoPlay={false}
                />
              </div>

              {/* Technical Specifications Bar */}
              <div className="video-specs-bar">
                <div className="spec-col">
                  <span className="spec-label">Resolution</span>
                  <span className="spec-val">
                    {selectedAspectRatio === '9:16'
                      ? '1080×1920'
                      : selectedAspectRatio === '1:1'
                      ? '1080×1080'
                      : '1920×1080 (FHD)'}
                  </span>
                </div>
                <div className="spec-col">
                  <span className="spec-label">Framerate</span>
                  <span className="spec-val">30 fps</span>
                </div>
                <div className="spec-col">
                  <span className="spec-label">Video Codec</span>
                  <span className="spec-val">H.264 / AVC (ultrafast)</span>
                </div>
                <div className="spec-col">
                  <span className="spec-label">Audio Codec</span>
                  <span className="spec-val">AAC Stereo 192kbps</span>
                </div>
                <div className="spec-col">
                  <span className="spec-label">Language</span>
                  <span className="spec-val">{(selectedJob.language || 'en').toUpperCase()}</span>
                </div>
              </div>

              {/* Production Deliverables Download Center */}
              <div className="download-deliverables-section">
                <h4>Production Deliverables & Export Assets</h4>
                <div className="download-buttons-grid">
                  <a
                    href={activeVideoUrl}
                    download={activeVideoUrl.split('/').pop() || `incubrix_video_${selectedJob.job_id.slice(0, 8)}.mp4`}
                    className="download-btn primary"
                  >
                    <span className="dl-icon">⬇️</span>
                    <div className="dl-text">
                      <strong>Download Video (.MP4)</strong>
                      <span>Master {selectedAspectRatio} rendered file ({activeVideoUrl.split('/').pop()})</span>
                    </div>
                  </a>

                  <a
                    href={getCaptionsDownloadUrl(selectedJob.job_id)}
                    download={`captions_${selectedJob.job_id.slice(0, 8)}.srt`}
                    className="download-btn"
                  >
                    <span className="dl-icon">💬</span>
                    <div className="dl-text">
                      <strong>Captions (.SRT)</strong>
                      <span>Locked subtitle timestamps</span>
                    </div>
                  </a>

                  <a
                    href={getTimelineDownloadUrl(selectedJob.job_id)}
                    download={`timeline_${selectedJob.job_id.slice(0, 8)}.json`}
                    className="download-btn"
                  >
                    <span className="dl-icon">📜</span>
                    <div className="dl-text">
                      <strong>Timeline (.JSON)</strong>
                      <span>Cuts, beats & asset IDs</span>
                    </div>
                  </a>

                  <a
                    href={getEvaluationCsvDownloadUrl(selectedJob.job_id)}
                    download={`evaluation_${selectedJob.job_id.slice(0, 8)}.csv`}
                    className="download-btn"
                  >
                    <span className="dl-icon">📊</span>
                    <div className="dl-text">
                      <strong>Evaluation (.CSV)</strong>
                      <span>30-column production audit</span>
                    </div>
                  </a>
                </div>
              </div>

              {/* Direct Page Links */}
              <div className="quick-actions-footer">
                <button
                  className="quick-nav-btn"
                  onClick={() => {
                    onSelectJob(selectedJob.job_id)
                    onNavigate('scenes')
                  }}
                >
                  🔬 Inspect Scene Relevance
                </button>
                <button
                  className="quick-nav-btn"
                  onClick={() => {
                    onSelectJob(selectedJob.job_id)
                    onNavigate('evaluation')
                  }}
                >
                  📈 View 30-Column Audit Sheet
                </button>
              </div>
            </div>
          ) : (
            <div className="no-selection">Select a video from the right sidebar</div>
          )}
        </div>

        {/* Right Side: Library List of Completed Videos */}
        <div className="library-list-column">
          <div className="list-card-header">
            <h3>Completed Videos ({completedJobs.length})</h3>
          </div>

          <div className="video-card-stack">
            {completedJobs.map((j) => {
              const isSelected = selectedJob?.job_id === j.job_id
              return (
                <div
                  key={j.job_id}
                  className={`video-item-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectJob(j.job_id)}
                >
                  <div className="card-thumb-area">
                    <span className="thumb-play">▶</span>
                  </div>
                  <div className="card-meta-area">
                    <span className="item-title">
                      {j.input_text ? j.input_text.slice(0, 50) + '...' : 'Audio Voiceover Run'}
                    </span>
                    <div className="item-specs">
                      <span>{(j.language || 'en').toUpperCase()}</span>
                      <span>•</span>
                      <span>{j.scenes_count || 2} Scenes</span>
                      <span>•</span>
                      <span>{new Date(j.created_at).toLocaleDateString()}</span>
                    </div>
                    <code className="item-id">{j.job_id.slice(0, 8)}...</code>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
export default VideoLibraryPage
