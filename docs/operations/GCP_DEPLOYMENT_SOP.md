# MeetChi GCP 企業內部建置 SOP

> **版本**: v1.0 | **更新日期**: 2026-04-25  
> **適用對象**: IT 管理員、DevOps 工程師、系統負責人  
> **預計完成時間**: 1~2 個工作天（含 GPU 配額審核）

---

## 目錄

1. [前置需求與工具安裝](#1-前置需求與工具安裝)
2. [IT 申請事項 — 請 IT 完成此階段](#2-it-申請事項)
3. [GCP 專案初始化](#3-gcp-專案初始化)
4. [Service Account 建立與 IAM 設定](#4-service-account-建立與-iam-設定)
5. [啟用 GCP API 服務](#5-啟用-gcp-api-服務)
6. [Artifact Registry 建立](#6-artifact-registry-建立)
7. [Terraform State Bucket 建立](#7-terraform-state-bucket-建立)
8. [Secret Manager 設定](#8-secret-manager-設定)
9. [Terraform 基礎設施部署](#9-terraform-基礎設施部署)
10. [GPU ASR 服務部署（手動）](#10-gpu-asr-服務部署手動)
11. [Docker Image 建置與推送](#11-docker-image-建置與推送)
12. [資料庫 Migration](#12-資料庫-migration)
13. [部署驗證與 Smoke Test](#13-部署驗證與-smoke-test)
14. [附錄：常見問題與排除](#14-附錄常見問題與排除)

---

## 1. 前置需求與工具安裝

### 1.1 本機工具安裝清單

請在執行部署的工作機器（CI Server 或開發者電腦）上安裝以下工具：

| 工具 | 版本要求 | 安裝指令 / 說明 |
|------|----------|-----------------|
| Google Cloud SDK (`gcloud`) | 最新版 | https://cloud.google.com/sdk/docs/install |
| Terraform | >= 1.0 | https://developer.hashicorp.com/terraform/install |
| Docker Desktop | 最新版 | https://www.docker.com/products/docker-desktop |
| Git | >= 2.x | https://git-scm.com/downloads |

### 1.2 驗證安裝

```bash
gcloud version
terraform version
docker version
```

### 1.3 gcloud 登入認證

```bash
# 使用企業 Google 帳號登入
gcloud auth login

# 設定 Application Default Credentials（供 Terraform 使用）
gcloud auth application-default login
```

---

## 2. IT 申請事項

> ⚠️ **此章節為提交給 IT / 雲端管理員的申請清單，請在開始部署前確認以下項目全數到位。**

### 2.1【申請項目一】建立 GCP 專案

請 IT 建立一個新的 GCP 專案，並提供以下資訊：

| 項目 | 說明 | 填入值 |
|------|------|--------|
| 專案名稱 | 建議命名 `meetchi-prod` | ________ |
| 專案 ID | 全域唯一字串，例如 `meetchi-prod-abc123` | ________ |
| 計費帳號 | 綁定企業計費帳號 | ________ |
| 所屬組織 | 企業 GCP Organization | ________ |

### 2.2【申請項目二】部署者帳號的 IAM 權限

請 IT 為執行部署的人員（或 CI/CD Service Account）在該專案下授予以下角色：

| IAM Role | 必要原因 |
|----------|----------|
| `roles/owner` 或以下所有角色的組合 | 執行 Terraform 建立資源 |
| `roles/resourcemanager.projectIamAdmin` | Terraform 設定 IAM 綁定 |
| `roles/cloudbuild.builds.editor` | 觸發 Cloud Build |
| `roles/run.admin` | 部署 Cloud Run 服務 |
| `roles/iam.serviceAccountAdmin` | 建立 Service Account |
| `roles/secretmanager.admin` | 建立與管理 Secrets |
| `roles/storage.admin` | 建立 GCS Bucket |
| `roles/cloudsql.admin` | 建立 Cloud SQL 執行個體 |
| `roles/cloudtasks.admin` | 建立 Cloud Tasks Queue |
| `roles/artifactregistry.admin` | 建立 Artifact Registry |

> **最小權限建議**: 若企業要求最小權限，可以使用上表中的個別角色組合，而非 `roles/owner`。

### 2.3【申請項目三】GPU 配額申請（最重要）

> ⚠️ **此項目需要 2~5 個工作天審核，請優先申請！**
> `asia-east1`（台灣區）**不支援** Cloud Run GPU，必須使用 `asia-southeast1`（新加坡）。

申請步驟：
1. 前往 [GCP Console > IAM & Admin > Quotas](https://console.cloud.google.com/iam-admin/quotas)
2. 選擇專案
3. 篩選 **Service**: `Cloud Run Admin API`
4. 搜尋 Quota 名稱: `NvidiaL4GpuAllocPerProjectRegion`
5. 選擇地區: `asia-southeast1`
6. 點擊「Edit Quotas」，申請值填入 **3**（建議最少 1，生產環境 3~6）
7. 填寫業務理由（範例）：
   ```
   We are deploying an enterprise AI meeting transcription service (MeetChi) 
   that requires NVIDIA L4 GPU on Cloud Run for real-time audio transcription 
   using WhisperX model in the asia-southeast1 region.
   ```

### 2.4【申請項目四】外部服務帳號申請

| 服務 | 申請說明 | 需要的資訊 |
|------|----------|-----------|
| **Hugging Face** | 建立企業帳號，前往 [hf.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) 同意使用條款 | Access Token (`hf_xxxxx`) |
| **Google Gemini API** | 若不使用 Vertex AI，需申請 Gemini API Key | API Key |
| **通知 Webhook**（選用） | Slack 或企業通訊工具 Webhook URL | Webhook URL |

---

## 3. GCP 專案初始化

```bash
# 設定當前使用的 GCP 專案（將 YOUR_PROJECT_ID 替換為實際值）
gcloud config set project YOUR_PROJECT_ID

# 確認設定正確
gcloud config list
# 預期輸出: project = YOUR_PROJECT_ID

# 確認計費帳號已綁定
gcloud billing projects describe YOUR_PROJECT_ID
```

---

## 4. Service Account 建立與 IAM 設定

此 Service Account 是 Cloud Run 應用程式的執行身份，負責存取所有 GCP 資源。

```bash
# 設定環境變數（方便後續指令複用）
export PROJECT_ID="YOUR_PROJECT_ID"
export SA_NAME="meetchi-cloudrun"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export REGION="asia-southeast1"

# Step 1: 建立 Service Account
gcloud iam service-accounts create ${SA_NAME} \
  --display-name="MeetChi Cloud Run Service Account" \
  --project=${PROJECT_ID}

# Step 2: 授予 Cloud SQL 連線權限
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client"

# Step 3: 授予 Cloud Storage 讀寫權限（音檔存取）
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

# Step 4: 授予 Secret Manager 讀取權限（環境變數機密）
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

# Step 5: 授予 Service Account Token Creator（產生 Signed URL）
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountTokenCreator"

# Step 6: 授予 Cloud Tasks Enqueuer（派發非同步任務）
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudtasks.enqueuer"

# Step 7: 授予 Vertex AI User（呼叫 Gemini API）
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"

# Step 8: 授予呼叫 GPU ASR Cloud Run 服務的權限
gcloud run services add-iam-policy-binding meetchi-gpu-asr \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.invoker" \
  --region=${REGION} || echo "[跳過] GPU ASR 服務尚未建立，部署後再執行此步驟"

# 驗證：列出 SA 的所有 IAM 綁定
gcloud projects get-iam-policy ${PROJECT_ID} \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SA_EMAIL}" \
  --format="table(bindings.role)"
```

---

## 5. 啟用 GCP API 服務

```bash
# 一次啟用所有必要的 API（約需 2~3 分鐘）
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  artifactregistry.googleapis.com \
  cloudtasks.googleapis.com \
  vpcaccess.googleapis.com \
  aiplatform.googleapis.com \
  --project=${PROJECT_ID}

# 驗證：確認已啟用
gcloud services list --enabled --project=${PROJECT_ID} \
  --filter="name:(run OR sqladmin OR secretmanager OR cloudbuild OR artifactregistry OR cloudtasks OR aiplatform)" \
  --format="table(name,state)"
```

---

## 6. Artifact Registry 建立

Artifact Registry 用於存放 Docker Image。

```bash
# 建立 Docker 格式的 Artifact Registry Repository
gcloud artifacts repositories create meetchi \
  --repository-format=docker \
  --location=${REGION} \
  --description="MeetChi Docker Images" \
  --project=${PROJECT_ID}

# 設定 Docker 認證（讓本機 docker 指令可推送到 GCP）
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# 驗證
gcloud artifacts repositories list --location=${REGION} --project=${PROJECT_ID}
```

---

## 7. Terraform State Bucket 建立

> ⚠️ **此步驟必須在執行 `terraform init` 之前完成。**  
> Terraform 使用此 Bucket 儲存基礎設施狀態，是協作部署的核心。

```bash
# 建立 Terraform State 專用 Bucket
gcloud storage buckets create gs://${PROJECT_ID}-terraform-state \
  --location=${REGION} \
  --project=${PROJECT_ID} \
  --uniform-bucket-level-access

# 開啟版本控制（防止 State 意外被覆蓋）
gcloud storage buckets update gs://${PROJECT_ID}-terraform-state \
  --versioning

# 驗證
gcloud storage buckets describe gs://${PROJECT_ID}-terraform-state
```

### 更新 Terraform Backend 設定

編輯 `terraform/main.tf`，更新 bucket 名稱：

```hcl
backend "gcs" {
  bucket = "YOUR_PROJECT_ID-terraform-state"  # ← 替換為實際值
  prefix = "terraform/state"
}
```

---

## 8. Secret Manager 設定

在執行 Terraform 之前，需要先在 Secret Manager 中建立初始機密值。

```bash
# 建立所需的 Secrets（建立容器）
gcloud secrets create meetchi-db-password --replication-policy="automatic" --project=${PROJECT_ID}
gcloud secrets create meetchi-hf-token --replication-policy="automatic" --project=${PROJECT_ID}
gcloud secrets create meetchi-secret-key --replication-policy="automatic" --project=${PROJECT_ID}
gcloud secrets create meetchi-gemini-api-key --replication-policy="automatic" --project=${PROJECT_ID}

# 填入機密值（請替換為實際值）

# DB 密碼（建議使用 openssl 生成強密碼）
echo -n "$(openssl rand -base64 24)" | \
  gcloud secrets versions add meetchi-db-password --data-file=- --project=${PROJECT_ID}

# Hugging Face Token
echo -n "hf_YOUR_TOKEN_HERE" | \
  gcloud secrets versions add meetchi-hf-token --data-file=- --project=${PROJECT_ID}

# JWT Secret Key
echo -n "$(openssl rand -hex 32)" | \
  gcloud secrets versions add meetchi-secret-key --data-file=- --project=${PROJECT_ID}

# Gemini API Key（若使用 Vertex AI 則填入空值）
echo -n "YOUR_GEMINI_API_KEY" | \
  gcloud secrets versions add meetchi-gemini-api-key --data-file=- --project=${PROJECT_ID}

# 驗證：列出所有 Secrets
gcloud secrets list --project=${PROJECT_ID}
```

---

## 9. Terraform 基礎設施部署

### 9.1 設定 Terraform 變數

```bash
cd terraform

# 複製範本檔
cp terraform.tfvars.example terraform.tfvars
```

編輯 `terraform/terraform.tfvars`，填入以下內容：

```hcl
project_id    = "YOUR_PROJECT_ID"
region        = "asia-southeast1"
hf_auth_token = "hf_YOUR_TOKEN_HERE"
secret_key    = "YOUR_JWT_SECRET"
gemini_api_key = "YOUR_GEMINI_API_KEY"   # 若使用 Vertex AI 可留空 ""

# Docker Image（第一次部署時先用預設值，建置完 Image 後再更新）
backend_image = "asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/meetchi/meetchi-backend:v1"

# 縮放設定
min_instances = 0
max_instances = 3
```

### 9.2 初始化與部署

```bash
# 初始化 Terraform（下載 Provider、連接 GCS State）
terraform init

# 預覽將要建立的資源（務必仔細檢查）
terraform plan

# 執行部署（約需 5~10 分鐘）
terraform apply
# 輸入 yes 確認

# 查看部署輸出（含資料庫連線資訊、Service URL 等）
terraform output
```

### 9.3 Terraform 建立的資源清單

執行完畢後，以下資源將被自動建立：

| 資源類型 | 資源名稱 | 說明 |
|----------|----------|------|
| Cloud SQL | `meetchi-db-pg` | PostgreSQL 15，已開啟 pgvector |
| Cloud Storage | `{project_id}-meetchi-audio` | 音檔儲存，365 天自動刪除 |
| Cloud Storage | `{project_id}-meetchi-db` | 資料庫備份用 |
| Cloud Tasks Queue | `meetchi-transcription-queue` | 語音轉錄非同步佇列 |
| Cloud Tasks Queue | `meetchi-summarization-queue` | 摘要生成非同步佇列 |
| Cloud Run | `meetchi-backend` | 後端 API (2 CPU, 4GB) |
| Secret Manager | 4 個 Secrets | DB密碼、HF Token、JWT Key、Gemini Key |
| IAM Binding | 7 個角色綁定 | Service Account 的最小權限 |

---

## 10. GPU ASR 服務部署（手動）

> ⚠️ **GPU ASR 服務無法透過 Terraform 部署**（Provider 相容性問題），必須手動執行。  
> 此步驟需要 [第 2.3 節](#23申請項目三gpu-配額申請最重要) 的 GPU 配額已審核通過。

### 10.1 建置 GPU ASR Docker Image

```bash
# 切換到專案根目錄
cd d:/Side_project/MeetChi

# 建置 GPU ASR Image
gcloud builds submit \
  --config apps/backend/cloudbuild-gpu-asr.yaml \
  apps/backend \
  --substitutions=_IMAGE_TAG="v1" \
  --timeout=1800
```

### 10.2 部署 GPU ASR Cloud Run 服務

```bash
gcloud run deploy meetchi-gpu-asr \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-gpu-asr:v1 \
  --region=${REGION} \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account=${SA_EMAIL} \
  --cpu=4 \
  --memory=16Gi \
  --gpu=1 \
  --gpu-type=nvidia-l4 \
  --no-cpu-throttling \
  --max-instances=3 \
  --timeout=3600 \
  --set-env-vars="HF_HOME=/tmp/hf_cache" \
  --set-secrets="HF_AUTH_TOKEN=meetchi-hf-token:latest"
```

### 10.3 取得 GPU ASR Service URL 並更新後端

```bash
# 取得 GPU ASR 的 Service URL
GPU_ASR_URL=$(gcloud run services describe meetchi-gpu-asr \
  --region=${REGION} --format="value(status.url)")
echo "GPU ASR URL: ${GPU_ASR_URL}"

# 更新後端的 GPU_ASR_SERVICE_URL 環境變數
gcloud run services update meetchi-backend \
  --update-env-vars="GPU_ASR_SERVICE_URL=${GPU_ASR_URL}" \
  --region=${REGION}

# 授予 SA 呼叫 GPU ASR 的權限（若第 4 章跳過了此步驟）
gcloud run services add-iam-policy-binding meetchi-gpu-asr \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.invoker" \
  --region=${REGION}
```

---

## 11. Docker Image 建置與推送

### 11.1 建置並部署 Backend

```bash
# 從專案根目錄執行
cd d:/Side_project/MeetChi

# 建置 Backend Image
gcloud builds submit \
  --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-backend:v1 \
  --timeout=900 \
  apps/backend

# 更新 Cloud Run 使用新 Image
gcloud run services update meetchi-backend \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-backend:v1 \
  --region=${REGION}
```

### 11.2 建置並部署 Frontend

```bash
# 建置 Frontend Image（使用 cloudbuild 模式確保 API URL 正確注入）
gcloud builds submit \
  --config apps/frontend/cloudbuild-frontend.yaml \
  apps/frontend \
  --substitutions=_IMAGE_TAG="v1"

# 部署 Frontend Cloud Run 服務
gcloud run deploy meetchi-frontend \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-frontend:v1 \
  --region=${REGION} \
  --platform=managed \
  --allow-unauthenticated \
  --port=3000 \
  --cpu=1 \
  --memory=512Mi \
  --max-instances=5
```

---

## 12. 資料庫 Migration

```bash
# 取得 Cloud SQL Instance Connection Name
DB_CONN=$(gcloud sql instances describe meetchi-db-pg \
  --format="value(connectionName)")
echo "Connection Name: ${DB_CONN}"

# 方法一：透過 Cloud SQL Proxy 執行 Alembic（本機執行）
# 先下載 Cloud SQL Auth Proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.0/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy

# 在背景執行 Proxy
./cloud-sql-proxy ${DB_CONN} --port=5432 &

# 執行 Migration
cd apps/backend
pip install -r requirements.txt
DATABASE_URL="postgresql+psycopg2://postgres:YOUR_DB_PASSWORD@localhost:5432/meetchi" \
  alembic upgrade head

# 方法二：透過 Cloud Run Jobs 執行（無需本機連線）
gcloud run jobs create meetchi-db-migrate \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/meetchi/meetchi-backend:v1 \
  --region=${REGION} \
  --service-account=${SA_EMAIL} \
  --add-cloudsql-instances=${DB_CONN} \
  --command="alembic" \
  --args="upgrade,head" \
  --set-env-vars="DATABASE_URL=postgresql+psycopg2://postgres:PASSWORD@/meetchi?host=/cloudsql/${DB_CONN}"

gcloud run jobs execute meetchi-db-migrate --region=${REGION} --wait
```

---

## 13. 部署驗證與 Smoke Test

```bash
# 取得各服務的 URL
BACKEND_URL=$(gcloud run services describe meetchi-backend \
  --region=${REGION} --format="value(status.url)")
FRONTEND_URL=$(gcloud run services describe meetchi-frontend \
  --region=${REGION} --format="value(status.url)")

echo "Backend URL:  ${BACKEND_URL}"
echo "Frontend URL: ${FRONTEND_URL}"

# Test 1: Backend Health Check（含 DB 連線驗證）
echo "=== Backend Health Check ==="
curl -s ${BACKEND_URL}/health
# 預期: {"status":"healthy","service":"meetchi-backend"}

# Test 2: Frontend Health Check
echo -e "\n=== Frontend Health Check ==="
curl -s ${FRONTEND_URL}/api/health
# 預期: {"status":"healthy","service":"meetchi-frontend",...}

# Test 3: 確認 Frontend 打到正確的 Backend URL（非 localhost）
echo -e "\n=== Frontend API URL 驗證 ==="
curl -s ${FRONTEND_URL} | grep -o "meetchi-backend[^\"]*"
# 預期: 出現 meetchi-backend 的 GCP URL，不能出現 localhost 或 127.0.0.1

# Test 4: 列出所有 Cloud Run 服務狀態
echo -e "\n=== Cloud Run Services ==="
gcloud run services list --region=${REGION} \
  --format="table(name,status.url,status.conditions[0].type)"

# Test 5: 驗證 env vars 數量正常（≥ 10 個）
echo -e "\n=== Backend Env Vars Count ==="
gcloud run services describe meetchi-backend \
  --region=${REGION} \
  --format="json(spec.template.spec.containers[0].env[].name)" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Env vars: {len(d)}')"
```

---

## 14. 附錄：常見問題與排除

### ❌ 錯誤：`RESOURCE_EXHAUSTED: GPU quota exceeded`

**原因**: GPU 配額尚未申請或尚未審核通過。  
**解決**: 依照[第 2.3 節](#23申請項目三gpu-配額申請最重要)申請配額，等待審核（2~5 工作天）。

---

### ❌ 錯誤：`The object 'terraform.tfstate' does not exist`

**原因**: Terraform State Bucket 尚未建立。  
**解決**: 先執行[第 7 節](#7-terraform-state-bucket-建立)建立 Bucket，再重新執行 `terraform init`。

---

### ❌ 錯誤：`Backend health: {"status":"unhealthy"}`

**原因**: Cloud SQL 連線失敗，通常是環境變數設定錯誤或 Service Account 缺少 `cloudsql.client` 權限。  
**解決**:
```bash
# 確認 env var 數量是否正常（< 10 代表有變數被覆蓋）
gcloud run services describe meetchi-backend \
  --region=${REGION} \
  --format="json(spec.template.spec.containers[0].env[].name)"

# 若有異常，用 Terraform 恢復正確設定
terraform apply -target="google_cloud_run_v2_service.backend" -auto-approve
```

---

### ❌ 錯誤：`Frontend API 打到 localhost`

**原因**: Frontend 建置時沒有正確注入 `NEXT_PUBLIC_API_URL`。  
**解決**: 務必使用 `--config cloudbuild-frontend.yaml` 模式建置，**禁止使用 `--tag` 模式**。

---

### ❌ 錯誤：`Error 403: Permission denied on Secret`

**原因**: Service Account 缺少 `secretmanager.secretAccessor` 角色。  
**解決**:
```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 部署完成確認清單

部署完成後，請確認以下所有項目皆為 ✅：

- [ ] `curl ${BACKEND_URL}/health` 回傳 `{"status":"healthy"}`
- [ ] `curl ${FRONTEND_URL}/api/health` 回傳 200
- [ ] Frontend 頁面可正常開啟，且 Network 請求指向 GCP Backend（非 localhost）
- [ ] 上傳一個測試音檔，確認轉錄任務可成功入佇列
- [ ] GPU ASR 服務在收到任務後可正常啟動並回傳結果
- [ ] 摘要生成功能可正常運作

---

*本文件由 MeetChi 工程團隊撰寫，如有問題請聯繫系統負責人。*
