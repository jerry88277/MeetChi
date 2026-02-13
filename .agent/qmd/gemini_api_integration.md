# Gemini 2.5 Flash Lite API Integration

## 1. Problem Context: The "Processing" Deadlock
Meeting summaries were observed to be stuck in `PROCESSING` indefinitely due to the `meetchi-llm-gpu` service running in CPU-only mode (pending GPU quota). The local `Llama-Breeze` model failed to load, leading to null summary outputs and broken state transitions.

## 2. Solution: Serverless Gemini Engine
Integration of **Gemini 2.5 Flash Lite** allows summarization to run on standard Cloud Run CPU slots, bypassing GPU dependencies while maintaining high quality and structured output.

## 3. Implementation Details

### 3.1 Dependencies
- **SDK**: `google-genai>=1.0.0`
- **Validation**: `pydantic>=2.0.0`

### 3.2 Structured Output Schemas
To ensure predictable JSON responses across different meeting templates, Pydantic models are passed directly to the Gemini SDK:

```python
class GeneralSummary(BaseModel):
    summary: str
    action_items: List[str]
    decisions: List[str]
    risks: List[str]

class SalesBANTSummary(BaseModel):
    summary: str
    BANT: BANTInfo # Budget, Authority, Need, Timeline
    next_steps: List[str]

class HRSTARSummary(BaseModel):
    candidate_summary: str
    STAR_stories: List[STARStory] # Situation, Task, Action, Result
    key_strengths: List[str]

class RDSummary(BaseModel):
    summary: str
    technical_decisions: List[TechnicalDecision]
    challenges: List[Challenge]
    risks: List[Risk]
    action_items: List[ActionItem]
```

### 3.3 Normalization Logic
Since the backend expects a standard JSON structure for the Dashboard (Scenario 2), the LLM service normalizes template-specific fields back to the core fields (`summary`, `action_items`, etc.):

- **Sales BANT**: Maps `next_steps` to `action_items`.
- **HR STAR**: Maps `candidate_summary` to `summary`.
- **R&D**: Flattens task objects into string lists for `action_items`.

### 3.4 Request Pattern (Google GenAI SDK)
```python
response = gemini_client.models.generate_content(
    model=GEMINI_MODEL,
    contents=f"{template.system_prompt}\n\n{user_prompt}",
    config={
        "response_mime_type": "application/json",
        "response_json_schema": schema_class.model_json_schema(),
        "temperature": 0.2,
        "max_output_tokens": 4096
    }
)
```
*Note: Using `response_json_schema` with `model_json_schema()` is required for Pydantic classes in the GenAI Python SDK (Feb 2026).*

## 4. Infrastructure (Terraform) Implementation

To securely manage the Gemini API integration, the following Terraform pattern was implemented:

### 4.1 Secret Manager Selection
The `GEMINI_API_KEY` is not stored in plain text. It is managed via **Google Secret Manager**:
```hcl
# database.tf
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "meetchi-gemini-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "gemini_api_key" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key
}
```

### 4.2 Cloud Run Environment Injection
The LLM service is configured to use Gemini as the primary engine through environment variables:
```hcl
# cloudrun.tf
env {
  name  = "USE_GEMINI"
  value = "true"
}

env {
  name = "GEMINI_API_KEY"
  value_source {
    secret_key_ref {
      secret  = google_secret_manager_secret.gemini_api_key.secret_id
      version = "latest"
    }
  }
}

env {
  name  = "GEMINI_MODEL"
  value = "gemini-2.5-flash-lite-preview-06-17"
}
```

### 4.3 Persistence in terraform.tfvars
To ensure consistency across deployments, the API key is persisted in the local `terraform.tfvars` file:
```hcl
# terraform.tfvars
gemini_api_key = "AIzaSy..." # Obtained from GCP Console
```

## 5. Strategic Analysis (First Principles & MECE)

### 5.1 First Principles: Resolving the "Processing Deadlock"
- **Fundamental Requirement**: Generate a structured meeting summary from a specific character stream.
- **Resource Constraint**: Local LLM inference requires ~8GB+ VRAM. Cloud Run CPU instances provide high compute but zero VRAM by default.
- **Mismatch**: Deploying a GPU-dependent model (Breeze) on a CPU-heavy instance causes a "Deadlock" (Load failure -> Null output -> Processing hang).
- **Core Solution (Capability Offloading)**: Since "Intelligence" is commodity-accessible via API, we separate **transcription (local/GPU)** from **abstraction (external/API)**. This offloads the VRAM requirement to a managed SaaS environment while maintaining data structure integrity via Pydantic.

### 5.2 MECE Breakdown of the Summary Pipeline

| Component | Function | Implementation |
|-----------|----------|----------------|
| **Ingestion** | Capture & Buffer | Tauri Client + GCS |
| **Orchestration** | Async Triggering | Cloud Tasks (HTTP Target) |
| **Abstraction** | Intelligence / LLM | Gemini 2.5 Flash Lite |
| **Validation** | Schema Integrity | Pydantic (python-genai SDK) |
| **Persistence** | Data Mapping | Backend FastAPI (SQLAlchemy) |
| **Delivery** | Visual Display | Next.js Dashboard |

## 6. Operational Flow (Tier 1 Optimized)
1. **Primary**: Attempt Gemini API call (requires `GEMINI_API_KEY`).
2. **Failure Handling**: If Gemini fails or is unconfigured, the service returns a 503 error with diagnostic details.
3. **Note on Fallbacks**: Local model fallbacks (Breeze/WhisperX) have been **completely removed** from the `meetchi-llm-gpu` production service in Feb 2026. The logic now uses Gemini exclusively, returning a clean 500 error if the API fails, which simplifies troubleshooting and avoids the "No model available" ambiguity.
4. **Outcome**: Ensures high reliability, 5-second cold starts, and 99.8% reduction in image size.

## 5. Configuration
| Var | Description | default |
|---|---|---|
| `USE_GEMINI` | Toggle Gemini path | `true` |
| `GEMINI_API_KEY` | GCP/AI Studio Key | (secret) |
| `GEMINI_MODEL` | Chosen model | `gemini-2.5-flash-lite-preview-06-17` |

## 7. Deployment Pitfalls & Troubleshooting

During the specialized Ultrawork deployment phase, two critical issues were identified and resolved via automated browser orchestration:

### 7.1 Project ID Inaccessibility
- **Issue**: Attempting to deploy to an intuitive but incorrect project handle (e.g., `meetchi-446907`) resulted in permission errors.
- **Resolution**: Resources (Cloud Run, Secret Manager) were verified to be in the generated project `project-51769b5e-7f0f-4a2f-80c`. This project ID has been confirmed and persisted in `terraform.tfvars`. Always verify the active project using `gcloud config get-value project` or checking resource existence in the console.

### 7.2 API Enablement (Silent Disablement)
- **Issue**: Even with the correct API Key, calls to the Gemini API failed because the **Generative Language API** was disabled by default in a new project.
- **Resolution**: Manually enabled the API via the Google Cloud API Library.
- **Terraform Note**: Consider adding a `google_project_service` resource to Terraform to automate this enablement:
  ```hcl
  resource "google_project_service" "gemini" {
    service = "generativelanguage.googleapis.com"
  }
  ```

### 7.3 Secret Manager Versioning
- **Note**: When updating the `gemini_api_key` via Terraform, Cloud Run is configured to use the `latest` version. Ensure rotation or updates correctly trigger a new version if hardcoded versions are used elsewhere.

### 7.4 Verification: Health Check Signatures
To verify if Gemini is actually active vs. a silent fallback occurring, inspect the `/health` endpoint output:

- **Active Gemini (Success)**:
  `{"status": "ready", "use_gemini": true, "gemini_model": "..."}`
- **Mock Fallback (Failure)**:
  `{"status": "ready", "mock_mode": true, "device": "cpu"}`
  - **Interpretation**: This signature indicates that the `gemini_client` failed to initialize AND the local model failed to load. The system is in a "Stealth Fallback" state where it responds to health checks but cannot perform real inference.

### 7.5 Initialization Fallbacks (Silent Failures)
The LLM service uses a protective `try-except` block during startup. If `google-genai` is missing from the build or the API key is invalid, it sets `USE_GEMINI = False`.
- **Root Cause 1: Missing Library**: If `google-genai` is not correctly pinned in `requirements.txt` or the Docker layer cache is stale.
- **Root Cause 2: Secret Permission**: Even if the secret exists, the Cloud Run service account must have `roles/secretmanager.secretAccessor` permission to read it.

## 8. Finalized Pydantic Schemas

The following schemas are used for structured output generation with Gemini 2.5 Flash Lite. These are passed to the `response_schema` parameter in the GenAI SDK.

```python
class GeneralSummary(BaseModel):
    summary: str
    action_items: List[str]
    decisions: List[str]
    risks: List[str]

class BANTInfo(BaseModel):
    Budget: str
    Authority: str
    Need: str
    Timeline: str

class SalesBANTSummary(BaseModel):
    summary: str
    BANT: BANTInfo
    next_steps: List[str]

class STARStory(BaseModel):
    Situation: str
    Task: str
    Action: str
    Result: str

class HRSTARSummary(BaseModel):
    candidate_summary: str
    STAR_stories: List[STARStory]
    key_strengths: List[str]
```

## 9. Explicit Health Signaling Implementation

To differentiate between a healthy Local GPU state and a "Degraded" but operational API Fallback state, the `/health` endpoint signature was updated as follows:

```python
@app.route('/health', methods=['GET'])
def health_check():
    gemini_available = gemini_client is not None
    return jsonify({
        "status": "ready",
        "gemini_enabled": gemini_available,
        "gemini_model": GEMINI_MODEL if gemini_available else None,
        "mock_mode": MOCK_LLM,
        "version": "2.0.0-gemini-only"
    }), 200
```

## 10. Build Lifecycle & Log Verification

When deploying the GPU-capable image via Cloud Build, the following markers in the `command_status` or Cloud Build logs confirm a healthy build environment for Gemini:

- **Base Image**: `nvidia/cuda:12.1.0-runtime-ubuntu22.04` (Crucial for GPU-based local model fallback).
- **Core Dependencies**:
  - `torch-2.10.0` (or latest compatible) ~915MB download.
  - `google-genai` (Requirement for API communication).
  - `transformers`, `mtkresearch`.
- **Optimization Signatures**: 
  - `Uploading tarball... totals 42.1 KiB` (indicates successful context minimization via subdirectory targeting or `.gcloudignore`).
  - **Heavy Dependency Markers**: `Downloading torch-2.10.0... (915.6 MB)` is the primary build bottleneck. Expect ~1-2 minutes for this step alone on standard Cloud Build machines.
  - **Version Transition**: Logs show `Successfully uninstalled torch-2.1.0+cu121` and `Successfully installed torch-2.10.0`. This upgrade ensures compatibility with the latest `google-genai` and `accelerate` features.
  - **Build Progress**: `Step 12/17 whisperx complete` signifies that the multi-gigabyte dependency installation phase is finished and the build is entering the application layer finalization.

### 10.1 Post-Deployment Verification
Run the following PowerShell command to verify the service is running in **Tier 1 (API-Only) Mode**:
```powershell
Invoke-RestMethod -Uri "[SERVICE_URL]/health" | ConvertTo-Json
```
**Expected Response**:
```json
{
    "status": "ready",
    "gemini_enabled": true,
    "gemini_model": "gemini-2.5-flash-lite-preview-06-17",
    "mock_mode": false,
    "version": "2.0.0-gemini-only"
}
```
*Note: The `version` flag and the absence of `local_model_loaded` confirm the production environment has successfully transitioned to the optimized, lightweight orchestrator.*

### 10.2 Registry Push Stability
For images > 1GB (containing Torch/CUDA), the push phase to Artifact Registry may show multiple layers "Waiting" or "Pushing" simultaneously. 
- **Wait Pattern**: If a layer (e.g., the 900MB Torch layer) appears to hang, it is likely being uploaded in segments. Do not cancel the build unless no progress is shown for > 10 minutes.

### 10.3 Build Success Confirmation (Feb 2026)
Cloud Build ID `26bd2fe5-86b1-444e-889d-ab6ed414aabd` was confirmed **SUCCESSFUL** (Exit Code: 0) after approximately 11 minutes. This build successfully transitioned the environment to **Torch 2.10.0** and **google-genai 1.0.0**, resolving the previous library version conflicts.

### 10.4 Final Deployment Command
To deploy the verified image from Artifact Registry to Cloud Run, use the following production-hardened command:
```powershell
gcloud run services update meetchi-llm-gpu `
  --image=asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-llm-gpu:latest `
  --region=asia-southeast1
```
*Note: Using backticks (`) for line continuation in PowerShell. For Bash, use backslash (\).*

## 11. Local Development Configuration

Unlike the Cloud Run production environment where secrets are injected automatically, local developers must manually configure API keys to enable Gemini.

- **Environment Variable**: `GEMINI_API_KEY`
- **Location**: Define in `apps/llm_service/.env` (excluded from git) or current shell.
- **Validation**: If `/health` reports `"gemini_enabled": false` while running on a local GPU, check that the key matches the value in Secret Manager (`meetchi-gemini-api-key`).

## 12. Template Design Principles (MECE)
The following design principles guide the expansion of the summarization system:

### 12.1 Framework Design
- **MECE Alignment**: Templates are designed so business needs (Sales, R&D, HR) are mutually exclusive and collectively exhaustive.
- **JSON Schema Validation**: Injected directly into Gemini prompts via Pydantic models.
- **Traceability**: Future goal of linking action items to word-level timestamps.

### 12.2 Template Specs
- **Sales (Revenue & Friction)**:
    - **Target**: Prospective revenue, competitor friction, customer pain points, and CRM next steps.
    - **Current Support**: `SalesBANTSummary` (BANT+Next Steps).
- **R&D (Production Health)**:
    - **Target**: Technical feasibility, resource blockers, prototype milestones, scope refinement, and parking lot ideas.
    - **Current Support**: `RDSummary` (Technical Decisions, Challenges, Actions).
- **HR & Legal**:
    - **HR**: Policy implications, cultural sentiment, and headcount changes (`HRSTARSummary`).
    - **Legal/Board**: Risk identification, regulatory citations, liability mitigation, formal resolutions, and quorum confirmation (Planned).
- **Finance**:
    - **Target**: Budget variance rationale, cash flow forecast, audit requirements, and period adjustments (Planned).

### 12.3 Implementation Gap Analysis (Feb 2026)
Current gaps in `templates.py` vs MECE standard:
- **Sales**: Needs "Customer Pain Points" field.
- **R&D**: Needs "Parking Lot" and "Artifact Links".
- **Legal/Finance**: No dedicated templates yet. 
- **Next Steps**: Expand `templates.py` models and update backend JSON normalization.

## 13. Verifying Health vs. Execution (The Fallback Trap)
A successful `/health` response does **not** guarantee a successful `/summarize` call.

- **Healthy Signature**: `{ "gemini_enabled": true }` only confirms the client was initialized (key exists, library loaded).
- **Execution failure**: If the API key is invalid, quota is exceeded, or the **SDK parameters are incorrect**, `generate_content` will raise an exception.
- **The SDK Parameter Trap**: As of early 2026, the `google-genai` Python SDK requires `response_json_schema` with the `.model_json_schema()` method when providing a Pydantic class. Using the `response_schema` parameter directly with a Pydantic class will trigger a `google.genai.errors.ClientError` or `ServerError`.
    - **Correct Pattern**:
      ```python
      response = gemini_client.models.generate_content(
          model=MODEL_NAME,
          contents=prompt,
          config={
              "response_mime_type": "application/json",
              "response_json_schema": MyPydanticClass.model_json_schema()
          }
      )
      ```
- **The Trap**: The current fallback logic attempts to use the local model on failure. On Cloud Run (CPU), the local model is usually `None`, leading to a generic `"error": "No model available"` response which masks the Gemini API error.
- **Verification**: Always test the `/summarize` endpoint with sample text after a new deployment to confirm the API pipeline is end-to-end functional.

## 14. Text Polishing & Translation (`/polish`)

The `/polish` endpoint leverages Gemini for bilingual text refinement, providing both natural Chinese flow and an English translation in a single pass.

### 14.1 Implementation Pattern
```python
@app.route('/polish', methods=['POST'])
def polish_text():
    # ... request validation ...
    prompt = f"""請幫我潤色以下文字，使其更通順自然。同時提供英文翻譯。
請以 JSON 格式回覆，包含 "refined" (潤色後的中文) 和 "translated" (英文翻譯) 兩個欄位。

原文：{raw_text}"""

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "temperature": 0.3
        }
    )
    
    result = json.loads(response.text)
    return jsonify({
        "polished_text": result.get("refined", raw_text),
        "translated": result.get("translated", "")
    })
```

### 14.2 Error Handling
If the API call fails, the service returns a 500 error. The `mock_mode` fallback provides a static string to prevent breaking the frontend during testing.

---

## 15. Docker Image Rationalization (API-Only vs. Hybrid)

As the project transitions to Gemini API for summarization, the necessity of a 5GB+ Docker image is re-evaluated based on functional requirements:

### 14.1 Tier 1: API-Only (Gemini Only)
- **Base Image**: `python:3.10-slim`
- **Dependencies**: Exclude `torch`, `cuda-runtime`, `whisperx`, and `transformers`.
- **Image Size**: ~300-500 MB.
- **Benefits**: Faster Cold Starts on Cloud Run, lower storage costs, and simplified `requirements.txt`.
- **Constraint**: No local ASR or LLM fallback capability.

### 14.2 Tier 2: Hybrid (Local GPU + Gemini Fallback)
- **Base Image**: `nvidia/cuda:12.1.0-runtime-ubuntu22.04`
- **Dependencies**: Include `torch`, `whisperx`, etc.
- **Image Size**: ~5-8 GB.
- **Rationality**: Justified ONLY if 100% availability/privacy (local model) is a requirement that outweighs the operational cost of large images.

### 14.3 Validated Migration (Feb 6, 2026)
The production service `meetchi-llm-gpu` has successfully migrated to **Tier 1 (API-Only)**. 
- **Result**: Image size reduced from ~15GB to **148MB**. 
- **Operation**: The service now runs exclusively on CPU slots, significantly reducing costs and deployment time while utilizing Gemini 2.5 Flash Lite for all `summarize` and `polish` tasks.
---

## 16. Case Study: The "Stale Masking" 400 Error (Feb 6, 2026)

During the final cutover to Tier 1, the `/summarize` endpoint returned a `400 INVALID_ARGUMENT` while the `/health` endpoint correctly reported `gemini_enabled: true`.

### 16.1 Diagnostics
- **Symptom**: `{"error": "400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key."}`.
- **Initial Assumption**: Stale environment variables (`HF_AUTH_TOKEN`, `MODEL_NAME`) were polluting the context.
- **Interim Resolution**: A full `terraform apply` was performed to purge the legacy variables. 
- **Persistence**: Even with a clean "Tier 1" configuration, the 400 error persisted, despite `/health` reporting `gemini_enabled: true`.

### 16.2 Root Cause: Invalid Secret Value
Accessing the secret directly revealed the underlying issue:
```powershell
gcloud secrets versions access latest --secret=meetchi-gemini-api-key
# Output: AIzaSyCt3px4MmHnxIC6cloMRfT0OsPjyBwvpjs
```
The key was valid in format but rejected by the Gemini API, indicating it had been **revoked, expired, or was never properly linked** to the target production project in Google AI Studio.

### 16.3 Final Resolution
1.  **Regeneration**: Navigate to [Google AI Studio API Keys](https://aistudio.google.com/app/apikey).
2.  **Project Binding**: Ensure the key is generated for or bound to the specific GCP Project ID (`project-51769b5e-7f0f-4a2f-80c`).
3.  **HCL Update**: Update `gemini_api_key` in `terraform.tfvars`.
4.  **Sync**: Run `terraform apply` to push the new secret version to Secret Manager.

- **Lesson**: /health signaling `gemini_enabled: true` only confirms the *presence* of a key, not its *validity*. Always verify the actual key string if 400 errors occur in a clean environment.
