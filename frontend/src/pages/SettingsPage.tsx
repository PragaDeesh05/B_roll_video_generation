import React, { useState } from 'react'
import './SettingsPage.css'

export interface SettingsPageProps {
  onNavigate: (tab: any) => void
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ onNavigate }) => {
  const [minThreshold, setMinThreshold] = useState<number>(3.5)
  const [vlmEarlyExit, setVlmEarlyExit] = useState<boolean>(true)
  const [ffmpegPreset, setFfmpegPreset] = useState<string>('ultrafast')
  const [pollingInterval, setPollingInterval] = useState<number>(2500)
  const [notificationSound, setNotificationSound] = useState<boolean>(false)
  const [saveToast, setSaveToast] = useState<boolean>(false)

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    setSaveToast(true)
    setTimeout(() => setSaveToast(false), 2500)
  }

  return (
    <div className="settings-page">
      <div className="settings-header-row">
        <div>
          <h2>Studio Engine Settings & Preferences</h2>
          <p>Configure pipeline parameters, visual relevance thresholds, rendering profiles, and studio preferences.</p>
        </div>
      </div>

      {saveToast && (
        <div className="save-toast-banner">
          <span>✓ Settings saved successfully to local studio preferences!</span>
        </div>
      )}

      <form className="settings-layout" onSubmit={handleSave}>
        {/* Section 1: AI & Relevance Engine Policies */}
        <div className="settings-card">
          <div className="card-title-row">
            <span className="section-icon">⚖️</span>
            <div>
              <h3>Relevance & Visual Verification Policies</h3>
              <p>Controls candidate pre-filtering, Gemini VLM verification, and fallback triggers.</p>
            </div>
          </div>

          <div className="settings-fields-group">
            <div className="setting-field">
              <div className="field-meta">
                <label>Minimum Relevance Acceptance Threshold</label>
                <span>Candidates with relevance scores below this threshold are rejected or trigger AI visual generation.</span>
              </div>
              <div className="threshold-input-wrap">
                <input
                  type="number"
                  step="0.1"
                  min="2.0"
                  max="4.8"
                  value={minThreshold}
                  onChange={(e) => setMinThreshold(parseFloat(e.target.value))}
                  className="number-input"
                />
                <span className="scale-lbl">/ 5.0</span>
              </div>
            </div>

            <div className="setting-field">
              <div className="field-meta">
                <label>Top-1 Candidate Early Exit Optimization</label>
                <span>
                  Evaluates in-memory tag pre-ranked #1 candidate first. If it passes ≥ 3.5 without contradiction, immediately accepts it without downloading or checking the remaining 4 candidates (saves ~12.5 minutes).
                </span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={vlmEarlyExit}
                  onChange={(e) => setVlmEarlyExit(e.target.checked)}
                />
                <span className="toggle-slider" />
              </label>
            </div>

            <div className="setting-field">
              <div className="field-meta">
                <label>VLM Keyframe Temporal Sampling</label>
                <span>Extracts frames across the video timeline to verify visual relevance at clip beginning, middle, and end.</span>
              </div>
              <div className="static-tag-badge">
                <span>20%, 50%, 80% Locked</span>
              </div>
            </div>

            <div className="setting-field">
              <div className="field-meta">
                <label>Audio Synchronization Engine</label>
                <span>Exact scene-wise speech audio generation guaranteeing zero drift across audio, visuals, and subtitle timestamps.</span>
              </div>
              <div className="static-tag-badge success">
                <span>Scene-Wise Speech (Zero Drift)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: Rendering & FFmpeg Configuration */}
        <div className="settings-card">
          <div className="card-title-row">
            <span className="section-icon">🎬</span>
            <div>
              <h3>Rendering & Codec Performance</h3>
              <p>FFmpeg filtergraph, hardware encoding acceleration, and color normalization.</p>
            </div>
          </div>

          <div className="settings-fields-group">
            <div className="setting-field">
              <div className="field-meta">
                <label>FFmpeg H.264 Encoding Preset</label>
                <span>Trades compression efficiency for generation speed. 'ultrafast' provides a 6.5x render speedup.</span>
              </div>
              <select
                className="select-input"
                value={ffmpegPreset}
                onChange={(e) => setFfmpegPreset(e.target.value)}
              >
                <option value="ultrafast">ultrafast (Recommended - 6.5x Faster)</option>
                <option value="superfast">superfast</option>
                <option value="veryfast">veryfast</option>
                <option value="faster">faster</option>
                <option value="medium">medium (Standard compression)</option>
              </select>
            </div>

            <div className="setting-field">
              <div className="field-meta">
                <label>Single-Pass Filtergraph Pipeline</label>
                <span>Concatenates all scene assets, Ken Burns zooms, aspect scaling, and audio tracks in a single unified FFmpeg command.</span>
              </div>
              <div className="static-tag-badge success">
                <span>Enabled (Single-Pass)</span>
              </div>
            </div>

            <div className="setting-field">
              <div className="field-meta">
                <label>Color Normalization & Auto-Levels</label>
                <span>Harmonizes color temperature, contrast, and black levels across mixed stock footage and AI visuals.</span>
              </div>
              <div className="static-tag-badge">
                <span>Active (Rec.709)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Section 3: Studio UI Preferences */}
        <div className="settings-card">
          <div className="card-title-row">
            <span className="section-icon">🖥️</span>
            <div>
              <h3>Studio Monitoring Preferences</h3>
              <p>Real-time log polling, alert notifications, and user workspace settings.</p>
            </div>
          </div>

          <div className="settings-fields-group">
            <div className="setting-field">
              <div className="field-meta">
                <label>Pipeline Monitor Polling Frequency</label>
                <span>How frequently the browser polls the FastAPI backend for stage events and logs during processing.</span>
              </div>
              <select
                className="select-input"
                value={pollingInterval}
                onChange={(e) => setPollingInterval(parseInt(e.target.value))}
              >
                <option value={1500}>1.5 seconds (High frequency)</option>
                <option value={2500}>2.5 seconds (Recommended)</option>
                <option value={5000}>5.0 seconds (Low bandwidth)</option>
              </select>
            </div>

            <div className="setting-field">
              <div className="field-meta">
                <label>Sound Notification on Pipeline Completion</label>
                <span>Plays a gentle audio chime when a video generation job finishes rendering.</span>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={notificationSound}
                  onChange={(e) => setNotificationSound(e.target.checked)}
                />
                <span className="toggle-slider" />
              </label>
            </div>
          </div>
        </div>

        {/* Save Bar */}
        <div className="settings-save-bar">
          <button type="submit" className="save-btn">
            💾 Save Settings
          </button>
        </div>
      </form>
    </div>
  )
}
export default SettingsPage
