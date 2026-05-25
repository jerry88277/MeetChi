# MeetChi GCP 部署指南（Terraform Quick Reference）

> **本文件聚焦**：已有 GCP 專案 + Service Account 後，怎麼用 Terraform + Cloud Build 跑起 MeetChi 整套服務（backend / frontend / gpu-asr / migrate job + 周邊 GCP 資源）。

## 📋 前置需求

- GCP 專案已建立
- `gcloud` CLI 已安裝並授權（`gcloud auth login` + `gcloud auth application-default login`）
- Terraform >= 1.0
- Docker（本機 build 才需要；推薦走 Cloud Build）
- Cloud Run GPU quota（asia-southeast1）— 預設 0，要申請至少 2 才能跑 `meetchi-gpu-asr` 平行 ASR

---

## 🏗️ 服務拓樸

| 服務 | 類型 | TF 資源 | Image build config |
|---|---|---|---|
| `meetchi-backend` | Cloud Run service | `cloudrun.tf` `backend` | `cloudbuild-backend.yaml` |
| `meetchi-frontend` | Cloud Run service | `cloudrun.tf` `frontend` | `apps/frontend/cloudbuild-frontend.yaml` |
| `meetchi-gpu-asr` | Cloud Run service (L4 GPU) | `cloudrun.tf` `gpu_asr` | `cloudbuild-gpu-asr.yaml` |
| `db-migrate-v19` | Cloud Run **Job**（alembic） | `cloudrun.tf` `db_migrate` | 共用 backend image |
| Cloud SQL `meetchi-db-pg` | PostgreSQL 15 + pgvector | `database.tf` | n/a |
| GCS `meetchi-audio` / `meetchi-db` | Audio + DB backup bucket | `database.tf` | n/a |
| Cloud Tasks (transcription / summarization) | Job queue | `database.tf` | n/a |
| Secret Manager (db_password / hf_token / secret_key / gemini_api_key) | Secrets | `database.tf` | n/a |

> ⚠️ **`meetchi-llm-gpu` 已退役**（2026-04）。原 LLM 服務改用 Gemini API direct call（ADC + Vertex AI），不再需要自架 GPU LLM。`var.llm_service_image` 保留為歷史相容，未在資源中引用。

---

## 🚀 首次部署流程

### 1. 設定 Terraform 變數

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

編輯 `terraform.tfvars`：
```hcl
project_id     = "your-project-id"
region         = "asia-southeast1"  # 必須是 GPU-supported region
hf_auth_token  = "hf_..."
secret_key     = "jwt-secret-..."
gemini_api_key = ""  # 留空走 ADC (Vertex AI)；若用 AIStudio API Key 才填
discord_webhook_url = ""  # 可選
```

### 2. 申請 GPU 配額

> ⚠️ `asia-east1` 不支援 Cloud Run GPU；`asia-southeast1` (新加坡) 是離台灣最近的 GPU region。

1. [GCP Console > IAM > Quotas](https://console.cloud.google.com/iam-admin/quotas)
2. 篩選: `Service: Cloud Run Admin API`
3. 搜尋: `Total Nvidia L4 GPU allocation, per project per region`
4. 選擇地區: `asia-southeast1`
5. **申請至少 2 個 GPU**（對齊 Phase A.1 `ASR_PARALLELISM` 預設值）
6. 等待 ~1-2 工作天審核

### 3. 初始化 Terraform

```bash
terraform init
terraform plan
```

### 4. 既有服務 IaC 接管（**僅首次** apply 前）

`backend / frontend / gpu-asr / migrate job` 若已用 gcloud 手動建過，需先 import 進 state 避免 plan 嘗試重建：

```bash
# gpu-asr
terraform import google_cloud_run_v2_service.gpu_asr \
  projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-gpu-asr

# backend
terraform import google_cloud_run_v2_service.backend \
  projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-backend

# frontend (2026-05-25 P0 補)
terraform import google_cloud_run_v2_service.frontend \
  projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-frontend

# migrate job (2026-05-25 P0 補)
terraform import google_cloud_run_v2_job.db_migrate \
  projects/${PROJECT_ID}/locations/asia-southeast1/jobs/db-migrate-v19

# IAM bindings（public access）
terraform import google_cloud_run_v2_service_iam_member.backend_public \
  "projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-backend roles/run.invoker allUsers"
terraform import google_cloud_run_v2_service_iam_member.frontend_public \
  "projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-frontend roles/run.invoker allUsers"
terraform import google_cloud_run_v2_service_iam_member.gpu_asr_backend \
  "projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-gpu-asr roles/run.invoker serviceAccount:meetchi-cloudrun@${PROJECT_ID}.iam.gserviceaccount.com"
```

跑完後 `terraform plan` 應該 **0 changes**。若有 N changes，逐欄調整 HCL 對齊 live（不要盲套 apply，GPU 服務 recreate 會 ~90s 中斷）。

### 5. 建立 / 更新基礎設施

```bash
terraform apply
```

### 6. HF Token 輪替（**僅當需要時**）

線上 v15 之前的 revision 把 `HF_AUTH_TOKEN` 寫成明文；新版 TF 改成 Secret Manager `meetchi-hf-token` 引用。

```bash
# 1. https://huggingface.co/settings/tokens 撤銷舊 token、產生新 token
# 2. 寫進 terraform.tfvars
# 3. apply 只更新 secret version，不動服務
terraform apply -target=google_secret_manager_secret_version.hf_token

# 4. gpu-asr 下次冷啟動自動讀取最新版（version=latest）
```

---

## 🐳 Image Build 流程

> Image lifecycle **不在 Terraform 管理範圍**（各 `*_image` 變數只是 first-time bootstrap default；HCL 已 `lifecycle.ignore_changes` 排除 image 欄位）。日常更新走 Cloud Build。

### Backend
```bash
gcloud builds submit \
  --config=cloudbuild-backend.yaml \
  --project=${PROJECT_ID}
```
產出 `meetchi-backend:latest`，**db-migrate-v19 共用此 image**。

### Frontend
```bash
gcloud builds submit \
  --config=apps/frontend/cloudbuild-frontend.yaml \
  --project=${PROJECT_ID} \
  apps/frontend
```
注意 `cloudbuild-frontend.yaml` 內含 `--build-arg NEXT_PUBLIC_API_URL=...`，這個 URL 在 build time 烙進 JS bundle，**改 API URL 必須重 build**。

### GPU ASR
```bash
gcloud builds submit \
  --config=cloudbuild-gpu-asr.yaml \
  --project=${PROJECT_ID}
```
模型權重大、build 慢（~10-20 min），日常 deploy 通常重用既有 image，只在 ASR provider / pyannote 升級時重 build。

---

## 🚢 Deploy 流程（日常更新）

### Backend
```bash
gcloud run services update meetchi-backend \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-backend:latest
```

### Frontend
```bash
gcloud run services update meetchi-frontend \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-frontend:latest
```

### Alembic Migration（**只在 schema 改動時**）
```bash
# migrate job 共用 backend image：必須先 build backend 才能跑 migration
gcloud run jobs execute db-migrate-v19 --region=asia-southeast1
```
看執行記錄：`gcloud run jobs executions describe <execution-id> --region=asia-southeast1`

> 💡 schema 改動 = 新增 alembic version 檔。Job command 是 `alembic upgrade head`，會跑到最新 revision。

### GPU ASR（**只在 ASR/diarization 程式碼改動時**）
```bash
gcloud run services update meetchi-gpu-asr \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-gpu-asr:latest
```

---

## ⚙️ 重要環境變數參考

### Backend (`meetchi-backend`)
| Env | Default | 用途 |
|---|---|---|
| `DATABASE_URL` | TF 自動填 | Cloud SQL connection via /cloudsql/ |
| `GCS_BUCKET` | TF 自動填 | Audio 上傳 bucket |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Summary LLM |
| `GEMINI_LOCATION` | `us-central1` | Vertex AI endpoint |
| `GEMINI_MAX_OUTPUT_TOKENS` | `65535` | LLM output 上限（Gemini API 硬上限） |
| `GPU_ASR_SERVICE_URL` | TF 寫死 | Backend → GPU 內網 URL |
| `ASR_PARALLELISM` | `2` | Phase A.1 平行 chunk 數，**對齊 GPU max-instances quota** |
| `LONG_AUDIO_THRESHOLD_SEC` | `1200` | 超過此秒數觸發切片 |
| `AUDIO_CHUNK_SEC` | `1200` | 切片秒數 |
| `ADMIN_TOKEN` | 空 | 設了才需 `X-Admin-Token` header 才能用 /admin/* |

### Frontend (`meetchi-frontend`) — build-time only
| Build arg | 用途 |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend URL（bundle 進 JS，改了要重 build）|

---

## 📊 成本估算（每月，asia-southeast1，2026-05 行情）

| 服務 | 規格 | 估算 |
|---|---|---|
| Cloud Run Backend | 2 vCPU / 4 GiB / min=0 | $5–15 |
| Cloud Run Frontend | 1 vCPU / 512 MiB / min=0 | $1–5 |
| Cloud Run GPU ASR | L4 GPU / 8 vCPU / 32 GiB | $20–80（按使用） |
| Cloud SQL `db-f1-micro` | shared CPU / 0.6 GiB | $8 |
| GCS audio + db bucket | ~50 GB | $1–2 |
| Cloud Tasks | <10K dispatches/month | $0（free tier） |
| Gemini API | per-token | $5–30（看流量） |
| Secret Manager | <10 secrets, 4 versions | $0–1 |
| **總計** | | **~$40–140 / 月** |

> 註：與舊版 DEPLOYMENT.md 列的 $200–310 估算落差大，因為已退役 LLM GPU、用 Cloud Tasks 取代 Redis、Cloud SQL 從 db-g1-small 降規到 db-f1-micro。

---

## 🔧 驗證部署

```bash
# Cloud Run 服務狀態
gcloud run services list --region=asia-southeast1

# Backend health
curl https://meetchi-backend-${PROJECT_NUMBER}.asia-southeast1.run.app/health

# Frontend
curl -I https://meetchi-frontend-${PROJECT_NUMBER}.asia-southeast1.run.app

# 跑 admin backfill（讓現有歷史 meeting 對指定 user 可見）
curl -X POST -d '' \
  "https://meetchi-backend-${PROJECT_NUMBER}.asia-southeast1.run.app/api/v1/admin/backfill-participants?user_upn=YOUR_EMAIL"
```

---

## 🆘 故障排除

### GPU 配額不足
```
Error: RESOURCE_EXHAUSTED: GPU quota exceeded
```
解決: 至 GCP Console 申請增加 `Total Nvidia L4 GPU allocation` 配額。

### Frontend 無法呼叫 Backend
症狀：browser console 出現 CORS error 或打到 `localhost:8000`
原因：build-time `NEXT_PUBLIC_API_URL` 沒對到 prod backend URL
解決：檢查 `apps/frontend/cloudbuild-frontend.yaml` 的 `--build-arg`，重 build + deploy frontend

### Migration 卡住 / 找不到 DB
症狀：`db-migrate-v19` 跑完 status=Failed，log 顯示 `connection refused` 或 `db not found`
原因：job 沒掛 `cloudsql-instances` annotation，或 service account 缺 `cloudsql.client` 角色
解決：跑 `terraform plan -target=google_cloud_run_v2_job.db_migrate` 確認對齊 live

### Gemini 400 INVALID_ARGUMENT
症狀：summary 階段 backend log 出現 `maxOutputTokens value of XXX but the supported range is...`
原因：環境變數 `GEMINI_MAX_OUTPUT_TOKENS` 設超出 Gemini API 範圍（上限 65535）
解決：設回 65535 或更低
