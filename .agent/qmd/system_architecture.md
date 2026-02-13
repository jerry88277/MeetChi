# MeetChi System Architecture & Transcription Pipeline

## 1. Overview
MeetChi is a streaming audio intelligence platform. It utilizes a **Dual-Frontend Architecture** consisting of a **Tauri Desktop Client** (for real-time recording and overlay) and a **Next.js Web Dashboard** (for meeting management and analytics). It orchestrates real-time Voice Activity Detection (VAD), Automatic Speech Recognition (ASR), and LLM-driven polishing to provide low-latency, high-fidelity meeting transcripts and summaries.

## 2. Audio Processing & VAD
- **Input Sampling**: Raw PCM 16-bit Mono @ 16,000Hz.
- **VAD (Voice Activity Detection)**:
    - Implementation: `VADAudioBuffer`.
    - Triggers: Silence threshold (0.3), minimum silence (0.6s), max segment duration (7.0s).
    - **Dual Mode Support**:
        - **Standard (GPU)**: Uses **Silero VAD** via PyTorch for high-precision speech detection.
        - **Lightweight (CPU/Backend)**: Implements an **Energy-based Fallback** (RMS thresholding) when `torch` is not present. This allows the Backend service to perform basic segment gating for the UI without requiring heavy ML libraries.
- **Filtering**:
    - **Hallucination Blacklist**: Uses `HALLUCINATIONS_EXACT` in `main.py` to filter exact matches of ASR noise (e.g., "喔", "點點點").
    - **Duration Gating**: Discards segments shorter than `min_speech_duration` (0.5s in `vad.py`) or failing an orchestration-level check (1.0s in `main.py`).
    - **RMS Gating**: Discards segments with `RMS < 0.0001` (effectively silent) during the VAD `flush()` phase.
    - **Noise Reduction**: Web version uses `rnnoise-wasm`.

## 3. Transcription & Alignment Strategy
The system supports two primary modes:
- **Transcription Mode**: Real-time ASR (WhisperX / Breeze-ASR-25) followed by async LLM polishing/translation.
    - **Multilingual Support**: Uses **Automatic Language Detection** (setting `language=None`) or multilingual initial prompts to support code-switching (e.g., Chinese-English mixed) in a single segment.
- **Alignment Mode (Smith-Waterman)**:
    - **Concept**: Matches ASR output against a pre-flattened script character stream.
    - **Algorithm**: Local alignment score (Match +3, Mismatch -1, Gap -2).
    - **Search Window**: `[cursor-20, cursor+600]`.
    - **Global Resync**: Reverts to full-script search after 3 consecutive failures.
    - **Low-Confidence Fallback**: Emits "Best Guess" segments tagged as `low_confidence: true` without advancing the cursor state to prevent drifting.

## 4. Parallel Multi-ASR & LLM Fusion (Phase 4)
The system implements a parallel inference pipeline for multilingual support:
- **Parallel Pass**: Audio segments are dispatched concurrently to `WhisperX (zh)` and `Whisper-Small-Taiwanese-ASR-v2` via `DualASREngine`.
- **Model Registry**: Centralized management of ASR (WhisperX, Whisper-Taiwanese) and LLM (Breeze-7B, Gemini Flash) models.
- **Fusion Logic**:
    1. **Time-based Alignment**: Aligns segments from both models using max overlap of start/end timestamps.
    2. **LLM Fusion**: Gemini 2.5 Flash Lite (or Breeze) evaluates the aligned transcripts. If they differ, the LLM selects the more accurate/fluent version based on context, preserving Taiwanese Hokkien when appropriate.

## 5. WebSocket Protocol
- **Endpoint**: `/ws/transcribe`.
- **Handshake**: Clients must send a `config` JSON as the first frame (meeting metadata, lang, mode, initial_prompt).
- **Streaming**:
    - Client sends binary PCM frames.
    - Server returns JSON frames with segment ID, content, translation, and status (`isPartial`, `isPolished`, `low_confidence`).
- **Resilience (Verified Feb 2026)**:
    - **Native Auto-Reconnection**: The Tauri client (`audio_processor.rs`) implements an asynchronous writer task with logic-preserving handshakes and session recovery.
    - **Frontend Synchronization**: React state management (`connectionStatus` and `isConnected` in Dashboard) provides visual status and handles state cleanup only after retries are exhausted.
- **REST Integration**: The Web Dashboard consumes the Backend API via a centralized **`ApiClient`** singleton (`src/lib/api.ts`). This client is extended with:
    - **Authentication Support**: Implements `setToken(idToken)` to inject a bearer token into the `Authorization` header of every request.
    - **Loop Closure**: A `useEffect` hook in the `DashboardPage` monitors the NextAuth session; upon login, the `idToken` from Google OAuth is automatically passed to the `ApiClient`.
    - **Health Monitoring**: Periodically checking `/health` to update UI connectivity status (`isConnected`).
    - **Data Transformation**: A dedicated `transformMeeting` layer in the UI ensures backend Pydantic models (JSON) are mapped correctly to frontend state.

## 6. Organization & Discovery (Phase 2 & 5)
- **Full Text Search (FTS)**:
    - **Implementation**: PostgreSQL `TSVECTOR` columns with GIN indexes (`idx_meeting_search_vector`, `idx_segment_search_vector`).
    - **Auto-Update**: Trigger functions (`meetings_search_vector_trigger`) automatically update vectors from title, transcript, and summary on every INSERT/UPDATE.
    - **Ranking**: Uses `ts_rank_cd` for relevance sorting and `ts_headline` for hit highlighting in search results.
- **Hierarchical Folders**: Supports nested folder structures with path-based selection (e.g., `/Sales/2024/Q1`).
- **Tagging**: Flexible labeling with customizable colors and system-predefined categories (e.g., "Important", "To-Follow").

## 7. Advanced Meeting Operations (Phase 6)
- **Meeting Merge**: Combines multiple meetings into one. Concatenates audio via FFmpeg (`concat`) and merges transcripts with adjusted global timestamps.
- **Meeting Split**: Splits a meeting at a specific time-point. Generates two new meetings with sliced audio and re-ordered transcript segments.
## 8. Externalized Model Management (LLM Service)
To optimize container image size and improve startup performance for the **LLM GPU Service**, MeetChi uses an externalized model management strategy:
- **Registry**: Google Cloud Storage (GCS) acts as the centralized repository for LLM and ASR models.
- **Workflow**: 
    1. Models are downloaded from HuggingFace to a local/Cloud Build workspace.
    2. Models are uploaded to `gs://${PROJECT_ID}-meetchi-audio/models/`.
    3. The **LLM Service** pulls these models from GCS at runtime to avoid bloated images.
- **Supported Models**: 
    - `whisper-large-v3` (Faster-Whisper), `taiwanese-asr` (Whisper-Small), `breeze-7b`, and `pyannote-diarization`.
- **Runtime Loading (startup.sh)**:
    - The `meetchi-llm-gpu` container uses a `startup.sh` entrypoint.
    - **Logic**: Uses `gsutil -m cp -r` to sync models from GCS to local `/app/models`.
    - **Optimization**: This keeps the image under 2GB (Ubuntu + PyTorch + CUDA) while granting access to 50GB+ of potential model artifacts.
    - **Cold Start Handling**: `startup_probe` in Cloud Run handles the initial multi-gigabyte download time.
- **Dual-Capability Backend**: 
    - **Standard (CPU)**: A lightweight coordination service without heavy ML dependencies.
    - **GPU-Enabled (Dockerfile.gpu)**: In production environments, the Backend can be promoted to a GPU-accelerated service to handle real-time ASR using `faster-whisper`.
    - **Optimization**: Uses lazy-loading of ML modules to ensure a single codebase can run in both CPU (FastAPI only) and GPU (ASR + FastAPI) environments without startup crashes.
- **LLM Service Priority**: While the Backend can handle ASR, the dedicated **LLM Service** remains the primary host for heavy batch inference, diarization, and LLM-driven polishing, maintaining isolation between real-time streaming and high-latency batch tasks.

## 9. Quality Assurance & Testing
The system employs a multi-tiered verification strategy and automated E2E testing framework:
- **Testing Pyramid**: Standard structure following Unit (Vitest/Jest) → Integration (API mocking) → E2E (Playwright) layers.
- **Automated E2E Framework**: Built on **Playwright**, covering critical paths:
    - **Dashboard Navigation**: Verifying list rendering, search, and detail views.
    - **Recording Workflow**: Validating real-time UI state changes, timers, and stop/cancel logic.
    - **Settings & Integration**: Confirming frontend-backend connectivity and environment configuration.
- **Verification Strategy**: Uses First Principles and MECE analysis to categorize and prioritize critical user journeys.
- **Resilience Testing**: Simulates backend outages to verify client-side auto-reconnection and UI state preservation.
## 10. Security & Authentication Layer
MeetChi implements a cryptographically verifiable authentication loop using **Google OAuth 2.0 (OIDC)**.

### 10.1 Multi-Layer Architecture
| Layer | Technology | Status |
|-------|------------|--------|
| **Frontend** | NextAuth.js (v5) + Google OAuth | ✅ Implemented |
| **Backend API** | FastAPI + `google-auth` (ID Token Verification) | ✅ Implemented |

### 10.2 Frontend Implementation (NextAuth.js v5)
- **Configuration (`src/auth.ts`)**: uses `prompt: "consent"` and `access_type: "offline"` to ensure consistent ID token delivery.
- **Capture & Propagation**:
    - **JWT Callback**: Captures `account.id_token` and persists it as `token.idToken`.
    - **Session Callback**: Maps `token.idToken` to `session.idToken`, making it available to client-side components.
- **API Client Integration**: The `setToken` method in `ApiClient` injects the bearer token into the `Authorization` header. A `useEffect` in the `DashboardPage` monitors the session and passes the token to the client.

### 10.3 Backend API Implementation (`auth.py`)
- **Token Verification**: Uses `google.oauth2.id_token.verify_oauth2_token` to validate signatures, issuers, and client IDs against Google's public keys.
- **Dependency Injection**: `get_current_user` dependency protects sensitive routes (Meetings, Summaries).
- **Development Mode**: Controlled by `AUTH_REQUIRED` toggle (default: `false`). If disabled, returns a virtual "Development User".

### 10.4 Administrative Scope & Role Management
- **Verification**: Email whitelist via `ADMIN_EMAILS`.
- **Admin Views**: Components like `AdminView` (system stats) and `TemplatesView` are gated by the `get_admin_user` dependency.

### 10.5 OAuth Safety Mechanics
- **Client ID vs. User Tokens**: Client ID identifies the application; User Token (idToken) identifies the specific verifiable session.
- **Redirect URI Security**: The primary defense against phishing. Google blocks redirections to any URI not explicitly whitelisted (e.g., `http://localhost:3000/api/auth/callback/google`).
- **Production Deployment**: Cloud Run requires `AUTH_SECRET`, `AUTH_URL`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET` environment variables.
## 11. Background Task Processing (Serverless Cloud Tasks)
To prevent blocking the main API thread during high-latency AI operations (Summarization, Post-Process ASR), MeetChi utilizes an asynchronous serverless task queue.
- **Architecture (Google Cloud Tasks)**: **✅ COMPLETED (Feb 2026)**. Fully migrated from Celery/Redis to a serverless HTTP-triggered pattern.
    - **Trigger**: The API pushes a JSON payload to a Cloud Task queue.
    - **Pattern: Core-Wrapper Separation**: Decouples business logic from task transport.
        - **Core Logic (`_core`)**: Pure Python function (e.g., `generate_summary_core`) that handles work in isolation.
        - **Logic Wrapper**: Maintains original signatures for internal calls to prevent "Cascade Refactoring".
        - **HTTP Adapter**: FastAPI endpoint that validates `X-CloudTasks-QueueName` headers to ensure security.
    - **Execution**: Cloud Tasks sends an HTTP POST to a `/tasks/...` endpoint (`app/routes/cloud_tasks.py`).
    - **LLM Integration**: The summarization task defaults to **Gemini 2.5 Flash Lite** (via serverless API) to avoid GPU resource deadlocks in Cloud Run.
    - **Resilience & Retries**:
        - **Idempotency**: Handlers check a `status` field in the DB before start. If `processing` or `completed`, the task returns success immediately to avoid redundant API costs.
        - **Concurrency Control**: Queue limits (e.g., `max_dispatches=5`) prevent LLM quota exhaustion.
        - **Dead Letter Queues (DLQ)**: Failed generations are moved to a secondary queue for audit after 5 retries.
    - **Cost Efficiency**: Realized ~$40/mo savings by decommissioning Cloud Memorystore Redis. Achieved **90% cost reduction** compared to persistent Cerely workers.
- **Workflows**:
    - **Summarization**: Triggered after meeting completion. Uses Pydantic for high-fidelity JSON mapping.
    - **ASR Post-Processing**: Handles high-fidelity re-transcription of 1-hour meetings in the background via the LLM Service callback.
- **Reliability Framework (MECE)**:
    - **Capture**: Mic disconnection handled via browser event listeners + UI alerts.
    - **Buffering**: Browser/Tab crash mitigated via **IndexedDB Local Persistence** (segments written every 10-30 seconds).
    - **Transport**: Network outage addressed via **Chunked Resumable Uploads** (5-minute chunks with integrity verification).
    - **Logic**: API Key/LLM Timeout handled by **Cloud Tasks / Queue Retries**.
    - **Resources**: GPU VRAM Exhaustion bypassed via **API Offloading (Gemini 2.5 Flash Lite)**.
- **Legacy Note**: The `celery_app.py` and Redis broker dependencies have been decommissioned and removed from the codebase to ensure a thin, non-crashing Cloud Run CPU environment.

## 12. Regenerate Summary Flow
For cases where summarization fails or users want to use a different template/context, MeetChi provides a manual regeneration trigger.
- **Trigger**: `POST /api/v1/meetings/{meeting_id}/regenerate-summary`.
- **Logic**:
    1. **State Reset**: Clears `summary_json` and resets `status` to `processing` in the database.
    2. **Background Task**: Invokes `generate_summary_core` via FastAPI `BackgroundTasks`.
    3. **UI Sync**: The frontend `DashboardPage` receives a `200 OK` and immediately refreshes the meeting list/detail view to reflect the `processing` state and show a spinner.
- **Guardrails**: The endpoint verifies that the meeting contains valid transcript data (raw or polished) before starting the task.

## 13. Recording Persistence & Metadata Flow
Details the transition from ephemeral recording state to a persisted meeting record.

### 13.1 Flow Overview
1. **Trigger**: User clicks "Start Recording"; sidebar state switches to active.
2. **Metadata Generation**: System generates default title (`會議記錄 - YYYY/MM/DD HH:MM`) for context.
3. **Capture**: Audio chunks are buffered and sent via WebSocket.
4. **Shutdown**: User clicks "Stop"; final duration is collected.
5. **Persistence**: Frontend calls `api.createMeeting`. The `isSaving` state manages the UI lifecycle (disabling buttons, showing persistence animations).
6. **UI Synchronization**: After successful creation, `fetchMeetings()` refreshes the list, and `transformMeeting()` maps the response to the `selectedMeeting` state for the Detail View.

### 13.2 Component Contract (`RecordingView`)
The `RecordingView` accepts an `onStop` callback:
```typescript
interface RecordingViewProps {
    onStop: (durationSeconds: number) => void;
    onCancel: () => void;
    isSaving?: boolean;
}
```

## 14. Multi-Speaker Sequential Alignment
To support scenarios where multiple speakers deliver speeches in a pre-defined order, MeetChi implements a **Zone-Restricted Alignment** strategy.
- **`MultiSpeakerScriptAligner`**: A specialized engine that parses a script containing speaker markers (e.g., `===SPEAKER:講者A===`).
- **Zone Parsing**: The script is divided into `zones`. Each zone corresponds to a single speaker's segment of the text.
- **Alignment Lock**:
    - **Logic**: Search is strictly restricted to the **Current Zone**. The Smith-Waterman algorithm will not match ASR hypothesis against text in previous or future zones.
    - **Stability**: This prevents "Matching Jump Errors" where ASR noise from Speaker A might accidentally match a similar phrase in Speaker B's script.
- **Auto-Advance (Threshold Trigger)**:
    - **Threshold**: **90% Completion**.
    - **Mechanism**: When the aligner identifies that 90% of the characters in the current zone have been matched/emitted, it automatically shifts the search window to the beginning of the **Next Zone**.
    - **Transition**: This ensures a smooth handoff between speakers without manual intervention.
- **Manual Intervention**: The API support `advance_speaker()` and `previous_speaker()` commands via WebSocket to allow users to force a zone change if the automatic threshold is not met.
