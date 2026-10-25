# AI Coding Tools Used

## Overview

This project was developed and maintained with assistance from an AI
assistant using the GitHub Copilot SDK in Visual Studio Code.

## AI Models and Agents Used

### Coding Agents

#### GitHub Copilot

GitHub Copilot, accessed through the Copilot SDK in Visual Studio Code, was
used for code exploration, implementation, debugging, documentation, testing,
and deployment assistance.

The exact underlying Copilot model can vary by workspace configuration and
was not recorded as part of the application runtime. No private prompts or
credentials are documented here.

#### Agent Antigravity

Agent Antigravity was used as an AI coding and project-assistance agent for
development workflow support, including analysis, implementation guidance,
documentation, and validation assistance.

The exact underlying model for Agent Antigravity is deployment-dependent and
was not recorded in the project source. This report identifies the agent by
name without claiming an unverified model version.

### Application AI Models

The following model identifiers are configured or used by the application:

| Area | Model or provider | Purpose |
|---|---|---|
| Scene planning | `gemini-3.5-flash-lite` | Narration analysis and structured scene planning |
| Visual verification | `gemini-3.5-flash-lite` | Strict image-to-narration relevance verification |
| Primary image generation | `gemini-2.5-flash-image` | Generate a scene image when stock candidates fail |
| Secondary image generation | `gemini-3.1-flash-lite-image` | Fallback image generation after primary-model failure |
| Local semantic ranking | OpenCLIP `ViT-B-32` | Optional local visual/semantic ranking |
| Speech-to-text | Whisper | Narration transcription and timing alignment |
| Optional speech-to-text | Groq-hosted models | Alternative transcription/provider path |
| Text-to-speech | Edge TTS, gTTS, pyttsx3 | Narration/audio synthesis fallback chain |


These provider models are attempted only when the corresponding provider path
is configured and available.

### Model Selection and Fallback Order

For scene visuals, the application uses this sequence:

```text
Pixabay retrieval and local ranking
        |
        v
Gemini visual verification
        |
        | no stock candidate passes
        v
gemini-2.5-flash-image
        |
        | generation failure
        v
gemini-3.1-flash-lite-image
        |
        | generation failure
        v
Best locally ranked Pixabay candidate
```

The selected asset provenance records the provider and actual successful
generation model where available.

## Tools and Capabilities Used

### GitHub Copilot SDK in Visual Studio Code

Used for:

- Exploring the existing backend, frontend, and deployment configuration.
- Tracing application behavior across API routes, services, workers, and UI
  components.
- Reviewing Docker and Google Cloud deployment configuration.
- Implementing focused code and configuration changes.
- Improving prompts for scene planning and visual verification.
- Implementing Gemini image-generation fallback behavior.
- Reviewing relevance-score and asset-provenance behavior.
- Creating deployment and project documentation.
- Suggesting and running focused validation commands.

### Workspace File and Code Tools

The AI-assisted workflow used workspace tools for:

- Reading source files and configuration.
- Searching for symbols, references, and relevant implementation patterns.
- Applying precise file edits.
- Reviewing staged files and exclusions before Git operations.

### Validation and Runtime Tools

The workflow also used command-line tools through the development environment
for:

- Python compilation and focused tests.
- Frontend builds.
- Docker Compose validation and service inspection.
- Container health checks.
- FFmpeg and FFprobe verification.
- Google Cloud VM, IAM, firewall, and deployment checks.
- HTTPS, certificate, and renewal verification.
- Git staging, secret checks, commits, and pushes.
