# Incubrix B-Roll Video Generation Engine

## 1. Executive Summary

Incubrix is an automated B-roll video generation platform that converts a
narration script or uploaded audio into captioned videos. The system plans
scenes, retrieves and ranks visual assets, verifies visual relevance, falls
back to Gemini image generation when stock footage is unsuitable, and renders
multiple output formats with FFmpeg.

The application includes:

- A FastAPI backend for job processing and artifact management.
- A React/Vite frontend for job submission, monitoring, inspection, and
  evaluation.
- Pixabay asset retrieval and local relevance ranking.
- Gemini/Vertex AI scene planning and visual verification.
- Gemini image-generation fallback models.
- Redis and MinIO services for containerized deployments.
- FFmpeg-based rendering and FFprobe output validation.
- Docker Compose deployment for local and Google Cloud VM environments.
- Nginx HTTPS termination with automatic Let's Encrypt renewal.

## 2. Project Objectives

The project is designed to:

1. Convert written narration or audio narration into a structured scene plan.
2. Select visual media that matches each scene's literal subject and action.
3. Avoid repeating visual concepts across scenes.
4. Use conservative visual verification rather than broad thematic similarity.
5. Provide a bounded, traceable fallback path when stock footage fails.
6. Generate validated videos in common aspect ratios.
7. Expose scene-level provenance, scores, and validation information.
8. Support local development, Docker deployment, and GCP VM hosting.

## 3. System Architecture

```text
                         +----------------------+
                         |  Browser / User      |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | React/Vite Frontend  |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | Nginx HTTP/HTTPS     |
                         | Reverse Proxy        |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | FastAPI Backend      |
                         | Job Orchestration    |
                         +---+-------+-------+--+
                             |       |       |
                             v       v       v
                         Gemini   Pixabay  Redis
                         /Vertex  API      Service
                             |
                             v
                    +----------------------+
                    | Scene Assets         |
                    | MinIO / Local Storage|
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | FFmpeg / FFprobe     |
                    | Rendering/Validation |
                    +----------------------+
```

## 4. Main Components

### 4.1 Backend

The backend is a Python FastAPI application. It provides:

- Job submission and status tracking.
- Text and audio input handling.
- Scene planning.
- Candidate retrieval and ranking.
- Visual verification.
- Image-generation fallback.
- Timeline and caption generation.
- Video rendering.
- Artifact and evaluation endpoints.
- Health and readiness checks.

Important backend areas include:

```text
backend/app/api/
backend/app/services/
backend/app/workers/
backend/app/models/
backend/app/schemas/
backend/app/utils/
```

### 4.2 Frontend

The frontend is a React/Vite application served through Nginx. It provides:

- Text-script and audio-upload forms.
- Job progress monitoring.
- Video library and artifact views.
- Scene inspection.
- Candidate and score inspection.
- Evaluation and human-rating workflows.
- System health information.

### 4.3 External AI Services

The system supports:

- Gemini API key authentication.
- Vertex AI authentication using Google Application Default Credentials.
- Gemini scene planning.
- Strict visual verification.
- Gemini image generation.

In production on Compute Engine, the preferred authentication mechanism is
an attached VM service account with Vertex AI permissions. Local user ADC
files should not be copied into production containers.

### 4.4 Media Services

- Pixabay provides stock images and videos.
- FFmpeg performs media conversion and final rendering.
- FFprobe validates generated video metadata.
- MinIO provides S3-compatible object storage when enabled.
- Redis provides the containerized service used by the application.

## 5. Video Generation Workflow

### 5.1 Input

The user can submit:

- A written narration script.
- An uploaded narration audio file.

Supported output profiles include:

- 16:9 landscape.
- 9:16 portrait.
- 1:1 square.

### 5.2 Audio Preparation

For audio input, the backend:

1. Validates the file type and size.
2. Determines the narration duration.
3. Transcribes the narration when possible.
4. Aligns narration text to a timeline.
5. Falls back to duration-based alignment when transcription is unavailable.

### 5.3 Scene Planning

The planner converts narration into scene-level requirements, including:

- Scene narration text.
- Visual subject.
- Visual action.
- Setting and context.
- Search queries.
- Alternative search queries.
- Image-generation prompt.
- Narrative role.
- Timeline duration.

Planning prompts require literal visual evidence and discourage:

- Reusing the same visual concept.
- Repeating the opening visual at the ending.
- Reusing generic images for different actions.
- Selecting an image that matches only the broad topic.

### 5.4 Stock Asset Retrieval

For each scene:

1. Pixabay candidates are retrieved.
2. Candidates are locally ranked.
3. Relevance scores are calculated.
4. Candidates are considered in local-rank order.
5. Candidates are sent to the visual verifier when verification is required.
6. The first passing candidate is selected.

The frontend uses the term **Relevance Score** for the scene-facing score.

### 5.5 Gemini Visual Verification

The visual verifier is intentionally strict. It checks whether the image
contains the required:

- Objects.
- People or entities.
- Actions.
- Settings.
- Relationships.
- Narrative-specific evidence.

Broad thematic similarity is not sufficient. If an essential object or action
is absent, the candidate should be rejected or receive a low score.

### 5.6 Image-Generation Fallback

The fallback path is bounded and deterministic:

```text
Pixabay retrieval
        |
        v
Local ranking and candidate verification
        |
        | no candidate passes
        v
gemini-2.5-flash-image
        |
        | failure after retries
        v
gemini-3.1-flash-lite-image
        |
        | failure
        v
Best locally ranked Pixabay candidate
```

If a Gemini image is successfully generated, it is accepted as the selected
scene image without another generation cycle. The provenance records the
actual model used.

If both Gemini models fail, the top locally ranked Pixabay candidate is
retained. This includes quota exhaustion, model errors, authentication errors,
network errors, and other generation failures.

### 5.7 Rendering

The backend:

1. Builds the scene timeline.
2. Prepares video and image assets.
3. Generates subtitles and timing tracks.
4. Combines audio, visuals, and captions.
5. Renders requested aspect ratios with FFmpeg.
6. Validates the outputs with FFprobe.
7. Persists manifests, timelines, captions, and validation reports.

## 6. Fallback and Resilience Behavior

| Component | Primary behavior | Fallback |
|---|---|---|
| Gemini scene planning | Gemini/Vertex AI planning | Sentence-boundary planner |
| Pixabay retrieval | Real Pixabay candidates | Mock/placeholder assets |
| Visual verification | Vertex AI or Gemini API | Deterministic local verifier |
| Primary image generation | `gemini-2.5-flash-image` | Secondary Gemini image model |
| Secondary image generation | `gemini-3.1-flash-lite-image` | Best local Pixabay candidate |
| TTS | Edge TTS | gTTS, then pyttsx3 |
| Transcription | Whisper | Duration-based alignment |
| Storage | MinIO/object storage | Local filesystem |
| Rendering | FFmpeg | Explicit job failure if unavailable |

Failures are recorded in job logs and provenance metadata where possible.

## 7. Data and Artifact Model

Job data is stored under:

```text
storage/jobs/{job_id}/
```

Typical job artifacts include:

- Rendered MP4 files.
- Scene images and videos.
- Captions.
- Timeline JSON.
- Manifest JSON.
- Validation report JSON.
- Evaluation sheet data.
- Candidate metadata.
- Relevance explanations.
- Provider and model provenance.

Generated media and runtime storage are intentionally excluded from Git.

## 8. API Surface

### Job operations

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/jobs` | Submit a text-script job |
| POST | `/jobs/upload` | Submit an audio job |
| GET | `/jobs` | List jobs |
| GET | `/jobs/{job_id}` | Read job status |
| POST | `/api/v1/jobs/{job_id}/cancel` | Cancel a job |
| POST | `/api/v1/jobs/{job_id}/retry` | Retry a failed job |
| GET | `/api/v1/jobs/{job_id}/logs` | Read job logs |

### Artifact operations

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/jobs/{job_id}/timeline` | Read timeline data |
| GET | `/jobs/{job_id}/manifest` | Read output manifest |
| GET | `/jobs/{job_id}/captions` | Download captions |
| GET | `/jobs/{job_id}/validation` | Read validation report |
| GET | `/jobs/{job_id}/artifacts` | List artifacts |
| GET | `/jobs/{job_id}/download/{file}` | Download an artifact |
| GET | `/api/v1/jobs/{job_id}/candidates` | Read candidate data |

### Scene operations

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/jobs/{job_id}/scenes/{scene_id}/swap-clip` | Replace a scene asset |
| GET | `/api/v1/jobs/{job_id}/evaluation` | Read evaluation data |
| POST | `/api/v1/jobs/{job_id}/evaluation/rate` | Save a human rating |

### Service operations

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Basic health and media-tool check |
| GET | `/ready` | Dependency and configuration readiness |

## 9. Deployment Summary

### Local deployment

Local development uses:

```text
Python backend
React/Vite frontend
Optional Redis
Optional MinIO
Local SQLite and filesystem storage
```

### Docker deployment

Docker services are defined in:

```text
docker-compose.yml
docker-compose.gcp.yml
```

The GCP configuration includes:

- Backend container.
- Frontend/Nginx container.
- Redis container.
- MinIO container.
- Persistent MinIO volume.
- Persistent backend storage mount.
- Internal-only backend, Redis, and MinIO services.
- Public frontend HTTP/HTTPS ports.

### Google Cloud VM

The deployed VM uses:

```text
Project: incubrix-project1
VM: incubrix-vm
Zone: asia-south1-a
Machine type: e2-standard-4
Disk: 200 GB SSD
Service account: incubrix-vm@incubrix-project1.iam.gserviceaccount.com
```

The VM service account has:

- `roles/aiplatform.user`
- `roles/logging.logWriter`
- `roles/monitoring.metricWriter`

The VM uses the `cloud-platform` OAuth scope, while IAM roles limit access.

## 10. HTTPS Deployment

The hosted website uses:

```text
https://34-93-105-109.sslip.io
```

The hostname resolves to the VM IP using `sslip.io`. Nginx:

- Redirects port 80 to port 443.
- Terminates TLS.
- Proxies API requests to the backend container.
- Serves the frontend application.

Let's Encrypt provides the certificate. Certbot renewal hooks:

1. Stop the frontend container so standalone validation can use port 80.
2. Renew the certificate.
3. Copy the renewed certificate into the Nginx-mounted directory.
4. Restart the frontend container.

The raw IP URL is not equivalent to the hostname URL. A certificate issued
for `34-93-105-109.sslip.io` will not validate for `34.93.105.109`.

## 11. Security Controls

The deployment follows these security practices:

- Environment files are excluded from Git.
- API keys are not stored in source files.
- Google credentials are not committed.
- TLS private keys are excluded from Git.
- Generated videos and job media are excluded from Git.
- Redis and MinIO are not publicly exposed in the GCP Compose file.
- Backend port 8000 is internal to the Docker network.
- SSH access is restricted and IAP is available.
- The VM uses a dedicated service account.
- Strong MinIO credentials are configured outside source control.
- Health checks avoid exposing credential values.

## 12. Testing and Validation

Validation performed during development and deployment included:

- Python compilation checks.
- Focused backend test suites.
- Frontend TypeScript and production builds.
- Docker Compose configuration checks.
- Backend health checks.
- FFmpeg and FFprobe checks.
- Redis `PONG` check.
- Vertex client initialization.
- Authenticated Vertex text requests.
- Authenticated Vertex image-generation requests.
- HTTPS certificate verification.
- HTTP-to-HTTPS redirect verification.
- Let's Encrypt renewal dry-run verification.

Recommended commands:

```bash
cd backend
python -m pytest -q
python -m py_compile app/services/image_generation_service.py
```

```bash
docker compose config
docker compose ps
docker compose logs --tail=200 backend
```

## 13. Known Limitations

### No custom domain

The current deployment uses an `sslip.io` hostname. A custom domain is
recommended for production branding and long-term DNS ownership.

### Image-generation quotas

Vertex image-generation models can return quota or resource-exhaustion
errors. The secondary model and Pixabay fallback reduce impact but do not
remove provider quota limits.

### SQLite suitability

SQLite is suitable for local and low-volume use. A production installation
with concurrent workers should use PostgreSQL or another managed database.

### Storage growth

Generated videos and intermediate media can consume substantial disk space.
Retention policies, backups, and disk monitoring are required for long-running
deployments.

### Visual uniqueness

Planner prompts and candidate selection reduce repeated scenes, but external
stock catalogs can still return visually similar assets. Strict uniqueness
cannot be guaranteed by prompts alone.

### HTTPS hostname dependency

The browser-trusted certificate applies to the configured hostname, not the
VM's numeric IP address.

## 14. Recommended Future Improvements

1. Attach a custom domain and use managed DNS.
2. Move SQLite data to PostgreSQL.
3. Move generated assets to managed object storage.
4. Add formal job retention and cleanup tasks.
5. Add metrics and alerting for Gemini quota failures.
6. Add asynchronous worker scaling for concurrent jobs.
7. Add authenticated user access to the hosted website.
8. Add automated deployment from the Git repository.
9. Add integration tests for both Gemini image models.
10. Add a persistent certificate deployment strategy using a reverse proxy
    managed outside the frontend container.

## 15. Repository Contents

```text
backend/
  app/
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
report.md
```

Runtime data, secrets, generated videos, local databases, caches, and TLS
private keys are not part of the repository.

## 16. Conclusion

Incubrix provides a complete narration-to-video pipeline with AI-assisted
scene planning, strict visual validation, deterministic asset fallback,
multi-format rendering, and cloud deployment support. The current system is
operational in Docker on Google Cloud with Vertex AI authentication, HTTPS,
automatic certificate renewal, and a controlled Gemini image-generation
fallback path.
