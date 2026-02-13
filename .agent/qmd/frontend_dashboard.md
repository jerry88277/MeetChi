# Web Dashboard & UI Features

## 1. Frontend Architecture (Redesign 2026-02-03)
The MeetChi Web Dashboard was redesigned for a modern, professional aesthetic using Next.js 15+ and React 19. It uses a component-based state management system for switching between views.

### View States
- **`landing`**: A modern introduction page with feature highlights and entry CTA.
- **`dashboard`**: The primary hub for meeting management and discovery.
- **`pre-record`**: (New) Pre-recording page for microphone selection and audio level testing.
- **`record`**: A focused recording interface with live wave visualization.
- **`detail`**: An in-depth view of a single meeting, featuring AI horizontal summaries and action items.
- **`settings`**: System and API configuration.
- **`templates`**: (New) Meeting template showcase.
- **`admin`**: (New) System administration and statistics.

### Component Architecture
- **`Sidebar`**: A dark, persistent navigation component. Optimized in Phase 1.5 to prioritize the **"Start Recording"** (Mic) button at the top of the menu, followed by **"All Meetings"** (FileText).
    - **Device Labeling Pattern**: To ensure human-readable mic names are visible, the view implements a **"Permission-First" enumeration**: it calls `getUserMedia({ audio: true })` and immediately stops it, which triggers the browser permission prompt. Once granted, subsequent calls to `enumerateDevices` return actual device names instead of empty labels.
    - **State Transition**: Halts all media tracks before transitioning to the recording state to ensure device release and prevent "Device in Use" errors during state handover.
- **`RecordingView`**: High-focus recording mode with a real-time JS wave visualizer and duration timer.
- **`MeetingCard`**: Glassmorphic-inspired cards with hover states, status badges (completed/processing/failed), and metadata (date/duration).
- **`DashboardView`**: Grid-based layout for meeting cards with integrated search and action buttons.
- **`DetailView`**: Split-panel design for intelligence (Summaries/Actions) and evidence (Transcript).
- **`SettingsView`**: Configuration for Backend URLs and ASR/Diarization logic.
- **`TemplatesView`**: Showcase of predefined templates (General, Standup, 1:1, Interview).
- **`AdminView`**: Comprehensive administrative dashboard for user and system monitoring.

## 2. Intelligence & Player Features
- **Split-Panel Design**: Left panel for AI intelligence (Summaries, Actions); Right panel for transcript evidence.
- **AI Blocks**: Dynamic rendering of Action Items with assignment badges and due dates.
- **Interactive Transcript**: Grouped by speaker with monospace timestamps.
- **Visual Feedback**: Pulse indicators for active recording and rotate-spin loaders for status transitions.

## 3. Design Principles (Web Frontend Development Skill)
- **Typography**: Standardized on **Inter** (via Google Fonts) and **Space Grotesk** for headings to ensure a precise, technical feel.
- **Color Palette**: Uses a deep **Indigo** (`#6366f1`) and **Slate** (Slate-50 to Slate-900) palette with specific attention to contrast and accessibility.
- **Motion & Effects**: 
    - Smooth CSS animations for view transitions (`fade-in`, `slide-in-from-bottom`, `slide-in-from-right`).
    - Hand-coded visualizer using `requestAnimationFrame` and random wave generation for the recording state.
    - Glassmorphism: Semi-transparent white backgrounds (`bg-white/5` or `bg-white/10`) with subtle backdrop blurs, borders, and shadows.
- **Status indicators**: Standardized colors (Emerald-completed, Amber-processing, Red-failed) with pulse and rotate-spin animations.


## 4. Backend Integration & Data Flow
The dashboard is fully integrated with the MeetChi Backend Service via a centralized REST API client.

### API Client (`src/lib/api.ts`)
- **Singleton Architecture**: Exports a shared `api` instance configured via `NEXT_PUBLIC_API_URL`.
- **Core Features**:
    - **Health Monitoring**: `checkHealth()` identifies backend availability.
    - **Meeting Management**: `listMeetings()`, `getMeeting(id)`, `createMeeting(data)`.
    - **Intelligence Triggering**: `generateSummary(id)` launches async background tasks on the server.
- **Resilient Fetching**: Implements a generic fetch wrapper with standardized error parsing and "Connection Failed" user messaging.

### Data Transformation & State
To decouple the UI from backend database schemas, the frontend implements a transformation layer within the Dashboard component.
- **`transformMeeting`**: Maps the backend `MeetingRead` Pydantic model to the UI-friendly `Meeting` interface.
    - **Summary Parsing**: Attempts to parse `summary_json` if present; falls back to raw text.
    - **Time Formatting**: Converts raw seconds to `MM:SS` format.
    - **Transcript Mapping**: Flattens `TranscriptSegment` objects into simple `TranscriptLine` items for the detail view.
- **Global State**:
    - **`isConnected`**: Visual indicator in the sidebar based on periodic or trigger-based health checks.
    - **`isLoading` / `error`**: Reactive states for smooth loader transitions and error banners in the Dashboard grid.


## 5. Deployment & Optimization
The web frontend is optimized for low-latency delivery and minimal container footprint on Cloud Run.

### Standalone Output
- **Configuration**: `next.config.ts` includes `output: 'standalone'`.
- **Purpose**: Next.js automatically bundles only the files necessary for production, excluding the massive `node_modules` from the final container.

### Production Dockerization
- **Multi-Stage Build**:
    - **Builder**: Uses `npm ci` and `npm run build`. Passes `ARG NEXT_PUBLIC_API_URL` to bake the backend URL into the client bundle.
    - **Runner**: Uses `node:20-alpine`, copying only the `.next/standalone`, `.next/static`, and `public` folders.
- **Port Binding**: Explicitly sets `ENV PORT=3000` and `EXPOSE 3000`.
- **Health Check**: Implemented via a dedicated API route (`/api/health`) to return JSON status for Cloud Run probes.

#### Health API Implementation (`src/app/api/health/route.ts`)
```typescript
import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    status: 'healthy',
    service: 'meetchi-frontend',
    timestamp: new Date().toISOString()
  });
}
```

## 6. Build Optimization & Context Management
To ensure fast deployments on Cloud Build, the frontend uses a strict context management strategy.

### .dockerignore (Critical)
Without a `.dockerignore`, Cloud Build may attempt to upload gigabytes of `node_modules` and `.next` build artifacts. 
- **Current Strategy**: Exclude `node_modules`, `.next`, `out`, and `.env*.local`.
- **Result**: Reduced upload context from several GBs to ~600KB, significantly decreasing the "Creating temporary archive" phase of `gcloud builds submit`.


## 7. Build-Time Environment Configuration (`cloudbuild.yaml`)
Since `NEXT_PUBLIC_*` variables are inlined at build time, the frontend uses a dedicated `cloudbuild.yaml` to manage environment-specific builds.

### Build Step Detail
```yaml
steps:
  # Build Docker image with build-arg
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '--build-arg'
      - 'NEXT_PUBLIC_API_URL=https://meetchi-backend-705495828555.asia-southeast1.run.app'
      - '-t'
      - 'asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-frontend:v6'
      - '.'
```

> **Note**: Avoid using variables like `$SHORT_SHA` in manual `gcloud builds submit` commands unless they are explicitly defined via `--substitutions`. For production-ready consistency, use explicit version tags (e.g., `:v6`).

> **Permission Warning**: Running `gcloud run deploy` as a step within Cloud Build requires the build's service account to have `Cloud Run Admin` and `Service Account User` roles. If these are missing, the step will fail with "status 1". In such cases, the image will still be successfully pushed, and you can deploy it manually.


### Advantages
- **Single Source of Truth**: The `cloudbuild.yaml` explicitly defines which backend the frontend bundle will communicate with.
- **Security**: Inlines the URL during build, reducing the risk of runtime environment manipulation.
- **CI/CD Friendly**: Easily integrates with Cloud Build triggers to switch backend URLs between staging and production environments by passing different tags or using different config files.


## 8. Post-Verification Identified Gaps (2026-02-03)
Following successful E2E test implementation (13/13 passing), a deep code analysis of `src/app/dashboard/page.tsx` was performed to identify functional and architectural debt.

### 8.1 Functional & Logic Gaps (Root Cause Analysis)
- **Duplicate Recording Entry Points**:
    - **Logic**: Two separate "Start Recording" buttons exist.
    - **Sidebar** (Line 117): `{ id: 'record', icon: Mic, label: '開始錄音', primary: true }`
    - **DashboardView Header** (Line 342-348): Standard button within the main grid view.
    - **Impact**: Inconsistent UI entry points; Sidebar uses a "primary" highlight style while the DashboardView remains the primary hub.

- **Recording Integrity & API Sync**:
    - **Issue**: The `handleStopRecord` function (Lines 641-645) only calls `fetchMeetings()` and switches the view back to `dashboard`.
    - **Root Cause**: It lacks a call to `api.createMeeting()`. Consequently, recording sessions are not persisted to the backend database.
    - **Validation**: Current recording logic exists only in the volatile local state.

- **Mocked Recording UI**:
    - **Analysis**: The `RecordingView` component (Lines 192-246) is currently a UI mock.
    - **Dummy Logic**: Uses `setInterval` to increment a local `duration` state and generate random `waves` heights for visual feedback.
    - **Missing Components**: Lacks `MediaRecorder` API integration, Browser audio permissions handling, and WebSocket streaming to the MeetChi Backend.

### 8.2 Architectural & Design Debts
- **Sidebar & Mobile Navigation**:
    - **Analysis**: Desktop uses a persistent `Sidebar` (Line 670), while mobile renders a top header bar with a hamburger menu (Lines 680-691).
    - **Issue**: The transition between mobile and desktop states creates a "double layer" feel where the mobile menu overlays a dashboard that already contains a mobile header. Consolidation into a single responsive navigation hierarchy is required.

- **Missing Strategic Views**:
    - **Template Management**: No route or component exists for managing AI meeting summary templates, which is a core value proposition of the platform.
    - **System Administration**: Laps an admin interface for cross-meeting analytics or user level settings.

## 9. Next Steps: Deep Research with NotebookLM
To address these architectural and functional challenges, the project will leverage **NotebookLM via MCP** for "Deep Research." 

### Research Objectives:
1. **Meeting Intelligence Workflow**: Industry-standard patterns for "Record -> Process -> Review" flows to fix the missing persistence step.
2. **Audio Streaming Patterns**: Best practices for low-latency browser-to-server audio streaming (WebSocket vs WebRTC) for `RecordingView` implementation.
3. **Consolidated Sidebar Navigation**: UX patterns for complex dashboards with multiple management layers (Meetings, Templates, Admin).

> **Current Status**: **NotebookLM MCP is configured and authenticated** (`authenticated=true`). The agent will perform Deep Research via the Gemini Interactions API once sources are selected or a notebook URL is provided.

## 10. Refinement Implementation (2026-02-03)
Following the identification of gaps in Section 8, the following refinements were implemented:

### 10.1 Interaction Consolidation
- **Duplicate Recording Button**: Removed secondary "Start Recording" button from `DashboardView` header.
- **Unified Entry Point**: Sidebar's primary recording button is now the single source for starting sessions.

### 10.2 Recording Persistence & API Integration
Implemented a functional persistence layer in `handleStopRecord`.
- **Metadata Generation**: Uses `toLocaleDateString` and `toLocaleTimeString` with `zh-TW` locale to generate human-readable titles like `會議記錄 - 2026/02/03 14:30`.
- **API Integration**: Calls `api.createMeeting()` with the generated title and default template.
- **Navigation**: Automatically transitions to `detail` view after successful creation.

### 10.3 RecordingView UI Enhancements
Transformed `RecordingView` from a pure visual mockup to a state-aware component.
- **`isSaving` State**: 
    - Buttons (Stop, Cancel) are disabled during persistence.
    - Text changes from "正在錄音" to "儲存中...".
    - Description updates to "正在儲存會議記錄...".
    - Visualization color shifts from Indigo to Amber.
- **Duration Callback**: Updated `onStop` to pass the final `duration` back to the parent `DashboardPage`.

```typescript
// Child: RecordingView implementation snippet
const RecordingView = ({ onStop, onCancel, isSaving = false }: RecordingViewProps) => {
    const [duration, setDuration] = useState(0);
    // ... timer & waves effect ...

    const handleStop = () => {
        onStop(duration); // Pass duration to parent
    };

    return (
        // UI renders with isSaving state (disabled buttons, loader, amber bars)
        <button onClick={handleStop} disabled={isSaving}>
            {isSaving ? <Loader2 className="animate-spin" /> : <Square />}
        </button>
    );
}

// Parent: DashboardPage calling point
{currentView === 'record' && (
    <RecordingView
        onStop={handleStopRecord}
        onCancel={handleBackToDashboard}
        isSaving={isSaving}
    />
)}
```

### 10.4 Persistence Logic
Implemented a functional persistence layer in `handleStopRecord`.

```typescript
// Final handleStopRecord Implementation
const handleStopRecord = async (durationSeconds: number) => {
    setIsSaving(true);
    try {
        const now = new Date();
        const dateStr = now.toLocaleDateString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit' });
        const timeStr = now.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
        const title = `會議記錄 - ${dateStr} ${timeStr}`;

        const newMeeting = await api.createMeeting({
            title,
            language: 'zh-TW',
            template_name: 'general'
        });

        await fetchMeetings();
        const transformedMeeting = transformMeeting(newMeeting);
        setSelectedMeeting(transformedMeeting);
        setCurrentView('detail');
    } catch (err) {
        setError(err instanceof Error ? err.message : '儲存會議失敗');
        // Fallback to dashboard on error
        setCurrentView('dashboard');
    } finally {
        setIsSaving(false);
    }
};
```

## 11. Web Media Implementation Patterns

### 11.1 The "Permission-First" Enumeration
A common pitfall in web media apps is that `navigator.mediaDevices.enumerateDevices()` returns empty labels for microphone names if audio permission hasn't been granted.
- **Implementation**:
    ```typescript
    // Request permission first to get labels
    const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    tempStream.getTracks().forEach(track => track.stop()); // Immediately release
    
    // Now call enumerateDevices; labels will be populated
    const devices = await navigator.mediaDevices.enumerateDevices();
    const mics = devices.filter(d => d.kind === 'audioinput');
    ```
- **Benefit**: Provides a better UX by showing "MacBook Pro Mic" instead of "Microphone 1".

### 11.2 Real-time Audio Level Visualization
Uses the Web Audio API to provide non-blocking visual feedback during the preparation phase.
- **Node Chain**: `MediaStreamSource` -> `AnalyserNode`.
- **Calculation**: Calculates average frequency data (`getByteFrequencyData`) to drive a reactive volume bar.
- **Optimization**: Uses `requestAnimationFrame` for smooth 60fps updates, ensuring the UI remains responsive.
## 12. User-Centric Optimization UI Enhancements (Phase 5, 2026-02-05)

Following initial user testing, the dashboard was optimized to improve clarity and handle "stuck" AI processes.

### 12.1 Improved MeetingCard & Dashboard Clarity
- **Avatar Removal**: Removed hard-coded "P" and "J" circles from the card footer to eliminate user confusion regarding "participants" which were not yet implemented.
- **Enhanced Status Labels**:
    - **`processing`**: Displays as **"AI 處理中"** with an animated spinner and a sub-caption "正在轉錄音檔並生成摘要".
    - **`failed`**: Displays as **"處理失敗"** in red with a sub-caption "點擊重試".
- **Dynamic Content Placeholders**: When in the processing state, the card summary displays "⏳ AI 正在分析會議內容，請稍候..." instead of a generic "Waiting for AI..." message.

### 12.2 Intelligent DetailView & Regeneration
- **Status-Aware Summary View**: 
    - If `status === 'processing'`, a dedicated loader box shows "通常需要 1-3 分鐘".
    - If `status === 'failed'`, an alert icon prompts the user to "重新生成".
- **Regenerate Summary Feature**:
    - Introduced a **"RefreshCw" (Regenerate)** button in the Summary section header.
    - **Contextual Action**: Label changes dynamically between "生成摘要" (if missing) and "重新生成" (if existing).
    - **State Management**: Button is disabled during active generation to prevent overlapping task triggers.

### 12.3 API Integration for Regeneration
- **Backend Trigger**: Invokes the `POST /api/v1/meetings/{id}/regenerate-summary` endpoint.
- **State Management**:
    - Uses `isRegenerating` boolean state to track the active API call.
    - Disables the regeneration button and shows a loading spinner during the process.
- **Implementation Pattern**:
    ```typescript
    const handleRegenerateSummary = useCallback(async (meetingId: string) => {
        setIsRegenerating(true);
        try {
            const response = await fetch(`${API_BASE_URL}/meetings/${meetingId}/regenerate-summary`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(session?.idToken ? { 'Authorization': `Bearer ${session.idToken}` } : {})
                },
                body: JSON.stringify({ template_name: 'general' })
            });
            // ... error handling and list refresh ...
        } finally {
            setIsRegenerating(false);
        }
    }, [fetchMeetings, selectedMeeting, session?.idToken]);
    ```
- **Polling Strategy**: The dashboard triggers a refresh of the meeting list (`fetchMeetings`) to fetch the latest status after the manual trigger occurs.
