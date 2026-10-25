import React from 'react'

export interface StatusBadgeProps {
  status: string
  label?: string
  stage?: string | null
  size?: 'sm' | 'md'
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, stage, size = 'md' }) => {
  const norm = (status || '').toLowerCase().trim()

  let bg = '#1e293b'
  let text = '#94a3b8'
  let dot = '#64748b'
  let displayLabel = label || (stage && norm === 'processing' ? stage : status)

  if (norm === 'completed' || norm === 'success' || norm === 'selected' || norm === 'healthy') {
    bg = 'rgba(16, 185, 129, 0.12)'
    text = '#10b981'
    dot = '#10b981'
    if (!label) displayLabel = norm === 'selected' ? 'Selected' : 'Completed'
  } else if (norm === 'processing' || norm === 'running' || norm === 'rendering') {
    bg = 'rgba(59, 130, 246, 0.12)'
    text = '#3b82f6'
    dot = '#3b82f6'
    if (!label) displayLabel = 'Processing'
  } else if (norm === 'queued' || norm === 'pending' || norm === 'warning' || norm === 'review_needed' || norm === 'review_required' || norm === 'flagged_low_relevance' || norm === 'low_relevance') {
    bg = 'rgba(245, 158, 11, 0.15)'
    text = '#f59e0b'
    dot = '#f59e0b'
    if (!label) displayLabel = norm === 'queued' ? 'Queued' : 'Review Required'
  } else if (norm === 'failed' || norm === 'error' || norm === 'rejected' || norm === 'unavailable') {
    bg = 'rgba(239, 68, 68, 0.12)'
    text = '#ef4444'
    dot = '#ef4444'
    if (!label) displayLabel = norm === 'rejected' ? 'Rejected' : 'Failed'
  } else if (norm === 'ai_generated' || norm === 'fallback') {
    bg = 'rgba(168, 85, 247, 0.12)'
    text = '#a855f7'
    dot = '#a855f7'
    if (!label) displayLabel = 'AI Generated'
  }

  const isSmall = size === 'sm'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: isSmall ? '4px' : '6px',
        padding: isSmall ? '2px 8px' : '4px 10px',
        borderRadius: '9999px',
        fontSize: isSmall ? '0.72rem' : '0.8rem',
        fontWeight: 600,
        backgroundColor: bg,
        color: text,
        border: `1px solid ${bg}`,
        whiteSpace: 'nowrap',
        letterSpacing: '0.02em',
      }}
    >
      <span
        style={{
          width: isSmall ? '5px' : '6px',
          height: isSmall ? '5px' : '6px',
          borderRadius: '50%',
          backgroundColor: dot,
          boxShadow: norm === 'processing' ? `0 0 6px ${dot}` : 'none',
        }}
      />
      {displayLabel}
    </span>
  )
}
export default StatusBadge
