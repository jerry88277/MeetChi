# Infrastructure & Deployment

## 1. Cloud Run Readiness
MeetChi is standardized on **Google Cloud Run** for production deployment.

### 1.1 Regional Strategy
- **Status**: **GPU QUOTA APPROVED** for `asia-southeast1` (Singapore).
- **✅ Selection**: Standardized on **`asia-southeast1` (Singapore)** to leverage L4 GPU acceleration.
- **Asia-Pacific Availability (NVIDIA L4)**:
    - **Singapore** (`asia-southeast1`): ✅ Available & Verified
    - **Tokyo** (`asia-northeast1`): ✅ Available
    - **Taiwan** (`asia-east1`): ❌ Not Available

### 1.2 Resource Specifications
- **GPU Instance**: Standardized on 1x NVIDIA L4 (using `nvidia/cuda:12.1.0-runtime-ubuntu22.04` or specialized ML images) for both **LLM** and **ASR (Backend)** components.
- **CPU/Memory**: 4 vCPU and 16GiB RAM mandatory for L4 GPU instances on Cloud Run.
- **Scaling constraint**: To avoid zonal redundancy quota conflicts, GPU services are initially capped at `max_instance_count = 1`.
- **Port**: Default 8000 for backend API / WebSocket, 5000 for LLM Service.
- **Warm-up**: Fast-Whisper adds ~30s start latency. LLM model loading can take 2-5 min. Service uses `startup_probe` (120s+) to handle cold starts.

## 2. Stateless Storage & Database
- **Database**: Standardized on **Google Cloud SQL (PostgreSQL)** with `pgvector` for future semantic search.
- **Object Storage**: Audio files are stored in **Google Cloud Storage (GCS)** using the signed URL pattern.
- **Task Queue**: Google Cloud Tasks handles background processing.
    - **Transcription Queue**: High-priority; handles Whisper inference results.
    - **Summarization Queue**: Standard-priority; handles LLM processing.
    - **Environment Variable**: `CLOUD_TASKS_QUEUE` (format: `projects/[PROJECT]/locations/[REGION]/queues/[NAME]`).
    - **Benefit**: Serverless; eliminates the baseline cost of a dedicated Redis instance.
- **Deletion Protection**: Enabled by default for the Production Cloud SQL instance to prevent accidental data loss.

### 2.1 Security & Networking (Development Setup)
The current Terraform configuration prioritizes rapid deployment:
- **Cloud SQL**: Authorized networks are set to `0.0.0.0/0` to allow the Backend service to connect without complex VPC peering initially. **⚠️ MUST be restricted to Cloud Run service IPs or VPC internal access in production.**
- **Secret Manager**: Secrets are replicated automatically and accessible via the `meetchi-cloudrun` service account.

## 3. Terraform IaC
The infrastructure is defined in the `terraform/` directory:
- `main.tf`: Provider setup and API enablement.
- `database.tf`: Cloud SQL instance, Google Cloud Tasks Queues, and GCS buckets.
- `cloudrun.tf`: Service definitions for Backend and LLM GPU (Beta launch stage).
- `outputs.tf`: Contains GPU Quota instructions and connection strings.

### 3.1 Provisioning Performance
When running `terraform apply`, expect the following durations for resource creation in `asia-southeast1`:
- **Cloud SQL (PostgreSQL)**: ~5 - 10 minutes.
- **Google Cloud Tasks Queue**: ~1 - 2 minutes.
- **Service API Enablement**: ~1 - 2 minutes.
- **Overall Stack**: Typically completes in **12 - 15 minutes**.

### 3.2 Cloud Run GPU Syntax Correctness
When configuring GPUs in `google_cloud_run_v2_service`, ensure the following:
- **❌ DO NOT** use the `node_selector` block inside `template` (Terraform provider unsupported).
- **❌ DO NOT** use `gpu_zonal_redundancy_disabled = true` (Terraform provider unsupported).
- **✅ DO** use `provider = google-beta` for the service resource.
- **✅ DO** use `resources.limits` with `"nvidia.com/gpu" = "1"` within the `containers` block.
- **✅ DO** set `launch_stage = "BETA"` at the service level.
- **✅ DO** ensure CPU is set to at least "4" and memory to "16Gi" for L4 GPUs.
- **✅ HYBRID STRATEGY**: If Terraform fails due to quota/zonal-redundancy despite `max_instance_count = 1`, use the `gcloud run services update` command (Section 6.3) to apply the `--no-gpu-zonal-redundancy` flag manually.

## 4. Quota Application Procedures
### 4.1 Requesting Quota (Step-by-Step)
For the `meetchi-llm-gpu` service, you need the **NVIDIA L4 GPU** quota.
1.  Go to **IAM & Admin > Quotas & System Limits**.
2.  Filter for `NvidiaL4GpuAllocPerProjectRegion` (or `NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion` for better approval odds).
3.  Select your region (e.g., `asia-southeast1`).
4.  Click **Edit Quotas** and request at least **3**.
    - **The 3x Rollout Buffer**: Even if you plan to run only 1 instance (`max_instances=1`), Cloud Run requires a regional quota of **3** units to perform a non-disruptive, atomic rollout of a new revision. 
    - **The 1-Unit Workaround**: If you only have 1 unit of quota, you must **delete the existing service** (`gcloud run services delete`) before deploying the new version to bypass the 3x transaction check.
5.  Check for **Memory Quota** (`MemAllocPerProjectRegion`): 16GiB (minimum for GPU) x 3 (buffer) = **48GiB**. Ensure your regional memory quota supports this request.

### 4.2 CLI Promotion Pattern
As of early 2026, the `google-beta` Terraform provider may not support all Cloud Run v2 GPU tuning attributes (like `--no-gpu-zonal-redundancy`).
**Verified Workaround**:
1. Use Terraform to deploy IAM, Secrets, and DNS/SSL.
2. Use the `gcloud` CLI to apply the GPU configuration:
   ```bash
   gcloud alpha run services update meetchi-llm-gpu \
     --gpu=1 --gpu-type=nvidia-l4 \
     --no-gpu-zonal-redundancy \
     --memory=16Gi --cpu=4 \
     --region asia-southeast1
   ```
- **Crucial**: Even with `max_instances = 1`, Cloud Run reserves **3x** capacity during rollout. A quota of 1 will cause `Quota violated` errors.
4. **Application Form Recommendations (Verified Feb 2026)**:
    - **Service Purpose**: Web Application - Real-time speech-to-text transcription using Whisper Large V3 and Speaker Diarization.
    - **Usage Pattern**: Stable during business hours (09:00-18:00 UTC+8). Usage scales to zero when idle.
    - **Quantities**: Median 1, Max 1 (initially).
    - **Model Size**: ~6-8 GB total (Whisper v3 + Pyannote + LLM).
    - **GCP Representative Email**: **Leave blank** unless specifically assigned.
5. **Wait Time**: Initial manual quota application typically takes **24-48 hours**.
6. **CPU Fallback Strategy**: While waiting for quota, see `troubleshooting.md` Section 2.14 for temporary CPU-only configuration or Section 2.39 for decoupling logic.
7. **Production Recommendation**: Request at least **6-10 L4 GPUs** if planning for high concurrency or multi-region failover.

## 5. Dockerization
- **Backend Service (GPU)**: Evolved from a pure coordination layer to includes **GPU acceleration for ASR (Faster-Whisper)**. While it still handles API management and WebSocket coordination, it now leverages NVIDIA L4 for real-time transcription. It requires the same 4 CPU / 16GiB RAM baseline as the LLM service.
- **LLM Service (GPU)**: Specialized `Dockerfile.gpu` with PyTorch and Transformers pre-installed. This is the designated host for heavy LLM inference tasks.
- **Build Workflow**: `cloudbuild.yaml` triggers parallel build and push to Artifact Registry, then deploys to Cloud Run with appropriate secrets and GPU mounting.
- **⚠️ Build Latency & Strategy**: 
    - **LLM Service**: ~10-15 minutes (downloads >1.5GB of CUDA/PyTorch layers).
    - **Backend Service**: ~3-5 minutes (minimal Python packages). 
    - **Baseline**: As of Feb 2026, experiments with an ML-enabled Backend (v2) resulted in consistent `container-failed-to-start` errors on Cloud Run CPU due to the `ctranslate2` dependency. The current strategy reverts the Backend to a pure API layer.
    - **Advice**: Set build timeouts to at least 30 minutes (1800s) and use the `--no-cache` strategy in `cloudbuild-backend.yaml` for application logic updates.

### 5.1 Dockerfile Implementation

#### 5.1.1 Optimized Backend Dockerfile (CPU)
For the Backend API (which handles audio coordination but not heavy LLM inference), use a optimized `Dockerfile` with system-level audio dependencies:

```dockerfile
FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app PORT=8000
WORKDIR /app

# System dependencies for audio (ffmpeg, libsndfile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git ffmpeg libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Permissions and directories for audio processing
RUN mkdir -p /app/audio_files /app/logs && chmod -R 777 /app/audio_files /app/logs
EXPOSE 8000

# Health check (requires curl)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 5.1.3 Backend GPU Dockerfile (ASR-Enabled)
For production environments where the Backend handles real-time ASR using GPU acceleration:
- **Base Image**: `nvidia/cuda:12.1.0-runtime-ubuntu22.04` (to match L4 GPU requirements).
- **Dependencies**: Includes `torch`, `faster-whisper`, and `ctranslate2`.
- **Optimization**: Lazy-loading of ML dependencies prevents startup crashes in non-GPU environments.
- **Verification**: Subdirectory submission reduced Backend context to **1.9 MiB** and LLM service context to **35 KB**.

#### 5.1.4 LLM GPU Dockerfile
The LLM service uses a specialized `Dockerfile.gpu`.
- **Build Strategy**: Standard `gcloud builds submit` does not support `-f` for custom Dockerfiles. Renaming to `Dockerfile` or using a configuration file is mandatory.
- **Recommended Pattern (Windows/PowerShell)**: Use a dedicated `cloudbuild-llm.yaml` file to explicitly set the `-f Dockerfile.gpu` flag and configure `E2_HIGHCPU_8` for faster ML build cycles (see Section 9.6).

#### 5.1.2 Health Check & Dependency Verification
When using `python-slim` base images, the `HEALTHCHECK` instruction using `curl` requires manual installation of the `curl` package. Additionally, audio-processing backends (like MeetChi's) require libraries for `sndfile` and `ffmpeg` to avoid runtime import errors:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*
```
**Verification Insight**: In the Feb 2026 deployment, adding these specific libraries allowed the Backend service to transition from a consistent `container-failed-to-start` state (failing within 5-10 seconds) to a stable "Still creating/Propagating" state (extending past 2 minutes as expected for Cloud Run v2 stabilization).

### 5.2 Build Optimization & Monitoring

#### 5.2.1 Source Optimization (.gcloudignore)
To avoid multi-gigabyte uploads when running `gcloud builds submit`, a `.gcloudignore` file must be present in the project root.
- **Goal**: Exclude `node_modules`, `.cache`, `models/`, and other local artifacts.
- **Result**: Reduces the upload package from ~10GB (with models/nodes) to <50MB (code only), significantly speeding up the build cycle.

#### 5.2.2 Subdirectory Builds
If the root project remains too large (e.g., due to many sub-apps), use `gcloud builds submit` from specific service directories:
```powershell
# Navigate to service directory
cd apps/backend

# Build and tag with specific region and repository
gcloud builds submit --tag asia-southeast1-docker.pkg.dev/[PROJECT_ID]/meetchi/meetchi-backend:latest .
```
This restricts the "build context" upload to only the necessary files for that specific service, drastically reducing the initial archive upload time.
- **Verification (Feb 2026)**: Subdirectory submission reduced Backend context from **>1GB** to **1.9 MiB**, and LLM service context to **35 KB**.

#### 5.2.3 Build Monitoring & Cache Management
- **Persistence**: In Antigravity IDE, `command_status` can be used to poll build progress without blocking.
- **Cache Mismatches**: Docker layer caching may occasionally retain stale code versions even after local fixes.
- **Force Rebuild**: Use the `--no-cache` flag in `cloudbuild.yaml` or as a CLI argument to ensure every layer is rebuilt from current source.
  ```bash
  gcloud builds submit --config=cloudbuild-backend.yaml --no-cache
  ```

#### 5.2.4 Service-Specific Ignore Files
To ensure rapid builds for both LLM and Backend services, specialized ignore files should be placed in each subdirectory:
- **`apps/llm_service/.gcloudignore`**: Excludes huge `models/` (loaded from GCS instead) and `.venv/`.
- **`apps/backend/.gcloudignore`**: Excludes local `recording/`, `audio_files/`, and `.venv/`.

**Recommended Pattern for `.gcloudignore` and `.dockerignore`**:
```ignore
.venv/
venv/
__pycache__/
.git/
models/
audio_files/
recordings/
*.bin
*.pt
*.pth
```
Using these files reduces the "Build Context" upload from several gigabytes to ~2MB for the backend and ~35KB for the LLM service.

### 5.3 Artifact Registry Setup
Standardized on **Artifact Registry** as the successor to GCR. 
- **Common Repo**: `meetchi` (Docker format).
- **Location**: `asia-southeast1`.
- **Command**:
  ```bash
  gcloud artifacts repositories create meetchi --repository-format=docker --location=asia-southeast1 --description="MeetChi Docker images"
  ```
- **Path Pattern**: `[REGION]-docker.pkg.dev/[PROJECT_ID]/meetchi/[IMAGE_NAME]`
    - Example: `asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-llm-gpu:latest`
- **Permissions Required**: The Service Account running the build (Cloud Build or Compute Engine default) MUST have `roles/artifactregistry.writer` on this repository to push images.
- **Deployment Status (Active Feb 2026)**: 
    - **LLM Service**: Successfully deployed at `https://meetchi-llm-gpu-705495828555.asia-southeast1.run.app`. Currently returning **200 OK** on health checks with **GPU enabled** (L4) and **Gemini 2.5 Flash Lite** integration verified.
    - **Backend Service (Phase 5: Task Modernization)**: **✅ STABILIZED**. Migrated from Redis/Celery to **Google Cloud Tasks**. Final blockers (orphaned imports and fatal startup hooks) resolved.
    - **GPU Support**: Activated for `meetchi-llm-gpu` following quota approval. The service is now configured with 4 CPUs, 16GiB RAM, and 1x Nvidia L4 GPU.
    - **Gemini Integration**: Verified successful structured summarization via `/summarize` endpoint using Pydantic schemas. 
    - **Artifact Registry Fix**: Resolved `Permission Denied` on `uploadArtifacts` by explicitly granting `roles/artifactregistry.writer` to the Compute Engine default service account and ensuring regularized repository naming (`meetchi`).
    - **Web Frontend (Phase 6)**: **✅ PRODUCTION READY (v7)**. Optimized via multi-stage Docker build and Next.js `standalone` output. Accessible at `https://meetchi-frontend-705495828555.asia-southeast1.run.app`.
        - **UI Redesign (v4)**: Migrated to a modern landing page and dashboard with Indigo/Slate aesthetics and glassmorphic components.
        - **Full Integration (v5)**: Centralized `ApiClient` implemented for real-time health monitoring and dynamic meeting list retrieval.
        - **Final Configuration (v7)**: Finalized `cloudbuild.yaml` to inject `NEXT_PUBLIC_API_URL` (`https://meetchi-backend-wfqjx2j42q-as.a.run.app`) at build-time.
        - **Auth Stabilization**: Resolved "Server Error (500)" by configuring `AUTH_SECRET` and `AUTH_URL` environment variables via `gcloud run services update`.
        - **Workaround**: Used manual `gcloud run deploy` after automated Step #2 failed due to `roles/logging.logWriter` IAM constraints.
        - **Verification**: Verified healthy status for Backend, LLM GPU, and Frontend. Confirmed Google OAuth visibility on the `/login` page and verified `/api/auth/providers` returns the correctly configured Google provider.

- **Artifact Registry Verification (Verified Feb 2026)**: Confirmed existence and integrity of `meetchi-llm-gpu`, `meetchi-backend`, and `meetchi-frontend` repositories.
- **Resolution Strategy (Completed)**: 
    1. **Dependency Pruning**: Verified removal of GPU-heavy packages (v3).
    2. **Cascading Import Fix (v5/v6)**: Implemented conditional imports for `torch` and `torchaudio` across all submodules.
    3. **Circular Dependency Resolution**: Migrated `get_db`, `engine`, and `SessionLocal` from `main.py` to a standalone `app/database.py`.
    4. **Quota Management**: NVIDIA L4 GPU quota application submitted for `asia-southeast1`.
    - **Health Verification**: Confirmed healthy status via `/health` endpoint using PowerShell `Invoke-RestMethod`. LLM response verified as: `{"device": "cuda", "mock_mode": true, "status": "ready"}`.
    6. **Build Phase Corrections (Frontend)**: Installed missing `date-fns` and updated `tailwind.config.ts` darkMode to `"class"` for Tailwind v4 compatibility.
        - **Note**: Internal services (like LLM GPU) may present 403 Forbidden if `--allow-unauthenticated` is not enabled, which is the expected secure default for internal processing layers.

### 5.4 Lightweight Backend Requirements (`requirements.txt`)
To ensure compatibility with Cloud Run CPU and avoid binary conflicts, use this minimal coordination-only pattern:
```text
# Core Framework
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
python-multipart>=0.0.6
websockets>=11.0

# Database
sqlalchemy>=2.0.0
alembic>=1.11.0
psycopg2-binary>=2.9.0
asyncpg>=0.28.0

# Cloud Tasks (Coordination)
google-cloud-tasks>=2.15.0

# Audio handling (CPU processing)
pydub>=0.25.1
soundfile>=0.12.0
librosa>=0.10.0

# Decoupling: NO torch, whisperx, faster-whisper, or ctranslate2
```

### 5.5 Backend Fresh Build Configuration (`cloudbuild-backend.yaml`)
To resolve persistent startup failures where code fixes don't seem to apply, use this specialized build configuration:

```yaml
steps:
  # Build Backend image with no cache
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '--no-cache'
      - '-t'
      - 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest'
      - '.'
    dir: 'apps/backend'

  # Push Backend image
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest'

images:
  - 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest'

timeout: '3600s'

### 5.6 Build Performance Tuning
- **Machine Type**: For faster dependency installation (especially for C++ based audio libraries like `libsndfile`), use `machineType: 'E2_HIGHCPU_8'` in the `cloudbuild.yaml` options.
- **Region**: Ensure `asia-southeast1` is specified to minimize inter-region network latencies.

### 5.7 Manual Build Optimization (Feb 2026)
If `gcloud builds submit` encounters "retry budget exhausted" errors during the push phase despite correct permissions, use the `--machine-type` flag to provide more resources for compression and network throughput:
```powershell
gcloud builds submit --tag [TAG] --machine-type=e2-highcpu-8 --timeout=2400s .
```
This was found to resolve push hangs for heavy Python images (~1GB) by reducing CPU-bound compression bottlenecks during the Artifact Registry upload phase.
```

## 6. Manual Deployment (Alternative to Terraform)
While Terraform is the recommended method for infrastructure consistency, a manual `gcloud` workflow is supported for rapid debugging or specific resource bypass.

### 6.1 Database & Storage Setup
```bash
# Cloud SQL instance & database
gcloud sql instances create meetchi-db --tier=db-g1-small --region=asia-southeast1
gcloud sql databases create MeetChi --instance=meetchi-db

# Storage bucket
gcloud storage buckets create gs://$PROJECT_ID-meetchi-audio --location=asia-southeast1
```

### 6.2 Secret Management
Sensitive configuration is decoupled from the container images using Google Secret Manager:
- `meetchi-db-password`: PostgreSQL credentials.
- `meetchi-hf-token`: HuggingFace Auth (for WhisperX models).
- `meetchi-secret-key`: JWT signing key for the backend.
- `meetchi-gemini-api-key`: Google Gemini API Key for serverless summarization.

### 6.3 Deploying Services
```bash
# LLM GPU Service (with Zonal Redundancy Disabled)
# Note 1: Requires regional GPU quota of at least 3 units for UPDATES.
# Note 2: WORKAROUND for quota of 1: Delete the service first, then deploy fresh.
gcloud run deploy meetchi-llm-gpu \
  --image asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-llm:latest \
  --gpu 1 --gpu-type nvidia-l4 \
  --no-gpu-zonal-redundancy \
  --max-instances 1 --min-instances 0 \
  --memory 16Gi --cpu 4 --port 5000 \
  --execution-environment gen2 \
  --allow-unauthenticated \
  --region asia-southeast1 \
  --project $PROJECT_ID

# Backend Service (with GPU for ASR)
# Note: Requires regional MemAlloc quota of at least 48GiB (3x 16GiB) to succeed.
gcloud beta run deploy meetchi-backend \
  --image asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend \
  --gpu 1 --gpu-type nvidia-l4 \
  --no-gpu-zonal-redundancy \
  --memory 16Gi --cpu 4 \
  --add-cloudsql-instances $PROJECT_ID:asia-southeast1:meetchi-db \
  --region asia-southeast1
```

### 6.4 Gemini API Specifics (Serverless Intelligence)
If using the Gemini summarization engine (Phase 8), ensure the following:
1. **API Enablement**: The `Generative Language API` (`generativelanguage.googleapis.com`) must be manually enabled in your project's [API Library](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com).
2. **Project Verification**: Verify that your `GEMINI_API_KEY` belongs to the correct project (identified as **`project-51769b5e-7f0f-4a2f-80c`** in production).
   - **Pattern: Project ID Discrepancy**: During deployment, it was discovered that the intuitive project name (e.g., `meetchi-446907`) differed from the manifested Project ID. Browser orchestration was used to verify the correct ID by looking for the `meetchi-cloudrun` service account.
3. **Secret Store**: The key must be stored in Secret Manager as `meetchi-gemini-api-key`.
4. **✅ Verification**: Successfully deployed following individual Secret creation and `terraform.tfvars` persistence.

## 7. Cost Estimates & Optimization
Estimated monthly cost for a production stack in `asia-southeast1`:
- **Cloud Run (GPU)**: ~$150-240 (Depending on utilization; scaled to 0 when idle).
- **Cloud SQL**: ~$30 (Tier: db-g1-small).
- **Cloud Tasks**: $0 (First 1 million tasks/month are free).
- **Cloud Storage & Others**: ~$5-10.
- **Total**: Approx. **$185 - $280 / Month** (Saved ~$35-50/mo by removing Redis).

**Optimization**:
- `min_instances = 0`: Services scale down to zero when not in use to eliminate compute costs.
- `cpu-throttling`: Enabled for the backend to reduce billing during idle request-response cycles.

### 7.1 Service Cost Deep Dive
| Service | Tier | Purpose | Monthly Cost (Est.) |
|---------|------|---------|---------------------|
| **Cloud SQL (PostgreSQL)** | `db-g1-small` | Meeting storage, full-text search, user data. | $25 - $40 |
| **Cloud Run (GPU)** | 1x NVIDIA L4 | ASR and LLM inference. | $150 - $240 |
| **Google Cloud Tasks** | Serverless | Message queue for async processing. | $0 (Free Tier) |

**Cloud SQL Role**: Relying on PostgreSQL specific features like `TSVECTOR` for real-time meeting search. The `db-g1-small` tier remains the primary baseline cost. 
**Optimization Potential**: Switching to serverless DBs like **Firestore** or **Neon** could reduce costs to near-zero for low volumes.

### 7.2 Decommissioning Blueprint (Redis to Cloud Tasks)
1.  **Phase 1 (COMPLETED Feb 2026)**: Removed `google_redis_instance` from Terraform.
2.  **Enabled** `cloudtasks.googleapis.com` API.
3.  **Configured** Cloud Tasks queues for Transcription and Summarization.
4.  **Result**: Instant savings of ~$40/month.
5.  **Lesson Learned (The Ralph Loop)**: Terraform validation failures occurred due to dangling references. Resolution involved replacing `REDIS_URL` with `CLOUD_TASKS_QUEUE` and updating `depends_on` blocks.

## 8. Environment Prerequisites
Before deploying, ensure the following tools are installed and configured on your local machine:

### 8.1 Google Cloud SDK (gcloud CLI)
The `gcloud` CLI is required for authentication and service management.
- **Direct Download**: [GCP SDK Installer](https://cloud.google.com/sdk/docs/install)
- **Winget**: `winget install Google.CloudSDK`
- **Verification**: Run `gcloud --version`. Confirmed successful installation via `winget` on developer machines.

### 8.2 Terraform CLI
- **Winget**: `winget install HashiCorp.Terraform`
- **Verification**: Run `terraform version`. Note: Refresh PATH or restart terminal after winget installation.

## 9. AI-Assisted Deployment Workflow
To deploy MeetChi using an AI agent (like Gemini/Antigravity), follow this security-conscious workflow:

### 9.1 Local Authentication Required
The AI agent operates within a restricted sandbox and **cannot** directly access your GCP credentials. You must perform local authentication first:
```powershell
# Core GCP Authentication
gcloud auth login

# Application Default Credentials (for Terraform/SDKs)
gcloud auth application-default login

# Configure Target Project
gcloud config set project [YOUR_PROJECT_ID]
```

### 9.2 GCP API Enablement
Before running Terraform, specific Google Cloud APIs must be enabled. 
**Note**: `cloudresourcemanager.googleapis.com` must often be enabled first. If prompted with `Would you like to enable and retry? (y/N)?`, select `y` to proceed.

```powershell
# 1. Enable Resource Manager first
gcloud services enable cloudresourcemanager.googleapis.com

# 2. Enable Artifact Registry (Required before builds)
gcloud services enable artifactregistry.googleapis.com

# 2. Enable other core services
gcloud services enable `
  run.googleapis.com `
  sqladmin.googleapis.com `
  secretmanager.googleapis.com `
  cloudbuild.googleapis.com `
  containerregistry.googleapis.com `
  cloudtasks.googleapis.com
```

### 9.3 Terraform Variables (terraform.tfvars)
Create a `terraform.tfvars` file in the `terraform/` directory. The following template has been verified for the `asia-southeast1` production stack:

```hcl
# MeetChi GCP Deployment Configuration
# Project ID: project-51769b5e-7f0f-4a2f-80c

project_id    = "project-51769b5e-7f0f-4a2f-80c"
region        = "asia-southeast1" # Singapore (closest GPU-enabled to Taiwan)
db_password   = "your-secure-password"
hf_auth_token = "hf_..."
secret_key    = "..." # JWT Secret

# Docker Images (Artifact Registry) - Verified Feb 2026
backend_image     = "asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-backend:latest"
llm_service_image = "asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-llm-gpu:latest"

# GPU settings (disabled during initial deployment until quota approved)
gpu_enabled   = false
gpu_type      = "nvidia-l4"

# Scaling (Scale to zero when idle)
min_instances = 0
max_instances = 3

# Gemini API Key (for LLM summarization)
gemini_api_key = "AIzaSy..."

# GCS Model Loading (configured automatically in cloudrun.tf)
# GCS_MODELS_PATH = "gs://${var.project_id}-meetchi-audio/models"
```

### 9.4 Agent Interaction Model (Collaborative Deployment)
1. **Command Generation**: Provide the agent with your target configuration (from `terraform.tfvars`).
2. **Review & Approve**: The agent will propose `terraform` or `gcloud` commands. You must review and approve each execution in your terminal.
3. **Execution Options**:
    - **Step-by-Step**: Agent proposes individual commands (recommended for complexity).
    - **Script Generation**: Agent generates a `deploy.ps1` or `deploy.sh` for you to execute manually.

### 9.5 Initialization & Verification
After configuration, verify the environment with a successful initialization:
```powershell
terraform init
```
**Verification Checkpoint**:
- Backend: successfully initialized.
- Provider `google`: v5.45.2+ installed.
- Provider `google-beta`: v5.45.2+ installed.
- All plugins signed by HashiCorp.

#### 9.6 Deployment Operations (Sequence)
1. **Step 1: Resource Preparation (Manual/Model)**:
   Since containers are optimized for size, models must be uploaded to GCS first.
   ```powershell
   gcloud builds submit --config=cloudbuild-models.yaml
   ```
### 6.2 Building Images
The mono-repo structure requires building from specific subdirectories. However, for complex builds (like the GPU LLM service), using a dedicated `cloudbuild.yaml` in the project root is preferred to manage the context and custom Dockerfiles.

```bash
# Build Backend (Standard/CPU or with lazy GPU deps)
gcloud builds submit --tag asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest apps/backend

# Build LLM Service (GPU-Optimized)
# Option A: Targeted build with custom config
gcloud builds submit --config cloudbuild-llm.yaml --project $PROJECT_ID

# Option B: Quick rename (if no config file is desired)
cp apps/llm_service/Dockerfile.gpu apps/llm_service/Dockerfile
gcloud builds submit --tag [TAG] apps/llm_service
```

**cloudbuild-llm.yaml** (Verified Production Build):
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-llm:latest', '-f', 'Dockerfile.gpu', '.']
    dir: 'apps/llm_service'

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-llm:latest']

images:
  - 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-llm:latest'

options:
  machineType: 'E2_HIGHCPU_8'
  logging: CLOUD_LOGGING_ONLY

timeout: '3600s'
```
    *Ensure `.gcloudignore` is present in `apps/backend/` and `apps/llm_service/` before running these.*

#### 9.7 Cloud Build Identity Check (Critical)
In newer projects, granting permissions to the `@cloudbuild.gserviceaccount.com` account may not be sufficient. 
- **Check**: If a build fails with `403 Forbidden` on storage, verify if the log mentions `[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`.
- **Permission**: Ensure the **Compute Engine default service account** has the following roles:
    - `roles/storage.objectAdmin`: To resolve `403 Forbidden` on staging/artifacts buckets.
    - `roles/artifactregistry.writer` (or `repoAdmin`): To resolve "retries exhausted" push errors. **Critical Note**: A "Retry budget exhausted" error in `gcloud builds submit` is often a silent mask for `Permission Denied` on the `uploadArtifacts` action.
- **Remediation Note**: Granting these roles requires the performing user to have `roles/resourcemanager.projectIamAdmin` or `roles/owner` on the project.
- **Verification**: This pattern was successfully validated in February 2026 when granting these roles to the `705495828555-compute` account enabled the completion of both Backend and LLM/ASR service deployments to Artifact Registry.

3. **Step 3: Apply Infrastructure**:
   ```powershell
   terraform apply -auto-approve
   ```

4. **Step 4: Post-Apply (Initialization)**:
   - Run Alembic migrations (see Section 12.2).

## 10. Agentic Skills for Infrastructure
Experience shows that enabling specialized agent skills improves deployment reliability:
- **`terraform-skill`**: Provides deep context on module structure, CI/CD patterns, and security best practices for Terraform/OpenTofu.
- **`gcp-cloud-run`**: Specialized in serverless patterns, cold-start optimization, and GCP-specific resource configuration.
- **`google-ai-media`**: Useful for handling large audio artifacts and multi-modal context.

> **💡 Troubleshooting Tip**: If `npx skill-installer` fails (e.g., 404 or auth issues), skills can be manually installed by cloning the [Awesome Skills Repo](https://github.com/sickn33/antigravity-awesome-skills) and copying the desired directory into `.agent/skills/`.

## 11. Deployment Implementation Reference
A comprehensive [DEPLOYMENT.md](../../terraform/DEPLOYMENT.md) guide is available in the codebase, detailing:
- Terraform variable configuration.
- Step-by-step GPU quota application.
- Alembic migration procedures for Cloud SQL.
- Verification steps.

## 12. Post-Infrastructure Workflow
Once Terraform completes, the following steps are required to initialize the application:

### 12.1 Container Build & Push
Use the provided `cloudbuild.yaml` to build and push images to Artifact Registry:
```bash
gcloud builds submit --config=cloudbuild.yaml
```

### 12.2 Database Initialization (Alembic)
Since Cloud SQL is isolated in the VPC (or restricted by IP), migrations should be run via the **Cloud SQL Auth Proxy** or from a machine with authorized access:
```bash
# 1. Download and run Cloud SQL Auth Proxy
# ./cloud-sql-proxy [INSTANCE_CONNECTION_NAME]

# 2. Set LOCAL DATABASE_URL to the proxy address (usually localhost:5432)
alembic upgrade head
```

### 12.3 Service Activation
Final verification of the `/health` endpoints for both:
- `https://meetchi-backend-[hash].a.run.app/health`
- `https://meetchi-llm-gpu-[hash].a.run.app/health`
## 13. Externalized Model Preparation
To support multi-ASR and LLM features without 50GB container images, models are managed as GCS artifacts.

### 13.1 Automation with cloudbuild-models.yaml
The provided `cloudbuild-models.yaml` automates the following for a clean project:
- Downloads WhisperX large-v3.
- Downloads Taiwanese ASR (Whisper-Small).
- Downloads Pyannote segmentation and diarization (Requires `HF_TOKEN`).
- Uploads all to `gs://${PROJECT_ID}-meetchi-audio/models/`.

**Execution (Optimized)**:
Use the `--no-source` flag to skip uploading the local directory entirely, since the build steps download everything directly from HuggingFace Hub.
```powershell
gcloud builds submit --no-source --config=cloudbuild-models.yaml `
  --substitutions=_HF_TOKEN=hf_...,_PROJECT_ID=project-id
```

### 13.2 Manual Download Script
A backup Python script `scripts/download_models_to_gcs.py` is available for local execution:
```bash
python scripts/download_models_to_gcs.py --bucket gs://[PROJECT_ID]-meetchi-audio
```
**Prerequisites**: `pip install huggingface_hub gsutil`.

## 14. Automated Deployment Workflows
To streamline multi-step deployments and avoid manual approval for frequent `gcloud` or `terraform` operations, use custom workflows.

### 14.1 The gcp-deploy.md Pattern
A specialized workflow file `.agent/workflows/gcp-deploy.md` can be created with the `// turbo-all` hook.
- **Goal**: Automatically executes non-destructive infrastructure commands (init, plan, apply, build, deploy).
- **Safety**: Destructive operations (destroy, delete) are excluded from the turbo list to ensure human oversight.
- **Workflow Usage**: Mention `gcp-deploy` or use a dedicated mode to trigger the automated sequence.

### 14.2 Security: Command Whitelisting
To prevent the agent from repeatedly asking for permission to run `gcloud`, `terraform`, and `docker` commands, configure the Antigravity IDE settings:
- **Terminal Execution Policy**: Set to `Turbo / Always Proceed` or `Auto / Agent Decides`.
- **Allow List**: Add the following patterns to the IDE's allow list to enable automatic execution:
    - `gcloud*`
    - `gsutil*`
    - `terraform*`
    - `docker*`
- **Method**: Access settings via `Ctrl + ,` (Windows) or `Cmd + ,` (Mac) and search for "Terminal Execution Policy" or "Allow List".

## 15. Cloud Tasks Queue Implementation Details
As of the Feb 2026 migration, MeetChi employs two specialized queues to balance latency and throughput:

### 15.1 Transcription Queue (`meetchi-transcription-queue`)
*   **Purpose**: Processing ASR results immediately after meeting ends.
*   **Rate Limits**: 10 dispatches/second.
*   **Concurrency**: 5 simultaneous worker triggers.
*   **Retry Policy**: 5 attempts with exponential backoff.

### 15.2 Summarization Queue (`meetchi-summarization-queue`)
*   **Purpose**: Generating AI summaries and action items.
*   **Rate Limits**: 5 dispatches/second.
*   **Concurrency**: 3 simultaneous worker triggers (to protect LLM API quotas).
*   **Retry Policy**: 3 attempts.

## 16. Resource Decommissioning & Verification
When migrating away from managed instances (like Redis), verification is required to ensure billing has stopped.

### 16.1 Verification Checklist
1.  **Scope Verification**: 
    - **Phase 1 (Active)**: Only **Cloud Memorystore (Redis)** is intended for decommissioning. 
    - **Phase 2 (Target)**: **Cloud SQL** is targeted for future removal. **⚠️ DO NOT remove Cloud SQL in Phase 1 as it holds live meeting data.**
2.  **Terraform Destroy State**: Run `terraform plan` to ensure `google_redis_instance` is no longer managed.
3.  **CLI Verification**:
    ```powershell
    # Check for remaining Redis instances in the region (Should be EMPTY)
    gcloud redis instances list --region asia-southeast1
    
    # Check Cloud SQL (Should still contain 'meetchi-db' in Phase 1)
    gcloud sql instances list
    ```
4.  **Cloud Console Audit**: Manually inspect the **Memorystore** dashboard to confirm `meetchi-redis` is removed. Verify **Cloud SQL** remains active and healthy.

### 16.3 Legacy Deployment Configuration (Pre-Migration)
Before the serverless migration, the project utilized dedicated Cloud Build YAML files for different stack components:
- **`cloudbuild-backend.yaml`**: Configured with `E2_HIGHCPU_8` and a `3600s` timeout to handle heavy builds. It targeted `asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest`.
- **`apps/frontend/cloudbuild.yaml`**: Baked the `NEXT_PUBLIC_API_URL` environment variable at build time and triggered a direct `gcloud run deploy`.
- **`cloudbuild-models.yaml`**: Managed the externalized model downloads to GCS.

Historically, these were likely executed by a CI/CD service account or an administrative user with sufficient permissions to the `meetchi` Artifact Registry repository. 
- **Critical Pitfall**: During migration to Terraform, ensure the repository name in variable files matches the existing one. In the February 2026 migration, the stack shifted from a hardcoded `meetchi` to a variable `meetchi-repo`, causing push failures until the names were synchronized.
The current migration attempts to unify these under Terraform-managed infrastructure, revealing previously masked permission gaps.
