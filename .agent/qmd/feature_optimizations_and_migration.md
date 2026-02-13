# MeetChi Implementation & Optimization History

## 1. Infrastructure Migration: Serverless Cloud Tasks

### 1.1 Rationale
To reduce operational costs (~$40/month) and improve scalability, MeetChi migrated from a **Celery + Redis** model to **Google Cloud Tasks**.

### 1.2 Core-Wrapper Separation Pattern
To maintain backward compatibility and facilitate testing:
- **Core Logic**: Extracted into `generate_summary_core` in `app/tasks.py`.
- **HTTP Wrapper**: Implemented in `app/routes/cloud_tasks.py` to handle GCP-triggered POST requests with header validation.
- **Legacy Wrappers**: Original function names (`generate_meeting_minutes`) retained as simple wrappers calling the Core logic.

### 1.3 Lazy ML Dependency Loading
To prevent the API coordination layer (CPU) from crashing due to `torch` or `ctranslate2` missing CUDA libraries:
- Implemented `_ensure_gpu_deps()` to perform conditional imports.
- Standardized non-ML coordination in the primary `main.py`.

---

## 2. Phase 5: User-Centric Optimizations

### 2.1 Stability Fixes (Summary Pipeline)
- **Problem**: Users faced infinite spinners (stuck in `PROCESSING`).
- **Fixes**:
  - Implemented `POST /meetings/{id}/regenerate-summary` for manual recovery.
  - Updated Frontend `MeetingCard` and `DetailView` to handle error states and showing progress.
  - Identified `transformers` version mismatch as a root cause for model loading failures.

### 2.2 UI/UX Enhancements
- **Iconography**: Removed confusing hardcoded mock avatars; replaced with status icons and duration tags.
- **Terminology Dictionary**: Introduced a keyword replacement engine injected into the LLM system prompt for domain-specific transcript correction.
- **Time Estimation**: Implemented $T = \text{audio\_length} \times 0.4$ as a rule of thumb for pending task duration.

---

## 3. Stabilization Logs (Feb 2026)
- **ASR Pipeline**: Resolved `HealthCheckContainerError` by removing orphaned Celery imports.
- **Build Cycle**: Optimized context size from **7.9 GiB** to **2.2 MiB** by building from subdirectories.
- **Auth**: Stabilized Google OAuth 2.0 (OIDC) flow in production Cloud Run environments.
