# External Integrations

**Analysis Date:** 2026-02-04

## APIs & External Services

**AI Providers:**
- Google Gemini API - Video + transcript analysis
  - SDK/Client: `google-genai` (`src/podcast_pipeline/providers/gemini.py`)
  - Auth: `GEMINI_API_KEY` (loaded in `src/podcast_pipeline/config/settings.py`)
- Kimi (Moonshot) API - Fallback transcript analysis
  - SDK/Client: `httpx` (`src/podcast_pipeline/providers/kimi.py`)
  - Auth: `KIMI_API_KEY` (loaded in `src/podcast_pipeline/config/settings.py`)

**Research:**
- YouTube Data API - Trend and competitor research
  - Client: `httpx` (`src/podcast_pipeline/research/youtube.py`)
  - Auth: `YOUTUBE_API_KEY` (loaded in `src/podcast_pipeline/config/settings.py`)

## Data Storage

**Databases:**
- Not detected (state stored on filesystem)
  - State: `jobs/<job_id>/state.json` (`src/podcast_pipeline/models/job.py`)
  - Artifacts: `jobs/<job_id>/analysis/*`, `jobs/<job_id>/output/*`

**File Storage:**
- Local filesystem only (`jobs/`, `models/`, configured in `config.yaml`)

**Caching:**
- None detected (Whisper model caching uses local filesystem path in `config.yaml`)

## Authentication & Identity

**Auth Provider:**
- API key auth only (Gemini, Kimi, YouTube)
  - Implementation: Environment variables loaded via `python-dotenv` (`src/podcast_pipeline/config/settings.py`)

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- Structured logging via `structlog` (`src/podcast_pipeline/utils/logging.py`)

## CI/CD & Deployment

**Hosting:**
- Local execution (CLI + Streamlit UI)

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars:**
- `GEMINI_API_KEY` (primary AI provider)
- `KIMI_API_KEY` (fallback provider)
- `YOUTUBE_API_KEY` (research)
- `OPENAI_API_KEY` (declared but no provider implementation found)

**Secrets location:**
- `.env` in project root (loaded in `src/podcast_pipeline/config/settings.py`)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-02-04*
