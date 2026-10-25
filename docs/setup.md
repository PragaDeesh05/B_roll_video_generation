# Setup & Deployment Guide

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | ≥ 3.11 | `python --version` |
| FFmpeg | any modern | `ffmpeg -version` |
| FFprobe | same build as FFmpeg | `ffprobe -version` |
| Node.js | ≥ 18 | `node --version` |
| npm | ≥ 9 | `npm --version` |

## 1. Clone & Navigate

```bash
cd ag_incubrix
```

## 2. Backend Setup

```bash
cd backend

# Create & activate virtual environment (recommended)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env file and fill in your API keys
copy ..\\.env.example ..\\.env   # Windows
# cp ../.env.example ../.env     # macOS/Linux
```

Edit `.env` and fill in:
```
GEMINI_API_KEY=your_gemini_api_key_here
PIXABAY_API_KEY=your_pixabay_api_key_here
```

> **API Keys:**
> - **Gemini**: https://aistudio.google.com/app/apikey (free tier available)
> - **Pixabay**: https://pixabay.com/api/docs/ (free, register at pixabay.com)

## 3. Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The API will be available at http://localhost:8000  
Interactive docs: http://localhost:8000/docs

## 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

## 5. Running Tests

```bash
cd backend
python -m pytest tests/test_all.py -v --timeout=30
```

All 39 tests should pass. No API keys required for tests (fully mocked).

## 6. Verify the Setup

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`/ready` will report any missing API keys.

## 7. Using the Application

1. Open http://localhost:5173
2. Select **Text Script** or **Audio Upload**
3. Enter your script or upload MP3/WAV/M4A (max 10 min)
4. Select output aspect ratio(s): 16:9, 9:16, 1:1
5. Click **Generate Video**
6. Monitor progress in real time
7. Download MP4, captions, timeline, manifest, validation report

## 8. API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/jobs` | Submit text script job |
| POST | `/jobs/upload` | Submit audio file job |
| GET | `/jobs/{id}` | Get job status & progress |
| GET | `/jobs/{id}/timeline` | Get timeline.json |
| GET | `/jobs/{id}/manifest` | Get manifest.json |
| GET | `/jobs/{id}/captions` | Download captions.srt |
| GET | `/jobs/{id}/validation` | Get validation report |
| GET | `/jobs/{id}/artifacts` | List all artifacts |
| GET | `/jobs/{id}/download/{file}` | Download a file |
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |

## 9. Fallback Behavior

| External Service | If Unavailable |
|-----------------|----------------|
| Gemini API | Sentence-boundary fallback planner used |
| Pixabay API | Returns `None` per scene; placeholder video used |
| TTS (edge-tts) | Falls back to gTTS → pyttsx3 |
| Whisper | Falls back to duration-based alignment |
| FFmpeg | Job fails with clear error message |

## 10. Development Without API Keys

The application runs in **mock mode** without API keys:
- Scene planner uses sentence-boundary splitting
- Pixabay provider returns mock asset records (no real downloads)
- TTS uses local engines (edge-tts / gTTS / pyttsx3)
- Rendered video uses solid-color placeholders for missing clips

Set `GEMINI_API_KEY=` and `PIXABAY_API_KEY=` empty to force mock mode.

## 11. Production Notes

- The default SQLite DB (`storage/broll.db`) is fine for local/demo use
- For production, set `DATABASE_URL` to PostgreSQL
- All generated files are stored in `storage/jobs/{job_id}/`
- No API keys are ever logged or included in JSON artifacts
- The `storage/` directory should NOT be committed to git
