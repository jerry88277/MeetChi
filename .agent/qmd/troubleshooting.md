# Troubleshooting & Integration Testing

## 1. Integration Verification Result (Feb 1, 2026)
Local integration between React dashboard and FastAPI backend verified:
- **Core API**: ✅ Functional (Meetings/Settings CRUD).
- **ASR Service**: ✅ Functional (WhisperX real-time streaming).
- **CORS**: ✅ Configured for frontend/backend dev nodes.

## 2. Common Technical Issues
### 2.1 SQLAlchemy 2.0 Syntax
- **Problem**: Raw SQL failing in SQLAlchemy 2.0.
- **Solution**: Wrap raw SQL in `text()` from `sqlalchemy`.

### 2.2 Model Cold Starts
- **Problem**: WhisperX takes ~30s to load.
- **Solution**: Implement warm-up probes or Min Instances in Cloud Run.

### 2.3 Audio Setup
- **Sample Rate**: Ensure 16,000Hz PCM Mono.
- **FFmpeg**: CLI avoids `ffprobe` to improve environment compatibility.

### 2.4 Hallucinations
- **Issue**: Short, repetitive output or "hallucinated" thank-yous.
- **Fix**: Uses `HALLUCINATIONS_EXACT` blacklist in the backend pipeline.

### 2.5 CLI Command Not Found
- **Problem**: `gcloud` or `terraform` not recognized as a cmdlet.
- **Cause**: Tools newly installed via `winget` or `choco` are not in the current session's PATH.
- **Solution**: Restart the terminal session OR refresh the PATH manually for the current session:
  ```powershell
  # Refresh Path from Environment variables
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
  ```
- **Note**: For `gcloud` specifically, you can also use the absolute path if needed: `& "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.ps1"`

### 2.6 API Not Enabled
- **Problem**: `API [X.googleapis.com] not enabled on project [Y].`
- **Cause**: Terraform or manual commands cannot manage resources if the service API is disabled.
- **Solution**: Run `gcloud services enable X.googleapis.com`. See `deployment_and_infra.md` Section 9.2 for the full list of required APIs.

### 2.7 Permission Denied (403)
- **Problem**: `caller does not have permission` or `403 Forbidden`.
- **Cause**: Missing IAM role or using the wrong account.
- **Solution**: Run `gcloud auth login` and `gcloud auth application-default login` to ensure the correct credentials are active. Verify the project ID with `gcloud config list`.

### 2.8 Terraform Unsupported Block: node_selector
- **Problem**: `Error: Unsupported block type ... Blocks of type "node_selector" are not expected here.` in `google_cloud_run_v2_service`.
- **Cause**: The `google_cloud_run_v2_service` resource (unlike v1 `google_cloud_run_service`) does not use `node_selector` for GPU assignment.
- **Solution**: Remove the `node_selector` block. Simply adding the `nvidia.com/gpu` limit in the `resources` block of the container is sufficient to trigger GPU allocation in v2 Cloud Run.

### 2.9 Terraform/GCloud Interactive Prompts
- **Issue**: Command hangs or fails during automated script execution.
- **Cause**: GCP requires interactive confirmation for some API enablements or resource deletions.
- **Solution**: When prompted (e.g., `(y/N)?`), ensure the terminal is interactive or use the `-auto-approve` (Terraform) / `-q` (gcloud) flags.

### 2.10 Cannot Destroy Database
- **Problem**: `terraform destroy` fails with `Error: Error, failed to delete instance: [...] instance is currently deletion protected.`
- **Cause**: `deletion_protection = true` is set in `database.tf` to prevent data loss.
- **Solution**: Manually set `deletion_protection = false` in `database.tf`, run `terraform apply`, and then proceed with `terraform destroy`.

### 2.11 Provider Failed: [service].googleapis.com: no such host
- **Problem**: `Error: ... googleapis.com: no such host` during `terraform apply`.
- **Cause**: Often occurs during initial deployment if service APIs were recently enabled. The DNS for the API endpoint might not have fully propagated to the provider's execution context.
- **Solution**: Wait 60 seconds and retry `terraform apply`. The propagator delay is usually transient and resolves once the GCP service mesh recognizes the project's new API state.

### 2.12 Resource Already Exists (Terraform)
- **Problem**: `Error: Error creating [Resource]: googleapi: Error 409: The [Resource] '...' already exists.`
- **Cause**: The resource was created manually in the GCP Console, by a previous `gcloud` command, or during a Terraform run that timed out/interrupted before saving state.
- **Solution**: Use `terraform import` to manually bring the existing infrastructure into your state file. Replace `[PROJECT_ID]` with your project ID.
  
  **For Cloud SQL Instance**:
  ```powershell
  terraform import google_sql_database_instance.main projects/[PROJECT_ID]/instances/meetchi-db
  ```
  
  **For Redis Instance**:
  ```powershell
  terraform import google_redis_instance.celery projects/[PROJECT_ID]/locations/asia-southeast1/instances/meetchi-redis
  ```
  
  After importing, run `terraform apply` again. Terraform will now identify the existing resources and managed them.
### 2.13 GPU Quota Exceeded
- **Problem**: `Error: Error creating Service: googleapi: Error 400: Validation failed: nvidia.com/gpu: requested: 1 allowed: 0` or similar message stating quota is 0.
- **Cause**: Google Cloud Projects have 0 GPU quota by default in most regions. Cloud Run GPU is a separate quota (`NvidiaL4GpuAllocPerProjectRegion`).
- **Solution**: 
  1. Follow the quota application steps in `deployment_and_infra.md` Section 4.
  2. While waiting for approval (approx. 2 days), use the **CPU Fallback Strategy** (Section 2.14) to continue testing.

### 2.14 CPU Fallback Strategy (Temporary)
- **Problem**: Need to deploy and test the system while waiting for GPU quota.
- **Solution**: Modify `terraform/cloudrun.tf` to downgrade the GPU service to a CPU-only configuration.
  - **Provider**: Comment out `provider = google-beta`.
  - **Launch Stage**: Comment out `launch_stage = "BETA"`.
  - **Resources**: Replace 4 CPU / 16Gi / 1 GPU with 2 CPU / 8Gi / 0 GPU (comment out `nvidia.com/gpu`).
  - **Image**: Ensure the container image can run on CPU (the LLM service image typically supports CPU fallback but will be much slower).
- **Note**: The backend and frontend will function, but LLM/ASR processing times will increase significantly (e.g., 5-10x slower).
### 2.15 Image Not Found during Terraform Apply
- **Problem**: `Error: Error creating Service: googleapi: Error 400: The image ... was not found.`
- **Cause**: Terraform is trying to create a Cloud Run service using a container image that has not been pushed to Artifact Registry or GCR yet.
- **Solution**:
  1. **Build and Push first**: Run `gcloud builds submit --config=cloudbuild.yaml` (or your preferred build command) BEFORE running `terraform apply`.
  2. **Wait for propagation**: Sometimes it takes a few seconds for the image to be available to the Cloud Run API after pushing.
  3. **Check Visibility**: Ensure the image matches the project ID and you have permission to read it.
### 2.16 Cloud Build Timeout (Model Download)
- **Problem**: `Error: build step 0 "python:3.11-slim" failed: execution exhausted time limit`.
- **Cause**: Large models (Breeze 7B is ~15GB, Whisper is ~3GB) can exceed default Cloud Build timeouts or machine bandwidth.
- **Solution**: 
    1. Ensure `timeout: '7200s'` is set in `cloudbuild-models.yaml`.
    2. Use `machineType: 'E2_HIGHCPU_8'` (or higher) to improve network throughput.
    3. If it still fails, run the download steps in parallel or individually using the `--substitutions` flag to isolate specific models.

### 2.17 Startup Script Failures (GCS Download)
- **Problem**: Cloud Run service starts but fails health checks, logs show `gsutil: command not found` or `AccessDenied`.
- **Cause**:
    1. `google-cloud-cli` not installed in the Dockerfile.
    2. Missing permissions for the Cloud Run Service Account on the GCS bucket.
    3. `GCS_MODELS_PATH` environment variable is incorrect.
- **Solution**:
    1. **Installation**: Ensure the Dockerfile installs `google-cloud-cli` (see `Dockerfile.gpu` implementation).
    2. **Permissions**: Verify the `meetchi-cloudrun` service account has `roles/storage.objectViewer` on the bucket (Terraform's `google_project_iam_member.cloudrun_storage` usually handles this).
    3. **Logs**: Check Cloud Run logs for the specific `gsutil` output in `startup.sh`.

### 2.18 Massive Source Uploads (GBs) during Build
- **Problem**: `gcloud builds submit` takes forever and shows "Creating temporary archive of ... totalling X.X GiB".
- **Cause**: The command is archiving and uploading local `models/`, `node_modules/`, or large audio recordings.
- **Solution**: 
    1. Create a `.gcloudignore` file in the root directory and add large directories.
    2. For `cloudbuild-models.yaml`, use the `--no-source` flag if the script does not depend on local files.
    3. **Subdirectory Submission**: Instead of submitting from the root `.`, run the command targetting a specific app folder: `gcloud builds submit --tag [TAG] apps/[SERVICE_NAME]`. This drastically reduces the scanner scope. In Feb 2026 testing, this reduced Backend context to **1.9 MiB** and LLM context to **35 KB**.

### 2.19 Model Path Formatting in Terraform
- **Problem**: `GCS_MODELS_PATH` appears as `gs://${var.project_id}-meetchi-audio/models` in logs instead of the actual project ID.
- **Cause**: Using single quotes or incorrect interpolation in Terraform or shell scripts.
- **Solution**: Ensure double quotes are used in Terraform for variable interpolation: `"gs://${var.project_id}-meetchi-audio/models"`.

### 2.20 403 Forbidden during Build Submission (Service Account Mismatch)
- **Problem**: `ERROR: (gcloud.builds.submit) INVALID_ARGUMENT: could not resolve source: googleapi: Error 403: [PROJECT_NUMBER]-compute@developer.gserviceaccount.com does not have storage.objects.get access`.
- **Cause**: 
    1. **Identity Mismatch**: In newer Google Cloud projects (created after mid-2023), Cloud Build defaults to using the **Compute Engine default service account** (`[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`) instead of the legacy `@cloudbuild` account.
    2. **Missing Permissions**: The Compute Engine account often has the 'Editor' role but may lack granular `storage.objects.get` permissions on the automatically created staging bucket (e.g., `gs://[PROJECT_ID]_cloudbuild`).
- **Solution**:
    1. **Identify the exact account**: Check the error message (e.g., `705495828555-compute@developer.gserviceaccount.com`).
    2. **Find Project Number**: `gcloud projects describe [PROJECT_ID] --format="value(projectNumber)"`
    3. **Grant Admin Access to the bucket**:
       ```bash
       SA_EMAIL="[PROJECT_NUMBER]-compute@developer.gserviceaccount.com"
       gcloud projects add-iam-policy-binding [PROJECT_ID] \
           --member="serviceAccount:$SA_EMAIL" \
           --role="roles/storage.objectAdmin"
       ```
    3. **Existing Bucket Check**: If the bucket already exists but access is denied, use `gsutil iam ch serviceAccount:$SA_EMAIL:objectAdmin gs://[PROJECT_ID]_cloudbuild`.

### 2.21 Subdirectory Upload still Large
- **Problem**: Running `gcloud builds submit` from a subdirectory still archives gigabytes of data.
- **Cause**: The `.gcloudignore` file is in the root, but the build is being run from inside the subdirectory where no ignore file exists.
- **Solution**: Copy or create a `.gcloudignore` specifically inside the subdirectory (e.g., `apps/llm_service/`) to ensure `.venv` and other large folders are excluded during the local archiving phase.

### 2.22 Transition to Artifact Registry (Deprecated GCR)
- **Problem**: `gcloud builds submit` fails with 403 or 404 when using `gcr.io` paths, or logs indicate Container Registry is deprecated.
- **Cause**: Google Cloud is moving towards Artifact Registry. Some newer projects or regions may have stricter requirements for repository existence.
- **Solution**:
    1. **Create Repository**: `gcloud artifacts repositories create [REPO_NAME] --repository-format=docker --location=asia-southeast1`.
    2. **Update Image Paths**: Transition from `gcr.io/[PROJECT]/[IMAGE]` to `[REGION]-docker.pkg.dev/[PROJECT]/[REPO]/[IMAGE]`.
    3. **Auth Check**: If pushing from local, run `gcloud auth configure-docker [REGION]-docker.pkg.dev`.

### 2.23 Service Account Permissions for Artifact Registry
- **Problem**: Cloud Run service fails to pull the image from Artifact Registry.
- **Cause**: Deployment might be using a default or custom service account that hasn't been granted the `Storage Object Viewer` or `Artifact Registry Reader` role on the specific repository.
- **Solution**: Grant `roles/artifactregistry.reader` to the Cloud Run service account:
  ```bash
  gcloud artifacts repositories add-iam-policy-binding [REPO_NAME] \
      --location=asia-southeast1 \
      --member="serviceAccount:[SA_EMAIL]" \
      --role="roles/artifactregistry.reader"
  ```

### 2.24 Bucket Creation 409 Conflict
- **Problem**: `ServiceException: 409 A Cloud Storage bucket named '...' already exists.`
- **Cause**: Attempting to create a bucket (e.g., `gs://[PROJECT_ID]_cloudbuild`) that is already globally or locally claimed.
- **Solution**: Skip creation and proceed directly to granting permissions on the *existing* bucket.
  ```bash
  gsutil iam ch serviceAccount:[SA_EMAIL]:objectAdmin gs://[PROJECT_ID]_cloudbuild
  ```

### 2.25 Build Error: No matching distribution found
- **Problem**: `ERROR: No matching distribution found for [PackageName]==[Version]`.
- **Cause**: The specified package version does not exist in PyPI or is incompatible with the base image's Python version/architecture. 
    - **Observed Cases**: 
        - LLM Service: `networkx==3.5` and `numpy==2.3.3` were requested.
        - Backend Service: `cfgv==3.5.0` and `scikit-learn==1.7.2` were requested.
    - **Context**: As of Feb 2026, these were "future-dated" or non-existent versions on standard PyPI mirrors.
- **Solution (Best Practice)**:
    1. **Use Flexible Version Ranges**: Instead of hard-coding exact versions, use ranges (e.g., `networkx>=3.0,<4.0`, `numpy>=1.24.0,<2.0.0`, or `cfgv>=3.0.0`). This prevents build breaks when specific minor versions are unlisted or incompatible.
    2. **Verify on PyPI**: Use `pip index versions [PackageName]` or search [PyPI](https://pypi.org/) for the latest stable release.
    3. **Architecture Consistency**: Ensure the Dockerfile base image (e.g., `nvidia/cuda`) uses a Python version compatible with the packages (typically Python 3.10+ for modern LLM libraries).

### 2.26 Tool Error: unsupported mime type text/plain; charset=utf-16le
- **Problem**: `view_file` or other agent tools fail with `unsupported mime type text/plain; charset=utf-16le`.
- **Cause**: The file was created in PowerShell using `>` or `Set-Content` without specifying UTF-8 encoding. Windows PowerShell (v5.1 and earlier) defaults to UTF-16LE for many operations.
- **Solution**: 
    1. **Read with Terminal**: Use `Get-Content` (PowerShell) or `cat` (Bash) which handles different encodings better than the `view_file` tool.
    2. **Convert to UTF-8**: Use PowerShell to re-save the file with standard encoding:
       ```powershell
       (Get-Content file.txt) | Set-Content -Encoding utf8 file.txt
       ```
    3. **IDE Standardization**: Ensure the IDE (VS Code) is set to save new files as `UTF-8`.

### 2.27 Artifact Registry Push Failure (Retries Exhausted)
- **Problem**: `ERROR: failed to push because we ran out of retries` after a successful build step.
- **Cause**: The Service Account performing the build (e.g., `cloudbuild.gserviceaccount.com` or `compute@developer.gserviceaccount.com`) lacks `roles/artifactregistry.writer` on the target repository.
- **Solution**:
    1. **Identify Repository**: Ensure the Artifact Registry repository (e.g., `meetchi`) exists in the target region.
    2. **Grant Permissions**: Identify the project number using `gcloud projects describe [PROJECT_ID] --format="value(projectNumber)"`.
       ```bash
       gcloud artifacts repositories add-iam-policy-binding [REPO_NAME] \
           --location=[REGION] \
           --member="serviceAccount:[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com" \
           --role="roles/artifactregistry.writer"
       
       # Also grant to Compute Engine default SA if used as the build identity
       gcloud artifacts repositories add-iam-policy-binding [REPO_NAME] \
           --location=[REGION] \
           --member="serviceAccount:[PROJECT_NUMBER]-compute@developer.gserviceaccount.com" \
           --role="roles/artifactregistry.writer"
       ```
    3. **Regional Matching**: Ensure the `--tag` used in `gcloud builds submit` matches the region of the repository (e.g., `asia-southeast1-docker.pkg.dev`).

### 2.28 Legacy Requirements Conflict (Future-dated versions)
- **Problem**: Build fails repeatedly on different packages despite fixing them one by one.
- **Cause**: The `requirements.txt` was likely generated in an environment with non-standard pre-releases or future-dated metadata (e.g., `torch==2.8.0`, `numpy==2.3.3`).
- **Solution**: Re-create a **Minimal Core Requirements** file (`requirements.txt`) using established stable version ranges instead of pinning to exact versions that may be non-existent in the target build environment. Focus on core functional dependencies (FastAPI, SQLAlchemy, Transformers, etc.) and let pip resolve the sub-dependencies.

### 2.29 Long Service Creation Time (Terraform)
- **Problem**: `google_cloud_run_v2_service` stays in "Still creating..." for 2-5 minutes.
- **Cause**: Cloud Run v2 services, especially those with many environment variables, secrets, and large images (like MeetChi's 1.5GB+ GPU images), can take significantly longer to initialize and propagate than v1 services. In Feb 2026, `llm_gpu` was observed taking over **3 minutes** for initial creation, with the `backend` service also taking **over 2 minutes and 20 seconds** to stabilize.
- **Solution**: Do not interrupt the `terraform apply` command. If it times out, wait 60 seconds and run `terraform apply` again; the service will likely be in a "Partial" or "Ready" state and Terraform will pick it up (or you can use `terraform import`).
### 2.30 Backend Container Failed to Start (Missing System Libraries)
- **Problem**: Cloud Run service shows `container-failed-to-start` or logs indicate errors related to audio processing (e.g., `sndfile library not found` or `ffmpeg: command not found`).
- **Cause**: Backend services performing audio manipulation often require OS-level libraries that are not included in standard `python-slim` images.
- **Solution**: Update the Backend `Dockerfile` to include essential system dependencies:
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      git \
      ffmpeg \
      libsndfile1 \
      curl \
      && rm -rf /var/lib/apt/lists/*
  ```

### 2.31 Port Mismatch vs Dockerfile CMD
- **Problem**: Cloud Run service fails to start or health checks consistently fail despite the application running locally.
- **Cause**: The container port configured in Terraform (e.g., 8000) does not match the port the application is listening on in the `CMD` instruction of the Dockerfile.
- **Solution**: 
  1. **Terraform**: Ensure `containers.ports.container_port = 8000`.
  2. **Dockerfile**: Ensure `CMD` specifies the same port: `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
  3. **Env Var**: Cloud Run sets a `$PORT` environment variable; ideally, the application should listen on that variable, but hardcoding to 8000 (matching Terraform) is a valid alternative.

### 2.32 Build Context Too Large (>1GB) / Upload Timeout
- **Problem**: `gcloud builds submit` hangs at "Creating temporary archive" or times out during the initial upload phase.
- **Cause**: 
    1. Running the build from the project root without a strict `.gcloudignore`. In Feb 2026, a root-level submission attempted to archive **7.8 GiB** of data.
    2. Submitting from a subdirectory that has been used for local development/testing without cleaning up transient files or having a local `.gcloudignore`.
- **Solution**: 
  1. **Subdirectory Builds**: Run the build from the specific service directory (e.g., `apps/backend`) instead of the root. This reduced Backend context size to **1.9 MiB**.
  2. **Cleanup**: Delete local `.venv/`, `node_modules/`, and `__pycache__/` before submission if not ignored.
  3. **Strict .gcloudignore**: Ensure the ignore file is present in the *directory from which you are submitting the build*.

### 2.33 Python Syntax Error: Nested f-string Quotes
- **Problem**: Cloud Run service fails with `Container called exit(1)` and logs show `SyntaxError: invalid syntax` pointing to an f-string.
- **Cause**: Using the same type of quotes (single or double) inside an f-string's expression without escaping or alternating.
    - **Example (Fail)**: `logger.info(f"Executing: {" ".join(cmd)}")` -> The inner double quotes terminate the f-string prematurely.
- **Solution**: Alternate quote types or use triple quotes.
    - **Fix 1 (Alternate)**: `logger.info(f"Executing: {' '.join(cmd)}")` (Single quotes inside double quotes).
    - **Fix 2 (Triple Quotes)**: `logger.info(f"""Executing: {" ".join(cmd)}""")`.
- **Context**: This error was observed during the Feb 2026 deployment of the MeetChi backend logic in `app/tasks.py`.

### 2.34 Debugging Methodology: Investigating Container Failures
- **Problem**: Terraform reports `container-failed-to-start` but provides no details on *why* (e.g., whether it was a port issue, a missing library, or a syntax error).
- **Solution**: Use the Google Cloud Logging CLI to pull the raw container output:
  ```powershell
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=[SERVICE_NAME]" --limit=50 --format="value(textPayload)"
  ```
- **Pattern**: 
  1. Check for **Missing Libraries**: Look for `ImportError` or `command not found`.
  2. Check for **Syntax errors**: Look for `SyntaxError: invalid syntax` and tracebacks.
  3. Check for **Port Binds**: Look for "Uvicorn running on http://0.0.0.0:[PORT]". If the port doesn't match Terraform (default 8080 vs project's 8000), refer to Section 2.31.

### 2.35 Stale Log Errors / Image Caching
- **Problem**: Logs show an error (e.g., a syntax error) that has been confirmed fixed in the local source and successfully rebuilt/pushed as `:latest`.
- **Cause**: 
    1. **Logging Latency**: `gcloud logging read` might return logs from a previous, crashed revision. Check the timestamp or revision name in the logs.
    2. **Cloud Build Cache**: Docker layers for dependencies or even code might be reused if the build system doesn't detect the delta or if it's using an aggressive caching policy.
    3. **Image Pinning**: Cloud Run services often pin to a specific image digest. If Terraform or `gcloud` doesn't detect a change in the tag string (always `:latest`), it may not trigger a fresh pull of the new digest.
- **Solution**: 
    1. **Force Rebuild (No-Cache)**: Use a `cloudbuild.yaml` with the `--no-cache` flag to guarantee a fresh build:
       ```yaml
       steps:
         - name: 'gcr.io/cloud-builders/docker'
           args: ['build', '--no-cache', '-t', 'IMAGE_URL', '.']
       ```
    2. **Explicit Revision**: Force a new revision with `gcloud run deploy [SERVICE] --image=[IMAGE]:latest`.
    3. **Digest Usage**: Use the specific image digest (e.g., `image@sha256:...`) in Terraform to guarantee the exact version.

### 2.36 Revision Creation Failure (Startup Crash)
- **Problem**: `gcloud run deploy` or `terraform apply` fails with "Exit code: 1" at the "Creating Revision" or "Routing Traffic" step.
- **Cause**: The container successfully pulled but crashed during its initialization/startup phase. 
    - **Observed Case**: A **Python SyntaxError** at the module level (e.g., in `tasks.py` which is imported early) causes the app to exit instantly, preventing the health check endpoint from even becoming available.
- **Solution**: Immediately check logs using Section 2.34. Filter by the very latest timestamp. Look for tracebacks that occur before the "Uvicorn running" message.
- **Observed Failure (Feb 2026)**: Even after fixing a primary SyntaxError and forcing a fresh build (`v2`) with `--no-cache`, the container may still fail with `container-failed-to-start`. This indicates the "Stale Revision" issue was bypassed, but a secondary blocker (e.g., database connection timeout, missing environment variables for Redis, or internal package initialization failure) is now the primary bottleneck.

### 2.37 UnicodeDecodeError during Local Scripts (UTF-8 vs CP950/Windows)
- **Problem**: Running Python diagnostic scripts (e.g., `ast.parse(open('file.py').read())`) fails with `UnicodeDecodeError: 'cp950' codec can't decode byte...`.
- **Cause**: Windows systems with Traditional Chinese locales default to the `cp950` encoding for `open()`, which fails on UTF-8 files containing Chinese comments or specific symbols.
- **Solution**: Explicitly set the encoding when reading files in scripts: `open('file.py', encoding='utf-8')`.

### 2.38 Monitoring Heavy Image Pushes (Artifact Registry)
- **Observation**: During `gcloud builds submit` or Cloud Build logs, the push phase may seem to "pause" or show partial progress (e.g., `8/9 layers pushed`, `e50a58335e13: Waiting`).
- **Explanation**: ML-heavy images (like the Backend v2 with `torch`) contain very large layers (~900MB). Artifact Registry pushes these in segments. The "Waiting" status for a specific hash typically indicates the largest layer is currently being uploaded and compressed.
- **Insight**: 
    - **Timing**: A 1GB layer can take 2-4 minutes to push depending on the build machine's egress.
    - **False Positive**: Do not assume the build has hung unless there is no progress for >10 minutes.
    - **Optimization**: Standardize on a base image that already contains `torch` if build frequency is high, reducing the delta that needs to be pushed per revision.

### 2.39 ImportError: ctranslate2._ext (GPU Libraries on Cloud Run CPU)
- **Problem**: Container fails to start (`container-failed-to-start`) with `ImportError: libctranslate2...: cannot enable executable stack as shared object requires: Invalid argument`.
- **Cause**: The application (or a dependency like `faster-whisper` or `whisperx`) is attempting to import `ctranslate2`, which requires specific GPU-optimized extensions or has binary incompatibilities with the Cloud Run CPU environment's security policies (executable stack).
- **Observed Case (Feb 2026)**: The backend service incorrectly included `whisperx` in `requirements.txt`. Early imports in the application tree (including in the `uvicorn` startup sequence) triggered the crash before reaching any application code.
- **Solution**: 
    1. **Decouple Concerns**: Move all ASR/ML processing to a dedicated GPU-enabled service (e.g., `meetchi-llm-gpu`).
    2. **Prune Requirements**: Remove `whisperx`, `faster-whisper`, `pyannote.audio`, and `ctranslate2` from the Backend's `requirements.txt`.
    3. **Deferred Imports**: If a library is needed only for optional scripts, use inside-function imports to prevent startup crashes.

### 2.40 ModuleNotFoundError: No module named 'torch' (Lightweight Backend Migration)
- **Problem**: Container fails to start with `ModuleNotFoundError: No module named 'torch'` despite having pruned `torch` from `requirements.txt`.
- **Cause**: The application source code contains top-level imports (e.g., `import torch` at the top of a file) that are executed during the module loading phase (e.g., in `app/main.py` or files it imports like `app/vad.py`). 
- **Observed Case (Feb 2026)**: In the transition to Backend v3, dependencies were removed from Docker but the `app/vad.py` file still contained `import torch` to support a Silero VAD fallback. This caused the container to crash immediately upon startup.
- **Solution**: 
    1. **Dynamic Imports**: Move ML imports inside the functions or classes where they are actually used.
    2. **Conditional Logic**: Surround imports with `try...except ImportError` blocks.
    3. **Cleanup**: Completely remove any VAD or ASR logic from the Backend that relies on heavy ML libraries.

**Implementation Reference (Conditional Import Pattern)**:
```python
# app/vad.py
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

class VADAudioBuffer:
    def __init__(self, ...):
        if TORCH_AVAILABLE:
            # Load Silero VAD
            self.model, _ = torch.hub.load(...)
        else:
            # Fallback to Energy VAD
            self.use_silero = False
```

### 2.41 ModuleNotFoundError: torch in Scripts (Cascading Imports)
- **Problem**: Container still fails with `ModuleNotFoundError: torch` after fixing the primary app files (e.g., `vad.py`). 
- **Cause**: The main application (`app/main.py`) imports helper scripts or legacy code (e.g., `from scripts.transcribe_sprint0 import ...`) that contain top-level ML imports. 
- **Solution**:
    1. **Trace Imports**: Check logs to see which file triggered the error during module loading.
    2. **Placeholder Logic**: Wrap script imports in `try...except` and provide dummy/placeholder functions if the script's features are optional in the current environment.
    3. **Isolation**: Avoid importing ML-dependent scripts in the main API entrypoint if those scripts are only intended for worker processes or specific GPU environments.
### 2.42 Missing/Empty Logs During Startup Failure
- **Problem**: Cloud Run reports `container-failed-to-start`, but commands like `gcloud logging read ... textPayload:Traceback` return no results.
- **Cause**: 
    1. **Restrictive Filters**: The error may not contain the exact string "Traceback" or "Error" in the `textPayload` (e.g., if it's a `libc` or `sh` level crash).
    2. **JSON Payloads**: Some structured logs put the message inside `jsonPayload`, which simple `textPayload` filters miss.
    3. **Buffered Output**: If the container crashes extremely fast, the log buffer may not flush to Cloud Logging before the instance is terminated.
- **Solution**:
    1. **Broader Search**: Remove the `textPayload` filter and search by `resource.labels.service_name` and `resource.labels.revision_name` with a short time window.
    2. **Format Change**: Use `--format="yaml"` or `--format="json"` to see the full log entry, including `jsonPayload` or `stderr`.
    3. **Entrypoint Debugging**: If logs are still empty, wrap the container entrypoint in a shell script that redirects all output: `exec python main.py 2>&1 | tee /tmp/startup.log`.

### 2.43 Circular Import with FastAPI Entrypoint
- **Problem**: `ImportError: cannot import name 'get_db' from partially initialized module 'app.main'`.
- **Cause**: The application entrypoint (`app/main.py`) performs two conflicting roles: 
    1. It declares database machinery (`engine`, `SessionLocal`, `get_db`).
    2. It imports and registers API routers (`app.include_router(api_router)`).
    If a router module (e.g., `app/routes/search_org.py`) needs to import `get_db`, it imports `app.main`, which hasn't finished initializing its router imports, creating a loop.
- **Solution**: 
    1. **Dependency Inversion**: Move all database creation and the `get_db` dependency provider to a standalone `app/database.py`.
    2. **Reference Update**: Update all route modules and the main app to import from the new module: `from app.database import get_db`.

### 2.44 Pydantic v2 Migration: regex vs pattern
- **Problem**: `pydantic.errors.PydanticUserError: 'regex' is removed. use 'pattern' instead`.
- **Cause**: Pydantic v2 renamed the `regex` parameter to `pattern` in `Field` and other validators.
- **Solution**: Replace `regex=r'...'` with `pattern=r'...'` in the affected Pydantic model.
- **Observed Case (Feb 2026)**: Occurred in `apps/backend/app/routes/search_org.py` for the `color` field in `TagCreate`.

### 2.45 Local Backend Verification (PowerShell)
- **Problem**: Confirming the backend is truly operational before building it for Cloud Run.
- **Verification Commands**:
  1. **Start Backend**: `cd apps/backend; .venv\Scripts\activate; uvicorn app.main:app --reload`
  2. **Wait for Startup**: Ensure logs show `Application startup complete`.
  3. **Health Check**:
     ```powershell
     Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing | Select-Object -ExpandProperty Content
     ```
- **Success Criteria**: Response must include `{"status":"healthy","service":"meetchi-backend"}`.

### 2.46 Alembic: Could not parse SQLAlchemy URL
- **Problem**: `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from given URL string`.
- **Cause**: In `alembic.ini`, the `sqlalchemy.url` field is empty or improperly formatted.
- **Solution**: 
    1. **Dynamic URL Injection**: Modify `alembic/env.py` to read the database URL from an environment variable instead of relying on the static `.ini` file.
    ```python
    # alembic/env.py
    import os
    config = context.config
    database_url = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")
    config.set_main_option("sqlalchemy.url", database_url)
    ```
    2. **Security Advantage**: This avoids hardcoding credentials in `alembic.ini`.

### 2.47 UndefinedColumn: column "folder_id" does not exist
- **Problem**: `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "folder_id" of relation "meetings" does not exist`.
- **Cause**: The SQLAlchemy models have been updated to include a new field (`folder_id`), but the physical database schema hasn't been migrated to reflect this change.
- **Solution**: Run the pending migrations. Ensure `alembic.ini` is correctly configured (see Section 2.46) and execute:
  ```powershell
  .venv\Scripts\python.exe -m alembic upgrade head
  ```

### 2.48 Alembic: Multiple head revisions are present
- **Problem**: `FAILED: Multiple head revisions are present for given argument 'head'`.
- **Cause**: This occurs when different branches have created migrations that both claim the same parent, or when migrations are manually created/edited without a clear linear history.
- **Solution**: 
    1. **Identify Heads**: Run `.venv\Scripts\python.exe -m alembic heads`.
    2. **Merge Heads**: Create a merge revision to join the divergent paths:
       ```powershell
       .venv\Scripts\python.exe -m alembic merge heads -m "merge_divergent_heads"
       ```
    3. **Upgrade**: Run `alembic upgrade head` again. This will apply both paths and then the merge script.

### 2.49 Alembic: NotImplementedError (Batch Mode / SQLite Fallback)
- **Problem**: `NotImplementedError: ... the batch mode feature which allows for SQLite migrations using a copy-and-move strategy`.
- **Cause**: This usually occurs when Alembic defaults to **SQLite** (often due to a fallback in `env.py` when `DATABASE_URL` is missing) while trying to execute migrations with **Foreign Key constraints** or other advanced features that SQLite's `ALTER TABLE` cannot handle directly.
- **Diagnostic**: Check the logs for `Context impl SQLiteImpl`. If you expected PostgreSQL, the `DATABASE_URL` environment variable is not being passed to the Alembic process.
- **Solution**: 
    1. **Alembic Dotenv Loading**: Explicitly call `load_dotenv()` in `alembic/env.py`.
    2. **Application Dotenv Loading**: Ensure `load_dotenv()` is also called in the module where the engine is created (e.g., `app/database.py`). Without this, even if Alembic is fixed, the running FastAPI app might still default to a local SQLite file, leading to "Missing Column" errors when the app looks at its private SQLite DB while the user expects it to be using the central PostgreSQL DB.
    3. **PowerShell Example**:
       ```powershell
       $env:DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"
       .venv\Scripts\python.exe -m alembic upgrade head
       ```

### 2.51 Manual Schema Patching (The Pragmatic Fix)
- **Problem**: Alembic upgrade fails due to complex constraint logic (e.g., `NotImplementedError` in SQLite or `DuplicateObject` in Postgres) that is difficult to fix via standard migration paths.
- **Cause**: Rapid development desynchronizes the migration history from the physical database state.
- **Solution**: 
    1. **Stamp**: Use `alembic stamp <target_revision>` to force Alembic to believe the DB is at a certain version.
    2. **Manual SQL**: Execute a Python script using SQLAlchemy `text()` or raw SQL to add the missing columns/tables directly.
- **Pragmatic Script Pattern**:
  ```python
  from app.database import engine
  from sqlalchemy import text
  with engine.connect() as conn:
      conn.execute(text('ALTER TABLE meetings ADD COLUMN IF NOT EXISTS folder_id VARCHAR(36)'))
      # Add search_vector for PostgreSQL Full Text Search
      conn.execute(text('ALTER TABLE meetings ADD COLUMN IF NOT EXISTS search_vector tsvector'))
      conn.execute(text('CREATE INDEX IF NOT EXISTS idx_meetings_search_vector ON meetings USING GIN(search_vector)'))
      conn.commit()
  ```
- **Observed Case (Feb 2026)**: Used to manually add `folder_id`, `search_vector`, and the `folders`/`tags` tables when Alembic's initial migration conflicted with existing ENUMs and complex FTS schema requirements.

### 2.52 UndefinedColumn: column "search_vector" does not exist
- **Problem**: `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "search_vector" of relation "meetings" does not exist`.
- **Cause**: The application uses PostgreSQL Full Text Search (FTS), which requires a `tsvector` column. This column was part of a migration that couldn't be applied due to previous desynchronization.
- **Solution**: Manually add the column and its GIN index to the PostgreSQL database:
  ```sql
  ALTER TABLE meetings ADD COLUMN IF NOT EXISTS search_vector tsvector;
  CREATE INDEX IF NOT EXISTS idx_meetings_search_vector ON meetings USING GIN(search_vector);
  
  -- Also for segments if used for search
  ALTER TABLE transcript_segments ADD COLUMN IF NOT EXISTS search_vector tsvector;
  CREATE INDEX IF NOT EXISTS idx_segments_search_vector ON transcript_segments USING GIN(search_vector);
  ```

### 2.50 Alembic: PostgreSQL Enum "already exists" (DuplicateObject)
- **Problem**: `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.DuplicateObject) type "meetingstatus" already exists`.
- **Cause**: This occurs when an Alembic migration tries to create a custom PostgreSQL type (ENUM) that was already created by the application's ORM (e.g., `Base.metadata.create_all(engine)`) or a previous manual schema setup.
- **Solution**: 
    1. **Synchronization**: If the schema is already correct but the migration history is missing, use `alembic stamp` to mark the current state as "up to date":
       ```powershell
       .venv\Scripts\python.exe -m alembic stamp <revision_id>
       ```
    2. **Idempotent Migrations**: Wrap the ENUM creation in a check (if supported by the dialect) or manually handle the exception if the migration is intended to be re-runnable.

### 2.53 Short Speech Segments Discarded (Gating Issues)
- **Problem**: Valid speech (especially short English phrases or quiet interjections) is recognized by the ASR model but never recorded in the database or UI.
- **Cause**: The system implements multiple layers of duration and energy filtering to suppress background noise hallucinations:
    1. **VAD Level (`vad.py`)**: `flushed_duration < min_speech_duration` (usually 0.5s) or `flushed_rms < SILENT_RMS_THRESHOLD` (0.0001).
    2. **Orchestration Level (`main.py`)**: A secondary check (e.g., `if duration < 1.0:`) may block transcription entirely to avoid expensive ASR calls for noise.
    3. **Language Interaction**: Short segments in a non-primary language (e.g., English when set to `zh`) are more likely to be discarded as "no speech" by the model.
- **Solution**: 
    - Lower the `min_speech_duration` to 0.3s if the environment is relatively quiet.
    - Reduce or disable the secondary duration check in `main.py` if high-recall is prioritized over noise suppression.
    - Adjust `SILENT_RMS_THRESHOLD` if quiet speakers are being cut off.
    - Ensure correct language detection (see Section 2.55).

### 2.54 Hallucination Blacklist Side Effects
- **Problem**: Phrases that contain blacklisted characters/words are being cleared even if they are valid parts of a sentence.
- **Cause**: The `Received empty transcription from ASR... Clearing partial` log entry often indicates that the ASR output was caught by the "Hallucination Filter" (which clears exact matches of common noise like "喔", "嗯", or repetitive valedictions in alignment mode).
- **Solution**: 
    - Verify if the phrase triggering the filter is a common hallucination (e.g., "謝謝", "大家好").
    - Check the `Filtered hallucination (exact)` log to see precisely what word was caught.
    - Refine the blacklist in `app/main.py` or `transcribe_sprint0.py` to be less aggressive.

### 2.55 ASR Mixed Language Failure (The "We are the world" Problem)
- **Problem**: Phrases in one language (e.g., English) are completely ignored or return empty results while another language (e.g., Chinese) works fine.
- **Cause**: Explicitly setting the `language` parameter (e.g., `language='zh'`) in faster-whisper forces the model to interpret all audio through that language's lens. If the audio is in English, the model may return an empty string or garbled output, which is then often cleared by hallucination filters or duration gates.
- **Solution**: 
    - **Language Auto-Detection**: Set `language=None` in `model.transcribe()` to allow the model to detect the language per-segment.
    - **Initial Prompts**: Use a multilingual prompt (e.g., "這是一段中英文混雜的對話。") to bias the model toward recognizing multiple languages.
    - **Frontend Config**: Ensure the client passes `language: null` or `"auto"` when mixed support is desired.
- **Environment Sensitivity (Feb 2026 Regression)**: In high-noise environments (e.g., a 12-person meeting room with external speakers and internal mics), `language=None` was found to perform significantly worse than explicitly set `language='zh'`. The auto-detection failed to yield output in scenarios where the fixed-language mode functioned.
- **Recommendation**: Prioritize fixed-language stability in professional/noisy settings. If mixed support is required, use a high-quality multilingual prompt while keeping the primary language fixed.

### 2.56 Frontend-Backend Connection Loss (Graceful Recovery)
- **Problem**: When the backend restarts (e.g., due to a code update with `--reload` or a crash recovery), the frontend (Tauri client or Web Dashboard) may stop receiving updates or stay in a "zombie" state without notifying the user or attempting to reconnect.
- **Cause**: 
    - WebSocket connections do not automatically reconnect by default in most standard browser implementations.
    - If the backend is down during a `reconnect` attempt, the frontend might give up or hang.
    - Recording state in the frontend might become desynchronized with the backend's session state.
- **Current Observation (Feb 2026)**: During a live recording session, a backend reload caused the frontend to lose connectivity silently.
- **Tauri Architecture Specifics**: 
    - The React layer calls `invoke('start_audio_command')`.
    - The Rust layer opens a WebSocket to the Python backend.
    - If the Python backend drops, the Rust WebSocket closes, but unless the Rust side explicitly emits a Tauri event (e.g., `emit('connection-failed')`), the React layer continues to show `isRecording: true` while `transcript-update` events simply stop arriving.
- **Solution Strategy**:
    - **Rust-to-React Error Propagation (Implemented)**: Modified the Rust `audio_processor.rs` to emit a `backend-disconnected` event to the frontend when the ASR WebSocket disconnects or errors.
    - **Heartbeat Management**: Implement a client-side heartbeat (ping/pong) to detect silent connection drops within 3-5 seconds.
    - **Exponential Backoff Reconnection**: Use a library like `reconnecting-websocket` or a custom wrapper to attempt reconnection with increasing delays.
    - **UI Feedback (Implemented)**: Updated React `page.tsx` to listen for the `backend-disconnected` event. When triggered, the app displays an alert notification to the user and automatically resets the `isRecording` state to `false`.
    - **Auto-Reconnection (Implemented)**: Implemented a native Rust-side loop in `audio_processor.rs` using a `tokio` async task. The system caches the initial session configuration, detects stream drops via the writer task, and automatically performs logic-preserving handshakes with exponential backoff/retry (up to 10 attempts).
    - **UI Status Integration (Implemented)**: Added `backend-reconnecting` and `backend-reconnected` event listeners to the React frontend, allowing the UI to show a "Connecting..." status instead of simply stopping or alerting the user immediately.

### 2.57 Duplicate Script Lines in Alignment Mode
- **Problem**: When a user jumps sentences in the pre-defined script (e.g., skips sentence 2 and reads sentence 3), the UI repeatedly displays the English translation for sentence 3 every time a new ASR chunk matches it.
- **Cause**: The `alignment.rs` algorithm found the best fit at sentence 3 and returned its index every time, without checking if that specific sentence had already been shown.
- **Solution**: Added an `emitted_segment_ids` HashSet to the `ScriptEngine`.
    - Once a segment is matched and returned, its unique ID is added to the set.
    - Subsequent matches for the same ID are suppressed, forcing the UI to remain steady once a line is confirmed or wait for the *next* unique line to be reached.

### 2.58 HealthCheckContainerError (Startup Probe Failure)
- **Problem**: Cloud Run deployment fails with "The user-provided container failed the configured startup probe checks" or `HealthCheckContainerError`.
- **Cause**: The container starts but either:
    1.  Crashes immediately due to missing environment variables or library errors.
    2.  The application doesn't bind to the correct port (must listen on `0.0.0.0:$PORT`).
    3.  The `/health` endpoint is not reachable within the `initialDelaySeconds`.
- **Diagnosis (Feb 2026)**: After deploying Backend v6, the container failed to start despite a successful local run. Logs filtered by `severity>=ERROR` revealed `ModuleNotFoundError: No module named 'torch'`.
- **Root Cause**: While `app/vad.py` had conditional imports, `app/diarization.py` (imported in the chain) still contained an unconditional `import torch`. In the thin `python:3.10-slim` container used for the Backend (CPU-mode), `torch` is not installed to save space (~2GB).
- **Resolution**: Make `torch` and `torchaudio` imports conditional in all utility modules (`diarization.py`, `vad.py`) to ensure the serverless orchestration layer remains lightweight.
- **Verification Steps**:
    - Use `gcloud logging read "severity>=ERROR"` to catch early startup crashes.
    - Audit all submodules in the main app entrypoint for transitive dependency leaks (e.g., ML libraries in the management backend).

### 2.59 Next.js Cloud Build Failure: Module not found (Shadcn/Path Aliases)
- **Problem**: `npm run build` fails in Cloud Build with `Module not found: Can't resolve '@/components/ui/table'`.
- **Cause**: 
    1.  **Missing Component**: The shadcn UI component was not initialized or its file is missing from the `src/components/ui` directory.
    2.  **Path Alias Mismatch**: The `tsconfig.json` or `tailwind.config.ts` path aliases (e.g., `@/*`) are not correctly interpreted in the Docker build environment.
    3.  **Case Sensitivity**: Linux-based Cloud Build environments (unlike Windows dev) are case-sensitive. `Table.tsx` vs `table.tsx` will cause a failure.
- **Diagnosis (Feb 2026)**: In the MeetChi frontend, `src/components/ui/table.tsx` existed and had correct exports. Local `npm run build` revealed the error originated from `src/app/dashboard/meetings/page.tsx` line 14.
- **Solution**: 
    1.  Verify the file exists at `src/components/ui/table.tsx` (using `list_dir`).
    2.  Check for typos in the import path in the consuming file (e.g., `import { ... } from "@/components/ui/table"`).
    3.  Ensure the build machine can resolve `@/` via `tsconfig.json`.
    4.  If the file is present but still failing, verify the export structure matches the import (e.g., `export { Table, ... }` vs `export default Table`).

### 2.60 Build Context Upload Delay (Creating temporary archive)
- **Problem**: `gcloud builds submit` hangs for several minutes at "Creating temporary archive".
- **Cause**: The command is scanning and zipping `node_modules` or `.next` folders because a `.dockerignore` file is missing or improperly placed.
- **Solution**: 
    1.  Create a `.dockerignore` in the same directory as the `Dockerfile`.
    2.  Add `node_modules`, `.next`, and other build artifacts to the ignore file.
    3.  Confirm the archive size in the console (target: < 5MB for Next.js source).
### 2.61 Missing Dependency during Next.js Build (date-fns)
- **Problem**: Local or Cloud Build fails with `Module not found: Can't resolve 'date-fns'`.
- **Cause**: A component (e.g., meeting list or detail page) imports `date-fns` but it is missing from the `dependencies` section of `package.json`.
- **Solution**: 
    1.  Run `npm install date-fns` in the `apps/frontend` directory.
    2.  Check for other missing peer dependencies in the build log if the error persists.

### 2.62 Tailwind CSS Type Error (darkMode)
- **Problem**: `npm run build` fails with `Type '["class"]' is not assignable to type '["class", string]'`.
- **Cause**: Tailwind CSS v4 is stricter with the `darkMode` schema.
- **Solution**: Changed `darkMode: ["class"]` to `darkMode: "class"` in `tailwind.config.ts`. This resolved the type mismatch.

### 2.63 Cloud Build Failure despite Local Success (Missing Build Args)
- **Problem**: `gcloud builds submit` fails with `non-zero status: 1` during page generation, while local `npm run build` passes perfectly.
- **Cause**: The `Dockerfile` expects an `ARG` (e.g., `NEXT_PUBLIC_API_URL`) that is used during `npm run build`. If this argument is not passed via the CLI, the build process may fail if the application logic or Next.js static generation requires a valid value at compile time.
- **Solution**: 
    1.  Verify if the `Dockerfile` uses `ARG`.
    2.  Include `--build-arg KEY=VALUE` in the `gcloud builds submit` command.
    3.  Example: `gcloud builds submit --tag [TAG] --build-arg NEXT_PUBLIC_API_URL=[URL]`.

### 2.64 Docker Build Failure: COPY failed: stat app/public (Missing Directory)
- **Problem**: Multi-stage Docker build fails at the final stage with `COPY failed: stat app/public: file does not exist`.
- **Cause**: The `Dockerfile` assumes a directory (like `public` in Next.js) exists in the builder stage. If the project does not have any static assets, the folder might not be present, causing the `COPY` command to fail.
- **Solution**: 
    1.  Ensure the directory exists in the source repository (e.g., create an empty `public/.gitkeep`).
    2.  Alternatively, use a conditional copy or create the directory in the builder stage if it's optional: `RUN mkdir -p public`.
    3.  In the MeetChi frontend, verify if `apps/frontend/public` exists using `list_dir`.
### 2.65 Tailwind CSS v4 Build Error: missing @reference
- **Problem**: `npm run build` fails with `missing @reference? https://tailwindcss.com/docs/upgrade-guide#using-apply-with-css-variables`.
- **Cause**: Tailwind CSS v4 is "CSS-first". Legacy `@tailwind` directives are deprecated in favor of `@import "tailwindcss";`. When using `@apply` for custom theme variables, v4 needs a reference to the global theme.
- **Solution (Finalized)**: 
    1.  **Upgrade Syntax**: Replace `@tailwind base; @tailwind components; @tailwind utilities;` with `@import "tailwindcss";` at the top of `globals.css`.
    2.  **CSS-First Configuration**: Move theme values from `tailwind.config.ts` into a CSS `@theme` block in `globals.css`. This is the preferred way to extend Tailwind v4.
    3.  **Theme Block Definition**:
        ```css
        @theme {
          --color-background: #ffffff;
          --color-primary: #6366f1;
          /* ... other variables */
        }
        ```
    4.  **Verification**: Confirmed successful build (`npm run build`) and deployment of the modern dashboard UI after this migration.

### 2.66 Next.js: NEXT_PUBLIC_* Environment Variables Not Working on Cloud Run
- **Problem**: Changing `NEXT_PUBLIC_API_URL` via `gcloud run deploy --set-env-vars` has no effect; the frontend still points to `localhost` or the previous build's URL.
- **Cause**: Next.js inlines `NEXT_PUBLIC_*` environment variables during **build time** (`npm run build`). Setting them at runtime (Cloud Run env vars) does not update the client-side bundle.
- **Solution**: 
    1.  **Use Build Arguments**: In the `Dockerfile`, define an `ARG NEXT_PUBLIC_API_URL` and `ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}` before running `npm run build`.
    2.  **Pass via Cloud Build**: Use `cloudbuild.yaml` with `--build-arg` to inject the target URL during the image creation phase:
        ```yaml
        args:
          - 'build'
          - '--build-arg'
          - 'NEXT_PUBLIC_API_URL=https://your-backend.run.app'
          - '.'
        ```
    3.  **Verification**: Confirm the variable is correctly inlined by checking the frontend's API calls in the browser console.

### 2.67 Cloud Build: $SHORT_SHA or $PROJECT_ID Not Resolving in Manual Builds
- **Problem**: `gcloud builds submit --config=cloudbuild.yaml` fails with errors like `could not parse reference` or `invalid image name`.
- **Cause**: Default variables like `$SHORT_SHA` are only automatically populated for builds triggered by source control. In manual builds (using the CLI directly), these variables are empty unless explicitly passed via `--substitutions`.
- **Solution**: 
    1.  **Manual Image Tagging**: Use a fixed version tag (e.g., `:v6`) or a manual timestamp tag instead of `$SHORT_SHA`.
    2.  **Hardcode Project IDs**: In the `cloudbuild.yaml` file, use the explicit project ID (e.g., `project-51769b5e-7f0f-4a2f-80c`) if `$PROJECT_ID` is not resolving correctly during the manual submission.
    3.  **Use Substitutions**: Alternatively, run `gcloud builds submit --substitutions=_SHORT_SHA=$(git rev-parse --short HEAD)` and use `$_SHORT_SHA` in the YAML.

### 2.68 Cloud Build: "step exited with non-zero status: 1" during `gcloud run deploy`
- **Problem**: The build and push steps succeed, but the final `deploy` step failing with a generic error 1.
- **Cause**: The Cloud Build Service Account (or the Compute Engine default account used by Cloud Build) lacks the necessary permissions to update Cloud Run services or act as the runtime service account.
- **Solution**: 
    1.  **Grant Cloud Run Admin**: Ensure the service account has `roles/run.admin`.
    2.  **Grant Service Account User**: Ensure it has `roles/iam.serviceAccountUser` on the runtime service account.
    3.  **Manual Fallback**: If IAM propagation is slow or restricted, perform the build/push via Cloud Build and execute the `gcloud run deploy` command manually from a local authenticated terminal.

### 2.69 Browser Subagent: "$HOME environment variable is not set" vs Playwright
- **Problem**: `browser_subagent` fails to open a URL with `failed to create browser context: failed to install playwright: $HOME environment variable is not set`.
- **Cause**: The agent's execution environment (e.g., a specific runner or sandbox) may not have the `$HOME` variable defined, which Playwright depends on to locate its cache and configuration directories.
- **Solution**: 
    1. **Manual API Testing**: Use `curl` or `Invoke-RestMethod` to verify backend and frontend healthy states if the visual check fails.
    2. **Environment Verification**: Confirm both `/health` (backend) AND `/api/health` (frontend) return successful JSON responses before assuming the integration is broken.
    3. **Shell Input**: Ensure that terminal-based verification doesn't stall on interactive prompts (e.g., when using `Invoke-WebRequest` without a URI parameter or incorrect pipe handling).

### 2.70 Playwright: Test Failures due to String/Terminology Mismatches
- **Problem**: Playwright tests fail to locate elements (e.g., `Locator: getByText('AI 智能摘要')`) even though the UI looks correct locally.
- **Cause**: The automated tests are using a different term or translation than the actual code (e.g., `智能` vs `智慧`). This is common in Chinese-language interfaces where multiple similar terms exist.
- **Solution**: 
    1. **Verify Source**: Inspect the component file (e.g., `page.tsx`) using `grep_search` to find the exact string.
    2. **Use Regex**: Use regex for more flexible matching: `await expect(page.getByText(/智慧|智能/)).toBeVisible();`.
    3. **Consistency**: Standardize terminology across the codebase and testing suites.
- **Observed Case (Feb 2026)**: Landing page feature cards used "智慧摘要" but the test expected "智能摘要", causing an E2E failure.
### 2.71 NextAuth Module Augmentation Lint Errors
- **Problem**: `Invalid module name in augmentation, module 'next-auth/jwt' cannot be found.` in `auth.ts`.
- **Cause**: TypeScript may not catch the path for `/jwt` subpath in some configurations, or `next-auth` is using a package structure that requires specific `moduleResolution` (e.g., `bundler` or `node16`).
- **Solution**: 
    1. **Simplify Augmentation**: Instead of augmenting the `next-auth/jwt` sub-module (which can cause IDE resolution failures), augment the core `next-auth` module and redeclare the `Session` interface including the standard `user` object properties.
    2. **Example Fix**:
       ```typescript
       declare module "next-auth" {
         interface Session {
           idToken?: string;
           user: { id?: string; name?: string | null; email?: string | null; image?: string | null; };
         }
       }
       ```
    3. **Restart TS Server**: A common ghost error; use `Restart TS Server` if the module name is correct but the red squiggle persists.

### 2.72 NextAuth ID Token Assignment Type Error
- **Problem**: `Type '{}' is not assignable to type 'string'.` when assigning `account.id_token` to `token.idToken`.
- **Cause**: The `account` object in the NextAuth `jwt` callback can be null or have an optional `id_token`.
- **Solution**: 
    1. **Type Guards**: Use a combined null-check and type-check: `if (token.idToken && typeof token.idToken === 'string') { session.idToken = token.idToken; }`. 
    2. **Strict Assignments**: Avoid simple truthy checks if the target is a specific primitive like `string`; TypeScript's `JWT` object can hold generic `Unknown` or `{}` values for extracted token properties.

### 2.73 The Ralph Loop / Dangling References (Migration Failure)
- **Problem**: `terraform validate` or `plan` fails with `Error: Reference to undeclared resource` for `google_redis_instance.celery` (or similar), despite the resource block being removed.
- **Cause**: The deleted resource is still referenced in other parts of the infrastructure as a dependency or provider of data.
- **Observed Case (Feb 2026)**: During the migration from Redis to Cloud Tasks, the `backend` service in `cloudrun.tf` had:
    1. An environment variable `REDIS_URL` whose value was `redis://${google_redis_instance.celery.host}:6379/0`.
    2. A `depends_on` block explicitly listing `google_redis_instance.celery`. 
    3. An output in `outputs.tf` for `redis_host`.
- **Solution**: 
    1. **Search & Replace**: Grep the entire `terraform/` directory for the name of the deleted resource.
    2. **Cleanup Environment**: Remove or update environment variables in Cloud Run/Functions.
    3. **Cleanup Lifecycle**: Update `depends_on` to point to the new replacement resource (e.g., the Cloud Tasks queue).
    4. **Cleanup Outputs**: Remove or update `outputs.tf`.
    5. **Validate**: Run `terraform validate` to ensure all loops are closed.

### 2.74 Runtime ModuleNotFoundError (Transitive Dependency Leak)
- **Problem**: Cloud Run service fails to start with `HealthCheckContainerError` or a generic "container failed to start" message. Logs show `ModuleNotFoundError: No module named 'torch'` (or similar).
- **Cause**: The deployment environment (e.g., Backend CPU) is using a lightweight image without heavy ML dependencies, but a shared utility or submodule implicitly imports those dependencies.
- **Observed Case (Feb 2026)**: The `backend` service imported `app.diarization` for user metadata, but `diarization` contained an unconditional `import torch`.
- **Solution**: 
    1. **Identify the Leak**: Examine the stack trace in Cloud Logging.
    2. **Conditional Imports**: Wrap the problematic import in a `try...except ImportError` block.
    3. **Structural Refactoring**: Ensure modules with heavy dependencies are only imported by the service that actually runs them (e.g., the LLM GPU service).

### 2.75 GCP API Decommissioning Shutdown Race Condition
- **Problem**: `terraform apply` fails with `dial tcp: lookup redis.googleapis.com: no such host` (or similar) while deleting a resource.
- **Cause**: The API (`google_project_service`) is being disabled in the same transaction as the resource deletion. As the API is disabled, the provider can no longer resolve the API endpoint to poll for the deletion status.
- **Observed Case (Feb 2026)**: In the transition to Cloud Tasks, `redis.googleapis.com` was removed from `google_project_service.apis` and `google_redis_instance.celery` was deleted. Terraform attempted to disable the API, causing the deletion-tracking logic for the Redis instance to fail.
- **Solution**: 
    1. **Staged Deletion**: (Best Practice) Delete the resource instances first. Once confirmed destroyed, remove the API from `google_project_service` in a subsequent `apply`.
    2. **DNS Diagnostics**: Verify resolution using `nslookup [api_host]` (e.g., `nslookup redis.googleapis.com`). If it fails, wait for DNS cache to clear.
    3. **State Verification**: Check if the resource is still in state: `terraform state list | Select-String -Pattern "[keyword]"`.
    4. **Manual State Cleanup**: If the resource is already deleted on GCP but Terraform is stuck polling a non-existent API host, use `terraform state rm <resource_address>` to clear the dangling state.
    5. **Retry Strategy**: Once DNS resolves, re-run `terraform apply -auto-approve`. 
    6. **Ignore Deletion Failure**: If the DNS error occurs only during the "waiting for operation" phase, manually check the Cloud Console. If the resource is gone, the next `plan` will show it as removed.

### 2.76 Cloud Run HealthCheckContainerError (Post-Migration Crash Loop) - RESOLVED
- **Problem**: After migrating from Redis to Cloud Tasks, the `meetchi-backend` service fails to start with `The user-provided container failed to start and listen on the port defined provided by the PORT=8000 environment variable.`
- **Reason (Cascading Discovery)**:
    1.  **Shared Library Fatality**: The backend CPU environment lacked GPU drivers. `faster-whisper` and `ctranslate2`, when imported at the top level, caused a low-level C-extension crash (`ctranslate2._ext: Invalid argument`) that bypassed Python `try...except` blocks.
    2.  **Transitive Dependency Leak**: Pruning `requirements.txt` was insufficient because shared utility scripts (`vad.py`, `transcribe_sprint0.py`) still contained top-level ML imports.
    3.  **Docker Caching Mask**: Even after applying lazy-loading fixes, the container error persisted because Cloud Build reused cached layers that contained the fatal imports.
    4.  **Orphaned Module Import (Root Cause)**: The final blocker was a dangling `from app.celery_app import celery_app` in `app/main.py` line 354. Since `celery_app.py` was deleted as part of the decommissioning, the app crashed with `ModuleNotFoundError`.
- **Resolution**:
    1.  **Lazy Loading Pattern**: Implemented `_ensure_gpu_deps()` in ML-related scripts to move fatal imports inside functions.
    2.  **No-Cache Build**: Forced a clean rebuild using `gcloud builds submit --no-cache` to invalidate stale layers.
    3.  **Import Sanitation**: Conducted a global grep for "celery" and "redis" to remove all lingering imports and decorators.
- **Outcome**: Revision `meetchi-backend-00001-tps` (and subsequent) successfully passed health checks.

### 2.77 Cloud Build Context Size Resolution (7.9 GiB -> 2.2 MiB)
- **Problem**: `gcloud builds submit` from the project root archived the entire monorepo, ignoring `.gcloudignore` rules for large sibling apps like `tauri-client` (10GB) and `llm_service` (7GB).
- **Cause**: Massive upload context caused deployment timeouts and excruciatingly slow build starts.
- **Solution**: 
    1.  **Targeted Submission**: Switched to `cd apps/backend; gcloud builds submit .`.
    2.  **Local Isolation**: Placed a strict `.gcloudignore` inside `apps/backend/` to exclude local `.venv` and model caches.
- **Result**: Reduced upload context from **7.9 GiB** to **2.2 MiB**, making deployments near-instant.

### 2.78 Cloud Build Image Push Failure (Retry Budget Exhausted)
- **Problem**: Build fails during the `PUSH` phase with `retry budget exhausted (10 attempts)`.
- **Reason**: 
    1.  **Permission Denied (Masked)**: Often hides an IAM error where the build SA lacks `artifactregistry.repositories.uploadArtifacts`. 
    2.  **Network Jitter**: Large layers (~1GB) being pushed to the registry can timeout.
- **Resolution**:
    1.  **Identity Permissions Deadlock**: Ensure the **Compute Engine default service account** (used by Cloud Build) has `roles/artifactregistry.writer`. Note that fixing this requires a user with `roles/resourcemanager.projectIamAdmin` or `roles/owner`.
    2.  **Extended Timeout**: Use `--timeout=1800s` for heavy image pushes.

### 2.79 Artifact Registry: Repository Name Mismatch
- **Problem**: Push fails with "denied" or "not found" despite correct IAM permissions.
- **Cause**: Target repository name in build scripts (`meetchi-repo`) mismatched the manually created repository name (`meetchi`).
- **Discovery**: Run `gcloud artifacts repositories list` to verify the exact identifier. Re-aligning tags to `meetchi` resolved the "permission" blocker.

### 2.80 Docker: "無法辨識 'docker' 詞彙" (Missing Local Docker)
- **Problem**: `docker` commands fail on the developer machine's terminal.
- **Solution**: Use `gcloud builds submit` to perform all container operations in the Cloud Run environment, bypassing local Docker engine requirements.
### 2.81 ASR Model Pre-loading Startup Failure (Fatal Startup Hooks) - RESOLVED
- **Problem**: Container fails to start with `RuntimeError: ASR model pre-loading failed. Cannot start application.` despite all library imports being lazy-loaded.
- **Cause**: The application lifecycle hook (`@app.on_event("startup")`) explicitly called `load_asr_model()` during the startup phase. Since many ASR models require shared libraries (`ctranslate2`, `torch`) that crash in CPU-only Cloud Run environments, this forced call triggered a fatal exception before the container could complete its health check.
- **Solution**: 
    1.  **Guard the Hook**: Wrapped the pre-loading logic in an environment variable check (e.g., `ENABLE_ASR_PRELOAD`).
    2.  **Non-Fatal Handling**: Changed the exception handling from `raise RuntimeError` to a warning log (`app_logger.warning`).
- **Result**: The API service now starts successfully in CPU environments, loggiing a warning rather than crashing, while the actual ASR work is delegated to a separate GPU-enabled service or task runner.

### 2.82 Cloud Run GPU Activation (Unsupported Resource Block)
- **Problem**: Deploying GPU-enabled Cloud Run services fails with `Unsupported block type` or `The resource requires the 'google-beta' provider`.
- **Cause**: 
    1.  Attempting to use `node_selector` (unsupported in v2 Terraform resource).
    2.  Missing `launch_stage = "BETA"` required for hardware acceleration.
    3.  Failing to set `provider = google-beta` for the Cloud Run resource.
- **Resolution**:
    1.  Remove `node_selector`.
    2.  Ensure `provider = google-beta` and `launch_stage = "BETA"` are set.
    3.  Confirm CPU/Memory meet minimums (4 CPU / 16Gi RAM) for L4 GPUs.
- **Status**: Resolved in MeetChi `cloudrun.tf` for the `llm_gpu` service.

### 2.83 Cloud Run GPU: Regional Memory Quota Violation (`MemAllocPerProjectRegion`)
- **Problem**: Deploying the GPU service fails even after GPU quota is approved. Log: `Quota violated: MemAllocPerProjectRegion requested: 51539607552 allowed: 42949672960`.
- **Cause**: The memory limit per instance multiplied by `max_instance_count` exceeded the regional total memory allocation (40Gi by default).
- **The "False Optimization" Pitfall**: An attempt to reduce memory to 8Gi to fit the quota failed with: `In order to set GPU, memory must be at least 16Gi`. Cloud Run enforces 16Gi as the absolute minimum for GPU acceleration.
- **Resolution**:
    1.  Restored memory limit to **16Gi** to satisfy GPU requirements.
    2.  Reduced `max_instance_count` from 3 to **2**. This brought total requested memory to 32Gi ($16 \times 2$), fitting within the 40Gi regional quota.
- **Learning**: GPU instances have a hard 16Gi floor. You cannot "thin out" a GPU instance to save regional memory quota; you must instead increase the regional quota or cap horizontal scaling.
### 2.84 Cloud Run GPU: Zonal Redundancy Quota Conflict
- **Problem**: Deploying the GPU service fails even with available quota. Log: `The project has no more available "nvidia-l4" GPUs in region "asia-southeast1"`.
- **Cause**: Cloud Run defaults to "Zonal Redundancy," requiring the quota to be available in multiple zones simultaneously. If your quota is exactly 1, this check fails.
- **Solution**: Use the `--no-gpu-zonal-redundancy` flag with `gcloud run deploy`. (See `deployment_and_infra.md` Section 6.3).

### 2.85 Artifact Registry Push Hangs (No Error Output)
- **Problem**: `gcloud builds submit` seems to hang indefinitely during the `PUSH` phase of a large image (>500MB), or output delta stops arriving but the command is still `RUNNING`.
- **Cause**: CPU-bound compression or network throughput bottlenecks on default build machines when handling heavy Python/ML layers.
- **Solution**: Use a high-performance machine type for the build:
  ```powershell
  gcloud builds submit --tag [TAG] --machine-type=e2-highcpu-8 --timeout=2400s .
  ```
- **Context**: Successfully resolved a push hang for the `meetchi-llm-gpu` service in February 2026.

### 2.86 Gemini API: 403 Forbidden / API Not Enabled
- **Problem**: LLM service logs show `google.api_core.exceptions.Forbidden: 403 Generative Language API has not been used in project [PROJECT_ID] before or it is disabled.`
- **Cause**: The **Generative Language API** (`generativelanguage.googleapis.com`) is not enabled in the GCP project.
- **Solution**: Enable the API via CLI:
  ```powershell
  gcloud services enable generativelanguage.googleapis.com
  ```
- **Verification**: Ensure your `GEMINI_API_KEY` belongs to the same project or has cross-project permissions. In the MeetChi project, verify the project ID is exactly **`project-51769b5e-7f0f-4a2f-80c`**.


### 2.87 LLM Service: Failed to load LLM model: 'architectures'
- **Problem**: The `meetchi-llm-gpu` service reports as healthy but returns mock data for all summaries/polishing. Logs show `Failed to load LLM model: 'architectures'`.
- **Cause**: This is usually a version incompatibility between the `transformers` library and the model's configuration (specifically seen with `MediaTek-Research/Llama-Breeze2-3B-Instruct`). The model's custom code requires feature support introduced in newer versions of the library.
- **Root Cause Diagnosis**:
    1. **`app.py`**: The service enters a fallback mock mode if `model is None`.
    2. **Dependency Resolution**: `requirements.txt` might have broad constraints (e.g., `>=4.35.0`) which resolve to a version too low for the Breeze2 architecture when running in the Cloud Run environment.
- **Solution**: 
    1. Update `apps/llm_service/requirements.txt` to pin `transformers>=4.38.0`.
    2. Update the `Dockerfile` in `apps/llm_service` to ensure the pip install step uses the same version.
    3. Force a clean rebuild (`--no-cache`) to ensure the correct library version is packaged.
- **Verification**: Check the `/health` endpoint of the LLM service. It should return `mock_mode: false` when correctly loaded.

### 2.88 Cloud Run GPU: The 3x Resource Reservation Trap
- **Problem**: Deploying the GPU service fails even with `max_instances=1` and `--no-gpu-zonal-redundancy`. 
  - Log A: `Quota violated: MemAllocPerProjectRegion requested: 51539607552 allowed: 42949672960` (48GiB requested vs 40GiB allowed).
  - Log B: `NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion requested: 3 allowed: 1`.
- **Cause**: Cloud Run's rollout mechanism (Canary/Blue-Green) inherently requests **3x the target capacity** (3 revisions or 3 zones worth of buffers) during the transition phase. Even for a **fresh deployment** of a non-existent service, the transaction calculates requirements as 3 units.
- **Verified Workaround: Service Deletion**: If you have exactly 1 unit of quota, you can bypass the 3x reservation during deployment by **deleting the existing service** (`gcloud run services delete`) first.
  - **Reason**: When creating a **new** service (or a fresh deployment on a name that no longer exists), Cloud Run requests resources equal to the target `max_instances` (1), rather than the 3-unit buffer required for a zero-downtime revision swap.
- **Quota Type Confirmation**: Verified that this applies specifically to the `NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion` quota. A user with exactly `1` unit is blocked from **updates** but can succeed on **fresh creations**.
- **Learning**: Quota of "1" is sufficient for a bootstrap/fresh deploy, but a minimum of 3 is required for non-disruptive updates.

### 2.89 Cloud Build: 'manifest unknown' for CUDA images
- **Problem**: Build fails during Layer 1 (`FROM`) with `manifest unknown: manifest unknown`.
- **Cause**: Using a version tag like `12.1-runtime-ubuntu22.04` which is not a valid alias in the `nvidia/cuda` repository.
- **Resolution**: Specify the full minor version: `12.1.0-runtime-ubuntu22.04`.
- **Status**: Verified Feb 2026. Applying this fix allowed the `meetchi-llm` build to proceed with layer pulling.

### 2.90 Cloud Build: Redundant Pip Uninstallation (Torch)
- **Problem**: Build takes significantly longer than expected (over 40 minutes) despite having cached layers for PyTorch.
- **Symptom**: Logs show `Attempting uninstall: torch` followed by `Successfully uninstalled torch-2.1.0+cu121` and then a multi-gigabyte download of `torch` from PyPI.
- **Cause**: In `Dockerfile.gpu`, `torch+cu121` was installed in one step, but a subsequent `pip install` for `whisperx` or other packages triggered a dependency re-resolution that replaced the specialized GPU-build with a standard one.
- **Resolution**: 
    1. Consolidate specific version requirements into the main `requirements.txt`.
    2. Use a single `pip install` command for all ML-related libraries to allow the pip resolver to settle on the correct version at once.
- **Stability Note**: Forcing the reinstall of a non-GPU torch can break the ASR engine's ability to access the L4 GPU.

### 2.91 PowerShell: "The '<' operator is reserved" (Here-Doc Failure)
- **Problem**: Attempting to use `gcloud builds submit --config=- <<EOF ...` results in a PowerShell error: `The '<' operator is reserved for future use.`
- **Cause**: Windows PowerShell (v5.1 and earlier) and standard cross-platform PowerShell do not support the `<<` heredoc redirection syntax common in Bash/Zsh.
- **Resolution**:
    1. **Dedicated File**: Write the build configuration to a standalone `cloudbuild.yaml` file using `write_to_file`.
    2. **Execution**: Run `gcloud builds submit --config=cloudbuild.yaml`.
    3. **Cleanup**: Delete the temporary YAML file after the build starts or completes.
- **Observation**: This was the primary blocker for custom Dockerfile builds (`Dockerfile.gpu`) on developer machines until the transition to `cloudbuild-llm.yaml`.

### 2.92 PowerShell: "Invoke-WebRequest" Prompt (curl Alias Trap)
- **Problem**: Running `curl <URL>` in PowerShell results in a prompt for `Uri:` or a failure in background tasks.
- **Cause**: In Windows PowerShell, `curl` is an alias for `Invoke-WebRequest`. If the argument parsing fails or if it's run in a way that triggers cmdlet parameter binding, it may hang or error.
- **Resolution**: 
    1. **Explicit Cmdlet**: Use `Invoke-RestMethod` for JSON API health checks.
    2. **Binary curl**: If the native `curl.exe` is required, use `curl.exe` explicitly to avoid the PowerShell alias.
- **Verification**: Used `Invoke-RestMethod -Uri "https://.../health" -Method GET` to verify the LLM GPU and Frontend services.

### 2.93 Next.js: "NEXT_PUBLIC_" Build-Time Injection Failure
- **Problem**: Frontend fails to connect to the backend URL (`undefined` or `localhost:8000`) after deployment.
- **Cause**: Environment variables prefixed with `NEXT_PUBLIC_` are baked into the client-side bundle during the **build phase** (`npm run build`). Setting them as Cloud Run runtime environment variables has no effect on the already-built static assets.
- **Resolution**:
    1. **Build Args**: Pass the backend URL as a `--build-arg` during `docker build`.
    2. **cloudbuild.yaml**: Update the build step to include `- --build-arg NEXT_PUBLIC_API_URL=https://...`.
- **Note**: MeetChi standardized on version **v7** for the frontend to reflect the finalized backend URL injection.

### 2.94 Cloud Build: "roles/logging.logWriter" Missing (Step Deployment Failure)
- **Problem**: A Cloud Build step executing `gcloud run deploy` fails with a non-zero exit status and log output mentioning `roles/logging.logWriter` or failing to write logs.
- **Cause**: When `gcloud run deploy` is executed within Cloud Build (e.g., using the `cloud-sdk` builder), the automation identity (Compute Engine default service account or Cloud Build service account) may lack the permissions to write logs for the newly created service or revision, especially in tightly constrained IAM environments.
- **Resolution**:
    1. **Grant Role**: Assign `roles/logging.logWriter` to the **Compute Engine default service account** (used by Cloud Build as the default execution identity in modern project settings).
    2. **Alternate Configuration**: Use `logging: CLOUD_LOGGING_ONLY` or `GCS_ONLY` in the build options to redirect logs if the standard writer continues to fail.
- **Verification**: This was identified as the blocker for the automated deployment of `meetchi-frontend` Revision v7.

### 2.95 E2E Verification: Full Stack 200 OK (PowerShell Method)
- **Problem**: Need to verify connectivity and health across multiple serverless components (Frontend, Backend, LLM GPU) without complex local VPC setup.
- **Resolution**: Utilized a centralized PowerShell monitoring block with `Invoke-RestMethod` to verify consistency of version **v7** rollout.
- **Results (Verified Feb 2024)**:
    1. **Frontend**: `/api/health` -> `healthy` (Next.js v16).
    2. **Backend**: `/health` -> `healthy` (FastAPI).
    3. **LLM GPU**: `/health` -> `device: cuda, status: ready` (WhisperX).
- **Observation**: The use of standardized `/health` or `/api/health` endpoints across all containers is verified as the most effective "heartbeat" for early rollout detection on Cloud Run.

### 2.96 NextAuth.js (Auth.js): "Server Error (500)" on Cloud Run
- **Problem**: Accessing `/api/auth/signin` or other auth endpoints returns a generic "Server error" (HTTP 500).
- **Cause**: The `auth.js` (formerly NextAuth) runtime requires the `AUTH_SECRET` environment variable to be set for encryption and session management. If it's missing on Cloud Run, the sign-in provider list fails to render, and providers (like Google) won't show up.
- **Resolution**: 
    1. **Generate Secret**: Create a base64-encoded secret (e.g., using `openssl rand -base64 32`).
    2. **Cloud Run Config**: Set `AUTH_SECRET` and `AUTH_URL` (the service URL) in the Cloud Run service environment variables.
- **Verification**: Verified using browser subagent diagnostics. The absence of `AUTH_SECRET` causes providers like Google to silently fail or return a configuration error.

### 2.97 Google OAuth: "Error 401: invalid_client" on Cloud Run
- **Problem**: Clicking the Google login button results in a Google error page showing `Error 401: invalid_client`.
- **Cause**: The `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` environment variables are missing, malformed, or not propagated to the Cloud Run runtime. In serverless environments, these must be explicitly set even if available during the build process if the auth library (Auth.js) executes server-side logic (e.g., getting provider list).
- **Resolution**: Verify these variables in the Cloud Run service configuration. Use `gcloud run services update --update-env-vars="GOOGLE_CLIENT_ID=...,GOOGLE_CLIENT_SECRET=..."` to ensure they are available to the container at runtime.
- **Verification**: Post-update, the Google login button should correctly redirect to the Google account selection screen instead of showing a 401 error.

### 2.98 Google OAuth: "Error 400: redirect_uri_mismatch"
- **Problem**: Redirecting to Google for authentication results in a "Error 400: redirect_uri_mismatch" page.
- **Cause**: The `redirect_uri` being sent by Auth.js (typically `[SERVICE_URL]/api/auth/callback/google`) is not present in the "Authorized redirect URIs" list for the specific OAuth 2.0 Client ID in the Google Cloud Console.
- **Resolution**:
    1. Identify the exact URI being blocked (visible in the Google "Request details" or the browser URL params).
    2. Go to [Google Cloud Console -> Credentials](https://console.cloud.google.com/apis/credentials).
    3. Edit the relevant OAuth 2.0 Client ID.
    4. Add the URI to the "Authorized redirect URIs" list.
    5. Save the changes (note: propagation may take a few minutes).
- **Verification**: Testing the login flow again should successfully show the Google account selection or login prompt.

### 2.99 Infinite Summary Spinner / LLM Mock Mode
- **Problem**: Users report the summary generation never completes (stuck in "Processing" or "Waiting for AI summary").
- **Cause**: 
    1. **Mock Mode Enabled**: The `meetchi-llm-gpu` service might be running in "Mock Mode" because it failed to load the model (OOM, missing files) or `MOCK_LLM=true` is set. 
    2. **Endpoint Mismatch**: The backend is calling the wrong URL or an outdated revision.
    3. **Callback Failure**: The LLM service completes but the callback to update the backend database fails.
- **Diagnosis**: 
    1. **Health Check**: Call `/health` on the LLM service. Check if `mock_mode: true`.
       ```powershell
       Invoke-RestMethod -Uri "https://meetchi-llm-gpu-wfqjx2j42q-as.a.run.app/health" -Method GET
       ```
    2. **Test Summarization**: Manually trigger a POST to verify response structure:
       ```powershell
       $body = @{ text = "Valid test text"; template_name = "general" } | ConvertTo-Json
       Invoke-RestMethod -Uri "https://meetchi-llm-gpu-wfqjx2j42q-as.a.run.app/summarize" -Method POST -Body $body -ContentType "application/json"
       ```
    3. **Env Audit**: Check `gcloud run services describe meetchi-backend` for the correct `LLM_SERVICE_URL`.
- **Solution**: 
    1. **Version Alignment**: Upgrade `transformers` to `4.38.0` or higher. Breeze2 models (MediaTek Research) often fail with `'architectures'` errors on older versions.
    2. **Dockerfile Optimization**: Pin `transformers>=4.38.0` in the Dockerfile and ensure subsequent `pip install` commands (like `whisperx`) do not downgrade it.
    3. **Memory Check**: Ensure the GPU service has enough memory (min 16Gi for 3B, 32Gi+ for 8B) and correct model paths.
    4. **Env Check**: Set `MOCK_LLM=false` in the GPU service env vars and restart.
    5. **Log Review**: Check `gcloud logging` for `Failed to load LLM model`. If it says `'architectures'`, it's almost certainly a library version issue.

### 2.100 Next.js: "Server Component: useState/useEffect is not a function"
- **Problem**: Build fails with an error indicating that `useState` or `useEffect` cannot be used in a Server Component, or the browser shows a 500 error when accessing a page.
- **Cause**: Next.js 13+ (App Router) defaults files in the `src/app` or `src/components` directory to **Server Components**. If the file uses React hooks (`useState`, `useEffect`) or browser-only APIs (like Tauri's `invoke` or `localStorage`), it must be explicitly marked as a **Client Component**.
- **Solution**: Add the `"use client";` directive at the very top of the file (before any imports).
- **Observed Case (Feb 2026)**: Occurred in `SummarySettingsModal.tsx` and `DetailsPage`. In Tauri-based environments where many components interact with the local hardware/OS via Rust invokes, almost all UI-heavy components should be Client Components.
- **Verification**: Run `npm run build` or `npx tsc --noEmit` and confirm the specific file no longer triggers the "hooks in Server Component" error.

### 2.101 next.config.ts: "Object literal may only specify known properties ... 'reactCompiler'"
- **Problem**: Next.js build fails with a TypeScript error: `Object literal may only specify known properties, and 'reactCompiler' does not exist in type 'NextConfig'`.
- **Cause**: The `reactCompiler` property (introduced as an experimental feature) is either not supported by the current Next.js version or is placed at the top level of the configuration object instead of inside the `experimental` block.
- **Solution**: 
    1. **Check Version**: Ensure Next.js is at a version that supports the React Compiler (v15+ or experimental builds).
    2. **Re-locate Property**: Move the setting under the `experimental` key:
       ```typescript
       const nextConfig: NextConfig = {
         experimental: {
           reactCompiler: true,
         },
         // ...
       };
       ```
    3. **Remove if Unused**: If the project doesn't strictly require the compiler, remove the property to restore build compatibility.
- **Verification**: Run `npm run build` and ensure the `next.config.ts` type error no longer appears.

### 2.102 next.config.ts: "Object literal may only specify known properties ... 'buildActivity' / 'appIsrStatus'"
- **Problem**: Next.js 16 build fails with `Object literal may only specify known properties, and 'buildActivity' / 'appIsrStatus' does not exist in type 'DevIndicators'`.
- **Cause**: In Next.js 16+, the `devIndicators` configuration has been simplified. The previous object format (targeting `buildActivity` and `appIsrStatus` directly) is removed/deprecated in favor of a single boolean or an object with a `position` property.
- **Solution**: 
    1. **Simplify**: Set `devIndicators: false` to disable indicators.
    2. **Reposition**: If needed, use the new format: `devIndicators: { position: 'bottom-right' }`.
- **Observed Case (Feb 2026)**: During the MeetChi Tauri client upgrade, the existing `next.config.ts` with explicit `buildActivity: false` caused the build to fail until simplified to `devIndicators: false`.
- **Verification**: `npm run build` should complete without configuration type errors.

### 2.103 TypeScript: "Expected 1-2 arguments, but got 5" (API Mismatch)
- **Problem**: Build fails or linting reports an incorrect number of arguments passed to `api.generateSummary(...)`.
- **Cause**: The frontend API client definition (`lib/api.ts`) likely only supports basic arguments (e.g., `meetingId`, `template`), while the UI is attempting to pass additional options (context, length, style) introduced during Phase 5 optimizations.
- **Solution**: 
    1. **Sync Definitions**: Update the `api.ts` method signature to match the new backend capability:
       ```typescript
       // lib/api.ts
       async generateSummary(meetingId: string, template_type: string = 'general', context: string = '', length: string = '', style: string = '') {
           // ... implementation using URLSearchParams
       }
       ```
    2. **Use Options Object**: For cleaner architecture, refactor the API to use a single options object instead of positional arguments.
- **Verification**: Ensure the `generateSummary` call in `[meetingId]/page.tsx` matches the signature in `src/lib/api.ts`.

### 2.104 Alignment Forward Window Constraint (Script Matching Failures)
- **Problem**: In "Alignment Mode", the system correctly transcribes speech, but fails to highlight or match the corresponding script segment, especially near the end of long scripts or during fast delivery.
- **Cause**: The `NORMAL_WINDOW_FORWARD` constant in `app/main.py` defines how many characters ahead the Aligner searches for matches. If the speaker jumps forward or the ASR processing lags significantly, the target text may fall outside this search window.
    - **Observed Case (Feb 5, 2026)**: Cursor position at 509/833 (chars). Target text at 800+. Window was 200, so effective search range was 509–709.
- **Solution**: Increase `NORMAL_WINDOW_FORWARD` to **600 characters**. This allows the system to recover from larger jumps or processing lags without waiting for the "Global Resync" (which usually requires 3 consecutive failures).
- **Verification**: Check server logs for `cursor: X/Y` and compare with the length of the transcript text being processed.

### 2.105 Politeness Markers (e.g., 謝謝) Filtered Out
- **Problem**: In "Alignment Mode", the user says "謝謝" (Thank you) or other greeting phrases that are in the script, but the system fails to match them, causing the highlight to skip or the cursor to lag.
- **Cause**: The ASR pipeline often includes a "Hallucination Filter" to post-process common noise or filler words. Phrases like "謝謝" are frequently on these blacklists to prevent random noises from being transcribed as text.
    - **Observed Case (Feb 5, 2026)**: Backend logs showed `Filtered hallucination (exact): 謝謝`. This prevented the Aligner from receiving the text needed to match the last line of the script.
- **Solution**: 
    1. Update the ASR function (e.g., `get_transcription`) to accept an `alignment_mode` flag (implemented as `skip_hallucination_filter`).
    2. Pass `skip_hallucination_filter=True` when the overarching mode is `alignment`.
    3. **Variable Mapping**: The `operation_mode` variable is typically defined in the WebSocket handler in `app/main.py` (around line 1148) based on the incoming JSON config.
- **Verification**: Ensure backend logs do not show "Filtered hallucination" for words that are explicitly included in the user's script.
### 2.106 Alignment Failure in Slow Speech (Score Threshold)
- **Problem**: Even with the forward window increased and hallucination filters disabled, the system fails to match correctly-transcribed text (e.g., "有個愉快的夜晚", "新的一年 祝事順心 謝謝").
- **Cause**: 
    1.  **Fragmentation**: Slow or precise speech results in more frequent VAD splits. Each split sends a smaller piece of text to the Aligner.
    2.  **Scoring Gap**: If the text is very short (e.g. 4–5 characters) or contains minor variations (ASR: "祝事" vs Script: "諸事"), the total alignment score may fall below the `MIN_MATCH_SCORE`.
    3.  **Result**: The Aligner reports a failure because it cannot reach the required confidence threshold, even if the text perfectly matches a part of the script.
- **Solution**:
    - **Homophone Tolerance**: Implemented a partial match mechanism (75% score) in the **Smith-Waterman** algorithm for phonetic variations (e.g., 諸/祝, 夜/一, 的/得).
    - **Score Balancing**: Lowered the **`MIN_MATCH_SCORE` to 6** and the alignment threshold to **0.30**.
    - **Fast Resync**: Reduced **`MAX_CONSECUTIVE_FAILURES` to 3** to trigger global resync sooner.
- **Verification**: Check server logs for `[DEBUG] ❌ Alignment completely failed for: '...'`. Compare the transcript length with `MIN_MATCH_SCORE`.

### 2.107 TypeError: MultiSpeakerScriptAligner.find_match() got an unexpected keyword argument 'alignment_mode'
- **Problem**: When attempting alignment in "Alignment Mode", the backend crashes with a `TypeError` in the WebSocket handler.
- **Cause**: A new parameter (`alignment_mode`) was added to the base class `ScriptAligner.find_match()` signature and used in the caller, but the derived class `MultiSpeakerScriptAligner` overridden `find_match` with its own fixed signature that lacked the new parameter.
- **Solution (Applied Feb 5, 2026)**: 
    1. Updated the `find_match` method signature in `MultiSpeakerScriptAligner` to match the base class: `def find_match(self, transcript_text, threshold=0.5, alignment_mode=False)`.
    2. Implemented the internal calculation of `effective_threshold = 0.30 if alignment_mode else threshold` within the subclass.
- **Verification**: Confirmed via server logs that the `TypeError` no longer occurs and alignment matches are successfully attempted in multi-speaker mode.

### 2.108 Stall at Speaker Zone Boundary (Trapped by lock_to_current_zone)
- **Problem**: When transitioning between speakers (e.g., from Speaker A to Speaker B), the Aligner stops updating for the start of the second speech, even with clear ASR input.
- **Cause**: The `lock_to_current_zone=True` policy restricts the search window to the boundaries of the `current_zone_index`. If the search window for Zone A ends at 509 and Zone B starts at 510, the aligner can never "see" the first characters of Zone B.
- **Resolution (Applied Feb 5, 2026)**: 
    - **Resolved by [Next-Zone Probing (Solution C)](#2107-premature-speaker-zone-handoff-false-positive-jump)**: The search window now explicitly "peeks" into the next zone (approx. 100 characters ahead).
    - **Verification**: Logs should show the cursor advancing into the next speaker's zone once the ASR matches the beginning of the next script.

### 2.109 Premature Speaker Zone Handoff (False Positive Jump)
- **Problem**: The system jumps to the next speaker (Speaker B) while the first speaker (Speaker A) is still speaking their final sentences. These final sentences then fail to translate/display.
- **Cause**: The `AUTO_ADVANCE_THRESHOLD` was too low (90%) and relied solely on cursor binary search.
- **Solution (Applied Feb 5, 2026 - Solution C)**:
    - **Next-Zone Probing**: The search range expansion (Current Zone + Start of Next Zone) is coupled with a "Dominance Check". Transition only triggers when a match is found that explicitly crosses the boundary into the next zone's unique starting phrase.
    - **Fallback Logic**: If the next zone's start isn't detected, a **95% progress fallback** ensures the system still advances once the current script is nearly exhausted.
    - **Benefit**: This acts as a more natural "handoff" signal than forcing the previous speaker to reach a 100% completion threshold or specific final segment matches.
- **Verification**: Inspect logs for auto-advance triggered by cross-zone matches or the 95% fallback message.

### 2.110 PowerShell: "Invoke-WebRequest : Cannot bind 'Headers' parameter" (curl -H Failure)
- **Problem**: Running `curl -X POST ... -H "Content-Type: application/json" ...` in PowerShell fails with: `Cannot bind parameter 'Headers'. Cannot convert value "Content-Type: application/json" of type "System.String" to type "System.Collections.IDictionary"`.
- **Cause**: Windows PowerShell's `curl` alias maps to `Invoke-WebRequest`. Unlike Linux `curl`, it does not accept string-formatted header flags (`-H "Key: Value"`). It requires a hash table or specific parameters.
- **Resolution**:
    1. **Native PowerShell**: Use `Invoke-RestMethod` which has a dedicated `-ContentType` parameter.
       ```powershell
       Invoke-RestMethod -Uri "https://..." -Method POST -ContentType "application/json" -Body '{"key": "value"}'
       ```
    2. **Avoid Aliases**: Use `curl.exe` explicitly if you want standard bash-style curl behavior.
- **Verification**: This was encountered and resolved while verifying the MeetChi LLM `/summarize` endpoint in February 2026.

### 2.111 LLM Service: "No model available" Error (Hybrid Inference Failure)
- **Problem**: The `/summarize` endpoint returns `{"error": "No model available", "summary": "模型未就緒..."}`.
- **Cause**: This error is triggered when the LLM service fails to load BOTH the local model (e.g., due to GCS connectivity errors) and the Gemini API client (e.g., due to missing API keys or initialization failure).
- **Diagnosis**: 
    1. Check Cloud Run logs for `Failed to load LLM model` or `Failed to initialize Gemini client`.
    2. Verify `USE_GEMINI` and `GEMINI_API_KEY` environment variables are correctly set.
    3. Check for `google-genai` library installation in the Docker image.
- **Context**: This indicates a total failure of the hybrid inference fallback mechanism.

### 2.112 Cloud Run: "No URLs matched: gs://[PROJECT_ID]" (GCS Path Error)
- **Problem**: Cloud Run logs show `CommandException: No URLs matched: gs://project-51769b5e-7f0f-4a2f-80c`.
- **Cause**: The `GCS_MODELS_PATH` or the logic in the startup script is attempting to access a bucket named exactly like the project ID, which may not exist or is missing the required suffix (e.g., `-meetchi-audio`).
- **Solution**: Ensure the `GCS_MODELS_PATH` environment variable in `cloudrun.tf` or the manual `gcloud run services update` command includes the full bucket name: `gs://${PROJECT_ID}-meetchi-audio/models`.
- **Verification**: Run `gsutil ls gs://[PROJECT_ID]-meetchi-audio/models` to verify the path exists.

### 2.113 PowerShell: "'&&' token is not a valid statement separator"
- **Problem**: Running multi-part commands like `git add -A && git commit -m "..."` fails with `ParserError: In this version of the statement '&&' is not a valid statement separator`.
- **Cause**: Standard Windows PowerShell (v5.1 and earlier) and some configurations of PowerShell Core do not support the `&&` (AND) or `||` (OR) pipeline chain operators found in Bash/Zsh. These were only introduced in PowerShell 7.
- **Solution**:
    1. **Semicolon**: Use `;` to run commands sequentially regardless of success: `git add -A; git commit -m "..."`.
    2. **Pipeline**: Use a script block or standard line breaks.
    3. **Upgrade**: Install PowerShell 7+ for natively supporting `&&`.
- **Verification**: Confirmed while attempting to commit LLM service changes in February 2026.

### 2.114 Cloud Build: Unexpected Context Upload Delay/Timeout
- **Problem**: `gcloud builds submit` takes several minutes just for the "Creating temporary archive" phase, even for small code changes.
- **Cause**: By default, `gcloud builds submit` includes the entire current directory context (including `node_modules`, `.next`, or large `.git` histories) unless a `.gcloudignore` file is present.
- **Solution**:
    1. **Target Subdirectory**: Run the build from the specific application subdirectory rather than the project root:
       ```powershell
       cd apps/llm_service
       gcloud builds submit --tag [TAG] .
       ```
    2. **.gcloudignore**: Create a `.gcloudignore` at the root to exclude heavy directories.
- **Impact**: Context size reduced from ~40MB (compressed) to ~40KB, making build triggers nearly instantaneous.
- **Verification**: In Cloud Build logs, check for the "Creating temporary archive" step context size.

### 2.115 Cloud Run: /health is 200 OK but Returns 'mock_mode: true'
- **Problem**: The service responds with HTTP 200, but the JSON payload contains `"mock_mode": true`. Summarization returns fallback text.
- **Cause**: The health endpoint logic (before Phase 6 updates) often reported `mock_mode` based solely on whether the **local GPU model** failed to load. In hybrid environments, the local model *will* fail to load on standard CPU instances, triggering this flag even if the Gemini API is active and capable of serving requests.
- **Solution**: 
    1. Upgrade to the **Explicit Health Signaling** pattern (implemented in Feb 2026).
    2. Check for the `gemini_enabled: true` field in the new health response.
    3. If `gemini_enabled` is false despite `USE_GEMINI=true`, investigate the `google-genai` library installation and Secret Manager permissions.
- **Verification**: Call `/health` and verify `gemini_enabled` is explicitly `true`.

### 2.116 Cloud Build: Terminal Hang or Build Cancellation
- **Problem**: The terminal hangs during the `Uploading tarball` or `Waiting for build` phase, or the build state is unexpectedly set to `CANCELED`.
- **Cause**: Shell timeouts, network instability during large uploads, or accidental terminal closure. Manual cancellation (Ctrl+C) during the polling phase does not necessarily stop the build on the server, but it loses the local state.
- **Solution**:
    1. **Asynchronous Submission**: Use the `--async` flag to trigger the build and return immediately.
       ```powershell
       gcloud builds submit --tag [TAG] --async
       ```
    2. **Status Check**: Re-attach or check status using the Build ID or list:
       ```powershell
       gcloud builds list --limit=5
       # Use 'beta' for real-time streaming from Cloud Logging
       gcloud beta builds log [BUILD_ID] --stream
       ```
- **Verification**: Confirmed in February 2026 after a build interruption; re-submitting with `--async` and using the `beta` log flag allowed for non-blocking monitoring of the 2GB image download.

### 2.117 Local Development: gemini_enabled is 'false' despite Correct Code
- **Problem**: Testing the service locally (e.g., `http://localhost:5000/health`) returns `"gemini_enabled": false`, even though the exact same code works on Cloud Run with Gemini.
- **Cause**: The local environment lacks the `GEMINI_API_KEY` environment variable. On Cloud Run, this is automatically injected via Secret Manager. Locally, it must be provided manually.
- **Solution**:
    1. Create a `.env` file in `apps/llm_service/` or set the system environment variable:
       ```bash
       GEMINI_API_KEY=AIzaSy...
       USE_GEMINI=true
       ```
    2. Restart the local service.
- **Verification**: Call `/health` locally and confirm `"gemini_enabled": true`.

### 2.118 PowerShell & CLI Discrepancies
- **`Invoke-WebRequest` vs `curl` Header Binding**:
    - **Problem**: Running `curl -X POST ... -H "Content-Type: application/json"` in PowerShell fails with `Cannot bind parameter 'Headers'`.
    - **Cause**: The `curl` alias in Windows PowerShell maps to `Invoke-WebRequest`, which does not support string-formatted header flags.
    - **Solution**: Use `Invoke-RestMethod` with specific parameters or use `curl.exe` explicitly.
- **`&&` Token Statement Separator**:
    - **Problem**: `git add -A && git commit` fails with `ParserError` in Standard PowerShell.
    - **Solution**: Use `;` for sequential execution or upgrade to PowerShell 7.

### 2.119 GCS Interpolation Pitfalls
- **"No URLs matched" GCS Error**:
    - **Problem**: `gsutil` or Python clients fail to find buckets despite correct project ID.
    - **Cause**: Buckets often require specific suffixes (e.g., `-data` or `-models`) that are missed in simple project-id variable interpolation.
    - **Solution**: Always use the full bucket URI in environment variables (e.g., `gs://${PROJECT_ID}-meetchi-models`).

### 2.120 Cloud Build: Library Version Conflicts ("Successfully uninstalled" Pattern)
- **Problem**: Build fails or service crashes due to incompatible library versions (e.g., `torch-2.1.0` vs `google-genai`).
- **Observation**: During a healthy build with updated `requirements.txt`, logs should explicitly show removals of stale packages. 
- **Signature (Feb 2026)**:
    - `Attempting uninstall: triton` -> `Successfully uninstalled triton-2.1.0`
    - `Attempting uninstall: torch` -> `Successfully uninstalled torch-2.1.0+cu121`
    - `Successfully installed torch-2.10.0 ...`
- **Action**: If you see these uninstallation markers, it confirms that your `requirements.txt` changes are successfully invalidating old Docker layers or base image defaults and forcing a clean environment transition. Use the `--no-cache` flag in `gcloud builds submit` if this transition is not occurring automatically.

### 2.121 Gemini "No model available" Fallback Trap
- **Symptom**: `/health` returns `gemini_enabled: true`, but `/summarize` returns `{"error": "No model available"}`.
- **Cause**: The Gemini API request (e.g., `generate_content`) fails (due to key, quota, or network). The code catches the exception and attempts to fall back to the local model. If no local model is loaded (standard for Cloud Run CPU nodes), it returns "No model available".
- **Signature (Cloud Run Logs)**: 
  - `Traceback (most recent call last): File "/app/app.py", line 399, in summarize_meeting response = gemini_client.models.generate_content(...)`
  - `google.genai.errors.ClientError` or `ServerError`.
- **Solution**: 
  1. Inspect the `textPayload` in Google Cloud Logging with a filter for `Gemini` and `Exception`.
  2. **Check SDK Parameters**: Ensure you are using `response_json_schema` with `Class.model_json_schema()` instead of `response_schema`. Passing a Pydantic class directly to `response_schema` is a common cause for `ServerError` in the `google-genai` Python SDK.
  3. Verify the `GEMINI_API_KEY` is valid in Secret Manager.

### 2.122 Docker Optimization: 15GB to 150MB Strategy (API-Only)
- **Context**: The `llm_service` was originally designed for local GPU inference, leading to a massive image containing CUDA, PyTorch, and heavy ML libs.
- **Problem**: Large images cause 10-15 minute build times and expensive Artifact Registry storage when only the Gemini API is needed for production summarization.
- **Solution (Feb 6, 2026)**:
    1. **Base Image**: Switch from `nvidia/cuda` to `python:3.11-slim`.
    2. **Requirements**: Prune `torch`, `whisperx`, and `transformers`.
    3. **Impact**: Reduced image size by **99%** (~148MB) and deployment time by **90%** (~60s).
    4. **Caveat**: This removes local fallback capabilities. Only use this for "Tier 1" services that 100% offload to managed APIs.

### 2.123 React Hydration Mismatch (Next.js + Tauri)
- **Problem**: `Hydration failed because the server rendered HTML didn't match the client.` logs during development or production.
- **Cause**: In Next.js (SSR), components are rendered on the server without `window` or `navigator` context. If a component uses a conditional branch like `if (isTauri())` or `if (typeof window !== 'undefined')` to render additional HTML elements (e.g., a resize handle div), the server-rendered HTML will lack those elements, while the client-rendered HTML will include them.
- **Observed Case (Feb 2026)**: In `SettingsPage`, a resize handle div was conditionally rendered using `{isTauri() && (<div ... />)}`.
- **Solution 1: isMounted State (Preferred)**:
  Use an `isMounted` flag to ensure the conditional element is only rendered after hydration is complete.
  ```tsx
  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => setIsMounted(true), []);
  
  return (
    <>
      {/* Ensure UI only renders client-only code after hydration */}
      {isMounted && isTauri() && (
        <div id="resize-handle" ... />
      )}
    </>
  );
  ```
- **Solution 2: Dynamic Import**:
  Disable SSR for the specific component using `next/dynamic`.
  ```tsx
  const SettingsPage = dynamic(() => import('./SettingsPage'), { ssr: false });
  ```
- **Pattern**: Avoid server/client divergence in the initial render tree. If an element depends on browser-only APIs, wait for the component to mount.
