# Audio & ML Runtime Integrity Patterns

This document consolidates MeetChi's patterns for audio signal processing, machine learning runtime optimization, and high-fidelity ASR orchestration.

---

## 1. Local-Cloud Hybrid Runtime

### 1.1 Lazy Dependency Loading Pattern
To prevent fatal crashes on CPU-only nodes (like the Backend orchestration API), heavy ML libraries (`torch`, `faster-whisper`, `whisperx`, `ctranslate2`) must be lazily loaded.

```python
# Helper to lazily load dependencies
torch = None
WhisperModel = None

def _ensure_gpu_deps():
    global torch, WhisperModel
    if torch is None:
        import torch as _torch
        torch = _torch
    if WhisperModel is None:
        from faster_whisper import WhisperModel as _WhisperModel
        WhisperModel = _WhisperModel

def load_asr_model():
    _ensure_gpu_deps()  # Only loads when this function is called
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return WhisperModel("model-name", device=device)
```

- **Dependency Removal Pattern (Tier 1 Preferred)**: For services where Managed APIs (Gemini) handle all compute, the "Lazy Loading" pattern is superseded by **total removal** of ML libraries (`torch`, etc.) from `requirements.txt`. This avoids the "Cascading Import" problem entirely, reduces build times by 90%, and ensures the image remains under 200MB.
- **Diagnostics**: Avoid top-level `DEVICE = "cuda" if ... else "cpu"` probes even if imports are lazy, as these can trigger fatal initialization errors on CPU-only machines if the library is present but hardware is not.
- **The "HealthCheckContainerError" Pattern**: If a container starts locally but fails on Cloud Run (CPU):
    1.  **Check for Cascading Imports**: Audit `main.py` and routers for hidden imports of heavy ML libs in shared utility files.
    2.  **Audit Lifecycle Hooks**: Ensure `on_startup` or `lifespan` handlers do not trigger model loading.
    3.  **Pydantic v2 Migration**: Note that upgrading an ML stack often requires replacing `regex` with `pattern` in all Pydantic `Field` configurations to avoid `PydanticUserError`.

---

## 2. Audio Processing Integrity

### 2.1 Voice Activity Detection (VAD) Orchestration
- **Silero vs. Energy Fallback**: Silero is precision-king but heavy. Use it on GPU nodes. For lightweight clients (Tauri/Web), implement a simple RMS energy-based gate (`rms > 0.005`).
- **Gating Logic**: Discard segments < 0.3s (noise) but keep segments ~0.5s for interjections ("Yeah", "OK"). 

### 2.2 Signal Conditioning (FFmpeg/Python)
- **High-Precision Extraction**: Use FFmpeg to extract mono 16kHz WAV. Re-encoding ensures duration accuracy for word-level timestamps.
- **Denoising**: Use `noisereduce`. **Sweet Spot**: `prop_decrease=0.8` (1.0 makes vocals sound robotic).
- **Normalization**: Target `-23.0 LUFS` to prevent clipping in feature extractors.

### 2.3 Hallucination Subtraction
- **ASR Blacklist**: Maintain `HALLUCINATIONS_EXACT` list for model artifacts (silent "Thank you", "大家好" in empty rooms).
- **Alignment Exception**: Disable halluncination filters when in "Alignment Mode", as filtering a valid script greeting will cause matching stalls.

---

## 3. Real-Time Script Alignment (Smith-Waterman)

MeetChi uses an optimized Smith-Waterman local alignment algorithm to synchronize live ASR with pre-defined scripts.

### 3.1 Tuning Parameters
- **FORWARD_LOOK (600 chars)**: Large window to handle processing lag or speaker speed.
- **BACK_LOOK (20 chars)**: Handles slight backtracking/repetitions.
- **Homophone Tolerance**: Award partial scores (75%) for similar-sounding characters (e.g., 諸 vs 祝) to increase cursor stability in fast speech.

### 3.2 Sequential Multi-Speaker Transitions
- **Proactive Probing**: The aligner "peeks" 100 characters into the *next* speaker's zone.
- **Trigger**: Identifying the start of the next speaker's script (e.g., "Thank you Chairman, I am delighted...") is a definitive high-confidence signal to advance the zone.

---

## 4. ML Model Lifecycle

### 4.1 GCS-Based "Hydration" Strategy
Instead of baking 20GB of models into Docker, the image contains only the GCP SDK.
1. **Startup**: Entrypoint runs `gsutil -m cp -r gs://${PROJECT}-models/path /app/models`.
2. **Advantage**: Instant image builds, zero Artifact Registry bloat, and model swapping via Env Var update.

### 4.2 API-Only Healthy Signaling
The `/health` endpoint for the optimized Tier 1 service provides explicit capability flags:
- `gemini_enabled: true` confirms the API integration is active.
- `local_model_loaded` is removed or returns `false` by design.
- **Verification Signature**: Look for `{ "status": "ready", "version": "2.0.0-gemini-only" }` to confirm the production environment has transitioned to the lightweight orchestrator.

### 4.3 Hardware-Specific Kernels (sm_120)
For modern GPUs (RTX 50-series), ensure the environment uses **PyTorch 2.6+** and **CUDA 12.8**. Using older binaries will result in `no kernel image is available for execution`.

---

## 5. Build & Rollout Efficiency

### 5.1 The Pip Redundant Installation Trap
When building GPU images, avoid installing standard `torch` versions *after* specialized ones (e.g., `torch+cu121`). 
- **Symptom**: Logs show `Successfully uninstalled torch-2.1.0+cu121` followed by a re-download of a standard CPU version.
- **Resolution**: Install all heavy dependencies in a **single** `pip install` command OR use a `constraints.txt` to lock the specialized build.

### 5.2 Build Machine Scaling
Default Cloud Build machines (`e2-medium`) may OOM during massive ML dependency resolution. Use `machineType: 'E2_HIGHCPU_8'` in `options` to ensure stability for images exceeding 5GB.

---

## 6. LLM Post-Processing Patterns

### 6.1 JSON Stability & Language Flips
- **Targeted Regex**: Extract JSON from LLM output using `re.search(r'\{.*\}', content, re.DOTALL)`.
- **Language Flip Detection**: If a model is asked to summarize in Chinese but returns English, detect via regex `[a-zA-Z]` (if no Chinese chars present) and auto-revert to raw text.
- **Breeze-3B Compatibility**: Newer models like MediaTek Breeze2-3B require `transformers>=4.38.0`. Outdated libraries cause `KeyError: 'architectures'`.
- **Temperature Control**: Maintain `temperature=0.1` for high-fidelity JSON mapping tasks.

### 6.2 Alignment Mode Polishing Bypass
- **Rule**: When `operationMode === 'alignment'`, LLM polishing (refining) **must be skipped**.
- **Rationale**: Alignment mode prioritizes synchronizing ASR with a *known script*. LLM polishing would rephrase the ASR output, potentially breaking the semantic markers used to calculate the Smith-Waterman cursor position in the script.
- **Client Handling**: The client should preserve the raw `content` and skip triggering the `polished` state to ensure the script text remains the source of truth for the display.

## 7. Docker Image Rationalization

Re-evaluating image size in light of the Gemini API integration:

### 7.1 "Fat" vs. "Lean" Selection
- **Fat Image (Legacy/Hybrid)**: Uses CUDA-runtime base + PyTorch. Essential for local WhisperX ASR.
- **Lean Image (API-Centric)**: Uses `python-slim` base. Suitable if the service primarily orchestrates external API calls (Gemini).
- **Optimization Threshold**: If >90% of tasks are offloaded to Gemini, move to a lean image and use a separate, dedicated "ASR worker" (fat image) for heavy lifting, rather than one giant hybrid service.

### 7.2 Multi-Stage Build Pattern
Even for Fat images, use multi-stage builds to discard build-essential libraries (`gcc`, `g++`) after compiling C-extensions or specialized wheels.
