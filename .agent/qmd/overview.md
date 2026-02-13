# MeetChi System Overview

## Purpose
MeetChi is a streaming audio intelligence platform designed for high-fidelity meeting transcription, specialized script alignment, and AI-driven intelligence (summaries, action items).

## Core Documentation Structure
The knowledge base is organized into the following specialized artifacts:

- **[System Architecture](./system_architecture.md)**: Details on VAD, ASR modes, WebSocket protocol, and the **Testing Strategy**.
- **[Deployment & Infra](./deployment_and_infra.md)**: Cloud Run GPU configuration (Singapore region), SQLAlchemy 2.0 integration, and Terraform IaC.
- **[Frontend Dashboard](./frontend_dashboard.md)**: React view states, **Build-Time Environment Configuration**, and Advanced audio features.
- **[Testing Strategy](./testing_strategy.md)**: E2E automation with Playwright, First Principles analysis, and MECE testing breakdown.
- **[Product Strategy](./product_strategy.md)**: Phased roadmap, cost analysis, and hardware evaluations.
- **[Troubleshooting](./troubleshooting.md)**: Integration testing results and common resolution patterns (e.g., Cloud Build permissions).
- **[Task Migration](./implementation/task_migration.md)**: Technical details on the Phase 5 Celery-to-Cloud-Tasks migration.
- **[Audio & ML Patterns](./implementation/audio_and_ml_patterns.md)**: High-fidelity ASR, Smith-Waterman alignment, and VAD orchestration.
- **[Gemini & Templates](./implementation/gemini_api_integration.md)**: Gemini 2.5 Flash Lite integration and BANT/STAR summary templates.
- **[Docker Optimization](./implementation/docker_optimization_patterns.md)**: Analysis of the 99% image reduction strategy for API-centric deployments.
- **[Tauri Client](./tauri_client.md)**: Maintenance documentation for the desktop overlay tool.

## Current Progress (Feb 2026)
### Phase 1: Core Enhancements (COMPLETED)
- **B1-Diarization**: 12-color harmonious palette with auto-assignment.
- **B2-Audio Player**: 0.5x-2x playback, sync-highlighting, and interactive seeking.
- **B3-Resilience**: Exponential backoff reconnection and 'reconnecting' status.
- **Settings**: Bulk JSON import/export for keyword corrections.

### Phase 2: Organization & Discovery (COMPLETED)
- **B5-Search**: Implemented PostgreSQL Full Text Search (FTS).
- **B7-Tagging**: Multi-level Folder UI and customizable tags.
- **Operations**: Implementation of Meeting Merge and Split functionality.

### Phase 3: Infrastructure (COMPLETED)
- **Deployment**: Standardized on Cloud Run L4 GPU in **asia-southeast1** (Singapore).
- **IaC**: Complete Terraform scripts for Cloud SQL, Cloud Tasks, GCS, and Secrets.

### Phase 4: Advanced ASR (COMPLETED)
- **Architecture**: Finalized Parallel Dual-ASR (Zh + Nan) + LLM Fusion strategy.
- **Implementation**: `DualASREngine` with time-based alignment and selection logic.

### Infrastructure Refinement (Feb 2026)
- **Build Lifecycle**: Optimized Cloud Build context for both **LLM** and **Backend** services using subdirectory-specific `.gcloudignore` and `.dockerignore`.
- **IAM Security**: Resolved critical permission mismatches between Cloud Build and Compute Engine default service accounts; granted `storage.objectAdmin` and `artifactregistry.writer` to the correct identities.
- **Dependency Management**: Standardized on stable version ranges for LLM requirements (numpy, networkx) to prevent build-time distribution errors.
- **✅ Build Success**: Finalized and validated **LLM** (`meetchi-llm-gpu`), **Backend** (`meetchi-backend`), and **Frontend** (`meetchi-frontend`) service images. Successfully pushed to Artifact Registry (`asia-southeast1`). 
- **🚀 Infrastructure Deployment**: Infrastructure is **LIVE** for all core services (Backend, LLM GPU, and Frontend).
- **Current Status**: The full stack is **Operational and Verified**. 
    - **Frontend**: `https://meetchi-frontend-705495828555.asia-southeast1.run.app` (v7)
    - **Backend**: `https://meetchi-backend-wfqjx2j42q-as.a.run.app`
    - **LLM GPU**: `https://meetchi-llm-gpu-705495828555.asia-southeast1.run.app` (Verified `device: cuda`)
- **Backend Resolution**: Successfully resolved Circular Imports (via `app/database.py`), Pydantic v2 compatibility (`regex` → `pattern`), Database Schema Mismatches (missing `folder_id` and `TSVector` columns), and **Orphaned Celery Imports**.
- **Completed and Verified**: Implemented native **Rust-side Auto-Reconnection** with session state persistence and multi-event signaling (`reconnecting`, `reconnected`).
- **Verified Frontend Integration**: Integrated connection status indicators and event listeners in the React overlay for a self-healing live recording experience.
- **Alignment Fix (Verified)**: Resolved duplicate script display in Alignment Mode using `HashSet` deduplication in the Rust engine.
- **GCP Deployment**: Backend Revision v7 successfully stabilized in **asia-southeast1**. Resolved 'API Shutdown' race conditions and orphaned Celery dependencies. Serverless orchestration via Cloud Tasks is fully operational.
- **✅ Phase 1 & 1.5 (COMPLETED)**: 
    - **Authentication**: Implemented NextAuth.js (Google OAuth) on the frontend and a JWT/ID-Token verification module (`auth.py`) on the backend. Completed the loop by capturing the ID token in `src/auth.ts` and injecting it into the API client via `Authorization: Bearer`.
    - **Recording UX**: Developed a `PreRecordingView` for microphone selection and real-time audio level testing.
    - **Sidebar Optimization**: Streamlined navigation order to prioritize "Start Recording".
    - **Security**: Updated `.gitignore` for Terraform and GCP credentials. Build verified on target routes with successful standalone output.
### Phase 5: Task Queue Modernization (COMPLETED Feb 2026)
- **Migration**: Replaced Celery + Redis with **Google Cloud Tasks**.
- **Optimization**: Realized ~$40/mo savings by decommissioning Cloud Memorystore.
- **Reliability**: Implemented concurrency control and automatic retries for Transcription/Summarization workflows.
- **IaC Update**: Resolved "Ralph Loop" dangling references in Terraform to ensure valid deployments.
- **Build Optimized**: Resolved **Build Context Bloat** (7.9 GiB) by transitioning to **subdirectory-targeted builds**. Reduced upload context to **2.2 MiB**, enabling near-instant iteration.
- **Resolution**: Removed **Orphaned Celery Imports** in `app/main.py`. Validated build and push of Backend Revision v7.
- **Verification**: Confirmed decommissioning of Redis/Celery. Infrastructure is now fully serverless for coordination.
- **LLM GPU Breakthrough**: Identified that `gcloud run deploy` (update) fails if quota is exactly 1 because Cloud Run requires a 3-unit reservation for the transaction to start. **Verified Workaround**: Deleting the existing service (`gcloud run services delete`) allows a fresh deployment to succeed with exactly 1 unit of quota. Recommended `cloudbuild-llm.yaml` strategy for Windows developers to handle custom Dockerfiles and machine scaling (E2_HIGHCPU_8).

### Phase 6: Frontend & Verification (COMPLETED Feb 2026)
- **Deployment**: Finalized frontend with Next.js standalone output (v7). Successfully deployed to Cloud Run.
- **Integration**: Baked `NEXT_PUBLIC_API_URL` into the build to ensure stable client-side connectivity.
- **Verification**: Verified E2E connectivity via `/api/health` and `/api/v1/meetings`. All services responding with 200 OK.
- **Resolution**: Identified `roles/logging.logWriter` IAM blocker for automated Cloud Build rollouts. Manual deployment used as fallback for Revision v7 success.

### Phase 7: ASR Alignment Optimization (COMPLETED Feb 2026)
- **Tuning**: Optimized `MIN_MATCH_SCORE` (6), `NORMAL_WINDOW_FORWARD` (600), and `MAX_CONSECUTIVE_FAILURES` (3) for responsive matching.
- **Robustness**: Implemented **Homophone Tolerance** in Smith-Waterman (75% score boost) to handle ASR phonetic confusion (e.g., 諸/祝, 的/得).
- **Policy**: Enabled **Hallucination Filter Bypass** and **Next-Zone Probing** (Solution C) in Alignment Mode to ensure seamless transitions by matching the start of the next speaker's script.
- **Verification**: Confirmed cursor advancement through 800+ character scripts. Resolved the **Speaker Zone Deadlock** by expanding the search window (Proactive Probing) into subsequent speaker zones. System now supports homophone-tolerant, low-threshold matching with natural multi-speaker handoffs.
- **Visuals**: Implemented specialized **Teleprompter Effects** (center-focus, active scaling, peripheral blurring) and **Glassmorphic Overlay** (edge fading, connection heartbeat) to enhance live readability.
- **Resize Handle**: Added custom resize handle to the Settings window and removed subtitle fade masks to improve legibility.

### Phase 8: Serverless Intelligence (COMPLETED Feb 2026)
- **Problem**: Identified "Processing Deadlock" where GPU-dependent models (Llama-Breeze) failed to load on CPU-only instances, causing summaries to stay in `PROCESSING`.
- **Solution**: Integrated **Gemini 2.5 Flash Lite** as the primary summarization engine.
- **Implementation**: Leveraged `google-genai` SDK with **Pydantic Structured Output** for 4 domain templates (General, Sales, HR, RD).
- **Resilience**: Implemented a hierarchical model fallback pattern: **Gemini API (Primary) → Local Breeze GPU (Secondary) → Mock Data (Testing)**.
- **Normalization**: Added output normalization logic to ensure template-specific AI responses remain compatible with the core Dashboard schema.
- **Status**: **✅ COMPLETED (Feb 2026)**. Gemini 2.5 Flash Lite is fully operational. Verified with health signatures (`gemini_enabled: true`) and successfully executed /summarize trials for Sales and R&D templates.

### Phase 9: Resource Rationalization (COMPLETED Feb 2026)
- **Rationalization**: Re-evaluated the "Fat Image" (15GB) requirement. Since Gemini API handles 100% of summarization, the local GPU dependencies were redundant for Cloud Run.
- **Optimization**: Transitioned to a **Tier 1 (Lean)** image using `python:3.11-slim`.
- **Impact**: Reduced image size from **15GB to ~150MB (99% reduction)**. 
- **Benefits**: Reduced build times from 15 minutes to 60 seconds. Improved cold starts and reduced storage costs on Artifact Registry.
- **Consolidation**: Merged all universal AI/ML deployment patterns from previous research into the MeetChi KB to establish a single source of truth for GCP serverless AI deployments.
