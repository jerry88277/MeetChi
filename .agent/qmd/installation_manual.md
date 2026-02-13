# MeetChi Developer Setup & Installation Guide

This guide provides the necessary steps and configuration details to set up the MeetChi platform (Frontend, Backend, and LLM Service) locally or in a production environment.

## 1. System Requirements

- **Local Development**:
    - **OS**: Windows (for Tauri Client), Linux/macOS (for Backend/Frontend).
    - **Node.js**: v20+ (Next.js 16 requirements).
    - **Python**: v3.10+ (Backend and LLM Service).
    - **Database**: PostgreSQL v15+.
    - **Rust**: Latest stable (for Tauri Client).
- **Production (GCP)**:
    - **Region**: `asia-southeast1` (Singapore).
    - **Deployment Tiers**:
        - **Tier 1 (Production Default)**: Gemini API-only. Runs on Standard Cloud Run CPU instances (no GPU req).
        - **Tier 2 (Legacy/ASR)**: Requires `NvidiaL4GpuAllocPerProjectRegion` for local WhisperX/Diarization.

---

## 2. Shared Infrastructure

### Database (PostgreSQL)
- **Database Name**: `meetchi`
- **Default Port**: `5432`
- **Schema Management**: Handled via Alembic (`apps/backend/alembic`).
- **Critical Tables**: `meetings`, `transcript_segments`, `folders`, `keyword_corrections`.

### Google Cloud Tasks
- **Usage**: Used for asynchronous summarization and ASR post-processing.
- **Local Fallback**: Uses standard FastAPI `BackgroundTasks` if `CLOUD_TASKS_ENABLED=false`.

---

## 3. Backend Service Setup

### Environment Variables (`apps/backend/.env`)
| Variable | Description | Default/Example |
|----------|-------------|-----------------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/meetchi` |
| `LLM_SERVICE_URL` | URL of the LLM/GPU service | `http://localhost:8001` |
| `AUTH_REQUIRED` | Enable JWT/OAuth verification | `true` (Production) / `false` (Dev) |
| `GOOGLE_CLIENT_ID`| OAuth Client ID for token validation | `...apps.googleusercontent.com` |
| `ADMIN_EMAILS` | Whitelist of admin users | `user@example.com` |

### Installation
1. Create virtual environment: `python -m venv .venv`
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `alembic upgrade head`
4. Start service: `uvicorn app.main:app --reload --port 8000`

---

### Deployment Tiers

#### Side A: Local Development / Hybrid (Tier 2)
1. **Requirements**: NVIDIA GPU with CUDA.
2. **Setup**:
    - Install PyTorch with CUDA support.
    - Install requirements: `pip install -r requirements-gpu.txt`
3. **Execution**: `python app.py --port 8001`

#### Side B: Production Cloud Run (Tier 1 - Optimized)
1. **Requirements**: Standard Cloud Run CPU slot.
2. **Setup**:
    - Uses `python:3.11-slim` base image.
    - Requirements: `flask`, `google-genai`, `pydantic`.
    - **API Key**: Must provide `GEMINI_API_KEY` (Secret Manager) and `USE_GEMINI=true`.
3. **Execution**: `python app.py` (Default port 5000 in Docker).

---

## 5. Gemini API Integration Setup
To enable AI summarization in Production or Local Dev:
1. **API Key**: Obtain a key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. **Project Binding**: Ensure the key is bound to the target GCP project.
3. **Secret Manager**:
   ```hcl
   # terraform.tfvars
   gemini_api_key = "AIzaSy..."
   ```
4. **Validation**: Check for `gemini_enabled: true` in the `/health` endpoint.

---

## 5. Frontend & Tauri setup

### Environment Variables
- `NEXT_PUBLIC_API_URL`: Points to the Backend API (default `http://localhost:8000`).

### Node.js Configuration
- **Next.js**: 16.0.1 (App Router).
- **React**: 19.2.0.
- **Compatibility Fix**: Set `devIndicators: false` in `next.config.ts` for Next.js 16 build stability.

### Installation
1. `cd apps/tauri-client` (or `apps/frontend`)
2. `npm install`
3. `npm run dev` (Web) or `npm run tauri dev` (Desktop)

---

## 6. Configuration Checkpoints

1. **API Signature**: Ensure `api.generateSummary` matches the 5-parameter signature (`meetingId`, `template`, `context`, `length`, `style`).
2. **Client Components**: All pages using `useState` or `invoke` in `tauri-client` must have `"use client";` at the top.
3. **Build Context**: Use standard `.gcloudignore` to prevent uploading the entire monorepo during Cloud Run/Build deployments.
