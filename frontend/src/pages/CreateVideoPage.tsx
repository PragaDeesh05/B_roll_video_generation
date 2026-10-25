import React, { useState, useMemo, useEffect } from 'react'
import { submitTextJob, submitAudioJob } from '../services/api'
import { JobStatus } from '../types'
import './CreateVideoPage.css'

function detectScriptLanguage(text: string): 'en' | 'hi' | 'ta' {
  if (!text) return 'en'
  let taCount = 0
  let hiCount = 0
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i)
    if (code >= 0x0B80 && code <= 0x0BFF) taCount++
    else if (code >= 0x0900 && code <= 0x097F) hiCount++
  }
  if (taCount > 0 && taCount >= hiCount) return 'ta'
  if (hiCount > 0) return 'hi'
  return 'en'
}

export interface CreateVideoPageProps {
  onJobCreated: (job: JobStatus) => void
  onNavigate: (tab: any) => void
}

export const CreateVideoPage: React.FC<CreateVideoPageProps> = ({
  onJobCreated,
  onNavigate,
}) => {
  const [inputMode, setInputMode] = useState<'text' | 'audio'>('text')

  // Text mode state
  const [scriptText, setScriptText] = useState('')
  const detectedScriptLang = useMemo(() => detectScriptLanguage(scriptText), [scriptText])
  const [narrationLanguage, setNarrationLanguage] = useState<string>('en')
  const [subtitleLanguage, setSubtitleLanguage] = useState<string>('en')
  const [narrationManualOverride, setNarrationManualOverride] = useState(false)
  const [aspectRatios, setAspectRatios] = useState<string[]>(['16:9'])
  const [stylePreference, setStylePreference] = useState('Cinematic documentary, natural clean lighting')
  const [avoidConstraints, setAvoidConstraints] = useState<string[]>([
    'watermarks',
    'brand logos',
    'blurry low quality',
  ])
  const [constraintInput, setConstraintInput] = useState('')

  // By default, have narration language match the script language unless user manually changed it
  useEffect(() => {
    if (!narrationManualOverride && inputMode === 'text') {
      setNarrationLanguage(detectedScriptLang)
    }
  }, [detectedScriptLang, narrationManualOverride, inputMode])

  // Audio mode state
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [audioDragOver, setAudioDragOver] = useState(false)

  // Status & loading
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Script text calculations
  const textStats = useMemo(() => {
    const chars = scriptText.length
    const words = scriptText.trim() ? scriptText.trim().split(/\s+/).length : 0
    // Estimate: ~140-150 words per minute -> ~0.4s per word
    const estDurationSec = Math.round(words * 0.4)
    const estScenes = Math.max(1, Math.ceil(estDurationSec / 4.5))
    return { chars, words, estDurationSec, estScenes }
  }, [scriptText])

  const toggleAspectRatio = (ratio: string) => {
    if (aspectRatios.includes(ratio)) {
      if (aspectRatios.length > 1) {
        setAspectRatios(aspectRatios.filter((r) => r !== ratio))
      }
    } else {
      setAspectRatios([...aspectRatios, ratio])
    }
  }

  const addConstraint = () => {
    const trimmed = constraintInput.trim().toLowerCase()
    if (trimmed && !avoidConstraints.includes(trimmed)) {
      setAvoidConstraints([...avoidConstraints, trimmed])
      setConstraintInput('')
    }
  }

  const removeConstraint = (tag: string) => {
    setAvoidConstraints(avoidConstraints.filter((t) => t !== tag))
  }

  const handleAudioDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setAudioDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0]
      if (/\.(mp3|wav|m4a|mp4)$/i.test(file.name)) {
        setAudioFile(file)
        setErrorMessage(null)
      } else {
        setErrorMessage('Please upload a valid audio file (.mp3, .wav, .m4a)')
      }
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setAudioFile(e.target.files[0])
      setErrorMessage(null)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMessage(null)

    if (inputMode === 'text') {
      if (!scriptText.trim()) {
        setErrorMessage('Please enter a narration script to generate a video.')
        return
      }
      if (scriptText.trim().length < 15) {
        setErrorMessage('Script is too brief. Please enter at least a full sentence (15+ characters).')
        return
      }
    } else {
      if (!audioFile) {
        setErrorMessage('Please select or drop an audio file for voiceover generation.')
        return
      }
    }

    setIsSubmitting(true)

    try {
      let createdJob: JobStatus
      const effectiveNarration = narrationLanguage || (inputMode === 'text' ? detectedScriptLang : 'en')
      const effectiveSubtitle = subtitleLanguage || 'en'

      if (inputMode === 'text') {
        createdJob = await submitTextJob(
          scriptText.trim(),
          aspectRatios,
          detectedScriptLang,
          null,
          stylePreference,
          avoidConstraints,
          effectiveNarration,
          effectiveSubtitle
        )
      } else {
        createdJob = await submitAudioJob(
          audioFile!,
          aspectRatios,
          effectiveNarration,
          null,
          stylePreference,
          avoidConstraints,
          effectiveNarration,
          effectiveSubtitle
        )
      }

      onJobCreated(createdJob)
      onNavigate('pipeline')
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to submit video generation request.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Pre-load prompt template helpers
  const applyTemplate = (type: 'finance' | 'technology' | 'nature' | 'health' | 'diwali' | 'pongal') => {
    setNarrationManualOverride(false)
    if (type === 'finance') {
      setScriptText(
        'Managing personal finance effectively requires steady discipline. ' +
        'Regular contributions allow savings to grow exponentially over time. ' +
        'Compound returns build financial security for a prosperous future.'
      )
      setStylePreference('Clean modern corporate office, sleek digital dashboard charts, warm sunlight')
    } else if (type === 'technology') {
      setScriptText(
        'Cloud computing connects distributed servers across modern global enterprise datacenters. ' +
        'Secure microservices process continuous data streams reliably and securely. ' +
        'Autonomous systems accelerate digital innovation worldwide.'
      )
      setStylePreference('Cinematic high-tech server room, glowing fiber optics, modern workstations')
    } else if (type === 'nature') {
      setScriptText(
        'Majestic snow-capped mountain ranges rise above pristine pine forests. ' +
        'Glacial streams flow gently into crystal clear alpine lakes. ' +
        'Untouched wilderness preserves the timeless beauty of our natural planet.'
      )
      setStylePreference('Breathtaking 4K nature documentary, golden hour morning light, soft atmospheric mist')
    } else if (type === 'health') {
      setScriptText(
        'A balanced lifestyle begins with mindful daily nutrition and wholesome hydration. ' +
        'Consistent physical movement rejuvenates cardiac stamina and mental focus. ' +
        'Restful restorative sleep rebuilds vitality for tomorrow.'
      )
      setStylePreference('Bright clean wellness studio, refreshing fresh fruit flat-lays, morning active routine')
    } else if (type === 'diwali') {
      setScriptText(
        'नमस्ते दोस्तों। भारत में दीवाली का पावन पर्व बहुत धूमधाम से मनाया जाता है। ' +
        'हर घर में मिट्टी के दीये जलते हैं और चारों तरफ खुशियां और रोशनी बिखर जाती है। ' +
        'यह त्योहार अंधकार पर प्रकाश की विजय और नई आशा का पावन प्रतीक है।'
      )
      setStylePreference('Warm festive oil lamps, glowing golden fireworks, traditional celebratory atmosphere')
    } else if (type === 'pongal') {
      setScriptText(
        'வணக்கம் நண்பர்களே. தமிழ்நாட்டில் பொங்கல் திருநாள் உழவர் மற்றும் அறுவடைத் திருநாளாக மகிழ்ச்சியுடன் கொண்டாடப்படுகிறது. ' +
        'புதுப் பானையில் புத்தரிசி இட்டு பொங்கலோ பொங்கல் என்று மக்கள் மகிழ்ச்சி பொங்கக் கொண்டாடுகிறார்கள். ' +
        'இயற்கைக்கும் சூரிய பகவானுக்கும் நன்றி செலுத்தும் உன்னதமான திருநாள் இது.'
      )
      setStylePreference('Vibrant South Indian harvest festival, decorated earthen pot, golden sunshine and sugarcane fields')
    }
  }

  return (
    <div className="create-video-page">
      <div className="create-header">
        <h2>Studio Video Creator</h2>
        <p>Turn scripts or spoken voiceover into synchronized 1080p B-roll videos with verified stock footage.</p>
      </div>

      <div className="create-layout">
        {/* Main Input Form */}
        <form className="create-main-card" onSubmit={handleSubmit}>
          {/* Mode Tabs */}
          <div className="mode-tabs">
            <button
              type="button"
              className={`mode-tab ${inputMode === 'text' ? 'active' : ''}`}
              onClick={() => {
                setInputMode('text')
                setErrorMessage(null)
              }}
            >
              <span className="tab-icon">✍️</span>
              <span>Script to Video</span>
            </button>
            <button
              type="button"
              className={`mode-tab ${inputMode === 'audio' ? 'active' : ''}`}
              onClick={() => {
                setInputMode('audio')
                setErrorMessage(null)
              }}
            >
              <span className="tab-icon">🎙️</span>
              <span>Voiceover Audio to Video</span>
            </button>
          </div>

          {errorMessage && (
            <div className="error-alert-banner">
              <span className="alert-icon">⚠️</span>
              <span className="alert-text">{errorMessage}</span>
            </div>
          )}

          {/* Mode A: Script Editor */}
          {inputMode === 'text' && (
            <div className="form-section">
              <div className="section-title-row">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <label className="section-label">Narration Script</label>
                  {scriptText.trim() && (
                    <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '4px', background: '#3b82f6', color: '#fff', fontWeight: 600 }}>
                      ⚡ Auto-Detected: {detectedScriptLang === 'ta' ? '🇮🇳 தமிழ் (Tamil)' : detectedScriptLang === 'hi' ? '🇮🇳 हिंदी (Hindi)' : '🇬🇧 English'}
                    </span>
                  )}
                </div>
                <div className="template-chips">
                  <span className="chips-label">Presets:</span>
                  <button type="button" className="chip-btn" onClick={() => applyTemplate('finance')}>
                    Finance
                  </button>
                  <button type="button" className="chip-btn" onClick={() => applyTemplate('technology')}>
                    Tech
                  </button>
                  <button type="button" className="chip-btn" onClick={() => applyTemplate('diwali')}>
                    🪔 दीवाली (HI)
                  </button>
                  <button type="button" className="chip-btn" onClick={() => applyTemplate('pongal')}>
                    🌾 பொங்கல் (TA)
                  </button>
                </div>
              </div>

              <textarea
                className="script-textarea"
                rows={7}
                placeholder="Type or paste your video narration script here. Each sentence will be cinematographically planned into synchronized visual scenes..."
                value={scriptText}
                onChange={(e) => setScriptText(e.target.value)}
              />

              <div className="textarea-stats">
                <span>{textStats.words} words</span>
                <span>•</span>
                <span>{textStats.chars} characters</span>
                <span>•</span>
                <span>Est. Duration: ~{textStats.estDurationSec}s</span>
                <span>•</span>
                <span>Est. Scenes: {textStats.estScenes}</span>
              </div>
            </div>
          )}

          {/* Mode B: Audio Upload */}
          {inputMode === 'audio' && (
            <div className="form-section">
              <label className="section-label">Upload Narration Audio</label>
              <div
                className={`audio-dropzone ${audioDragOver ? 'drag-over' : ''} ${audioFile ? 'has-file' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault()
                  setAudioDragOver(true)
                }}
                onDragLeave={() => setAudioDragOver(false)}
                onDrop={handleAudioDrop}
              >
                <input
                  type="file"
                  id="audio-file-input"
                  className="hidden-file-input"
                  accept="audio/mp3,audio/wav,audio/m4a,video/mp4"
                  onChange={handleFileChange}
                />
                <label htmlFor="audio-file-input" className="dropzone-inner">
                  <span className="drop-icon">{audioFile ? '🎵' : '📁'}</span>
                  {audioFile ? (
                    <div className="file-preview-meta">
                      <span className="file-name">{audioFile.name}</span>
                      <span className="file-size">{(audioFile.size / 1024 / 1024).toFixed(2)} MB</span>
                      <span className="change-file-hint">Click to change file</span>
                    </div>
                  ) : (
                    <div className="dropzone-text">
                      <span className="main-prompt">Drag & drop voiceover audio here, or browse</span>
                      <span className="format-hint">Supports MP3, WAV, M4A (16kHz / 44.1kHz recommended)</span>
                    </div>
                  )}
                </label>
              </div>
            </div>
          )}

          {/* Configuration Grid */}
          <div className="config-grid">
            {/* Option 1: Narration Language */}
            <div className="config-group">
              <label className="config-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>🎙️ Narration Language</span>
                {!narrationManualOverride && inputMode === 'text' && (
                  <span style={{ fontSize: '10px', color: '#10b981', fontWeight: 500 }}>Auto-matches script</span>
                )}
              </label>
              <select
                className="config-select"
                value={narrationLanguage}
                onChange={(e) => {
                  setNarrationLanguage(e.target.value)
                  setNarrationManualOverride(true)
                }}
              >
                <option value="en">🇬🇧 English (en-US-ChristopherNeural)</option>
                <option value="hi">🇮🇳 Hindi (hi-IN-MadhurNeural)</option>
                <option value="ta">🇮🇳 Tamil (ta-IN-ValluvarNeural)</option>
              </select>
              <span style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px', display: 'block' }}>
                {narrationManualOverride ? 'Custom voice override' : `Default: same as script (${detectedScriptLang.toUpperCase()})`}
              </span>
            </div>

            {/* Option 2: Subtitle Language */}
            <div className="config-group">
              <label className="config-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>💬 Subtitle Language</span>
                <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 500 }}>Default: English</span>
              </label>
              <select
                className="config-select"
                value={subtitleLanguage}
                onChange={(e) => setSubtitleLanguage(e.target.value)}
              >
                <option value="en">🇬🇧 English (en - Default)</option>
                <option value="hi">🇮🇳 Hindi (hi - Devanagari)</option>
                <option value="ta">🇮🇳 Tamil (ta - Unicode)</option>
              </select>
              <span style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px', display: 'block' }}>
                Default: English burned-in captions across all scripts
              </span>
            </div>

            {/* Aspect Ratio */}
            <div className="config-group full-width">
              <label className="config-label">Target Output Aspect Ratios</label>
              <div className="aspect-ratio-selector">
                <button
                  type="button"
                  className={`ar-pill ${aspectRatios.includes('16:9') ? 'selected' : ''}`}
                  onClick={() => toggleAspectRatio('16:9')}
                >
                  <span className="ar-box landscape" />
                  <div className="ar-info">
                    <span className="ar-name">16:9 Landscape</span>
                    <span className="ar-res">1920×1080 (YouTube/Desktop)</span>
                  </div>
                </button>

                <button
                  type="button"
                  className={`ar-pill ${aspectRatios.includes('9:16') ? 'selected' : ''}`}
                  onClick={() => toggleAspectRatio('9:16')}
                >
                  <span className="ar-box portrait" />
                  <div className="ar-info">
                    <span className="ar-name">9:16 Vertical</span>
                    <span className="ar-res">1080×1920 (Reels/Shorts)</span>
                  </div>
                </button>

                <button
                  type="button"
                  className={`ar-pill ${aspectRatios.includes('1:1') ? 'selected' : ''}`}
                  onClick={() => toggleAspectRatio('1:1')}
                >
                  <span className="ar-box square" />
                  <div className="ar-info">
                    <span className="ar-name">1:1 Square</span>
                    <span className="ar-res">1080×1080 (Instagram Feed)</span>
                  </div>
                </button>
              </div>
            </div>

            {/* Style Preference */}
            <div className="config-group full-width">
              <label className="config-label">Visual Style & Aesthetic Hint</label>
              <input
                type="text"
                className="config-input"
                value={stylePreference}
                onChange={(e) => setStylePreference(e.target.value)}
                placeholder="e.g. Modern cinematic documentary, warm soft lighting, crisp 4k"
              />
            </div>

            {/* Avoid Constraints Tags */}
            <div className="config-group full-width">
              <label className="config-label">Negative Constraints & Visual Avoids</label>
              <div className="constraints-input-row">
                <input
                  type="text"
                  className="config-input tag-input"
                  value={constraintInput}
                  onChange={(e) => setConstraintInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addConstraint()
                    }
                  }}
                  placeholder="Type an element to avoid and press Enter (e.g. human faces, dark shadows)..."
                />
                <button type="button" className="add-tag-btn" onClick={addConstraint}>
                  + Add Avoid
                </button>
              </div>

              <div className="tags-container">
                {avoidConstraints.map((tag) => (
                  <span key={tag} className="constraint-tag">
                    {tag}
                    <button type="button" className="remove-tag" onClick={() => removeConstraint(tag)}>
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Submit Action */}
          <div className="form-submit-row">
            <button
              type="submit"
              className="generate-submit-btn"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className="spinner" />
                  <span>Submitting to Engine Pipeline...</span>
                </>
              ) : (
                <>
                  <span>🚀 Generate Video (Voice: {narrationLanguage.toUpperCase()} · Subtitles: {subtitleLanguage.toUpperCase()})</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Live Pre-Submission Summary Sidebar Card */}
        <div className="create-summary-card">
          <h3>Generation Spec Summary</h3>
          <p className="summary-desc">Pipeline will execute the following configuration:</p>

          <div className="spec-list">
            <div className="spec-item">
              <span className="spec-key">Input Mode:</span>
              <span className="spec-val uppercase">{inputMode}</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">Script Language:</span>
              <span className="spec-val uppercase">{detectedScriptLang} (Auto-detected)</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">Narration Voice:</span>
              <span className="spec-val uppercase">{narrationLanguage}</span>
            </div>
            <div className="spec-item highlight">
              <span className="spec-key">Subtitles:</span>
              <span className="spec-val uppercase">{subtitleLanguage}</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">Aspect Ratios:</span>
              <span className="spec-val">{aspectRatios.join(', ')}</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">Audio Sync:</span>
              <span className="spec-val">Scene-Wise (100% Coherent)</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">Keyframe Sampler:</span>
              <span className="spec-val">20%, 50%, 80% Temporal VLM</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">Min Threshold:</span>
              <span className="spec-val">3.5 / 5.0 (Relevance Policy)</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">AI Fallback:</span>
              <span className="spec-val">Gemini 2.5 Flash Image</span>
            </div>
            <div className="spec-item">
              <span className="spec-key">FFmpeg Preset:</span>
              <span className="spec-val">ultrafast (Single-Pass)</span>
            </div>
          </div>

          <div className="pipeline-guarantee-box">
            <span className="guarantee-icon">🛡️</span>
            <div className="guarantee-text">
              <strong>Zero Drift Guarantee</strong>
              <span>Scene audio durations dictate video cuts and subtitle timestamps in exact lockstep.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
export default CreateVideoPage
