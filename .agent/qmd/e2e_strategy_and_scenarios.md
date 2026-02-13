# E2E Testing Strategy & User Scenarios

This document consolidates MeetChi's end-to-end (E2E) testing strategy, Playwright implementation details, and user-centric verification scenarios.

---

## 1. Testing Philosophy (First Principles)

E2E testing is the verification of complete business processes from the user's perspective.
```
E2E Test = User Action → System Response → Expected Outcome
```

### 1.1 Tool Selection: Why Playwright?
Playwright was selected for MeetChi because:
- **Next.js 16 Support**: Native compatibility with modern React patterns.
- **Cross-Browser Capability**: Parallel execution across Chromium, Firefox, and WebKit.
- **Resilience**: Built-in auto-wait mechanism significantly reduces "flaky" tests.
- **Network Interception**: Powerful API for mocking and verifying backend communication.

### 1.2 The Testing Pyramid (MECE)
MeetChi's quality assurance is structured into three distinct layers:
1.  **L1: Unit Tests (Vitest/Jest)**: Focuses on pure functions, React hooks, and individual components. Low cost, high speed.
2.  **L2: Integration Tests (Playwright + MSW)**: Verifies state management and API interactions by mocking the backend. Medium cost.
3.  **L3: E2E Tests (Playwright)**: Validates the full user journey with a live backend and database. High confidence.

---

## 2. User Scenarios

### Scenario 1: Real-time Recording & Transcription
**Goal**: User records a meeting via the Tauri client and sees real-time transcription.
- **Trigger**: Click "Start Recording".
- **Logic**: ASR service provides 16kHz PCM stream to WhisperX.
- **Acceptance Criteria**: 
    - First word appears within 2 seconds.
    - Transcript updates with < 500ms latency.
    - Meeting appears in Dashboard immediately after stopping.

### Scenario 2: Structured Meeting Summarization (Gemini API)
**Goal**: Generate a structured summary for a completed meeting using specialized templates.
- **Trigger**: Select Meeting → Click "Generate Summary".
- **Logic**: Backend offloads to LLM Service (Gemini 2.5 Flash Lite) with Pydantic JSON schemas.
- **Acceptance Criteria**:
    - Summary generation completes within 30 seconds.
    - Output includes mandatory fields: `summary`, `action_items`, `decisions`.
    - Status transitions: `PENDING` -> `PROCESSING` -> `COMPLETED`.

### Scenario 3: History Search & Retrieval
**Goal**: Search and review historical meetings with semantic context.
- **Logic**: Backend uses PostgreSQL Full-Text Search (FTS) with `tsvector` columns.
- **Acceptance Criteria**:
    - Search returns relevant results for partial keywords.
    - UI supports audio playback synchronization with transcript highlights.

---

## 3. Playwright Implementation Details

### 3.1 Functional Decomposition
| Module | Features | Priority | Complexity |
| :--- | :--- | :--- | :--- |
| **Landing Page** | First-visit experience, navigation. | P2 | Low |
| **Meeting List** | Dashboard view, search, filtering. | P0 | Low |
| **Meeting Detail** | Summary rendering, transcript display. | P0 | Medium |
| **Recording Flow** | Real-time UI, timer, stop/save logic. | P1 | High |
| **System Settings** | Backend URL config, status monitoring. | P2 | Low |

### 3.2 Configuration Highlights
- **Parallelism**: `fullyParallel: true` enabled.
- **Auto-Wait**: Uses `waitForLoadState('networkidle')`.
- **Latency Handling**: Extended `timeout` to 10s for Recording Flow assertions to account for API persistence.

### 3.3 Execution Commands
```bash
# Install dependencies
npx playwright install chromium

# Run tests
npm run test:e2e          # All tests (headless)
npm run test:e2e:ui       # Interactive UI mode
```

---

## 4. Manual Verification & Health Checks

### 4.1 Hybrid Mode Health Check
Verify the service is running in **Hybrid Mode** (GPU + Gemini API):
```bash
curl https://[LLM_SERVICE_URL]/health
```
**Expected Response**:
```json
{
    "status": "ready",
    "gemini_enabled": true,
    "gemini_model": "gemini-2.5-flash-lite-preview-06-17",
    "local_model_loaded": false
}
```

### 4.2 Manual Summary Triggering
```bash
curl -X POST "[BACKEND_URL]/api/v1/meetings/[ID]/generate-summary" \
  -H "Content-Type: application/json" \
  -d '{"template_name": "general"}'
```

### 4.3 Template Verification Matrix
| Template | Unique Field to Verify |
|----------|----------------------|
| **Sales BANT** | `BANT.budget` (Nested object) |
| **HR STAR** | `STAR_stories` (Array of objects) |
| **R&D** | `technical_decisions` |

---

## 5. Maintenance & Lessons Learned
- **Terminology Drift**: Localization-heavy UIs (Chinese/English) require regex selectors (e.g., `/智慧|智能/`) to prevent failures when terminology fluctuates.
- **Build-Time Env Vars**: `NEXT_PUBLIC_*` variables must be injected during the Docker build stage, not just at runtime.
- **Artifact Retention**: Capture traces/video on failure ONLY to minimize CI storage bloat.
