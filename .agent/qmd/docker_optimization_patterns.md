# Docker Image Optimization for LLM Services

This document analyzes the resource rationality and optimization strategies for MeetChi's LLM service Docker images, specifically comparing heavy GPU-enabled images vs. lightweight API-centric images.

---

## 1. Evolution of MeetChi Service Strategy

MeetChi's `llm_service` transitioned from a **Hybrid GPU Image** to a **Lean API-Centric Image** as the Gemini 2.5 Flash Lite API proved to be the more cost-effective and resilient engine for serverless deployments.

### 1.1 Legacy/Hybrid State (Early Feb 2026)
- **Base**: `nvidia/cuda:12.1.0-runtime-ubuntu22.04`
- **Key Dependencies**: `torch`, `whisperx`, `transformers`.
- **Size**: ~15.2 GB (total uncompressed), ~5.2 GB image.
- **Rationality**: Supported local ASR (WhisperX) and local LLM (Breeze) fallback during the GPU-dependent research phase.

### 1.2 Validated Lean State (Feb 6, 2026)
- **Base**: `python:3.11-slim`
- **Key Dependencies**: `google-genai`, `flask`, `pydantic`.
- **Image Size**: **~148 MB** (uncompressed).
- **Resources**: 1 vCPU, 512 MiB RAM.
- **Startup Latency**: < 5 seconds (Health check).
- **Rationality**: Optimized for Gemini-only summarization on serverless Cloud Run CPU instances. Removed all GPU/CUDA bloat.

---

## 2. Resource Rationality Review

With the successful integration of the **Gemini 2.5 Flash Lite API**, the requirement for a heavy image on Cloud Run (CPU slots) is questioned.

### 2.1 The "Why Heavy?" Checklist
A 5GB+ image is justified ONLY if:
- **Local ASR is required**: Real-time transcription using WhisperX.
- **Privacy Requirements**: Zero-data-leaking policy (no external APIs).
- **Cost at Scale**: Running local models on dedicated GPUs is cheaper than API tokens at extremely high volumes.
- **Connection Fail-Safe**: System must work in offline/air-gapped environments.

### 2.2 The "Why Light?" Checklist
A <500MB image is preferred if:
- **API-Priority**: Gemini handles 100% of summarization tasks.
- **Serverless Performance**: Cloud Run cold starts are significantly faster with small images.
- **Build Speed**: Cloud Build times drop from 10-15 mins to <2 mins.
- **Complexity**: No need to manage complex CUDA/PyTorch version compatibility.

---

## 3. Validated Implementation (Tier 1 Lean)

The following configuration has been verified in production to reduce image size by **99%** while maintaining full summarization functionality.

### 3.1 Verified Dockerfile
```dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install minimal Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Health check (Sub-second startup)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000
CMD ["python", "app.py"]
```

### 3.2 Pruned requirements.txt
```text
flask>=2.0.0
werkzeug>=2.0.0
python-dotenv>=1.0.0
google-genai>=1.0.0
pydantic>=2.0.0
requests>=2.28.0
```

### 3.3 Resource Limits (Terraform)
```hcl
resources {
  limits = {
    cpu    = "1"
    memory = "512Mi" # Reduced from 8Gi
  }
}
```

## 4. Key Findings

1.  **Dependency Bloat**: The primary source of image size is `torch` (~2GB) and `nvidia-cuda-runtime` (~1GB).
2.  **Redundancy**: On Cloud Run CPU-only slots, the 2GB `torch` library is almost never utilized for summarization when Gemini is enabled, serving only as a "passive fallback" that slows down deployment.
3.  **Deployment Latency**: Large images trigger "waiting for layers" periods in Artifact Registry. Transitioning to Tier 1 reduced deployment cycles from ~11 minutes to **< 2 minutes**.
4.  **Cold Start Optimization**: The `python:3.11-slim` image achieves a **< 5-second health check ready state**, compared to 60-120 seconds for the Hybrid image due to its lack of heavy library initialization.

---

## 5. Recommendation

Transition to a **Tiered Image Strategy**:
- Use **Lean Images** for the serverless Cloud Run backend where Gemini is the primary engine.
- Maintain **Heavy Images** only for localized, high-performance GPU nodes where ASR accuracy and low-latency audio processing are paramount.
