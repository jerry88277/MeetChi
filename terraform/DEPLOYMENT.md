# MeetChi GCP 部署指南（Terraform Quick Reference）

> 📖 **完整企業部署 SOP** 見 [`docs/operations/GCP_DEPLOYMENT_SOP.md`](../docs/operations/GCP_DEPLOYMENT_SOP.md)（含 IT 申請、本機工具安裝、GCP 專案初始化、Service Account 建立等 14 章流程）。
>
> **本文件聚焦：已有 GCP 專案 + Service Account 後，怎麼用 Terraform 跑起來。**

## 📋 前置需求

- GCP 專案已建立（流程見上方 SOP §2~§3）
- `gcloud` CLI 已安裝並授權（流程見上方 SOP §1）
- Terraform >= 1.0
- Docker 已安裝

---

## 🚀 部署流程

### 1. 設定 Terraform 變數

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

編輯 `terraform.tfvars`:
```hcl
project_id    = "your-project-id"
region        = "asia-southeast1"  # Singapore (GPU-enabled)
db_password   = "secure-password"
hf_auth_token = "hf_..."
secret_key    = "jwt-secret-..."
```

### 2. 初始化 Terraform

```bash
terraform init
terraform plan
```

### 3. 申請 GPU 配額

> ⚠️ **重要**: `asia-east1 (台灣)` 不支援 Cloud Run GPU，使用 `asia-southeast1 (新加坡)`

1. 前往 [GCP Console > IAM > Quotas](https://console.cloud.google.com/iam-admin/quotas)
2. 篩選: `Service: Cloud Run Admin API`
3. 搜尋: `NvidiaL4GpuAllocPerProjectRegion`
4. 選擇地區: `asia-southeast1`
5. 申請增加配額 (建議: 3-6 GPUs)
6. 等待 ~2 工作天審核

### 4. 建立基礎設施

```bash
terraform apply
```

### 4-bis. gpu-asr 由 gcloud → Terraform 接管（一次性）

`meetchi-gpu-asr` 自 v15-community1 起改由 Terraform 管理（`cloudrun.tf`）。
**第一次 apply 前**，必須先把線上既有服務 import 進 state，否則 plan 會嘗試
重建並造成 ~90s GPU cold-start 中斷：

```bash
# 1. 對齊：抓線上實際配置
gcloud run services describe meetchi-gpu-asr \
  --region asia-southeast1 --format=export > /tmp/live-gpu-asr.yaml

# 2. import 既有資源到 Terraform state
terraform import google_cloud_run_v2_service.gpu_asr \
  projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-gpu-asr

terraform import google_cloud_run_v2_service_iam_member.gpu_asr_backend \
  projects/${PROJECT_ID}/locations/asia-southeast1/services/meetchi-gpu-asr \
  roles/run.invoker \
  serviceAccount:meetchi-cloudrun@${PROJECT_ID}.iam.gserviceaccount.com

# 3. plan 必須是 0 changes 才可 apply；若 N changes，逐欄調整 HCL 直到對齊
terraform plan -target=google_cloud_run_v2_service.gpu_asr
```

> 💡 image tag 已由 `lifecycle.ignore_changes` 排除；cloudbuild-gpu-asr.yaml
> 仍是 image lifecycle 的擁有者，gcloud / cloudbuild 部署不會引發 drift。

### 4-ter. HF Token 輪替

線上 v15 之前的 revision 把 `HF_AUTH_TOKEN` 寫成明文 env var；新的 Terraform
資源已改成 Secret Manager `meetchi-hf-token` 引用。**輪替程序**：

```bash
# 1. 到 https://huggingface.co/settings/tokens 撤銷舊 token、產生新 token
# 2. 寫進 terraform.tfvars（或 -var）
# 3. 套用 — 只更新 secret version，不動服務
terraform apply -target=google_secret_manager_secret_version.hf_token

# 4. gpu-asr 下次冷啟動會自動讀取最新版（version=latest）
```

### 5. 建置 Docker 映像

```bash
# 使用 Cloud Build
gcloud builds submit --config=cloudbuild.yaml

# 或本地建置
docker build -f apps/backend/Dockerfile.gpu -t gcr.io/$PROJECT_ID/meetchi-backend apps/backend
docker build -f apps/llm_service/Dockerfile.gpu -t gcr.io/$PROJECT_ID/meetchi-llm-gpu apps/llm_service
docker push gcr.io/$PROJECT_ID/meetchi-backend
docker push gcr.io/$PROJECT_ID/meetchi-llm-gpu
```

### 6. 執行 Alembic Migration

```bash
# 取得 Cloud SQL IP
export DB_HOST=$(terraform output -raw database_connection | grep -oP '(?<=@)[\d.]+')

# 執行 migration
cd apps/backend
alembic upgrade head
```

---

## 📊 成本估算 (每月)

| 服務 | 規格 | 估算成本 |
|------|------|----------|
| Cloud Run Backend | 2 vCPU, 4GB | ~$30-50 |
| Cloud Run LLM GPU | 4 vCPU, 16GB, L4 GPU | ~$100-200 |
| Cloud SQL | db-g1-small | ~$25 |
| Redis | 1GB | ~$35 |
| Storage | 10GB | ~$2 |
| **總計** | | **~$200-310/月** |

---

## 🔧 驗證部署

```bash
# 檢查服務狀態
gcloud run services list --region=asia-southeast1

# 測試健康檢查
curl $(terraform output -raw backend_url)/health

# 測試搜尋 API
curl "$(terraform output -raw backend_url)/api/v1/search?q=會議"
```

---

## 🆘 故障排除

### GPU 配額不足
```
Error: RESOURCE_EXHAUSTED: GPU quota exceeded
```
解決: 至 GCP Console 申請增加 GPU 配額

### 模型載入逾時
LLM 服務啟動需 2-5 分鐘載入模型，已設定 `startup_probe` 120 秒
