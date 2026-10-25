import React, { useRef, useState, useEffect } from 'react'
import { PlayIcon, PauseIcon, VolumeIcon, MaximizeIcon } from './CommonIcons'
import './VideoPlayer.css'

export interface VideoPlayerProps {
  src: string
  captionSrc?: string
  aspectRatio?: string
  poster?: string
  title?: string
  autoPlay?: boolean
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  src,
  captionSrc,
  aspectRatio = '16:9',
  poster,
  title,
  autoPlay = false,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolume] = useState(1)
  const [isMuted, setIsMuted] = useState(false)
  const [showCaptions, setShowCaptions] = useState(true)
  const [hasError, setHasError] = useState(false)
  const [vttUrl, setVttUrl] = useState<string | null>(null)

  // Reset error when src changes
  useEffect(() => {
    setHasError(false)
    setIsPlaying(false)
    setCurrentTime(0)
    if (videoRef.current) {
      videoRef.current.load()
    }
  }, [src])

  // Convert SRT to WebVTT blob for native video track rendering
  useEffect(() => {
    if (!captionSrc) {
      setVttUrl(null)
      return
    }

    let isSubscribed = true
    fetch(captionSrc)
      .then((res) => {
        if (!res.ok) throw new Error('No captions')
        return res.text()
      })
      .then((srtText) => {
        if (!isSubscribed) return
        // Minimal SRT to VTT converter
        let vtt = 'WEBVTT\n\n' + srtText.replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, '$1.$2')
        const blob = new Blob([vtt], { type: 'text/vtt' })
        setVttUrl(URL.createObjectURL(blob))
      })
      .catch(() => {
        if (isSubscribed) setVttUrl(null)
      })

    return () => {
      isSubscribed = false
    }
  }, [captionSrc])

  const togglePlay = () => {
    if (!videoRef.current) return
    if (isPlaying) {
      videoRef.current.pause()
    } else {
      videoRef.current.play().catch(() => setHasError(true))
    }
    setIsPlaying(!isPlaying)
  }

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime)
    }
  }

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration)
      setHasError(false)
    }
  }

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = Number(e.target.value)
    if (videoRef.current) {
      videoRef.current.currentTime = time
      setCurrentTime(time)
    }
  }

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value)
    setVolume(val)
    if (videoRef.current) {
      videoRef.current.volume = val
      setIsMuted(val === 0)
    }
  }

  const toggleMute = () => {
    if (!videoRef.current) return
    const nextMute = !isMuted
    setIsMuted(nextMute)
    videoRef.current.muted = nextMute
  }

  const toggleFullscreen = () => {
    if (videoRef.current) {
      if (document.fullscreenElement) {
        document.exitFullscreen()
      } else {
        videoRef.current.requestFullscreen().catch(() => {})
      }
    }
  }

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60)
    const s = Math.floor(secs % 60)
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  // Calculate container aspect ratio style
  let containerAspect = '16 / 9'
  if (aspectRatio === '9:16') containerAspect = '9 / 16'
  if (aspectRatio === '1:1') containerAspect = '1 / 1'

  return (
    <div className={`video-player-wrapper aspect-${aspectRatio.replace(':', '-')}`}>
      {title && <div className="video-player-header">{title}</div>}

      <div
        className="video-container"
        style={{ aspectRatio: containerAspect }}
      >
        <video
          ref={videoRef}
          src={src}
          poster={poster}
          autoPlay={autoPlay}
          crossOrigin="anonymous"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
          onError={() => setHasError(true)}
          onClick={togglePlay}
        >
          {vttUrl && showCaptions && (
            <track
              kind="subtitles"
              src={vttUrl}
              srcLang="en"
              label="Captions"
              default
            />
          )}
        </video>

        {hasError && (
          <div className="video-error-overlay">
            <div className="error-box">
              <span className="error-icon">🎬</span>
              <p>Video output stream is not available or still processing.</p>
              <button
                className="retry-btn"
                onClick={() => {
                  setHasError(false)
                  if (videoRef.current) videoRef.current.load()
                }}
              >
                Reload Media
              </button>
            </div>
          </div>
        )}

        <div className="video-controls-overlay">
          <div className="scrubber-bar">
            <input
              type="range"
              min="0"
              max={duration || 100}
              step="0.05"
              value={currentTime}
              onChange={handleSeek}
              className="seek-slider"
            />
          </div>

          <div className="controls-row">
            <div className="controls-left">
              <button
                className="control-btn play-btn"
                onClick={togglePlay}
                aria-label={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? <PauseIcon size={18} /> : <PlayIcon size={18} />}
              </button>

              <div className="volume-wrapper">
                <button className="control-btn" onClick={toggleMute} aria-label="Volume">
                  <VolumeIcon size={18} />
                </button>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={isMuted ? 0 : volume}
                  onChange={handleVolumeChange}
                  className="volume-slider"
                />
              </div>

              <span className="time-display">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>

            <div className="controls-right">
              {vttUrl && (
                <button
                  className={`caption-btn ${showCaptions ? 'active' : ''}`}
                  onClick={() => setShowCaptions(!showCaptions)}
                  title="Toggle Subtitles"
                >
                  CC
                </button>
              )}

              <span className="ar-tag">{aspectRatio}</span>

              <button
                className="control-btn"
                onClick={toggleFullscreen}
                aria-label="Fullscreen"
              >
                <MaximizeIcon size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
export default VideoPlayer
