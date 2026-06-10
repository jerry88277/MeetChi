# MeetChi 部署進度追蹤紀錄 (Deployment Progress Log)

本文件用於紀錄 MeetChi 專案在 GCP `prj-ai-meetchi-du` 環境的部署進度。每次重大變更或步驟完成後，應更新此文件。

---

## 🏗️ 基礎資訊
- **GCP 專案**: `prj-ai-meetchi-du`
- **主要地區**: `asia-southeast1` (新加坡)
- **Terraform 狀態存儲**: `gs://prj-ai-meetchi-du-terraform-state` (asia-east1)
- **執行身份**: `meetchi-cloudrun@prj-ai-meetchi-du.iam.gserviceaccount.com`

---

## 📝 部署里程碑紀錄

### 🟢 Phase 1: 環境初始化與權限設定
- **狀態**: ✅ 已完成
- **完成時間**: 2026-05-29 05:58:55
- **詳細內容**:
    - [x] 啟用必要 API (Cloud Run, SQL, Secret Manager, Cloud Build, Artifact Registry, etc.)
    - [x] 建立執行身份 Service Account (`meetchi-cloudrun`) 並授予 IAM 角色。
    - [x] 建立 Artifact Registry (`asia-southeast1/meetchi`)。
    - [x] 建立 Terraform State Bucket (`prj-ai-meetchi-du-terraform-state`)。
    - [x] 初始化 Secret Manager 並寫入初始版本。
    - [x] 完成 `terraform init`。

---

## 🚀 待執行清單 (To-Do)

### 🟢 Phase 2: 映像檔建置 (Cloud Build)
- **狀態**: ✅ 已完成 (第 3 次嘗試成功)
- **完成時間**: 2026-05-29 06:59:12
- **詳細內容**:
    - [x] 建置 Backend (`meetchi-backend`) - ID: `c4fb0fec-bf52-4875-971c-654d0025155c` (已完成 ✅)
    - [x] 建置 Frontend (`meetchi-frontend`) - ID: `eaee70cb-9252-4f5f-94b3-7c0fd1918a34` (已完成 ✅)
    - [x] 建置 GPU ASR (`meetchi-gpu-asr`) - ID: `94238820-c794-401d-86ce-4f9a7ab46249` (已完成 ✅，耗時 15M3S)
    - [x] 權限提升：已授予 Compute SA & Cloud Build SA `artifactregistry.admin` 角色。

### 🟢 Phase 3: 基礎設施完整部署 (Terraform Apply)
- **狀態**: ✅ 已完成
- **完成時間**: 2026-06-01（確切時間未知，依 Terraform State 確認）
- **詳細內容**:
    - [x] `terraform apply` 成功，共 36 項資源部署完成。
    - [x] Cloud SQL (PostgreSQL 15): `meetchi-db-pg` (asia-southeast1)
    - [x] GCS Buckets: `meetchi-media-storage`, `meetchi-export-storage`
    - [x] Cloud Tasks Queue: `meetchi-task-queue`
    - [x] Secret Manager: 所有 Secrets 建立完成（含 `meetchi-db-password`）
    - [x] Cloud Run Services: `meetchi-backend`, `meetchi-frontend` 部署完成
    - [x] Cloud Run Job: `db-migrate-v19` 建立完成
    - ⚠️ 注意：`meetchi-gpu-asr` 未由 Terraform 部署（Provider 不支援 `gpu_zonal_redundancy_disabled`）

### 🟢 Phase 4: 資料庫遷移與驗證
- **狀態**: ✅ 已完成

Che
- **完成時間**: 2026-06-01T05:35:32Z（依 Cloud Logging 確認）
- **詳細內容**:
    - [x] 診斷發現 DB 是由 SQLAlchemy `create_all` 建立（非 Alembic），無 `alembic_version` 表。
    - [x] 手動建立 `alembic_version` 表，stamp 至 `e8f4a2b9d6c3`（最後一個已套用的 migration）。
    - [x] 執行 `db-migrate-v19` Job，成功套用最後 2 個 migration：
        - `e8f4a2b9d6c3 → a9b8c7d6e5f4`：新增 `rag_query_logs` 表
        - `a9b8c7d6e5f4 → b5c4d3e2f1a0`：新增 `meetings.failure_reason` 欄位（idempotent）
    - [x] DB 現在在 Alembic HEAD (`b5c4d3e2f1a0`)。

### 🟢 Phase 5: GPU ASR 服務部署
- **狀態**: ✅ 已完成
- **完成時間**: 2026-06-01T05:40:09Z（依 Cloud Run 修訂版狀態確認）
- **詳細內容**:
    - [x] 手動執行 `gcloud run deploy meetchi-gpu-asr`（Terraform 不支援 GPU 部署）
    - [x] 規格：cpu=8, memory=32Gi, gpu=1 nvidia-l4, min=0, max=1, concurrency=1, timeout=3600s
    - [x] 使用 `--no-gpu-zonal-redundancy`（必要參數，否則部署失敗）
    - [x] Service Account: `meetchi-cloudrun@prj-ai-meetchi-du.iam.gserviceaccount.com`
    - [x] Secrets: `HF_AUTH_TOKEN`, `HF_TOKEN` 掛載自 Secret Manager
    - [x] IAM 綁定：`meetchi-cloudrun` SA 授予 `roles/run.invoker`（resource-scoped）
    - [x] 更新 `meetchi-backend` 環境變數 `GPU_ASR_SERVICE_URL`
    - **服務 URL**: `https://meetchi-gpu-asr-315688033208.asia-southeast1.run.app`
    - **修訂版**: `meetchi-gpu-asr-00001-8hd`

### 🔍 Phase 6: 測試與盤點（2026-06-01T05:52Z）
- **狀態**: ⚠️ 部分完成，有待修復項目
- **完成時間**: 2026-06-01T05:52Z
- **詳細內容**:
    - [x] 執行後端單元測試：**81/81 PASSED** ✅（含 feedback, intent, offline_asr, rag_chunker, rag_prompt）
    - [x] 確認 `meetchi-cloudrun` SA 具備 `roles/aiplatform.user` → Gemini Vertex AI 可用 ✅
    - [x] 確認 backend 在 Cloud Run 上使用 ADC + Vertex AI（非 GEMINI_API_KEY）→ `meetchi-gemini-api-key` secret 為預留值但不影響運作 ✅
    - [x] 修正 `BACKEND_PUBLIC_URL`：舊值 `...705495828555...`（錯誤 project number）→ 正確值 `https://meetchi-backend-315688033208.asia-southeast1.run.app` ✅
    - [x] 更新 E2E 測試腳本 URL（`scripts/e2e/test_community1.py`、`test_upload.py`）至正確端點 ✅
    - [x] Smoke test（透過 `gcloud run services proxy`）：
        - `meetchi-backend`: `/health` → `{"status":"healthy"}` ✅、`/api/v1/meetings` → 200 ✅、`/docs` → 200 ✅
        - `meetchi-gpu-asr`: `/health` → `{"status":"healthy","gpu_available":true,"asr_available":true}` ✅
    - ❌ **`meetchi-hf-token` = 佔位值，導致 pyannote diarization fallback**
        - GPU ASR 目前以 `Breeze-ASR-25 (CTranslate2)` 運作（無說話人辨識）
        - 需要動作：取得真實 HF token 並執行 `echo "hf_xxx..." | gcloud secrets versions add meetchi-hf-token --data-file=-`，再重新部署 `meetchi-gpu-asr`

#### 待修復項目清單
| 優先級 | 項目 | 影響 | 修復方式 |
|--------|------|------|----------|
| 🔴 高 | `meetchi-hf-token` 為佔位值 | GPU ASR 模型下載失敗，diarization 無法運作 | 取得真實 HF token 後執行 `gcloud secrets versions add meetchi-hf-token --data-file=-` |
| 🔴 高 | Google OAuth redirect URI 未登記 | 前端 Google 登入跳轉後出現 `redirect_uri_mismatch` 錯誤 | 見 Phase 7 說明 |
| 🟡 中 | E2E 腳本 URL 過時 | `scripts/e2e/` 內仍使用舊 project URL，直接執行會打到錯誤端點 | 更新 `BASE_URL`、`COMMUNITY1_URL`、`GCS_BUCKET` 變數 |
| 🟢 低 | `DISCORD_WEBHOOK_URL` 為空 | Discord 通知失效，不影響核心功能 | 設定真實 Webhook URL 或保持停用 |
| 🟢 低 | Deprecation warnings | SQLAlchemy 1.x / Pydantic v1 API 呼叫 | 未來版本升級時處理，現在不影響運作 |

---

### 🟡 Phase 7: 前端存取設定（2026-06-01）
- **狀態**: ⚠️ 部分完成，需一個手動步驟

#### 已完成
- [x] 診斷 Forbidden 根因：GCP Org Policy `iam.managed.allowedPolicyMembers` 禁止 `allUsers` 為 `run.invoker`
- [x] 新增 `user:jerry_tai@mail.chimei.com.tw` 及 `domain:mail.chimei.com.tw` 為 `roles/run.invoker`（Cloud Run IAM）
- [x] 啟用 IAP API（`iap.googleapis.com`）
- [x] 建立 OAuth Brand（`projects/315688033208/brands/315688033208`，orgInternalOnly）
- [x] 建立 IAP OAuth Client（僅作為備用）：`315688033208-qfnqg25jc2dmruep8ccbbpqhdlusdo9i.apps.googleusercontent.com`
- [x] 設定 `meetchi-frontend` Cloud Run 環境變數：
  - `GOOGLE_CLIENT_ID`=315688033208-qfnqg25jc2dmruep8ccbbpqhdlusdo9i.apps.googleusercontent.com
  - `GOOGLE_CLIENT_SECRET`（已設定）
  - `AUTH_SECRET`（已設定，32-byte random）
  - `AUTH_URL`=http://localhost:8080
  - `AUTH_TRUST_HOST`=1
- [x] 將 OAuth credentials 存入 Secret Manager：`meetchi-google-client-id`、`meetchi-google-client-secret`、`meetchi-auth-secret`
- [x] 確認前端 Next.js Auth 流程正常（CSRF、PKCE 均正確產生）
- [x] 確認 Google OAuth redirect URL 正確指向 `http://localhost:8080/api/auth/callback/google`

#### ❌ 待完成（需人工操作 GCP Console）
**問題：** IAP OAuth Client 不支援設定 Authorized Redirect URIs（IAP Admin API 於 2026-03 下線），需建立標準 Web Application OAuth Client。

**步驟：**
1. 開啟 GCP Console：https://console.cloud.google.com/apis/credentials?project=prj-ai-meetchi-du
2. 點選「建立憑證」→「OAuth 用戶端 ID」
3. 應用程式類型選 **「網路應用程式 (Web application)」**
4. 名稱：`MeetChi Web Frontend`
5. 已授權的重新導向 URI 加入：
   - `http://localhost:8080/api/auth/callback/google`（Cloud Shell proxy 用）
   - `https://meetchi-frontend-315688033208.asia-southeast1.run.app/api/auth/callback/google`（備用）
6. 建立後取得 Client ID 和 Client Secret
7. 執行以下指令更新 Cloud Run：
```bash
gcloud run services update meetchi-frontend \
  --region=asia-southeast1 \
  --project=prj-ai-meetchi-du \
  --set-env-vars "GOOGLE_CLIENT_ID=<新CLIENT_ID>,GOOGLE_CLIENT_SECRET=<新SECRET>,AUTH_SECRET=7d01c39f3656d72b365635ec5810d268cb15a19bf66d007ff88dc20ef4939ec8,AUTH_URL=http://localhost:8080,AUTH_TRUST_HOST=1"
```

#### 前端存取方式（設定完成後）
```bash
# 1. 啟動 Cloud Shell proxy（每次 Cloud Shell session 需執行一次）
gcloud run services proxy meetchi-frontend \
  --region=asia-southeast1 \
  --project=prj-ai-meetchi-du \
  --port=8080 &

# 2. 點選 Cloud Shell 工具列「網路預覽」→ 「在連接埠 8080 上預覽」
# 或開啟瀏覽器：http://localhost:8080
```

---

## ⚠️ 注意事項與變更紀錄
- **2026-05-29**: 地區最終確認為 `asia-southeast1`。理由：GCP 配額申請介面目前僅支援新加坡申請 GPU (L4)，台灣區 (`asia-east1`) 雖然在 API 列表中顯示支援，但申請介面尚未開放選取。
- **2026-05-29**: Terraform `main.tf` 內的 Backend Bucket 已更新為專案專屬名稱 `prj-ai-meetchi-du-terraform-state` 以避免全域衝突。
- **2026-06-01**: 診斷 `db-migrate-v19` 失敗原因：DB 由 `SQLAlchemy create_all` 建立，無 `alembic_version`，導致 migration 誤判重複。手動建立 `alembic_version` 並 stamp，重新執行 migration 成功。
- **2026-06-01**: `meetchi-gpu-asr` 服務因 Terraform Provider 不支援 GPU 而缺失，改以 `gcloud run deploy` 手動部署（含 `--no-gpu-zonal-redundancy`），並更新 `meetchi-backend` 的 `GPU_ASR_SERVICE_URL`。
- **2026-06-01**: 所有服務狀態確認 Ready — backend (revision 00002), frontend (revision 00001), gpu-asr (revision 00001)。
- **2026-06-01**: 執行後端單元測試 81/81 PASSED。發現 `meetchi-hf-token` 為佔位值（非真實 HF token），導致 GPU ASR 說話人辨識（pyannote）無法初始化，fallback 到無 diarization 的 Breeze-ASR-25。`BACKEND_PUBLIC_URL` 使用舊 project number 已修正。E2E 腳本 URL 已更新至正確端點。
- **2026-06-01**: 診斷前端 Forbidden 根因：Org Policy 禁止 `allUsers`。已設定 IAM domain binding、OAuth Brand/Client、NextAuth 環境變數。前端可透過 `gcloud run services proxy --port=8080` 存取。Google OAuth 登入需在 GCP Console 建立 Web Application OAuth Client 並設定 redirect URI（見 Phase 7）。

---

### 🟢 Phase 9: 色彩 UX 優化 + 平行轉錄成本最佳化 + Admin 回報頁面
- **狀態**: ✅ 已完成
- **執行時間**: 2026-06-09 01:20 ~ 01:50
- **操作者**: AI (Copilot CLI)
- **詳細內容**:
    - [x] GPU ASR (`meetchi-gpu-asr`) min-instances 從 1 改為 0 (idle 時不付費)
    - [x] GPU ASR 新增 env: `ASR_PARALLELISM=3`, `AUDIO_CHUNK_SEC=900` → rev `00017-woq`
    - [x] Backend (`meetchi-backend`) 新增 env: `ASR_PARALLELISM=3`, `AUDIO_CHUNK_SEC=900` → rev `00018-nwp`
    - [x] Frontend 色彩優化 (pending=azure, badge 加 border, 背景改 #F5F7FA) → image tag `20260609-v1-color-ux`
    - [x] Frontend 新增 AdminFeedbackPanel 元件 + admin sidebar nav → rev `00033-572`
    - [x] DB: 將 `jerry_tai@mail.chimei.com.tw` 設為 `is_admin=true`
- **備註**:
    - GPU 成本估算：min=1 always-on ~$1,368/月 → min=0 按使用付費 ~$200-300/月 (UAT 階段)
    - 平行轉錄 parallelism 從 2→3 對齊 GPU concurrency=3；chunk 從 20min→15min 提升利用率
    - Admin 回報頁面路由：`/dashboard?view=admin`，非 admin 用戶無法看到此 tab
