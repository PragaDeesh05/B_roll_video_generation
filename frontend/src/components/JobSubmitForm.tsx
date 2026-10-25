import { useState, useEffect, useRef } from 'react'
import { submitTextJob, submitAudioJob, listJobs } from '../services/api'
import { JobStatus } from '../types'
import './JobSubmitForm.css'

interface Props {
  onJobCreated: (job: JobStatus) => void
  onJobSelected?: (job: JobStatus) => void
}

type InputMode = 'text' | 'audio'

const ASPECT_RATIOS = [
  { value: '16:9', label: '16:9 Landscape', icon: '🖥️' },
  { value: '9:16', label: '9:16 Vertical', icon: '📱' },
  { value: '1:1', label: '1:1 Square', icon: '⬜' },
]

interface LanguageOption {
  value: string
  label: string
  nativeLabel: string
  flag: string
  voice: string
  badge: string
  description: string
  placeholder: string
}

const LANGUAGES: LanguageOption[] = [
  {
    value: 'en',
    label: 'English',
    nativeLabel: 'English (en)',
    flag: '🇬🇧',
    voice: 'Azure Neural: Christopher / Aria',
    badge: 'Default',
    description: 'Documentary narration with natural pacing and global stock query alignment',
    placeholder: 'Enter your narration script in English. e.g.: Climate change is one of the biggest challenges facing our planet...',
  },
  {
    value: 'hi',
    label: 'हिंदी',
    nativeLabel: 'हिंदी (Hindi - hi)',
    flag: '🇮🇳',
    voice: 'Azure Neural: Madhur / Swara',
    badge: 'Devanagari',
    description: 'Authentic Hindi pronunciation, Indic cultural cues, and Nirmala UI subtitles',
    placeholder: 'यहाँ अपनी हिंदी पटकथा (स्क्रिप्ट) लिखें। उदा: नमस्ते दोस्तों। भारत में दीवाली का पावन पर्व बहुत धूमधाम से मनाया जाता है...',
  },
  {
    value: 'ta',
    label: 'தமிழ்',
    nativeLabel: 'தமிழ் (Tamil - ta)',
    flag: '🇮🇳',
    voice: 'Azure Neural: Valluvar / Pallavi',
    badge: 'Tamil Unicode',
    description: 'Pure Tamil diction, harvest & festival alignment, and flawless Tamil captions',
    placeholder: 'உங்கள் தமிழ் உரையை (ஸ்கிரிப்ட்) இங்கே உள்ளிடவும். எ.கா: வணக்கம் நண்பர்களே. தமிழ்நாட்டில் பொங்கல் திருநாள் மகிழ்ச்சியுடன் கொண்டாடப்படுகிறது...',
  },
]

const DEMO_PRESETS = [
  {
    title: '🌍 Climate Change & Earth',
    language: 'en',
    text: "Climate change is one of the biggest challenges facing our planet. Rising temperatures are melting glaciers, increasing sea levels, and changing weather patterns. Forests absorb carbon dioxide and help regulate the Earth's climate. By adopting renewable energy, protecting forests, and reducing waste, we can contribute to a more sustainable future.",
  },
  {
    title: '🌊 Ocean Biodiversity & Deep Sea',
    language: 'en',
    text: "The ocean covers more than seventy percent of our planet's surface. Beneath the turquoise waves lies a world of extraordinary biodiversity, from vibrant coral reefs teeming with marine creatures to the pitch-black mysteries of the abyssal plain. Every expedition uncovers alien ecosystems and miraculous adaptations.",
  },
  {
    title: '🪔 दीवाली का पावन पर्व (Diwali)',
    language: 'hi',
    text: "नमस्ते दोस्तों। भारत में दीवाली का पावन पर्व बहुत धूमधाम से मनाया जाता है। हर घर में मिट्टी के दीये जलते हैं और चारों तरफ खुशियां और रोशनी बिखर जाती है। यह त्योहार अंधकार पर प्रकाश की विजय का प्रतीक है।",
  },
  {
    title: '🌾 भारतीय कृषि और किसान (Agriculture)',
    language: 'hi',
    text: "भारत में कृषि ग्रामीण जीवन और अर्थव्यवस्था की रीढ़ है। मेहनती किसान खेतों में फसलें उगाते हैं और देश को अन्न प्रदान करते हैं। आधुनिक तकनीक और बेहतर सिंचाई से कृषि उत्पादकता में लगातार वृद्धि हो रही है।",
  },
  {
    title: '🌾 பொங்கல் அறுவடைத் திருநாள் (Pongal)',
    language: 'ta',
    text: "வணக்கம் நண்பர்களே. தமிழ்நாட்டில் பொங்கல் திருநாள் உழவர் மற்றும் அறுவடைத் திருநாளாக மகிழ்ச்சியுடன் கொண்டாடப்படுகிறது. புதுப் பானையில் புத்தரிசி இட்டு பொங்கலோ பொங்கல் என்று மக்கள் மகிழ்ச்சி பொங்கக் கொண்டாடுகிறார்கள்.",
  },
  {
    title: '💰 சேமிப்பு மற்றும் நிதி வளர்ச்சி (Finance)',
    language: 'ta',
    text: "தனிப்பட்ட நிதியை திறம்பட நிர்வகிப்பதற்கு நிலையான ஒழுக்கம் தேவைப்படுகிறது. வழக்கமான சேமிப்பு காலப்போக்கில் படிப்படியாக வளரும். கூட்டு வட்டி எதிர்காலத்திற்கு வலுவான நிதி பாதுகாப்பை உருவாக்குகிறது.",
  },
]

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

export default function JobSubmitForm({ onJobCreated, onJobSelected }: Props) {
  const [mode, setMode] = useState<InputMode>('text')
  const [scriptText, setScriptText] = useState('')
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [selectedRatios, setSelectedRatios] = useState<string[]>(['16:9'])
  const [narrationLanguage, setNarrationLanguage] = useState<string>('en')
  const [subtitleLanguage, setSubtitleLanguage] = useState<string>('en')
  const [narrationManualOverride, setNarrationManualOverride] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [recentJobs, setRecentJobs] = useState<JobStatus[]>([])
  const [loadingJobs, setLoadingJobs] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const detectedScriptLang = detectScriptLanguage(scriptText)

  // Automatically update narration language to match detected script unless user manually changed it
  useEffect(() => {
    if (!narrationManualOverride && mode === 'text') {
      setNarrationLanguage(detectedScriptLang)
    }
  }, [detectedScriptLang, narrationManualOverride, mode])

  useEffect(() => {
    async function loadRecent() {
      setLoadingJobs(true)
      try {
        const jobs = await listJobs(15)
        setRecentJobs(jobs)
      } catch (e) {
        console.warn('Could not load recent jobs:', e)
      } finally {
        setLoadingJobs(false)
      }
    }
    loadRecent()
  }, [])

  const currentLangObj = LANGUAGES.find(l => l.value === (mode === 'text' ? detectedScriptLang : narrationLanguage)) || LANGUAGES[0]

  const toggleRatio = (ratio: string) => {
    setSelectedRatios(prev =>
      prev.includes(ratio) ? prev.filter(r => r !== ratio) : [...prev, ratio]
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (selectedRatios.length === 0) {
      setError('Please select at least one aspect ratio.')
      return
    }

    setLoading(true)
    try {
      let job: JobStatus
      const effectiveNarration = narrationLanguage || (mode === 'text' ? detectedScriptLang : 'en')
      const effectiveSubtitle = subtitleLanguage || 'en'

      if (mode === 'text') {
        if (!scriptText.trim()) {
          setError('Please enter a script.')
          return
        }
        job = await submitTextJob(
          scriptText,
          selectedRatios,
          detectedScriptLang,
          null,
          undefined,
          undefined,
          effectiveNarration,
          effectiveSubtitle
        )
      } else {
        if (!audioFile) {
          setError('Please select an audio file.')
          return
        }
        job = await submitAudioJob(
          audioFile,
          selectedRatios,
          effectiveNarration,
          null,
          undefined,
          undefined,
          effectiveNarration,
          effectiveSubtitle
        )
      }
      onJobCreated(job)
    } catch (e: any) {
      setError(e.message || 'Submission failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setAudioFile(file)
  }

  const handleSelectRecent = (job: JobStatus) => {
    if (onJobSelected) {
      onJobSelected(job)
    } else {
      onJobCreated(job)
    }
  }

  return (
    <div className="submit-container">
      {/* Existing Jobs Quick Explorer (for Recruiters & Testers) */}
      {recentJobs.length > 0 && (
        <div className="card recent-jobs-card">
          <div className="recent-jobs-header">
            <div>
              <h3>🔍 Instant Showcase & Job Inspector</h3>
              <p className="card-sub">
                Select an existing processed job to immediately view all 7 pipeline steps, candidate score matrices, 30-column evaluation sheet, and MinIO storage.
              </p>
            </div>
            <span className="badge badge-info">{recentJobs.length} Jobs Available</span>
          </div>
          <div className="recent-jobs-grid">
            {recentJobs.slice(0, 6).map(j => (
              <button
                key={j.job_id}
                type="button"
                className={`recent-job-pill ${j.status === 'completed' ? 'success' : ''}`}
                onClick={() => handleSelectRecent(j)}
              >
                <div className="pill-top">
                  <span className="pill-id">{j.job_id}</span>
                  <span className={`badge ${j.status === 'completed' ? 'badge-success' : 'badge-warning'}`}>
                    {j.status}
                  </span>
                </div>
                <div className="pill-meta">
                  <span>{j.input_type.toUpperCase()}</span>
                  <span>·</span>
                  <span className="badge" style={{ padding: '1px 5px', fontSize: '10px' }}>
                    {j.language === 'hi' ? '🇮🇳 HI' : j.language === 'ta' ? '🇮🇳 TA' : '🇬🇧 EN'}
                  </span>
                  <span>·</span>
                  <span>{new Date(j.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main Submit Form */}
      <form onSubmit={handleSubmit} className="submit-form">
        {/* STEP 1: Input Content with Real-Time Script Language Detection */}
        <div className="card">
          <div className="card-header-row" style={{ marginBottom: '12px' }}>
            <div>
              <span className="step-tag">STEP 1: PROVIDE CONTENT</span>
              <h2 style={{ margin: '4px 0', fontSize: '1.3rem' }}>
                📝 Provide Script or Voiceover Audio
              </h2>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {mode === 'text' && scriptText.trim() && (
                <span className="badge badge-purple" style={{ padding: '4px 10px', fontSize: '0.8rem', fontWeight: 600 }}>
                  ⚡ Auto-Detected: {detectedScriptLang === 'ta' ? '🇮🇳 தமிழ் (Tamil)' : detectedScriptLang === 'hi' ? '🇮🇳 हिंदी (Hindi)' : '🇬🇧 English'}
                </span>
              )}
              <span className="badge badge-info">
                {mode === 'text' ? 'Text-to-Video' : 'Voiceover Alignment'}
              </span>
            </div>
          </div>

          {/* Input Mode Tabs */}
          <div className="mode-tabs">
            <button
              type="button"
              className={`mode-tab ${mode === 'text' ? 'active' : ''}`}
              onClick={() => setMode('text')}
            >
              <span>📝</span> Text Script (Any Language: EN / HI / TA)
            </button>
            <button
              type="button"
              className={`mode-tab ${mode === 'audio' ? 'active' : ''}`}
              onClick={() => setMode('audio')}
            >
              <span>🎙️</span> Audio Upload (Voiceover File)
            </button>
          </div>

          {/* Quick Script Presets */}
          {mode === 'text' && (
            <div className="presets-wrapper">
              <span className="presets-label">⚡ Demo Script Presets (Click to load):</span>
              <div className="presets-chips">
                {DEMO_PRESETS.map((p, i) => (
                  <button
                    key={i}
                    type="button"
                    className="preset-chip"
                    onClick={() => {
                      setScriptText(p.text)
                      setNarrationManualOverride(false)
                      setNarrationLanguage(p.language)
                      setSubtitleLanguage('en')
                    }}
                  >
                    {p.title}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Text Input */}
          {mode === 'text' && (
            <div className="form-group">
              <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Narration Script (English, हिंदी, or தமிழ்)</span>
                <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                  Auto-detects script language instantly · Preserved verbatim
                </span>
              </label>
              <textarea
                className="form-textarea"
                rows={6}
                placeholder="Type or paste your narration script in English, Hindi (हिंदी), or Tamil (தமிழ்)..."
                value={scriptText}
                onChange={e => setScriptText(e.target.value)}
                required
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', fontSize: '12px', color: '#94a3b8' }}>
                <span>Script Language: <strong style={{ color: '#38bdf8' }}>{detectedScriptLang === 'ta' ? 'தமிழ் (Tamil)' : detectedScriptLang === 'hi' ? 'हिंदी (Hindi)' : 'English'}</strong></span>
                <span>{scriptText.length.toLocaleString()} characters</span>
              </div>
            </div>
          )}

          {/* Audio Upload */}
          {mode === 'audio' && (
            <div className="form-group">
              <label className="form-label">Voiceover Audio File</label>
              <div
                className={`file-drop-zone ${audioFile ? 'has-file' : ''}`}
                onClick={() => fileRef.current?.click()}
              >
                {audioFile ? (
                  <div className="file-info">
                    <span className="file-icon">🎵</span>
                    <div>
                      <div className="file-name">{audioFile.name}</div>
                      <div className="file-size">
                        {(audioFile.size / 1024 / 1024).toFixed(2)} MB
                      </div>
                    </div>
                    <button
                      type="button"
                      className="file-remove"
                      onClick={e => {
                        e.stopPropagation()
                        setAudioFile(null)
                      }}
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <div className="file-placeholder">
                    <span className="drop-icon">📂</span>
                    <p>Click to select or drag voiceover audio file</p>
                    <p className="file-hint">MP3, WAV, or M4A · Automatic Whisper language detection (EN / HI / TA)</p>
                  </div>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".mp3,.wav,.m4a,audio/*"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
            </div>
          )}
        </div>

        {/* STEP 2: Dual Multilingual Customization Options */}
        <div className="card language-selection-card">
          <div className="card-header-row" style={{ marginBottom: '14px' }}>
            <div>
              <span className="step-tag">STEP 2: LANGUAGE CUSTOMIZATION</span>
              <h2 style={{ margin: '4px 0', fontSize: '1.3rem' }}>
                🌐 Narration Voice & Subtitle Settings
              </h2>
              <p className="card-sub" style={{ margin: 0 }}>
                Customize spoken voice and burned-in subtitle language independently.
              </p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            {/* Option 1: Narration Language */}
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label" style={{ fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
                <span>🎙️ Narration Language (Spoken Voice):</span>
                {!narrationManualOverride && mode === 'text' && (
                  <span style={{ fontSize: '11px', color: '#10b981', fontWeight: 500 }}>Auto-matches script</span>
                )}
              </label>
              <select
                value={narrationLanguage}
                onChange={e => {
                  setNarrationLanguage(e.target.value)
                  setNarrationManualOverride(true)
                }}
                style={{
                  background: '#0f172a',
                  border: '1px solid #334155',
                  color: '#f8fafc',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  width: '100%',
                  fontSize: '14px',
                }}
              >
                <option value="en">🇬🇧 English (en-US-ChristopherNeural)</option>
                <option value="hi">🇮🇳 हिंदी (Hindi - Madhur Neural)</option>
                <option value="ta">🇮🇳 தமிழ் (Tamil - Valluvar Neural)</option>
              </select>
              <span style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px', display: 'block' }}>
                {narrationManualOverride
                  ? 'Custom override selected'
                  : `Default: same as script (${detectedScriptLang.toUpperCase()})`}
              </span>
            </div>

            {/* Option 2: Subtitle Language */}
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label" style={{ fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
                <span>💬 Subtitle Language (On-Screen Captions):</span>
                <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 500 }}>Default: English</span>
              </label>
              <select
                value={subtitleLanguage}
                onChange={e => setSubtitleLanguage(e.target.value)}
                style={{
                  background: '#0f172a',
                  border: '1px solid #334155',
                  color: '#f8fafc',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  width: '100%',
                  fontSize: '14px',
                }}
              >
                <option value="en">🇬🇧 English (en - Default)</option>
                <option value="hi">🇮🇳 हिंदी (Hindi - Devanagari)</option>
                <option value="ta">🇮🇳 தமிழ் (Tamil - Unicode)</option>
              </select>
              <span style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px', display: 'block' }}>
                Default: English subtitles across all video scripts
              </span>
            </div>
          </div>
        </div>

        {/* STEP 3: Aspect Ratios */}
        <div className="card">
          <div className="card-header-row" style={{ marginBottom: '10px' }}>
            <div>
              <span className="step-tag">STEP 3: OUTPUT FORMAT</span>
              <h2 style={{ margin: '4px 0', fontSize: '1.3rem' }}>
                📐 Video Aspect Ratios
              </h2>
            </div>
            <span className="badge badge-purple">{selectedRatios.join(', ')}</span>
          </div>

          <div className="ratio-grid">
            {ASPECT_RATIOS.map(r => (
              <button
                key={r.value}
                type="button"
                className={`ratio-btn ${selectedRatios.includes(r.value) ? 'selected' : ''}`}
                onClick={() => toggleRatio(r.value)}
              >
                <span className="ratio-icon">{r.icon}</span>
                <span className="ratio-label">{r.label}</span>
                {selectedRatios.includes(r.value) && (
                  <span className="ratio-check">✓</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="error-banner" style={{ marginBottom: '16px' }}>
            ⚠️ {error}
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          className="submit-btn"
          disabled={loading || (mode === 'text' && !scriptText.trim()) || (mode === 'audio' && !audioFile)}
          style={{ width: '100%', padding: '16px', fontSize: '1.05rem', fontWeight: 700 }}
        >
          {loading ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
              <span className="spinner"></span> Generating Video (Voice: {narrationLanguage.toUpperCase()} · Captions: {subtitleLanguage.toUpperCase()})...
            </span>
          ) : (
            <span>🚀 Generate Video (Voice: {narrationLanguage.toUpperCase()} · Subtitles: {subtitleLanguage.toUpperCase()})</span>
          )}
        </button>
      </form>
    </div>
  )
}
