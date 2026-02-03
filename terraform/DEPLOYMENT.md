# MeetChi GCP 部署指南

## 📋 前置需求

- GCP 專案已建立
- `gcloud` CLI 已安裝並授權
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
