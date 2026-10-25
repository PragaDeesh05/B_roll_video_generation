# Incubrix B-Roll Video Generation Engine

An end-to-end video generation system that converts a text script or narration
audio into captioned videos with scene planning, stock-footage retrieval,
visual relevance scoring, Gemini visual verification, AI image fallback, and
multi-aspect-ratio rendering.

## Features

- Text-script and audio-upload video generation.
- Gemini-powered narration analysis and scene planning.
- Scene-level visual subjects, actions, search queries, and image-generation
  prompts.
- Pixabay image/video retrieval with local relevance ranking.
- Sequential visual candidate verification.
- Strict Gemini/Vertex AI visual verification.
- Gemini image generation fallback:
  - Primary model: `gemini-2.5-flash-image`
  - Secondary model: `gemini-3.1-flash-lite-image`
- Pixabay fallback when both Gemini image models fail.
- Local/mock fallback behavior for development without external API keys.
- TTS fallback chain using Edge TTS, gTTS, and pyttsx3.
- Whisper transcription with duration-based alignment fallback.
- FFmpeg and FFprobe media processing.
- Output profiles for 16:9, 9:16, and 1:1.
- Scene evaluation metadata, relevance scores, validation reports, and
  downloadable artifacts.
- React/Vite frontend served through Nginx.
- Optional Redis and MinIO services for containerized deployments.
- Docker Compose deployment for local and Google Cloud VM environments.
- HTTPS support through Nginx and Let's Encrypt.

## Architecture

```text
User
  |
  v
React/Vite frontend
  |
  v
Nginx reverse proxy
  |
  v
FastAPI backend
  |             |             |
  v             v             v
Gemini/Vertex  Pixabay       Redis
AI services    API            queue/cache
  |
  v
MinIO / local storage
  |
  v
FFmpeg rendering and video artifacts
```

The backend is the source of truth for job state, scene planning, candidate
selection, scoring, rendering, and artifact persistence.

## Requirements

### Local development

- Python 3.11 or newer
- Node.js 18 or newer
- npm 9 or newer
- FFmpeg and FFprobe
- Git

### Docker deployment

- Docker Engine
- Docker Compose v2
- At least 4 vCPUs and 16 GB RAM recommended for video processing
- Additional disk space for generated media and MinIO data

## Configuration

Copy the example configuration:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS/Linux

```bash
cp .env.example .env
```

Set values in `.env` as required:

```dotenv
GEMINI_API_KEY=
PIXABAY_API_KEY=
DATABASE_URL=sqlite:///./storage/broll.db
REDIS_URL=redis://localhost:6379/0
OUTPUT_DIR=./storage/jobs
UPLOAD_DIR=./storage/uploads
CACHE_DIR=./storage/cache
FALLBACK_LIBRARY_DIR=./storage/fallback_library
MAX_UPLOAD_SIZE_MB=200
MAX_AUDIO_DURATION_SECONDS=600
DEFAULT_FRAME_RATE=30
DEFAULT_ASPECT_RATIO=16:9
ENABLE_AI_IMAGE_FALLBACK=false
ENABLE_CLIP_RANKING=false
USE_IN_PROCESS_WORKER=true
APP_VERSION=1.0.0
LOG_LEVEL=INFO
```

Never commit `.env`, API keys, Google credentials, certificates, private keys,
databases, generated videos, or job media. These paths are excluded by
`.gitignore`.

### Google Vertex AI

For Vertex AI instead of the Gemini API-key path, configure:

```dotenv
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global
IMAGE_GEN_PROVIDER=vertexai
VISUAL_VERIFIER_PROVIDER=vertexai
ENABLE_AI_IMAGE_FALLBACK=true
```

Use Application Default Credentials locally:

```bash
gcloud auth application-default login
```

On Google Compute Engine, prefer an attached VM service account with
`roles/aiplatform.user`. Do not copy local user credential files into a
production VM or commit them to Git.

## Local backend setup

```bash
cd backend
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend endpoints:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Readiness: `http://localhost:8000/ready`

## Local frontend setup

```bash
cd frontend
npm install
npm run dev
```

The development frontend is normally available at:

```text
http://localhost:5173
```

## Docker deployment

### Local Compose stack

From the project root:

```bash
docker compose up -d --build
docker compose ps
```

The local stack contains:

| Service | Purpose | Default port |
|---|---|---:|
| `backend` | FastAPI application | 8000 |
| `frontend` | Nginx-served web application | 5173 |
| `redis` | Redis service | 6379 |
| `minio` | Object storage | 9000 / 9001 |

Verify the backend:

```bash
curl http://localhost:8000/health
```

### Google Cloud VM Compose stack

The production-oriented configuration is
`docker-compose.gcp.yml`. It uses the VM service account for Google
authentication and keeps Redis, MinIO, and the backend internal to the Docker
network.

```bash
docker compose -f docker-compose.gcp.yml config
docker compose -f docker-compose.gcp.yml up -d --build
docker compose -f docker-compose.gcp.yml ps
```

The GCP frontend publishes:

- HTTP: port 80
- HTTPS: port 443

Do not expose Redis, MinIO, or the backend directly to the public Internet.

## HTTPS

For a trusted certificate, use a DNS name that resolves to the VM. The
deployed example uses:

```text
https://34-93-105-109.sslip.io
```

The hostname resolves to the VM IP through `sslip.io`. Nginx redirects HTTP
to HTTPS, and Certbot obtains and renews the Let's Encrypt certificate.

A certificate for the raw IP address is not publicly trusted. A self-signed
certificate encrypts traffic but causes browser authority warnings.

## Video generation flow

1. The user submits a text script or narration audio.
2. Audio is validated and transcribed when necessary.
3. Gemini analyzes the narration and creates a scene plan.
4. The plan is aligned to the narration timeline.
5. Each scene is safety-checked and assigned visual requirements.
6. Pixabay candidates are fetched and locally ranked.
7. Candidates are sent to the visual verifier in local-rank order.
8. The first passing stock candidate is selected.
9. If stock candidates fail, the primary Gemini image model is attempted.
10. If the primary model fails, the secondary Gemini image model is attempted.
11. A genuine Gemini-generated image is accepted without another generation
    cycle.
12. If both Gemini models fail, the best locally ranked Pixabay candidate is
    retained.
13. Audio, captions, scene media, and timelines are rendered with FFmpeg.
14. Each requested aspect ratio is rendered and validated with FFprobe.
15. Manifests, evaluation sheets, captions, and validation reports are saved.

## Gemini image fallback behavior

The image-generation fallback is intentionally bounded:

```text
gemini-2.5-flash-image
        |
        | failure after retries
        v
gemini-3.1-flash-lite-image
        |
        | failure
        v
best locally ranked Pixabay candidate
```

The selected asset provenance records the actual successful provider and model.
No image is silently reported as Gemini-generated when the pipeline actually
used Pixabay or a mock fallback.

## API overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/jobs` | Submit a text-script job |
| POST | `/jobs/upload` | Submit an audio job |
| GET | `/jobs` | List jobs |
| GET | `/jobs/{job_id}` | Get job status |
| GET | `/jobs/{job_id}/timeline` | Get timeline data |
| GET | `/jobs/{job_id}/manifest` | Get output manifest |
| GET | `/jobs/{job_id}/captions` | Download captions |
| GET | `/jobs/{job_id}/validation` | Get validation report |
| GET | `/jobs/{job_id}/artifacts` | List job artifacts |
| GET | `/jobs/{job_id}/logs` | Get job logs |
| GET | `/jobs/{job_id}/download/{file}` | Download an artifact |
| GET | `/health` | Service health |
| GET | `/ready` | Dependency/API readiness |
| POST | `/api/v1/jobs/{job_id}/cancel` | Cancel a job |
| POST | `/api/v1/jobs/{job_id}/retry` | Retry a failed job |
| POST | `/api/v1/jobs/{job_id}/scenes/{scene_id}/swap-clip` | Swap a scene asset |

## Output artifacts

Each job is stored under:

```text
storage/jobs/{job_id}/
```

Typical artifacts include:

- Rendered MP4 videos
- `captions.srt`
- `timeline.json`
- `manifest.json`
- `validation_report.json`
- Evaluation sheet data
- Scene candidate and provenance metadata

Generated artifacts are intentionally excluded from Git.

## Testing

From the backend directory:

```bash
python -m pytest -q
```

Focused examples:

```bash
python -m pytest -q tests/test_best_effort_fallback.py
python -m pytest -q tests/test_phase9.py
```

Compile-check the image generation service:

```bash
python -m py_compile app/services/image_generation_service.py
```

The test suite is designed to run without production API keys by using mocks
and deterministic fallback behavior where appropriate.

## Troubleshooting

### Backend stuck during planning

Check:

```bash
docker compose logs --tail=200 backend
docker compose exec backend python -c "from google import genai; print('google.genai OK')"
```

Confirm that the VM has:

- A working attached service account
- Vertex AI API enabled
- `roles/aiplatform.user`
- `google-genai` installed
- A reachable Vertex AI endpoint

### Gemini image generation fails

Inspect the job timeline and provenance. Common causes include:

- Vertex quota exhaustion (`429 RESOURCE_EXHAUSTED`)
- Invalid or unavailable model
- Missing ADC credentials
- Network/API errors

The pipeline should attempt the secondary model before using the local
Pixabay fallback.

### HTTPS certificate warning

Use the hostname issued in the certificate, not the raw VM IP. A certificate
for `34-93-105-109.sslip.io` will not validate for
`https://34.93.105.109`.

### Storage growth

Generated media can consume substantial disk space. Monitor:

```bash
du -sh storage/jobs
df -h
```

Back up required data separately and remove old generated jobs according to
your retention policy.

## Security notes

- Keep `.env` files out of Git.
- Use a dedicated VM service account instead of user ADC files in production.
- Restrict SSH access to a known IP or use Identity-Aware Proxy.
- Expose only HTTP/HTTPS publicly.
- Use strong MinIO credentials.
- Do not expose Redis or MinIO administrative ports publicly.
- Rotate API keys if they are accidentally exposed.
- Store generated media on persistent storage with an explicit retention
  policy.

## Repository layout

```text
backend/
  app/
    api/
    models/
    schemas/
    services/
    utils/
    workers/
  tests/
  Dockerfile
  requirements.txt
frontend/
  src/
  Dockerfile
  nginx.conf
docker-compose.yml
docker-compose.gcp.yml
.env.example
.gitignore
README.md
```

## License and third-party services

Review the licenses and terms for all third-party services and media sources
used by your deployment, including Pixabay, Google Gemini/Vertex AI, MinIO,
FFmpeg, Whisper, and TTS providers. Generated output usage is subject to the
terms of the configured providers.
