# GCP Infrastructure & GPU Deployment Patterns

This document details the project-specific infrastructure patterns for deploying MeetChi's heavy-ML and serverless components on Google Cloud Platform.

---

## 1. Cloud Run v2 (GPU) Implementation

Cloud Run v2 requires specific combinations of resource limits and providers to enable hardware acceleration.

### 1.1 Mandatory Configuration (Terraform)
- **Provider**: The resource MUST be explicitly associated with the `google-beta` provider.
- **Launch Stage**: `launch_stage` MUST be set to `"BETA"`.
- **Resources**: NVIDIA L4 support requires a minimum of **4 vCPUs** and **16GiB RAM**.
- **GPU Limit**: Add `"nvidia.com/gpu" = "1"` to the `resources.limits` map.

### 1.2 The "CLI Promotion" Pattern
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

---

## 2. Serverless Light Pattern (Gemini-Centric)

For services offloading intelligence to externally managed APIs (e.g., Gemini), a lightweight CPU-only configuration is preferred to minimize costs and cold starts.

### 2.1 Optimized Configuration (Terraform)
- **Base Image**: `python:3.11-slim` or `alpine`.
- **Resources**: 1 vCPU and **512MiB RAM** are sufficient for Python/Flask API proxying.
- **Startup Probe**: Can be aggressive due to lack of heavy model loading.
  - `initial_delay_seconds = 5`
  - `period_seconds = 5`
- **Timeout**: Reduced to `300s` (from `900s`) as API responses are typically faster than local inference.

### 2.2 Advantages
1. **Zero Quota Friction**: Standard CPU/Memory quotas are generally abundant; no need for specific GPU quota requests.
2. **Atomic Rollouts**: Avoids the "3x Rollout Buffer" quota trap, allowing seamless deployments with `max_instances=1`.
3. **96% Cost Savings**: Comparing a $400/mo L4 GPU instance to a ~$15/mo serverless CPU instance (base cost).

---

## 3. Quota Management & Availability

### 2.1 The "3x Rollout Buffer" Pitfall
Cloud Run requires a regional quota of **3 GPUs** and **48GiB RAM** (`MemAllocPerProjectRegion`) to perform a non-disruptive, atomic rollout of a new revision, even when `max_instances=1` is specified.
- **Symptom**: `Quota violated: NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion requested: 3 allowed: 1`.
- **Verification**: Confirmed in Feb 2026 during MeetChi rollout.

### 2.2 The 1-Unit Workaround (Downtime Swap)
If you only have 1 unit of regional GPU quota, you must **delete the existing service** (`gcloud run services delete`) before deploying the new version to bypass the 3x transaction check.

---

## 4. Build & Registry Optimization

### 3.1 Targeted Build Submission
To avoid gigabyte-scale context uploads (e.g., local `node_modules` or `.venv`), navigate to the service directory before submitting:
```bash
cd apps/llm_service
gcloud builds submit --tag [TAG] .
```
- **Pattern**: Creating a targeted `.gcloudignore` inside the service folder prevents local build artifacts from being uploaded.

### 3.2 Artifact Registry Permissions
Verify that the **Compute Engine default service account** (`[PROJECT-NUMBER]-compute@developer.gserviceaccount.com`) has the following roles:
- `roles/artifactregistry.writer` (for push)
- `roles/artifactregistry.reader` (for Cloud Run pull)

---

## 5. Next.js Standalone for Serverless

### 4.1 Build Optimization
- **`output: 'standalone'`**: Essential for reducing image size and packaging dependencies.
- **Asset Persistence**: The standalone bundle does NOT include `public` or `.next/static`. These must be manually copied into the production container stage.

### 4.2 Frontend Env Var Injection
Variables prefixed with `NEXT_PUBLIC_` are baked at **build time**. 
- **Pattern**: Inject these via `--build-arg` during `gcloud builds submit`. They cannot be changed at runtime via Cloud Run console.

---

## 6. Security & Secret Lifecycle

### 5.1 Secret Mounting
Standard practice for MeetChi is to inject secrets (Gemini API Key, HF Token) as **environment variables sourced from Secret Manager versions**.
```hcl
env {
  name = "GEMINI_API_KEY"
  value_source {
    secret_key_ref {
      secret  = google_secret_manager_secret.gemini_key.secret_id
      version = "latest"
    }
  }
}
```

### 5.2 Token Verification (Auth.js)
MeetChi uses Google OAuth ID tokens.
1. **Frontend**: Captures `id_token` via NextAuth.js.
2. **Backend**: Verifies signature using `google-auth` library locally (low latency).
3. **Consistency**: Use `prompt: "consent"` in the OAuth provider config to ensure the `id_token` is consistently delivered across sessions.
## 7. Runtime Configuration Cleanup

### 7.1 Transitioning Tiers
When transitioning a service between **Tier 2 (Hybrid/GPU)** and **Tier 1 (Serverless Light)**, stale environment variables in the Cloud Run revision can cause functional failures.

- **The Stale Env Trap**: Updating only the container image via CLI (`gcloud run services update --image ...`) often preserves existing env vars (e.g., `HF_AUTH_TOKEN`, `MODEL_NAME`, `CUDA_VISIBLE_DEVICES`). 
- **Symptom**: New lightweight code may attempt to use legacy secrets or incorrectly initialized paths, leading to errors like `400 INVALID_ARGUMENT (API key not valid)` even if the new code seems correct.
- **Resolution**: Use `terraform apply` to explicitly synchronize the entire `template` spec. Terraform will detect and remove environment variables omitted from the HCL configuration, ensuring a clean runtime state. Note that if the error persists, the root cause shifts to the validity of the secret value itself rather than the environment configuration.

### 7.2 Service Account Permissions
Ensure the Cloud Run service account has `roles/secretmanager.secretAccessor` for **every** individual secret referenced. Adding a new secret (e.g., switching from HF to Gemini) requires updating the IAM policy.
