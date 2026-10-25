import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Layout, NavTab } from './components/Layout'
import { OverviewPage } from './pages/OverviewPage'
import { CreateVideoPage } from './pages/CreateVideoPage'
import { VideoJobsPage } from './pages/VideoJobsPage'
import { PipelineMonitorPage } from './pages/PipelineMonitorPage'
import { SceneInspectorPage } from './pages/SceneInspectorPage'
import { VideoLibraryPage } from './pages/VideoLibraryPage'
import { EvaluationPage } from './pages/EvaluationPage'
import { SystemHealthPage } from './pages/SystemHealthPage'
import { SettingsPage } from './pages/SettingsPage'
import { GlobalSwapBanner } from './components/GlobalSwapBanner'
import { listJobs, getJobStatus, getHealth, swapSceneClip } from './services/api'
import { JobStatus, HealthResponse, ActiveSwapTask } from './types'
import './App.css'

export default function App() {
  const [currentTab, setCurrentTab] = useState<NavTab>('overview')
  const [jobs, setJobs] = useState<JobStatus[]>([])
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [healthData, setHealthData] = useState<HealthResponse | null>(null)
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true)
  const [isLoadingJobs, setIsLoadingJobs] = useState<boolean>(true)
  const [activeSwap, setActiveSwap] = useState<ActiveSwapTask | null>(null)
  const pollTimerRef = useRef<any>(null)

  // Fetch all recent jobs from backend API
  const refreshJobs = useCallback(async () => {
    try {
      const data = await listJobs(50)
      setJobs(data)
      // If no active job is selected yet, pick the most recent one
      setActiveJobId((prev) => {
        if (prev) return prev
        return data.length > 0 ? data[0].job_id : null
      })
    } catch (err) {
      console.warn('Failed to fetch jobs list:', err)
    } finally {
      setIsLoadingJobs(false)
    }
  }, [])

  // Check backend server health
  const checkHealth = useCallback(async () => {
    try {
      const h = await getHealth()
      setHealthData(h)
      setBackendHealthy(h.status === 'ok')
    } catch {
      setBackendHealthy(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    refreshJobs()
    checkHealth()
    const healthInterval = setInterval(checkHealth, 15000)
    return () => clearInterval(healthInterval)
  }, [refreshJobs, checkHealth])

  // Get current active job object
  const activeJob: JobStatus | null =
    jobs.find((j) => j.job_id === activeJobId) || null

  // Refresh single active job (e.g. from pipeline monitor)
  const refreshActiveJob = useCallback(async () => {
    if (!activeJobId) return
    try {
      const updated = await getJobStatus(activeJobId)
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.job_id === activeJobId)
        if (idx >= 0) {
          const next = [...prev]
          next[idx] = updated
          return next
        }
        return [updated, ...prev]
      })
    } catch (err) {
      console.warn('Could not refresh active job status:', err)
    }
  }, [activeJobId])

  // Polling loop when active job is running
  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }

    if (activeJob && (activeJob.status === 'processing' || activeJob.status === 'queued')) {
      pollTimerRef.current = setInterval(() => {
        refreshActiveJob()
      }, 2000)
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
      }
    }
  }, [activeJob?.status, activeJob?.job_id, refreshActiveJob])

  // Navigation router with aliases
  const handleNavigate = (tab: string) => {
    if (tab === 'monitor') setCurrentTab('pipeline')
    else if (tab === 'scenes') setCurrentTab('inspector')
    else setCurrentTab(tab as NavTab)
  }

  // Handle selecting a job from anywhere
  const handleSelectJob = (jobOrId: JobStatus | string) => {
    const id = typeof jobOrId === 'string' ? jobOrId : jobOrId.job_id
    setActiveJobId(id)
  }

  // When a new job is created from CreateVideoPage
  const handleJobCreated = (newJob: JobStatus) => {
    setJobs((prev) => [newJob, ...prev.filter((j) => j.job_id !== newJob.job_id)])
    setActiveJobId(newJob.job_id)
    setCurrentTab('pipeline')
  }

  // Persistent Scene Swap Handler (survives tab switching & new job creations)
  const handleStartSceneSwap = useCallback(async (
    jobId: string,
    sceneId: string,
    sceneIndex: number,
    file: File,
    sceneSubject?: string
  ) => {
    setActiveSwap({
      jobId,
      sceneId,
      sceneIndex,
      targetSceneSubject: sceneSubject,
      status: 'uploading',
      progressStep: 'Uploading custom clip/image to backend...',
      details: [
        `[1/4] Uploading user visual: ${file.name} (${(file.size / 1024).toFixed(1)} KB)...`,
      ],
      startTime: Date.now(),
    })

    const timer1 = setTimeout(() => {
      setActiveSwap((prev) => {
        if (!prev || prev.status === 'failed' || prev.status === 'success') return prev
        return {
          ...prev,
          status: 'processing',
          progressStep: 'Normalizing segment to 1080p @ 25fps H.264...',
          details: [
            ...prev.details,
            `[2/4] Normalizing replacement segment to 1920x1080 @ 25fps...`,
          ],
        }
      })
    }, 400)

    const timer2 = setTimeout(() => {
      setActiveSwap((prev) => {
        if (!prev || prev.status === 'failed' || prev.status === 'success') return prev
        return {
          ...prev,
          progressStep: 'Hot-swapping cached segment & stream-copy concatenating...',
          details: [
            ...prev.details,
            `[3/4] Splicing segment cache & stream-copy concatenating timeline...`,
          ],
        }
      })
    }, 900)

    try {
      const res = await swapSceneClip(jobId, sceneId, { file })
      clearTimeout(timer1)
      clearTimeout(timer2)

      const duration = res.render_duration_seconds || 1.3
      setActiveSwap({
        jobId,
        sceneId,
        sceneIndex,
        targetSceneSubject: sceneSubject,
        status: 'success',
        progressStep: `Master video regenerated in ${duration}s!`,
        details: [
          `[1/4] Uploaded replacement visual: ${file.name}`,
          `[2/4] Normalized segment to 1920x1080 @ 25fps H.264`,
          `[3/4] Lossless stream-copy concat finished`,
          `[4/4] Master voiceover audio synchronized & published`,
          `✓ Video location: ${res.output_path || 'storage/jobs/' + jobId + '/output_16x9.mp4'}`,
        ],
        durationSeconds: duration,
        swappedAsset: res.swapped_asset,
        outputPath: res.output_path,
        videoUrl: res.video_url || `/jobs/${jobId}/video`,
        startTime: Date.now(),
        finishTime: Date.now(),
      })

      // Refresh job data globally
      refreshJobs()
    } catch (err: any) {
      clearTimeout(timer1)
      clearTimeout(timer2)
      setActiveSwap({
        jobId,
        sceneId,
        sceneIndex,
        targetSceneSubject: sceneSubject,
        status: 'failed',
        progressStep: 'Clip swap failed',
        details: [
          `⚠️ Swap error: ${err.message || 'File upload or render failed'}`,
        ],
        error: err.message || 'File upload or render failed',
        startTime: Date.now(),
      })
    }
  }, [refreshJobs])

  return (
    <>
      <Layout
        currentTab={currentTab}
        onTabChange={setCurrentTab}
        activeJob={activeJob}
        recentJobs={jobs}
        onSelectJob={handleSelectJob}
        backendHealthy={backendHealthy}
        onRefresh={() => {
          refreshJobs()
          checkHealth()
        }}
      >
        {currentTab === 'overview' && (
          <OverviewPage
            jobs={jobs}
            health={healthData}
            onNavigate={handleNavigate}
            onSelectJob={handleSelectJob}
          />
        )}

        {currentTab === 'create' && (
          <CreateVideoPage
            onJobCreated={handleJobCreated}
            onNavigate={handleNavigate}
          />
        )}

        {currentTab === 'jobs' && (
          <VideoJobsPage
            jobs={jobs}
            activeJobId={activeJobId}
            onSelectJob={handleSelectJob}
            onNavigate={handleNavigate}
            onRefresh={refreshJobs}
          />
        )}

        {currentTab === 'pipeline' && (
          <PipelineMonitorPage
            jobId={activeJobId}
            job={activeJob}
            allJobs={jobs}
            onSelectJob={handleSelectJob}
            onNavigate={handleNavigate}
            onRefreshJob={refreshActiveJob}
          />
        )}

        {currentTab === 'inspector' && (
          <SceneInspectorPage
            jobId={activeJobId}
            job={activeJob}
            allJobs={jobs}
            onSelectJob={handleSelectJob}
            onNavigate={handleNavigate}
            activeSwap={activeSwap}
            onStartSwap={handleStartSceneSwap}
            onClearSwap={() => setActiveSwap(null)}
          />
        )}

        {currentTab === 'library' && (
          <VideoLibraryPage
            jobs={jobs}
            activeJobId={activeJobId}
            onSelectJob={handleSelectJob}
            onNavigate={handleNavigate}
          />
        )}

        {currentTab === 'evaluation' && (
          <EvaluationPage
            jobId={activeJobId}
            job={activeJob}
            allJobs={jobs}
            onSelectJob={handleSelectJob}
            onNavigate={handleNavigate}
          />
        )}

        {currentTab === 'health' && (
          <SystemHealthPage
            onRefreshGlobal={() => {
              refreshJobs()
              checkHealth()
            }}
          />
        )}

        {currentTab === 'settings' && (
          <SettingsPage onNavigate={handleNavigate} />
        )}
      </Layout>

      {/* Global Persistent Swap Banner across all tabs */}
      <GlobalSwapBanner
        activeSwap={activeSwap}
        onDismiss={() => setActiveSwap(null)}
        onViewVideo={(jId) => {
          setActiveJobId(jId)
          setCurrentTab('library')
        }}
      />
    </>
  )
}
