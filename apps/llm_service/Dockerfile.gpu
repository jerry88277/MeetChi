# ============================================
# MeetChi LLM Service - GPU-Enabled Dockerfile
# Models loaded from GCS at startup for faster builds
# ============================================

# Use NVIDIA CUDA base image (correct tag format)
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04


# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CUDA_VISIBLE_DEVICES=0 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    MODELS_DIR=/app/models \
    GCS_MODELS_PATH=""

WORKDIR /app

# Install Python and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-dev \
    build-essential \
    git \
    ffmpeg \
    libsndfile1 \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/python3.10 /usr/bin/python

# Install Google Cloud SDK for gsutil
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements first for layer caching
COPY requirements.txt .

# Install PyTorch with CUDA support first
RUN pip install --no-cache-dir \
    torch==2.1.0 \
    torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cu121

# Install other requirements
RUN pip install --no-cache-dir -r requirements.txt

# Install WhisperX and transformers for dual ASR
RUN pip install --no-cache-dir \
    whisperx \
    transformers>=4.36.0 \
    accelerate \
    bitsandbytes

# Copy application code
COPY . .

# Create directories
RUN mkdir -p /app/.cache/huggingface /app/models && chmod -R 777 /app/.cache /app/models

# Copy startup script
COPY startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Expose port
EXPOSE 5000

# Run startup script
CMD ["/app/startup.sh"]
