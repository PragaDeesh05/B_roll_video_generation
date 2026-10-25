import React from 'react'

export interface ScoreBarProps {
  score: number | null | undefined
  threshold?: number
  maxScore?: number
  label?: string
  showLabel?: boolean
  showThresholdMarker?: boolean
  size?: 'sm' | 'md' | 'lg'
}

export const ScoreBar: React.FC<ScoreBarProps> = ({
  score,
  threshold = 3.5,
  maxScore = 5.0,
  label,
  showLabel = true,
  showThresholdMarker = true,
  size = 'md',
}) => {
  if (score === null || score === undefined || isNaN(Number(score))) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '0.8rem', color: '#64748b' }}>N/A</span>
      </div>
    )
  }

  const numScore = Number(score)
  const pct = Math.min(100, Math.max(0, (numScore / maxScore) * 100))
  const thresholdPct = (threshold / maxScore) * 100
  const isPassing = numScore >= threshold

  let fillColor = '#10b981' // Green
  if (numScore < 2.5) {
    fillColor = '#ef4444' // Red
  } else if (numScore < threshold) {
    fillColor = '#f59e0b' // Amber
  }

  const heights = { sm: 6, md: 10, lg: 14 }
  const barHeight = heights[size]

  return (
    <div style={{ width: '100%', minWidth: '130px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '4px' }}>
        {label && (
          <span style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 500 }}>
            {label}
          </span>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              fontSize: size === 'sm' ? '0.8rem' : '0.9rem',
              fontWeight: 700,
              color: fillColor,
            }}
          >
            {numScore.toFixed(2)}
          </span>
          <span style={{ fontSize: '0.7rem', color: '#64748b' }}>/ {maxScore.toFixed(1)}</span>
        </div>
      </div>

      <div
        style={{
          position: 'relative',
          height: `${barHeight}px`,
          backgroundColor: '#1e293b',
          borderRadius: '999px',
          overflow: 'hidden',
          border: '1px solid #334155',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            backgroundColor: fillColor,
            borderRadius: '999px',
            transition: 'width 0.4s ease',
          }}
        />

        {showThresholdMarker && (
          <div
            title={`Threshold: ${threshold}`}
            style={{
              position: 'absolute',
              left: `${thresholdPct}%`,
              top: 0,
              bottom: 0,
              width: '2px',
              backgroundColor: '#38bdf8',
              boxShadow: '0 0 4px #0284c7',
              zIndex: 2,
            }}
          />
        )}
      </div>

      {showThresholdMarker && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '2px' }}>
          <span style={{ fontSize: '0.65rem', color: isPassing ? '#10b981' : '#f59e0b', fontWeight: 600 }}>
            {isPassing ? '✓ Meets criteria' : '⚠ Below target'}
          </span>
          <span style={{ fontSize: '0.65rem', color: '#38bdf8' }}>
            Min: {threshold.toFixed(1)}
          </span>
        </div>
      )}
    </div>
  )
}
export default ScoreBar
