# Multi-Speaker Script Alignment Implementation

## 1. Problem Statement
In "Alignment Mode", the system originally matched real-time ASR against a single, flattened script. When two speakers give speeches sequentially (back-to-back), there is no time to manually switch scripts. This led to:
- **Cross-Matching**: Speaker A's speech might match fragments in Speaker B's script if they share common phrases (e.g., "Thank you").
- **Boundary Drift**: The search window might drift into the next speaker's territory if the first speaker goes off-script near the end.

## 2. Requirements
- **Sequential Support**: Load multiple scripts simultaneously in a single session.
- **Speaker Isolation**: Ensure matching for Speaker A is strictly zone-locked to Script A.
- **Seamless Transition**: Support "handoff" where the system auto-advances based on progress.

## 3. Overview
The multi-speaker alignment feature allows MeetChi to handle sequential speeches from different speakers without manual script switching. It prevents "cross-speaker matching" by introducing boundary-aware search logic using "Speaker Zones".

## 4. Multi-Speaker Data Format
The system uses a specific marker to distinguish speakers within a single combined script:

```text
===SPEAKER:董事長===
各位貴賓大家好 ||| Good evening distinguished guests
歡迎蒞臨 ||| Welcome
===SPEAKER:總經理===
感謝董事長 ||| Thank you Chairman
今天很高興 ||| I am delighted
```

- **Separators**: `===SPEAKER:Name===` defines the start of a new speaker's section.
- **Segment Format**: `Source Text ||| Target Translation` per line.

## 5. Backend: MultiSpeakerScriptAligner

The `MultiSpeakerScriptAligner` class extends the core `ScriptAligner` (Smith-Waterman based) to add zone awareness.

### 5.1 Zone Parsing
`_load_multi_speaker_script` uses regex to split the text:
- `re.split(r'===SPEAKER:([^=]+)===', script_text)`
- Each zone is stored as: `(start_char_idx, end_char_idx, speaker_name, (start_seg_idx, end_seg_idx))`.

### 5.2 Zone-Locked Search
Matching is restricted to the current speaker zone to prevent accidentally jumping to future speakers who might use similar greeting phrases.

- **Constraint Logic**: 
    - Search window for Smith-Waterman is clamped between `zone.start_idx` and `zone.end_idx`.
    - **Global Resync**: If 5+ consecutive failures occur, the search scope expands, but **only to the full range of the current zone**, not the entire multi-speaker script.

### 5.3 Auto-Advance Mechanism (Next-Zone Probing)
The aligner automatically transitions to the next speaker by "probing" the start of the next zone.

- **The Problem with Strict Completion (Solution B)**: Requiring the current zone's final segments to be matched was found to be too strict for natural speech where speakers might skip or paraphrase their final sentences.
- **The "Natural Handoff" (Solution C - Finalized Feb 5, 2026)**: Instead of waiting for the current speaker to *finish*, the system looks for the start of the *next* speaker's script as a definitive signal to switch.
- **Search Range Expansion**: 
    - The search window is expanded to include the current zone PLUS the first ~100 characters of the **next zone**.
    - If a match is found within the expanded range, the system checks the `match_start` index.
- **Trigger Logic**:
    - **Primary (Cross-Zone Detection)**: If `global_match_start >= next_zone.start_idx`, the system authorizes an immediate `advance_speaker()` call. This allows for seamless transitions even if the first speaker goes slightly off-script at the very end.
    - **Secondary (Progress Fallback)**: If the cross-zone trigger is missed (e.g., the ASR misses the first sentence of the next speaker), the system will automatically advance when the current zone progress reaches **95%** (`get_zone_progress() >= 0.95`).
- **Manual Advance**: Users can still manually trigger the next speaker via the UI.
- **State Reset**: Tracking sets (like `last_matched_segments`) are cleared during the switch to ensure a fresh state for the new speaker.

### 5.4 State Management
- `current_zone_index`: Tracks which speaker is active.
- `lock_to_current_zone`: Boolean toggle to enable/disable cross-speaker isolation.
- **Signature Consistency**: When adding parameters (like `alignment_mode`) to the base `ScriptAligner.find_match()`, the `MultiSpeakerScriptAligner` override must also be updated to accept these parameters. This avoids `TypeError` regressions in the WebSocket handler. The subclass implementation now includes `alignment_mode` and correctly calculates `effective_threshold` (0.30 vs 0.50) before conducting the zone-restricted search.

### 5.5 Alignment Search Parameters
The alignment performance is controlled by several key constants in the Aligner classes:

- **`NORMAL_WINDOW_BACK` (20 chars)**: How far back to search from the current cursor. Keeps the search efficient and prevents matching against historical text.
- **`NORMAL_WINDOW_FORWARD` (600 chars)**: How far ahead to search targets. 
    - *Correction (Feb 5, 2026)*: Increased from 200 to 600 to handle cases where the speaker jumps forward or the ASR processing time causes the actual speech to outpace the search window. This is critical for slow speech or long scripts (~800+ chars).
- **`MAX_CONSECUTIVE_FAILURES` (3)**: Triggers a "Global Resync" (searching the entire active zone) if the local window fails too many times. Reduced from 5 to 3 for faster recovery in alignment mode.
- **`MIN_MATCH_SCORE` (6)**: Baseline score to prevent low-confidence junk matches. Lowered from 10 to 6 to handle small fragments of speech.

### 5.6 ASR Interaction & Hallucination Filtering
For Script Alignment to work reliably, the ASR output must contain all words spoken, even brief phrases or politeness markers.

- **Conflict with Hallucination Filters**: Standard Whisper-based ASR often uses filters to remove "hallucinations" or common interjections (e.g., "謝謝", "大家好", "Yeah"). 
- **Impact on Alignment**: If a greeting like "謝謝" (Thank you) is in the script but filtered out by the ASR system before reaching the Aligner, the cursor will not advance to the final segment, causing a 100% completion failure.
- **Implementation (Feb 5, 2026)**: 
    - The ASR function `get_transcription()` in `scripts/transcribe_sprint0.py` now accepts a `skip_hallucination_filter` parameter.
    - Inside `get_transcription`, if `skip_hallucination_filter` is `True`, the `HALLUCINATIONS_SUBSTRING` and `HALLUCINATIONS_EXACT` checks are bypassed.
    - In `app/main.py`, the WebSocket handler passes this flag based on the active mode: 
      `skip_hallucination_filter=(operation_mode == "alignment")`.

### 5.7 Search Window Tuning for Long Scripts
During testing with scripts exceeding 800 characters, it was discovered that the cursor could "fall behind" the search window if the forward reach was too small.

- **Constraint**: `NORMAL_WINDOW_FORWARD` was originally 200 characters. 
- **Symptom**: A cursor at character 500 could only look ahead to character 700. If the speaker reached a sentence at character 800+, the Aligner would report a match failure despite correct ASR.
- **Solution**: Increased `NORMAL_WINDOW_FORWARD` to **600 characters**. This allows the system to recover from larger jumps or slight processing lags without triggering a full "Global Resync".

### 5.8 WebSocket Protocol & Mode Activation
The alignment mode is activated via a JSON configuration message sent over the WebSocket:

- **Message Type**: `"config"`
- **Key Fields**:
    - `"mode"`: Set to `"alignment"` to enable script matching.
    - `"initial_prompt"`: Contains the full script in multi-speaker marker format.
- **Backend Flow**:
    1. The WebSocket handler in `app/main.py` parses the config.
    2. It sets `operation_mode = "alignment"`.
    3. It calls `script_aligner.load_script(initial_prompt)`.
    4. Subsequent ASR outputs (from `snapshot` or `split` events) are transcribed with `skip_hallucination_filter=True` and passed to `script_aligner.find_match()`.

### 5.9 MECE Framework for Alignment Tuning
To ensure the Aligner reaches the high confidence thresholds required to trigger the next script segment, parameters must be optimized across four mutually exclusive layers:

1.  **Acoustic/VAD Layer** (Segmentation):
    - `min_speech_duration`: Determines the smallest unit of text sent for alignment. Too short = low score (fails `MIN_MATCH_SCORE`). Too long = delayed feedback.
    - `max_speech_duration`: Prevents accumulation of drift. Default 7s–10s.
    - `silence_threshold`: Ensures sentences are finalized naturally.
2.  **ASR Processing Layer** (Precision):
    - `beam_size`: Set to `5` or higher in alignment mode to ensure characters match the script with high precision.
    - `temperature`: Set to `0` for deterministic results.
    - `initial_prompt`: Used to inject specific keywords from the current speaker's script into the ASR context.
3.  **Text Normalization Layer** (Robustness):
    - **Punctuation Stripping**: The aligner must ignore full-width/half-width punctuation difference.
    - **Sound-Alike Mapping**: Critical for homophones (e.g., ASR outputs "祝事" while script says "諸事").
4.  **Alignment Logic Layer** (Matching):
    - `MIN_MATCH_SCORE`: The threshold for a valid match. Lowered to **6** to support short fragments.
    - `WINDOW_FORWARD`: (**600 chars**) Defines how far ahead the speaker can jump.
    - `NORMAL_WINDOW_BACK`: (20 chars) Handles slight backtracking or repetitions.
    - `Alignment Threshold`: (**0.30**) In alignment mode, the confidence threshold is lowered from 0.50 to 0.30 to accommodate VAD fragmentation and homophones.

### 5.10 Handling Slow vs Fast Speech
Performance varies significantly based on delivery speed:

- **Fast Speech**: Cursor may fall behind the ASR window. Solution: Larger `NORMAL_WINDOW_FORWARD` (600 chars).
- **Slow/Precise Speech**: ASR may split a single script sentence into multiple small fragments (e.g., "心...", "堅定的步伐...").
    - *Problem*: Individual fragments might not reach the original `MIN_MATCH_SCORE` (10) or strict threshold (0.50).
    - *Solution (Feb 5, 2026 Optimization)*: 
        1. Lowered `MIN_MATCH_SCORE` to 6.
        2. Lowered alignment threshold to 0.30 (via `alignment_mode=True`).
        3. Reduced `MAX_CONSECUTIVE_FAILURES` to 3 for faster global resync recovery.

### 5.11 Sound-Alike (Homophone) Tolerance
To handle ASR inaccuracies where characters sound similar but represent different words (common in Chinese), the Smith-Waterman algorithm was enhanced with a homophone tolerance layer.

- **Mechanism**: A `HOMOPHONES` mapping table identifies sets of similar-sounding characters.
- **Scoring**: If two characters do not match exactly but are identified as homophones, the algorithm awards a **partial match score (75% of the standard MATCH_SCORE)** instead of applying a mismatch penalty.
- **Key Mappings (Feb 5, 2026)**:
    - **諸 (Zhū)** ↔ **祝/竹/朱** (Common in "諸事順心" vs "祝事順心")
    - **夜 (Yè)** ↔ **一 (Yī)** (Common in "愉快的一晚" vs "愉快的一夜")
    - **的/得/地** (Grammatical particles often confused by ASR)
    - **事 (Shì)** ↔ **是/式**
    - **晚 (Wǎn)** ↔ **碗/萬**

This change significantly improves the confidence score for sentences like "新的一年諸事順心", which often returns "祝事" or "助事" in fast speech.

### 5.12 Zone Boundary Clipping (Speaker Transition Lag)
During verification of long multi-speaker scripts, a critical bottleneck was identified at the boundary between speakers:

- **The Clipping Problem**: When `lock_to_current_zone` is active, the aligner strictly clips the search window at `zone_end`. If the speech for Speaker A finishes at the boundary (e.g., character 509), the search logic calculates `min(509, 509+600)`, resulting in 509. 
- **The Deadlock**: When Speaker B starts talking, the ASR transcript (which matches text at character 510+) is compared against a window that ends at 509. Even with a lower threshold or homophone tolerance, **the physical overlap is zero**, leading to a permanent alignment stall.
- **The "False Positive" Handoff**: The deadlock is frequently caused by premature auto-advance. If the system incorrectly matches early Zone 1 text, it jumps the cursor prematurely.
- **Resolution (Solution C - Proactive Probing)**: 
    1. **Expanded Window**: The search window is allowed to "peek" into the next zone by 100 characters.
    2. **Conflict Resolution**: If the ASR matches the *end* of Zone A and the *start* of Zone B simultaneously, the system prioritizes the match with the higher score or maintains the current zone until the Zone B signal becomes dominant.
    3. **Natural Transition**: Matching the first sentence of the next speaker (e.g., "Good morning, I am [Name]") acts as a high-confidence trigger to unlock the next zone.

## 6. Frontend Integration


### 6.1 Script Editor UI
The Settings page (`src/app/settings/page.tsx`) features a redesigned Script Editor that toggles between single and multi-speaker modes.

**Note on Client Components**: Since this page uses browser hooks (`useState`, `useEffect`) and Tauri-specific `invoke` methods, it **must** include the `"use client";` directive at the top. This applies to most UI-heavy interactive pages in the MeetChi Tauri client.

**UI Components**:
- **Multi-Speaker Toggle**: Switches the editing mode and triggers script regeneration.
- **Speaker Sections (A & B)**: Collapsible `details` elements containing:
    - **Speaker Name**: Editable text input (defaults to "講者 A" and "講者 B").
    - **Chinese Script Area**: Large textarea for source text.
    - **English Script Area**: Matching textarea for target translations.
- **Combined View**: A hidden/internal state (`combinedScript`) that formats all inputs into the backend-consumable marker format.

### 6.2 Script Regeneration Logic
To ensure the backend always receives a valid multi-speaker script, the frontend uses two specific helper functions:

```typescript
// Helper: Regenerate multi-speaker combined script with sequence markers
const regenerateMultiSpeakerScript = () => {
    const speakerACh = speakerAChineseScript.split('\n').filter(l => l.trim());
    const speakerAEn = speakerAEnglishScript.split('\n').filter(l => l.trim());
    const speakerBCh = speakerBChineseScript.split('\n').filter(l => l.trim());
    const speakerBEn = speakerBEnglishScript.split('\n').filter(l => l.trim());
    
    let multiCombined = `===SPEAKER:${speakerAName}===\n`;
    multiCombined += speakerACh.map((ch, i) => `${ch.trim()} ||| ${speakerAEn[i]?.trim() || ''}`).join('\n');
    multiCombined += `\n===SPEAKER:${speakerBName}===\n`;
    multiCombined += speakerBCh.map((ch, i) => `${ch.trim()} ||| ${speakerBEn[i]?.trim() || ''}`).join('\n');
    
    setCombinedScript(multiCombined);
    saveSetting('combinedScript', multiCombined);
};

// Helper: Regenerate single-speaker combined script (backward compatibility)
const regenerateSingleSpeakerScript = () => {
    const chLines = chineseScript.split('\n').filter(l => l.trim());
    const enLines = englishScript.split('\n').filter(l => l.trim());
    setScriptPairCount(Math.min(chLines.length, enLines.length));
    const combined = chLines.map((ch, i) => `[${i + 1}] ${ch.trim()} ||| ${enLines[i]?.trim() || ''}`).join('\n');
    setCombinedScript(combined);
    saveSetting('combinedScript', combined);
};
```

### 6.3 Real-time Feedback Loop
The WebSocket response from the backend includes:
- `current_speaker`: The name currently identified by the Aligner.
- `zone_progress`: Numeric progress (0.0 to 1.0) within the current speaker's script.

This metadata is utilized by the `TeleprompterView` and `MeetingCard` components to show active speaker status and progress bars, guiding users through the sequential speech process.

### 6.4 API Considerations
For operations that require additional context (like triggering a summary with specific speaker focus), the `src/lib/api.ts` client utilizes `URLSearchParams` to encode multiple optional parameters (`context`, `length`, `style`) into the request URL, ensuring compatibility with the FastAPI dependency-injected query parameters.
