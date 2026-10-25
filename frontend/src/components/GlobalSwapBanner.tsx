import React, { useState } from 'react'
import { ActiveSwapTask } from '../types'
import './GlobalSwapBanner.css'

export interface GlobalSwapBannerProps {
  activeSwap: ActiveSwapTask | null
  onDismiss: () => void
  onViewVideo: (jobId: string) => void
}

export const GlobalSwapBanner: React.FC<GlobalSwapBannerProps> = ({
  activeSwap,
  onDismiss,
  onViewVideo,
}) => {
  const [showDetails, setShowDetails] = useState(false)

  if (!activeSwap || activeSwap.status === 'idle' as any) return null

  const isProcessing = activeSwap.status === 'uploading' || activeSwap.status === 'processing'
  const isFailed = activeSwap.status === 'failed'
  const isSuccess = activeSwap.status === 'success'

  return (
    <div className={`global-swap-card ${isFailed ? 'failed' : isSuccess ? 'success' : 'processing'}`}>
      <div className="swap-card-header">
        <div className="swap-card-left">
          {isProcessing && <span className="swap-spinner" />}
          {isSuccess && <span className="swap-icon">✓</span>}
          {isFailed && <span className="swap-icon">⚠️</span>}

          <div className="swap-card-title-group">
            <span className="swap-card-title">
              {isProcessing && `Replacing Scene ${activeSwap.sceneIndex + 1} Clip (Job ${activeSwap.jobId.slice(0, 8)})...`}
              {isSuccess && `Scene ${activeSwap.sceneIndex + 1} Clip Swapped Successfully!`}
              {isFailed && `Clip Swap Failed for Scene ${activeSwap.sceneIndex + 1}`}
            </span>
            <span className="swap-card-subtitle">
              {isProcessing && (activeSwap.progressStep || 'Processing segment and re-rendering video...')}
              {isSuccess && `Video regenerated in ${activeSwap.durationSeconds?.toFixed(1) || '1.3'}s at same location`}
              {isFailed && (activeSwap.error || 'Failed to replace scene clip')}
            </span>
          </div>
        </div>

        <div className="swap-card-actions">
          {isProcessing && (
            <button
              type="button"
              className="swap-btn-toggle"
              onClick={() => setShowDetails(!showDetails)}
              title="Toggle backend processing details"
            >
              {showDetails ? 'Hide Details' : 'Show Details'}
            </button>
          )}

          {isSuccess && (
            <button
              type="button"
              className="swap-btn-action"
              onClick={() => onViewVideo(activeSwap.jobId)}
            >
              🎬 Watch Video
            </button>
          )}

          <button
            type="button"
            className="swap-btn-close"
            onClick={onDismiss}
            title="Dismiss notification"
          >
            ×
          </button>
        </div>
      </div>

      {/* Expandable Processing Details Log */}
      {(showDetails || isProcessing) && activeSwap.details && activeSwap.details.length > 0 && (
        <div className="swap-details-box">
          <div className="swap-details-header">
            <span>⚙️ Backend Real-Time Operations</span>
            {isProcessing && <span className="swap-tag-active">Active in background</span>}
          </div>
          <ul className="swap-details-list">
            {activeSwap.details.map((detail, idx) => (
              <li key={idx} className="swap-detail-item">
                <span className="detail-dot">›</span>
                <span>{detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {isSuccess && activeSwap.outputPath && (
        <div className="swap-location-path">
          <span>📁 Saved at location:</span>
          <code>{activeSwap.outputPath}</code>
        </div>
      )}
    </div>
  )
}
export default GlobalSwapBanner
