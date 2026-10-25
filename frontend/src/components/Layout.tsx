import React, { useState } from 'react'
import {
  DashboardIcon,
  VideoCreateIcon,
  JobsIcon,
  PipelineIcon,
  InspectorIcon,
  LibraryIcon,
  EvaluationIcon,
  HealthIcon,
  SettingsIcon,
  RefreshIcon,
} from './CommonIcons'
import StatusBadge from './StatusBadge'
import { JobStatus } from '../types'
import './Layout.css'

export type NavTab =
  | 'overview'
  | 'create'
  | 'jobs'
  | 'pipeline'
  | 'inspector'
  | 'library'
  | 'evaluation'
  | 'health'
  | 'settings'

export interface LayoutProps {
  currentTab: NavTab
  onTabChange: (tab: NavTab) => void
  activeJob: JobStatus | null
  recentJobs: JobStatus[]
  onSelectJob: (job: JobStatus) => void
  backendHealthy: boolean
  onRefresh: () => void
  children: React.ReactNode
}

export const Layout: React.FC<LayoutProps> = ({
  currentTab,
  onTabChange,
  activeJob,
  recentJobs,
  onSelectJob,
  backendHealthy,
  onRefresh,
  children,
}) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const navItems = [
    { id: 'overview', label: 'Overview', icon: <DashboardIcon /> },
    { id: 'create', label: 'Create Video', icon: <VideoCreateIcon /> },
    { id: 'jobs', label: 'Video Jobs', icon: <JobsIcon /> },
    { id: 'pipeline', label: 'Pipeline Monitor', icon: <PipelineIcon /> },
    { id: 'inspector', label: 'Scene Inspector', icon: <InspectorIcon /> },
    { id: 'library', label: 'Video Library', icon: <LibraryIcon /> },
    { id: 'evaluation', label: 'Evaluation Audit', icon: <EvaluationIcon /> },
    { id: 'health', label: 'System Health', icon: <HealthIcon /> },
    { id: 'settings', label: 'Settings', icon: <SettingsIcon /> },
  ]

  const tabTitles: Record<NavTab, string> = {
    overview: 'Operations Dashboard',
    create: 'Studio Video Studio',
    jobs: 'Production Jobs Registry',
    pipeline: 'Live Pipeline & Event Logs',
    inspector: 'Scene Relevance & Candidate Inspector',
    library: 'Rendered Video Library & Playback',
    evaluation: '30-Column Evaluation Audit & Rating',
    health: 'Infrastructure & Component Health',
    settings: 'Engine & Studio Configuration',
  }

  return (
    <div className={`studio-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* ── Persistent Sidebar ─────────────────────────────────────── */}
      <aside className="studio-sidebar">
        <div className="sidebar-brand">
          <div className="brand-logo" onClick={() => onTabChange('overview')}>
            <span className="brand-icon">🎬</span>
            {!sidebarCollapsed && (
              <div className="brand-text">
                <span className="brand-title">IncuBrix</span>
                <span className="brand-sub">Studio v1.0</span>
              </div>
            )}
          </div>
          <button
            className="collapse-toggle"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label="Toggle sidebar"
          >
            {sidebarCollapsed ? '→' : '←'}
          </button>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const active = currentTab === item.id
            return (
              <button
                key={item.id}
                className={`nav-item ${active ? 'active' : ''}`}
                onClick={() => onTabChange(item.id as NavTab)}
                title={sidebarCollapsed ? item.label : undefined}
              >
                <span className="nav-icon">{item.icon}</span>
                {!sidebarCollapsed && <span className="nav-label">{item.label}</span>}
              </button>
            )
          })}
        </nav>

        {/* Active Job Widget in Sidebar */}
        {!sidebarCollapsed && activeJob && (
          <div className="sidebar-active-job">
            <div className="active-job-header">
              <span className="job-badge-label">Active Job</span>
              <StatusBadge status={activeJob.status} size="sm" />
            </div>
            <div className="active-job-id" title={activeJob.job_id}>
              {activeJob.job_id.slice(0, 14)}...
            </div>
            <div className="active-job-meta">
              <span>{activeJob.input_type.toUpperCase()}</span>
              <span>•</span>
              <span>{activeJob.language.toUpperCase()}</span>
              <span>•</span>
              <span>{activeJob.progress}%</span>
            </div>
            <div className="active-job-actions">
              <button
                className="mini-action-btn"
                onClick={() => onTabChange('pipeline')}
              >
                Pipeline
              </button>
              <button
                className="mini-action-btn"
                onClick={() => onTabChange('inspector')}
              >
                Inspect
              </button>
            </div>
          </div>
        )}

        <div className="sidebar-footer">
          <div className="engine-badge">
            <span className="engine-dot" />
            {!sidebarCollapsed && <span>Engine Core v1.0.0</span>}
          </div>
        </div>
      </aside>

      {/* ── Main Workspace Content ─────────────────────────────────── */}
      <div className="studio-main-container">
        {/* Top Header Bar */}
        <header className="studio-topbar">
          <div className="topbar-left">
            <div className="breadcrumbs">
              <span className="crumb-root">IncuBrix Studio</span>
              <span className="crumb-sep">/</span>
              <span className="crumb-current">{tabTitles[currentTab]}</span>
            </div>
          </div>

          <div className="topbar-right">
            {/* Backend Health Pill */}
            <div
              className={`health-pill ${backendHealthy ? 'online' : 'offline'}`}
              onClick={() => onTabChange('health')}
              title="Click to check system health"
            >
              <span className="pulse-dot" />
              <span>{backendHealthy ? 'Backend Connected' : 'Connecting...'}</span>
            </div>

            {/* Quick Job Switcher */}
            {recentJobs.length > 0 && (
              <div className="job-switcher-wrapper">
                <select
                  className="job-switcher-select"
                  value={activeJob?.job_id || ''}
                  onChange={(e) => {
                    const found = recentJobs.find((j) => j.job_id === e.target.value)
                    if (found) onSelectJob(found)
                  }}
                  title="Switch Active Job"
                >
                  <option value="" disabled>
                    Select Job ({recentJobs.length} available)
                  </option>
                  {recentJobs.map((j) => (
                    <option key={j.job_id} value={j.job_id}>
                      {j.status.toUpperCase()} — {j.job_id.slice(0, 10)}... ({j.input_type})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Refresh Action */}
            <button
              className="topbar-btn refresh-btn"
              onClick={onRefresh}
              title="Refresh Data"
              aria-label="Refresh"
            >
              <RefreshIcon size={15} />
            </button>

            {/* Create Video Shortcut */}
            {currentTab !== 'create' && (
              <button
                className="topbar-primary-btn"
                onClick={() => onTabChange('create')}
              >
                + New Video
              </button>
            )}
          </div>
        </header>

        {/* Viewport Content */}
        <main className="studio-content-area">{children}</main>
      </div>
    </div>
  )
}
export default Layout
