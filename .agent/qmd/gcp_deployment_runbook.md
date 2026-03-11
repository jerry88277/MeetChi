# GCP 部署實戰手冊 (Deployment Runbook)

本文件整合 MeetChi 專案部署至 GCP 的完整流程、實際操作步驟、踩坑紀錄與最佳實踐。作為一份可操作的 Runbook，涵蓋從本地建置到線上服務的端到端流程。

---

## 1. 專案基本資訊

| 項目 | 值 |
|------|-----|
| **GCP Project ID** | `project-51769b5e-7f0f-4a2f-80c` |
| **主要區域** | `asia-southeast1` (Singapore) |
| **前端備用區域** | `asia-east1` (Taiwan) |
| **Artifact Registry** | `asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/` |
| **GPU 類型** | NVIDIA L4 |
| **Terraform 目錄** | `terraform/` |

---

## 2. 線上服務清單 (Production Services)

截至 2026 年 2 月，以下服務已部署並運行：

| 服務名稱 | 區域 | URL | 用途 |
|----------|------|-----|------|
| `meetchi-backend` | asia-southeast1 | `https://meetchi-backend-wfqjx2j42q-as.a.run.app` | FastAPI 後端 API + WebSocket |
| `meetchi-llm-gpu` | asia-southeast1 | `https://meetchi-llm-gpu-wfqjx2j42q-as.a.run.app` | Gemini/LLM 摘要服務 |
| `meetchi-gpu-asr` | asia-southeast1 | `https://meetchi-gpu-asr-wfqjx2j42q-as.a.run.app` | GPU ASR 微服務 (Faster-Whisper) |
| `meetchi-frontend` | asia-southeast1 | `https://meetchi-frontend-wfqjx2j42q-as.a.run.app` | Next.js Web 前端 |
| `meetchi-frontend` | asia-east1 | `https://meetchi-frontend-wfqjx2j42q-de.a.run.app` | 前端 (台灣區域備份) |

---

## 3. 容器映像檔策略

MeetChi 採用**多層容器架構**，依據服務需求選擇不同的基底映像：

### 3.1 Backend (CPU-Only API)
- **Dockerfile**: `apps/backend/Dockerfile`
- **Base Image**: `python:3.10-slim`
- **用途**: FastAPI API 層、WebSocket 協調、Cloud Tasks 排程
- **映像大小**: ~200 MB
- **特色**: 不含 GPU 依賴，冷啟動 < 30 秒

### 3.2 Backend (GPU-Enabled)
- **Dockerfile**: `apps/backend/Dockerfile.gpu`
- **Base Image**: `nvidia/cuda:12.1.1-runtime-ubuntu22.04`
- **用途**: 完整後端 + 內建 ASR (Faster-Whisper)
- **資源需求**: 4 vCPU, 16 GiB RAM, 1x NVIDIA L4
- **特色**: 同時處理 API 請求與即時語音辨識

### 3.3 GPU ASR 微服務 (獨立)
- **Dockerfile**: `apps/backend/Dockerfile.gpu-service`
- **Base Image**: `nvidia/cuda:12.1.1-runtime-ubuntu22.04`
- **用途**: 專責 ASR 推論，最小化依賴
- **Port**: 8080 (Cloud Run GPU 預設)
- **啟動探針**: `start-period=120s`（模型載入需時）
- **特色**: 僅複製 `app/offline_asr.py`、`app/models.py` 和 `gpu_service/` 目錄，避免完整後端的依賴膨脹

### 3.4 Frontend (Next.js Standalone)
- **Dockerfile**: `apps/frontend/Dockerfile`
- **Base Image**: 多階段建置 — `node:20-alpine` (builder) → `node:20-alpine` (runner)
- **用途**: Next.js SSR 前端
- **關鍵**: `NEXT_PUBLIC_API_URL` 在建置時注入（Build-time ARG）
- **映像大小**: ~100 MB
- **Health Check**: `wget` (Alpine 不含 curl)

### 3.5 LLM Service (Lean / Gemini-Only)
- **Base Image**: `python:3.11-slim`
- **用途**: Gemini API 代理，不含本地模型
- **映像大小**: ~148 MB
- **資源**: 1 vCPU, 512 MiB RAM

---

## 4. 完整部署流程 (Step-by-Step)

### 4.1 前置準備

```powershell
# 1. GCP 認證
gcloud auth login
gcloud auth application-default login
gcloud config set project project-51769b5e-7f0f-4a2f-80c

# 2. 啟用必要 API
gcloud services enable cloudresourcemanager.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable cloudtasks.googleapis.com

# 3. 建立 Artifact Registry (僅首次)
gcloud artifacts repositories create meetchi `
  --repository-format=docker `
  --location=asia-southeast1 `
  --description="MeetChi Docker images"

# 4. 驗證 Terraform
cd terraform
terraform init
terraform plan
```

### 4.2 建置與推送映像檔

#### Backend (CPU)
```powershell
cd apps/backend
gcloud builds submit `
  --tag asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-backend:latest `
  --machine-type=e2-highcpu-8 `
  --timeout=2400s .
```

#### Backend (GPU)
```powershell
cd apps/backend
gcloud builds submit `
  --tag asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-backend-gpu:v7-polish `
  -f Dockerfile.gpu `
  --machine-type=e2-highcpu-8 `
  --timeout=3600s .
```

> **⚠️ 注意**: `gcloud builds submit` 不支援 `-f` 旗標。需使用 `cloudbuild.yaml` 配置檔指定自訂 Dockerfile，或將 `Dockerfile.gpu` 重新命名為 `Dockerfile`。

#### GPU ASR 微服務
```powershell
cd apps/backend
gcloud builds submit `
  --tag asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-gpu-asr:latest `
  -f Dockerfile.gpu-service `
  --machine-type=e2-highcpu-8 `
  --timeout=3600s .
```

#### Frontend
```powershell
cd apps/frontend
gcloud builds submit `
  --tag asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-frontend:latest `
  --build-arg NEXT_PUBLIC_API_URL=https://meetchi-backend-wfqjx2j42q-as.a.run.app .
```

#### LLM Service (Gemini-Only)
```powershell
gcloud builds submit --config cloudbuild-llm.yaml --project project-51769b5e-7f0f-4a2f-80c
```

### 4.3 部署至 Cloud Run

#### GPU 服務部署（需 GPU Quota）
```powershell
gcloud run deploy meetchi-backend-gpu `
  --image asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-backend-gpu:v7-polish `
  --gpu 1 --gpu-type nvidia-l4 `
  --no-gpu-zonal-redundancy `
  --max-instances 1 --min-instances 0 `
  --memory 16Gi --cpu 4 --port 8000 `
  --execution-environment gen2 `
  --allow-unauthenticated `
  --region asia-southeast1 `
  --project project-51769b5e-7f0f-4a2f-80c
```

#### LLM 服務部署（Serverless Light）
```powershell
gcloud run deploy meetchi-llm-gpu `
  --image asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-llm:latest `
  --memory 512Mi --cpu 1 `
  --max-instances 3 --min-instances 0 `
  --allow-unauthenticated `
  --region asia-southeast1
```

#### Frontend 部署
```powershell
gcloud run deploy meetchi-frontend `
  --image asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-frontend:latest `
  --memory 256Mi --cpu 1 `
  --max-instances 3 --min-instances 0 `
  --allow-unauthenticated `
  --region asia-southeast1
```

### 4.4 驗證健康狀態
```powershell
# PowerShell 驗證
Invoke-RestMethod https://meetchi-backend-wfqjx2j42q-as.a.run.app/health
Invoke-RestMethod https://meetchi-llm-gpu-wfqjx2j42q-as.a.run.app/health
Invoke-RestMethod https://meetchi-frontend-wfqjx2j42q-as.a.run.app/api/health
```

---

## 5. 環境變數與 Secrets 管理

### 5.1 Secret Manager 中的 Secrets
| Secret 名稱 | 用途 |
|-------------|------|
| `meetchi-db-password` | PostgreSQL 密碼 |
| `meetchi-hf-token` | HuggingFace Auth Token |
| `meetchi-secret-key` | JWT 簽名金鑰 |
| `meetchi-gemini-api-key` | Gemini API Key |

### 5.2 Frontend Build-time 變數
```
NEXT_PUBLIC_API_URL=https://meetchi-backend-wfqjx2j42q-as.a.run.app
```
> **關鍵**: `NEXT_PUBLIC_` 前綴變數在建置時烘焙 (baked)，無法在 Cloud Run console 中修改。

### 5.3 Frontend Runtime 變數
```
AUTH_SECRET=<隨機金鑰>
AUTH_URL=https://meetchi-frontend-wfqjx2j42q-as.a.run.app
```
> 透過 `gcloud run services update --set-env-vars` 設定。

---

## 6. 踩坑紀錄與最佳實踐

### 6.1 GPU Quota 的 3x 陷阱
即使設定 `max_instances=1`，Cloud Run 在部署新 Revision 時需要 **3 倍**的 GPU/記憶體 Quota 進行原子性部署。
- **症狀**: `Quota violated: NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion requested: 3 allowed: 1`
- **解法 (Quota=1)**: 先刪除舊服務再部署新版本
  ```powershell
  gcloud run services delete meetchi-backend-gpu --region asia-southeast1
  gcloud run deploy meetchi-backend-gpu --image ... --gpu 1 ...
  ```

### 6.2 Build Context 過大
本地 `node_modules`、`.venv`、`models/` 會導致上傳 context 高達 10 GB+。
- **解法**: 從子目錄提交（`cd apps/backend && gcloud builds submit .`）
- **結果**: Backend context 從 >1GB 降至 ~1.9 MiB

### 6.3 Artifact Registry 權限
- Cloud Build 預設使用 `[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`
- **必要角色**: `roles/artifactregistry.writer` + `roles/storage.objectAdmin`
- **症狀**: "Retry budget exhausted" 實際是權限不足的靜默失敗

### 6.4 環境變數殘留 (Stale Env Trap)
切換服務層級（GPU → CPU）時，舊的環境變數（如 `CUDA_VISIBLE_DEVICES`、`HF_AUTH_TOKEN`）會殘留在新 Revision 中。
- **解法**: 使用 `terraform apply` 全量同步，或在 `gcloud run deploy` 時使用 `--clear-env-vars` + `--set-env-vars`

### 6.5 Frontend Auth 500 錯誤
NextAuth.js 在 Cloud Run 上需要 `AUTH_SECRET` 和 `AUTH_URL` 環境變數，未設定會導致 500 Server Error。
- **解法**: `gcloud run services update meetchi-frontend --set-env-vars AUTH_SECRET=xxx,AUTH_URL=https://...`

### 6.6 cloudbuild.yaml 的 -f 限制
`gcloud builds submit` **不直接支援** `-f` 指定 Dockerfile。解決方案：
1. 使用 `cloudbuild-xxx.yaml` 配置檔：在 args 中指定 `-f Dockerfile.gpu`
2. 臨時重命名 `Dockerfile.gpu` → `Dockerfile`

### 6.7 GPU 服務部署逾時
GPU 模型載入（Whisper + Pyannote）需 2-5 分鐘，Cloud Run 預設 `startup_probe` 需設定 `initial_delay_seconds >= 120`。

---

## 7. CloudBuild 配置範本

### 7.1 Backend 標準建置 (`cloudbuild-backend.yaml`)
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '--no-cache', '-t',
      'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest', '.']
    dir: 'apps/backend'
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push',
      'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest']
images:
  - 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-backend:latest'
options:
  logging: CLOUD_LOGGING_ONLY
  machineType: 'E2_HIGHCPU_8'
timeout: '3600s'
```

### 7.2 LLM GPU 建置 (`cloudbuild-llm.yaml`)
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t',
      'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-llm:latest',
      '-f', 'Dockerfile.gpu', '.']
    dir: 'apps/llm_service'
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push',
      'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-llm:latest']
images:
  - 'asia-southeast1-docker.pkg.dev/$PROJECT_ID/meetchi/meetchi-llm:latest'
options:
  machineType: 'E2_HIGHCPU_8'
  logging: CLOUD_LOGGING_ONLY
timeout: '3600s'
```

---

## 8. 成本估算

| 服務 | 配置 | 估算月費 |
|------|------|----------|
| Cloud Run (GPU) | 1x L4, 4CPU/16GiB, scale-to-zero | $150 - $240 |
| Cloud Run (LLM) | 1CPU/512MiB, serverless | ~$15 |
| Cloud Run (Frontend) | 1CPU/256MiB, serverless | ~$5 |
| Cloud SQL | db-g1-small, PostgreSQL | $25 - $40 |
| Cloud Tasks | Serverless queue | $0 (Free Tier) |
| Cloud Storage | Audio files | ~$5 |
| **合計** | | **~$200 - $305/月** |

> `min_instances = 0` 確保閒置時不產生計算費用。

---

## 9. 常用操作速查

### 查看服務狀態
```powershell
gcloud run services list --project project-51769b5e-7f0f-4a2f-80c --region asia-southeast1
```

### 查看日誌
```powershell
gcloud run services logs read meetchi-backend --region asia-southeast1 --limit 50
```

### 更新環境變數
```powershell
gcloud run services update meetchi-frontend `
  --set-env-vars "AUTH_SECRET=xxx,AUTH_URL=https://..." `
  --region asia-southeast1
```

### 回滾至上一版本
```powershell
# 列出 Revisions
gcloud run revisions list --service meetchi-backend --region asia-southeast1
# 回滾
gcloud run services update-traffic meetchi-backend `
  --to-revisions REVISION_NAME=100 `
  --region asia-southeast1
```

---

## 10. Terraform IaC 部署

Terraform 是 MeetChi 基礎設施的**宣告式管理方式**，適合一次性佈建完整堆疊或需要可重複部署的場景。與手動 `gcloud` 部署互補使用。

### 10.1 檔案結構

```
terraform/
├── main.tf              # Provider 設定 (google + google-beta) + API 啟用
├── variables.tf         # 變數宣告 (project_id, region, images, GPU, secrets)
├── cloudrun.tf          # Cloud Run 服務定義 (Backend + LLM) + IAM
├── database.tf          # Cloud Tasks Queues + GCS Bucket + Secret Manager
├── outputs.tf           # 輸出值 (URLs, Queue names, GPU Quota 指引)
├── terraform.tfvars     # 實際變數值 (⚠️ 含機敏資料，勿提交 Git)
└── terraform.tfvars.example  # 變數範本
```

### 10.2 Provider 配置

Terraform 同時使用 `google` 和 `google-beta` 兩個 Provider：
- **`google`**: 標準資源（GCS、Secret Manager、Cloud Tasks）
- **`google-beta`**: Cloud Run v2 GPU 相關功能（`launch_stage = "BETA"`）

```hcl
terraform {
  required_version = ">= 1.0"
  required_providers {
    google      = { source = "hashicorp/google",      version = "~> 5.0" }
    google-beta = { source = "hashicorp/google-beta",  version = "~> 5.0" }
  }
}
```

### 10.3 terraform.tfvars 範本

```hcl
# MeetChi GCP Deployment Configuration
project_id    = "project-51769b5e-7f0f-4a2f-80c"
region        = "asia-southeast1"

# Docker Images (Artifact Registry)
backend_image     = "asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-backend:latest"
llm_service_image = "asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-llm-gpu:latest"

# Secrets (sensitive)
hf_auth_token  = "hf_..."
secret_key     = "..."        # JWT Secret (openssl rand -hex 32)
gemini_api_key = "AIzaSy..."

# GPU / Scaling
gpu_enabled   = true
gpu_type      = "nvidia-l4"
min_instances = 0   # Scale to zero
max_instances = 3
```

### 10.4 Terraform Apply 流程

```powershell
cd terraform

# 1. 初始化 (首次或 provider 更新後)
terraform init

# 2. 檢視變更計畫
terraform plan

# 3. 套用變更
terraform apply -auto-approve

# 4. 查看輸出 (Backend URL, LLM URL 等)
terraform output
```

**預估耗時**：
| 資源 | 建立時間 |
|------|----------|
| API 啟用 | ~1-2 分鐘 |
| Cloud Tasks Queue | ~1-2 分鐘 |
| GCS Bucket | ~30 秒 |
| Secret Manager | ~30 秒 |
| Cloud Run Service | ~2-3 分鐘 |
| **整體** | **~5-10 分鐘** |

### 10.5 Terraform 管理的資源

| 資源類型 | 名稱 | 說明 |
|----------|------|------|
| `google_cloud_run_v2_service` | `meetchi-backend` | FastAPI 後端 (CPU, 2vCPU/4GiB, GCS FUSE) |
| `google_cloud_run_v2_service` | `meetchi-llm-gpu` | Gemini LLM 服務 (CPU 1vCPU/1GiB) |
| `google_cloud_tasks_queue` | `meetchi-transcription-queue` | ASR 任務佇列 (10 dispatches/s) |
| `google_cloud_tasks_queue` | `meetchi-summarization-queue` | 摘要任務佇列 (5 dispatches/s) |
| `google_storage_bucket` | `${project_id}-meetchi-audio` | 音檔 + SQLite (GCS FUSE) |
| `google_secret_manager_secret` | `meetchi-hf-token` | HuggingFace Token |
| `google_secret_manager_secret` | `meetchi-secret-key` | JWT 金鑰 |
| `google_secret_manager_secret` | `meetchi-gemini-api-key` | Gemini API Key |
| `google_service_account` | `meetchi-cloudrun` | 服務帳號 |

### 10.6 CLI Promotion Pattern (Terraform + gcloud 混合策略)

Terraform `google-beta` provider **不支援**所有 Cloud Run GPU 屬性（如 `--no-gpu-zonal-redundancy`）。MeetChi 採用**混合策略**：

1. **Terraform 負責**: IAM、Secrets、GCS Bucket、Cloud Tasks、基礎 Cloud Run 服務定義
2. **gcloud CLI 負責**: GPU 配置、Zonal Redundancy 設定、手動 image 更新

```powershell
# Step 1: Terraform 佈建基礎設施
terraform apply -auto-approve

# Step 2: gcloud 套用 GPU 配置 (Terraform 無法處理的部分)
gcloud alpha run services update meetchi-llm-gpu `
  --gpu=1 --gpu-type=nvidia-l4 `
  --no-gpu-zonal-redundancy `
  --memory=16Gi --cpu=4 `
  --region asia-southeast1
```

> **⚠️ 注意**: 執行上述 `gcloud` 指令後，下次 `terraform apply` 可能會偵測到 drift（因為 Terraform state 與實際資源不一致）。建議使用 `terraform import` 或在 HCL 中加上 `lifecycle { ignore_changes = [...] }` 來避免衝突。

### 10.7 重要架構遷移紀錄

#### Cloud SQL → SQLite on GCS FUSE (2026-02-11)
- **Before**: `google_cloud_sql_database_instance` (db-g1-small, ~$30/月)
- **After**: `google_storage_bucket` + GCS FUSE volume mount (`/mnt/gcs/db/meetchi.db`)
- **原因**: 降低成本（GCS 幾乎免費 vs Cloud SQL $30/月）、簡化架構
- **Terraform 變更**: `database.tf` 中的 Cloud SQL 資源已移除，`cloudrun.tf` 中新增 GCS FUSE volume mount
- **DATABASE_URL**: `sqlite:////mnt/gcs/db/meetchi.db`

#### Redis → Cloud Tasks (2026-02)
- **Before**: `google_redis_instance` (Memorystore, ~$40/月)
- **After**: `google_cloud_tasks_queue` (Free Tier)
- **節省**: ~$40/月

### 10.8 Terraform 踩坑紀錄

| 問題 | 症狀 | 解法 |
|------|------|------|
| **GPU 語法錯誤** | `node_selector` 不被支援 | 使用 `resources.limits["nvidia.com/gpu"] = "1"` |
| **Dangling 參考** | Redis/Cloud SQL 移除後 `depends_on` 失效 | 清理所有相關的 `depends_on`、`env` 引用 |
| **Repository 名稱不一致** | push 失敗（`meetchi` vs `meetchi-repo`） | 確保 `tfvars` 中的 image path 與 AR repo 名稱一致 |
| **環境變數殘留** | 更新 image 但舊 env vars 保留 | `terraform apply` 會全量同步 template spec |
| **Secret 權限** | 新增 secret 後 Cloud Run 403 | 確認 SA 有 `secretmanager.secretAccessor` |
| **State drift** | gcloud 手動修改 GPU 後 Terraform 偵測 drift | 使用 `lifecycle { ignore_changes }` |
