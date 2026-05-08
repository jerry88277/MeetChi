# MeetChi GCP UAT 環境建置 — IT 申請單

> **版本**: v1.0｜**填表日期**: 2026-04-30｜**用途**: 企業內部 GCP 專案建置（UAT 階段）  
> **本文件依據**: `GCP_DEPLOYMENT_SOP.md`、`terraform/` 目錄實際資源宣告

---

## 0. 申請摘要（給 IT 一頁看懂）

| 項目 | 申請值 | 備註 |
|---|---|---|
| 專案用途 | MeetChi 企業 AI 會議轉錄 / 摘要系統 UAT | 內部測試，非對外正式服務 |
| 環境 | UAT | 預期上線後另開 `prod` 專案 |
| 建議專案名稱 | `meetchi-uat` | 專案 ID 由 IT 指派全域唯一字串 |
| **主要區域** | `asia-southeast1`（新加坡） | **必選**：`asia-east1`（台灣）不支援 Cloud Run GPU L4 |
| 計費帳號 | （由 IT 綁定企業計費帳號） | 預估每月 USD 200~600（依測試強度） |
| 預期到位時間 | 1~2 週（含 GPU 配額審核 2~5 工作天） | GPU 配額為瓶頸，請優先送審 |
| 主要服務 | Cloud Run、Cloud SQL (PostgreSQL 15)、Cloud Storage、Cloud Tasks、Secret Manager、Artifact Registry、Vertex AI、Cloud Build | |

---

## 1. 系統架構與 GCP 資源對應

```
[使用者瀏覽器]
      │ HTTPS
      ▼
[Cloud Run: meetchi-frontend] ──呼叫──► [Cloud Run: meetchi-backend (FastAPI)]
                                              │
            ┌─────────────────────────────────┼─────────────────────────────────┐
            ▼                                 ▼                                 ▼
   [Cloud SQL PostgreSQL 15]   [Cloud Storage 音檔/DB備份]    [Cloud Tasks 非同步佇列]
                                                                       │
                                                                       ▼
                              ┌────────────────────────────────────────┴──────────┐
                              ▼                                                    ▼
                  [Cloud Run: meetchi-gpu-asr (NVIDIA L4)]       [Vertex AI: Gemini 2.5 Flash]
                              │
                              ▼
                  [Secret Manager: HF Token / DB / JWT / Gemini Key]
```

| 資源類型 | 資源名稱 | 用途 |
|---|---|---|
| Cloud Run（一般） | `meetchi-backend` | FastAPI 後端 API（2 vCPU / 4 GiB） |
| Cloud Run（一般） | `meetchi-frontend` | Next.js 前端（1 vCPU / 512 MiB） |
| **Cloud Run（GPU）** | `meetchi-gpu-asr` | WhisperX 語音轉錄（4 vCPU / 16 GiB / **NVIDIA L4 ×1**） |
| Cloud SQL | `meetchi-db-pg` | PostgreSQL 15，啟用 `pgvector` |
| Cloud Storage | `${project_id}-meetchi-audio` | 會議音檔（保留 365 天自動刪除） |
| Cloud Storage | `${project_id}-meetchi-db` | 資料庫備份 / SQLite 持久化 |
| Cloud Storage | `${project_id}-terraform-state` | Terraform 遠端狀態檔（啟用版本控制） |
| Cloud Tasks Queue | `meetchi-transcription-queue` | 語音轉錄非同步派發 |
| Cloud Tasks Queue | `meetchi-summarization-queue` | LLM 摘要非同步派發 |
| Artifact Registry | `meetchi`（Docker 格式） | 存放 backend / frontend / gpu-asr 三組 image |
| Secret Manager | `meetchi-db-password`、`meetchi-hf-token`、`meetchi-secret-key`、`meetchi-gemini-api-key` | 機密集中管理 |
| Vertex AI | Gemini 2.5 Flash Lite（`us-central1`） | LLM 摘要產生 |

---

## 2. 角色與權限清單

> **設計原則**：分為「**部署身份**」與「**應用執行身份**」兩類，遵循最小權限原則（least privilege）。

### 2.1 角色清單一：**部署身份**（Bootstrap / DevOps）

> 用於執行 `terraform apply`、`gcloud` 部署與 IAM 設定的「**人類使用者**」或「**CI/CD Service Account**」。建議授予負責部署的同仁企業 Google 帳號，或建立一個專用 CI SA。

| # | IAM Role | 角色用途（為何需要） |
|---|---|---|
| D1 | `roles/resourcemanager.projectIamAdmin` | Terraform 為 `meetchi-cloudrun` SA 綁定 7 個專案層 IAM 角色（`google_project_iam_member`） |
| D2 | `roles/iam.serviceAccountAdmin` | 建立、刪除 `meetchi-cloudrun` Service Account |
| D3 | `roles/iam.serviceAccountUser` | Cloud Run / Cloud Build 部署時以 SA 身份執行 |
| D4 | `roles/serviceusage.serviceUsageAdmin` | 啟用 9 個 GCP API（`run`、`sqladmin`、`secretmanager` 等） |
| D5 | `roles/run.admin` | 部署、更新、刪除 Cloud Run 服務（backend / frontend / gpu-asr） |
| D6 | `roles/cloudsql.admin` | 建立 Cloud SQL 執行個體、資料庫、使用者 |
| D7 | `roles/secretmanager.admin` | 建立 4 個 Secret 並寫入版本 |
| D8 | `roles/storage.admin` | 建立 GCS Bucket（音檔、DB 備份、Terraform state） |
| D9 | `roles/cloudtasks.admin` | 建立 2 個 Cloud Tasks Queue |
| D10 | `roles/artifactregistry.admin` | 建立 `meetchi` Docker repository |
| D11 | `roles/cloudbuild.builds.editor` | 觸發 `gcloud builds submit` 建置 image |
| D12 | `roles/compute.networkAdmin`（選用） | 若日後啟用 VPC Connector / Private IP for Cloud SQL，方需要 |

> **替代方案**：若企業不接受逐角色授權，亦可暫時授予 `roles/owner` 完成首次建置後，立即降級為上述清單。

---

### 2.2 角色清單二：**應用執行身份**（Runtime Service Account）

> Service Account 名稱：`meetchi-cloudrun@<PROJECT_ID>.iam.gserviceaccount.com`  
> 由 Terraform 自動建立，附掛於三個 Cloud Run 服務（backend、frontend、gpu-asr）作為執行身份。

| # | IAM Role | 角色用途（為何需要） | Terraform 來源 |
|---|---|---|---|
| R1 | `roles/cloudsql.client` | Cloud Run backend 透過 Cloud SQL Auth Proxy 連線 PostgreSQL | `cloudrun.tf:11-15` |
| R2 | `roles/storage.objectAdmin` | 上傳 / 下載音檔到 GCS（也含 DB 備份 bucket） | `cloudrun.tf:17-21` |
| R3 | `roles/secretmanager.secretAccessor` | Cloud Run 啟動時讀取 4 個 Secret 注入 env var | `cloudrun.tf:23-27` |
| R4 | `roles/iam.serviceAccountTokenCreator` | 後端為前端產生 GCS Signed URL 上傳音檔 | `cloudrun.tf:29-33` |
| R5 | `roles/aiplatform.user` | 透過 ADC 呼叫 Vertex AI Gemini 2.5 Flash 產生摘要 | `cloudrun.tf:36-40` |
| R6 | `roles/cloudtasks.enqueuer` | Webhook 處理完成後派發摘要任務到 Cloud Tasks | `cloudrun.tf:43-47` |
| R7 | `roles/run.invoker`（資源層） | backend 跨服務呼叫 `meetchi-gpu-asr`（內部驗證） | `cloudrun.tf:193-198` |

> **R7 為「資源層」綁定**（綁在 `meetchi-gpu-asr` 服務上），不是「專案層」綁定，限制範圍僅限該 Cloud Run 服務。

---

### 2.3 角色清單三：**外部 / 公眾身份**

| 身份 | 綁定 | 用途 | 風險與緩解 |
|---|---|---|---|
| `allUsers` | `roles/run.invoker` on `meetchi-backend` | 對外 REST API（含 webhook callback），UAT 階段必要 | UAT 後改為 `roles/run.invoker` 限定 IAP 或內部網段；目前由應用層 JWT 驗證 |
| Google OAuth Client | （非 IAM）OAuth 2.0 同意畫面 | 前端 NextAuth 登入，限制 `ADMIN_EMAILS` 白名單 | 同意畫面僅限企業網域使用者 |

---

## 3. GCP API 啟用清單

請 IT 在專案上啟用以下 API（Terraform 會嘗試自動啟用，但 Org Policy 可能擋住，故先請 IT 開通）：

| # | API 名稱 | 用途 |
|---|---|---|
| 1 | `run.googleapis.com` | Cloud Run 服務（backend / frontend / gpu-asr） |
| 2 | `sqladmin.googleapis.com` | Cloud SQL PostgreSQL |
| 3 | `secretmanager.googleapis.com` | Secret Manager |
| 4 | `cloudbuild.googleapis.com` | Cloud Build 建置 Docker image |
| 5 | `artifactregistry.googleapis.com` | 存放 Docker image |
| 6 | `containerregistry.googleapis.com` | 相容性（部分早期 image 路徑） |
| 7 | `cloudtasks.googleapis.com` | 非同步任務派發 |
| 8 | `vpcaccess.googleapis.com` | 預留 VPC Connector（若日後需私有連線） |
| 9 | `aiplatform.googleapis.com` | Vertex AI（Gemini 摘要） |
| 10 | `iam.googleapis.com` | IAM 管理（預設啟用） |
| 11 | `iamcredentials.googleapis.com` | Signed URL 簽章（由 R4 觸發） |
| 12 | `storage.googleapis.com` | Cloud Storage（預設啟用） |
| 13 | `cloudresourcemanager.googleapis.com` | Terraform 操作專案層 IAM（預設啟用） |

---

## 4. 配額申請（**最關鍵，請優先送審**）

| 配額名稱 | 區域 | 申請值 | 業務理由 |
|---|---|---|---|
| `NvidiaL4GpuAllocPerProjectRegion` | `asia-southeast1` | **3** | MeetChi UAT 階段需 NVIDIA L4 ×1 執行 WhisperX 即時轉錄；min_instance=0、max_instance=3，配額需覆蓋並發峰值 |
| `CPUs`（一般 Cloud Run） | `asia-southeast1` | 預設值即可（24） | 三組 Cloud Run 服務合計 ≤ 10 vCPU |
| `Cloud SQL Instances per project` | 全域 | 預設值（100）即可 | 僅一個 `db-f1-micro` 執行個體 |

> **送審路徑**：GCP Console → IAM & Admin → Quotas → Service: `Cloud Run Admin API` → 過濾 `NvidiaL4GpuAllocPerProjectRegion`。  
> **預期審核時間**：2~5 個工作天，建議在專案建立當天即送出。

---

## 5. 外部服務帳號 / Token 申請

| 項目 | 申請對象 | 用途 | 建議責任人 |
|---|---|---|---|
| Hugging Face Access Token | hf.co 企業帳號（同意 `pyannote/speaker-diarization-3.1` 條款） | GPU ASR 載入 pyannote / whisper 模型 | 應用 Owner 自行申請 |
| Google Gemini API Key（選用） | `aistudio.google.com` 或改用 Vertex AI（已含 R5 權限） | LLM 摘要備援；若走 Vertex AI 可不申請 | 應用 Owner |
| Google OAuth Client ID / Secret | `console.cloud.google.com/apis/credentials` | 前端 NextAuth 登入 | 應用 Owner（需 IT 協助設定 OAuth 同意畫面網域） |
| Discord / Slack Webhook URL（選用） | 企業通訊工具 | 轉錄完成通知 | 應用 Owner |

> 上述 token 將透過 Secret Manager 儲存，**不寫入 Git**。

---

## 6. 網路與資安考量

| 項目 | UAT 階段設定 | 備註 / 上 prod 後調整 |
|---|---|---|
| `meetchi-backend` ingress | `allUsers` 公開（`roles/run.invoker`） | prod 改為 IAP 或限定企業 VPN 來源 |
| `meetchi-frontend` ingress | `--allow-unauthenticated` | 同上 |
| `meetchi-gpu-asr` ingress | **僅內部**（`--no-allow-unauthenticated`），由 backend SA 呼叫 | 維持不變 |
| Cloud SQL 連線 | Cloud SQL Auth Proxy + IAM（不開公網 IP；目前 `ipv4_enabled=true` UAT 用，prod 應改 Private IP + VPC） | 上 prod 前需 VPC Connector |
| GCS bucket CORS | `origin=["*"]`（UAT 方便測試） | prod 改限定前端網域 |
| Secret Manager 存取 | 僅 `meetchi-cloudrun` SA 可讀 | 已套用最小權限 |
| 計費警示 | 建議 IT 協助設定每月 USD 500 / 80% / 100% 三段警示 | 防 GPU 失控扣費 |

---

## 7. 待 IT 回填欄位（提交時請填妥）

> [!IMPORTANT] 待確認
> 1. **GCP 專案 ID**（IT 建立後回填）：`__________________`
> 2. **計費帳號 ID**：`__________________`
> 3. **所屬 Organization / Folder**：`__________________`
> 4. **OAuth 同意畫面允許網域**（企業 G Workspace 網域）：`__________________`
> 5. **是否啟用 VPC-SC / Org Policy 例外**（GCS public CORS、Cloud Run public ingress）：`是 / 否`

---

## 8. 部署流程一覽（IT 審核參考）

申請通過後的執行順序，**所有指令皆在已授權的部署機器上執行，不變更 IT 既有系統**：

1. `gcloud auth login` 與 `application-default login`
2. `gcloud config set project <PROJECT_ID>`
3. 建立 Terraform State Bucket（章 7）
4. 建立 Artifact Registry repository（章 6）
5. 建立 4 個 Secret 並寫入初始值（章 8）
6. `terraform apply` 部署一般資源（章 9）
7. 手動 `gcloud run deploy meetchi-gpu-asr`（章 10，因 Provider 不支援 GPU node_selector）
8. 建置 backend / frontend image 並 update Cloud Run（章 11）
9. 執行 Alembic migration（章 12）
10. Smoke test（章 13）

> 詳細 SOP 見 `GCP_DEPLOYMENT_SOP.md`。

---

## 9. 角色權限對照速查表（給 IT 直接複製到工單）

```text
[部署者帳號 / CI Service Account]（請選一名同仁或 CI SA）
  - roles/resourcemanager.projectIamAdmin
  - roles/iam.serviceAccountAdmin
  - roles/iam.serviceAccountUser
  - roles/serviceusage.serviceUsageAdmin
  - roles/run.admin
  - roles/cloudsql.admin
  - roles/secretmanager.admin
  - roles/storage.admin
  - roles/cloudtasks.admin
  - roles/artifactregistry.admin
  - roles/cloudbuild.builds.editor

[Runtime SA: meetchi-cloudrun@<PROJECT_ID>.iam.gserviceaccount.com]（Terraform 自動建立後綁定）
  - roles/cloudsql.client
  - roles/storage.objectAdmin
  - roles/secretmanager.secretAccessor
  - roles/iam.serviceAccountTokenCreator
  - roles/aiplatform.user
  - roles/cloudtasks.enqueuer
  - roles/run.invoker  (resource-scoped on meetchi-gpu-asr)

[GPU 配額]
  - NvidiaL4GpuAllocPerProjectRegion @ asia-southeast1 = 3
```

---

*本申請單由 MeetChi 工程團隊根據 `GCP_DEPLOYMENT_SOP.md` 與 `terraform/` 實際宣告產出，如 IT 需調整最小權限策略，請直接於本文件對應欄位批注。*
