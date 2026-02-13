# Tauri Desktop Client & Visual Design

The Tauri desktop client is a high-precision overlay tool for local computer audio capture, featuring transparent UI elements and real-time ASR integration.

---

## 1. Core Architecture
- **Rust Layer**: Native audio capture (`cpal` crate) + `webrtc-vad`.
- **Overlay UI**: Next.js 16 (App Router) with `"use client";` directives for browser/Rust integration.
- **State Persistence**: Settings saved in `localStorage`.
- **API Client**: Uses native `fetch` with `URLSearchParams` for FastAPI compatibility.

---

## 2. Visual Design & Glassmorphism

### 2.1 Overlay Aesthetics (`page.tsx`)
- **The "Glass Lens"**: Combination of `backdrop-blur-2xl`, semi-transparent backgrounds (`rgba(0, 0, 0, opacity)`), and `border-white/20` to create a floating lens effect.
- **Click-Through Mode**: When "Locked", all borders/shadows are removed (`border-transparent`, `shadow-none`) and pointer events are disabled (`pointer-events-none`).
- **High-Contrast Typography**: Uses heavy text shadows (`textShadow: '0 2px 4px rgba(0,0,0,0.8)'`) for readability over moving backgrounds.
- **Simplified Focus**: Removed `maskImage` vertical fading (Feb 2026) to ensure 100% legibility of technical terminology.
- **Real-Time Visualization**: 
    - **Partial Highlights**: Unfinalized ASR rendered with lower opacity (`text-white/60`) and *italics*.
    - **Polished Feedback**: LLM-processed segments shift to `text-blue-300`.
    - **Active Speech Anchor**: The latest segment is emphasized using **MeetChi Success Green** (#499544) to provide a persistent ocular anchor for the user.
    - **Bilingual Separation**: Split by `border-t border-white/10`.

### 2.2 Teleprompter View (Alignment Mode)
- **Center-Focus Scrolling**: Uses `scrollIntoView({ block: 'center' })` with `py-[50vh]` padding.
- **Hierarchical Pop**: The active line scales up (`scale(1.1)`), shifts to **Bright Yellow (`text-yellow-400`)**, and gains a soft glow (`textShadow: '0 0 20px rgba(250, 204, 21, 0.4)'`).
- **Noise Reduction (Peripheral Logic)**:
    - **Dynamic Blurring**: Progressive blurring (`blur(Npx)`) for off-center segments.
    - **Distance-Based Opacity**: Opacity drops from `1.0` to `0.3` based on distance.

---

## 3. Connection Resiliency (implemented Feb 2026)

- **Rust-Side Auto-Reconnection**: `audio_processor.rs` implements a `tokio` async loop to monitor WebSocket health.
- **Core Strategy**: 
    1.  **Asynchronous Writer Task**: Separates real-time audio capture from the retry-heavy WebSocket writer.
    2.  **Config Caching**: Caches meeting ID and prompts for automatic re-handshake.
    3.  **Exponential Backoff**: Up to 10 attempts with 2s starting delay.
- **UI State Monitoring**: 
    - **Connection Heartbeat**: Pulsing dot in title bar (`animate-pulse`).
    - **Status Colors**: Green (Active VAD), Orange (Reconnecting), Red (Disconnected).
    - **State Transitions**: React frontend transitions UI based on Tauri events.

---

## 4. Script Alignment (Smith-Waterman)
- **Engine**: `alignment.rs` local alignment algorithm.
- **Deduplication Pattern**: `ScriptEngine` maintains a `emitted_segment_ids: HashSet<usize>` to prevent visual "jumping" or repetitions when a speaker skips sentences or doubles back.

---

## 5. Custom Window Management
- **Draggable Regions**: Implemented via `data-tauri-drag-region`.
- **Undecorated Resizing**: The Settings window (`settings/page.tsx`) uses a custom resize handle.
    - **Logic**: Tracks mouse deltas and updates dimensions via Tauri `setSize` + `LogicalSize`.
    - **Constraints**: Enforced 400x300 minimum.
- **Auto-Hide UI**: Title bar and controls use `opacity-0` transitions with `-translate-y-4` slide, appearing only on hover.

---

## 6. Pairing Protocol (`|||`)
- **Format**: `Source Sentence ||| Translated Sentence`.
- **Logic**: Backend splits on `|||`; frontend pairs lines in the dual-pane editor.
- **Biasing**: Scripts injected as `initial_prompt` into Whisper to bias the model towards specific terminology.
## 7. React Hydration Management (Hydration Guard)
- **Problem**: Next.js App Router performs Server-Side Rendering (SSR). Components checking for browser-only globals (e.g., `window`, `__TAURI_INTERNALS__`) or using Tauri-specific conditional rendering will produce different HTML on the server vs. the client, triggering a "Hydration Mismatch" error.
- **Pattern**: The **Hydration Guard**.
    1.  Declare an `isMounted` state initialized to `false`.
    2.  Set `isMounted` to `true` inside a `useEffect` hook with an empty dependency array (runs only once on mount).
    3.  Wrap all client-only components or conditional blocks with `{isMounted && ...}`.
- **Example**:
    ```tsx
    const [isMounted, setIsMounted] = useState(false);
    useEffect(() => setIsMounted(true), []);

    return (
        <div>
            {/* Standard SSR-friendly UI */}
            <Header />
            
            {/* Tauri-only UI - Guarded from SSR */}
            {isMounted && isTauri() && <CustomResizeHandle />}
        </div>
    );
    ```
## 8. Viewport & Subtitle Constraints (Feb 2026 Updates)
To support diverse display sizes and user preferences for content density, the following setting limits were expanded in `settings/page.tsx`:
- **Max Lines**: Increased from 20 to **50**. Useful for large vertical monitors or review-heavy meeting sessions.
- **Font Size**: Range increased to **72px** (from 48px). Optimized for "overlay-only" modes where maximum legibility is required from a distance.
- **Font Weight**: Adjustable range from **100 (Thin)** to **900 (Black)**. Higher weights (700+) are recommended for high-transparency backgrounds to maintain legibility.
- **Dynamic Style Injection**: In `app/page.tsx`, settings from `localStorage` are injected into the container's `style` attribute:
    ```tsx
    <div style={{ 
        fontSize: `${fontSize}px`, 
        fontWeight: fontWeight,
        lineHeight: '1.6' 
    }}>...</div>
    ```
- **Minimum Window Size**: Fixed at 400x300 via `LogicalSize` enforcement to prevent UI breakage in settings.
## 9. Subtitle Display Strategies (Feb 2026 Updates)
To optimize readability and user focus during live meetings, the client supports two distinct display patterns controlled via state logic in `app/page.tsx`:

### 9.1 Single-Segment Replacement (Focus Mode)
- **Logic**: When a new segment is finalized or updated, the previous segment is cleared immediately.
- **Benefit**: Zero visual clutter.
- **Implementation (Simplified)**:
    ```tsx
    {segments.length > 0 && (() => {
        const seg = segments[segments.length - 1]; // Tail only
        return <span className="transition-colors duration-500">{seg.content}</span>;
    })()}
    ```

### 9.2 Rolling Highlight Pattern (Context Mode - Preferred)
- **Logic**: Maintains full scrolling history but applies high-contrast visual focus to the **active** (newest) segment.
- **Highlight Color**: **MeetChi Success Green** `#499544` (RGB: 73, 149, 68). This color is reserved for active speech segments to provide an immediate ocular anchor.
- **Behavior**: New segments append at the bottom; auto-scroll ensures the green segment is always visible.
- **Implementation**:
    ```tsx
    {segments.map((seg, index) => {
        const isLatest = index === segments.length - 1;
        return (
            <span
                key={seg.id}
                className={`mr-2 transition-colors duration-500 ${seg.isPartial ? 'italic opacity-60' : ''}`}
                style={{
                    color: seg.isPartial 
                        ? 'rgba(255,255,255,0.6)' 
                        : isLatest 
                            ? '#499544'  // MeetChi Success Green (Ocular Anchor)
                            : seg.isPolished
                                ? '#93c5fd' // Blue-300 for finalized context
                                : 'rgba(255,255,255,0.7)'  // Dimmed historical context
                }}
            >
                {seg.content}
            </span>
        );
    })}
    ```
