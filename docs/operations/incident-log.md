# MeetChi Incident Log — 問題排查與解決記錄

> **用途**：記錄部署過程中遭遇的所有問題點、根本原因、解決方案，以便日後備查與避免重踩同樣的雷。  
> **維護原則**：每次修復後於同日追加一筆，格式統一。  
> **GCP 專案**：`prj-ai-meetchi-du`  
> **Cloud Run 服務**：`meetchi-frontend` / `meetchi-backend` / `meetchi-gpu-asr`

---

## 目錄

- [INC-001 Google OAuth redirect_uri_mismatch](#inc-001-google-oauth-redirect_uri_mismatch)
- [INC-002 NextAuth PKCE InvalidCheck](#inc-002-nextauth-pkce-invalidcheck)
- [INC-003 前端顯示「後端未連線」— NEXT_PUBLIC_API_URL 未正確注入](#inc-003-前端顯示後端未連線--next_public_api_url-未正確注入)
- [INC-004 後端連線失敗 — CORS 未設定](#inc-004-後端連線失敗--cors-未設定)
- [INC-005 批次刪除 FK Violation — users 表缺少紀錄](#inc-005-批次刪除-fk-violation--users-表缺少紀錄)
- [INC-006 GCS CORS 設定消失](#inc-006-gcs-cors-設定消失)
- [INC-007 上傳失敗 — 企業 Proxy 封鎖大型 HTTP Body](#inc-007-上傳失敗--企業-proxy-封鎖大型-http-body)
- [INC-008 Chunked Upload Chunk 遺失 — Proxy 高並發掉包](#inc-008-chunked-upload-chunk-遺失--proxy-高並發掉包)
- [INC-009 轉錄 500 — GPU ASR 403 Forbidden (缺少 OIDC Token)](#inc-009-轉錄-500--gpu-asr-403-forbidden-缺少-oidc-token)
- [INC-010 GPU ASR 404 — Ingress 設定為 internal](#inc-010-gpu-asr-404--ingress-設定為-internal)
- [INC-011 刪除後選取狀態殘留](#inc-011-刪除後選取狀態殘留)
- [INC-012 Cloud Run Job IAM 權限不足 — Scale Job 無法拉取 Image](#inc-012-cloud-run-job-iam-權限不足--scale-job-無法拉取-image)
- [INC-013 Gemini MAX_TOKENS 截斷 — 長會議 Summary FAILED](#inc-013-gemini-max_tokens-截斷--長會議-summary-failed)
- [INC-014 regenerate-summary 誤觸發完整 ASR 流程](#inc-014-regenerate-summary-誤觸發完整-asr-流程)

---

## INC-001 Google OAuth redirect_uri_mismatch

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-10 |
| **症狀** | 瀏覽器登入後出現 `400 redirect_uri_mismatch` |
| **服務** | `meetchi-frontend` |
| **嚴重度** | Blocker |

**根本原因**

Cloud Run 環境變數 `AUTH_URL` 沿用開發預設值 `http://localhost:8080`。NextAuth 以此建構傳送給 Google OAuth 的 `redirect_uri`，導致與 Google Cloud Console 已登錄的 Redirect URI 不符。

**解決方案**

```bash
gcloud run services update meetchi-frontend \
  --region asia-southeast1 \
  --update-env-vars "AUTH_URL=https://meetchi-frontend-atro34poxq-as.a.run.app,NEXTAUTH_URL=https://meetchi-frontend-atro34poxq-as.a.run.app"
```

同時須在 Google Cloud Console → OAuth Client → **Authorized Redirect URIs** 新增：
```
https://meetchi-frontend-atro34poxq-as.a.run.app/api/auth/callback/google
```

**部署版本**：`meetchi-frontend-00006-gp4`

**注意事項**

- 原系統自動生成的 OAuth Client 是唯讀的，必須手動建立新的 Client（`315688033208-ic85b1n4tevi3d0oh5bqa5hi6pibv9u5`）
- `AUTH_URL` 必須用 hash-based canonical URL（`atro34poxq-as.a.run.app`），非 project-number URL

---

## INC-002 NextAuth PKCE InvalidCheck

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-10 |
| **症狀** | 登入後轉跳 callback 時出現 `InvalidCheck` 錯誤 |
| **服務** | `meetchi-frontend` |
| **嚴重度** | Blocker |

**根本原因**

NextAuth v5 預設啟用 PKCE。`code_verifier` 以 cookie 儲存在 sign-in 發起的域名。Cloud Run 有兩個 URL 格式（hash-based `atro34poxq` 與 project-number `315688033208`），若 sign-in 與 callback 走不同 URL，cookie 找不到 → `InvalidCheck`。

**解決方案**

在 `apps/frontend/src/auth.ts` Google provider 加入：
```typescript
checks: ["state"]  // 停用 PKCE，改用 state 驗證 (server-side OAuth 安全)
```

**部署版本**：`meetchi-frontend-00010-gb2`

---

## INC-003 前端顯示「後端未連線」— NEXT_PUBLIC_API_URL 未正確注入

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-11 |
| **症狀** | 登入成功但首頁顯示「後端尚未連線」 |
| **服務** | `meetchi-frontend` |
| **嚴重度** | Blocker |

**根本原因**

`NEXT_PUBLIC_` 前綴的環境變數在 Next.js **build time** 被 inline 到 JavaScript bundle。透過 `gcloud run services update --update-env-vars` 在 runtime 設定無效。  
Dockerfile 預設值為錯誤的舊 URL（`705495828555` project-number 格式）。

**解決方案**

1. 修正 `apps/frontend/Dockerfile`：
   ```dockerfile
   ARG NEXT_PUBLIC_API_URL=https://meetchi-backend-atro34poxq-as.a.run.app
   ```
2. 在 `cloudbuild.frontend.yaml` 傳入 build-arg：
   ```yaml
   args: ['build', ..., '--build-arg', 'NEXT_PUBLIC_API_URL=https://meetchi-backend-atro34poxq-as.a.run.app']
   ```
3. 重新 build（`gcloud builds submit apps/frontend --config=cloudbuild.frontend.yaml`）

**部署版本**：`meetchi-frontend-00012-74r`

**學到的教訓**

`NEXT_PUBLIC_*` 的值只能在 build 時決定，runtime 的環境變數覆寫對它完全無效。

---

## INC-004 後端連線失敗 — CORS 未設定

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-11 |
| **症狀** | 前端 API 呼叫被瀏覽器 CORS 攔截 |
| **服務** | `meetchi-backend` |
| **嚴重度** | Blocker |

**根本原因**

`apps/backend/app/main.py` 的 `cors_origins` 清單遺漏了目前的 Cloud Run 前端 URL，且包含 `your-production-domain.com` 佔位符。

**解決方案**

在 `main.py` 新增所有前端 URL：
```python
cors_origins = [
    "https://meetchi-frontend-atro34poxq-as.a.run.app",
    "https://meetchi-frontend-315688033208.asia-southeast1.run.app",
    "https://meetchi.chimei.com.tw",
    "http://localhost:3000",
]
```

**部署版本**：`meetchi-backend-00004-49g`

---

## INC-005 批次刪除 FK Violation — users 表缺少紀錄

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-15 |
| **症狀** | `psycopg2.errors.ForeignKeyViolation: insert or update on table "meetings" violates foreign key constraint "meetings_deleted_by_fkey"` |
| **服務** | `meetchi-backend` |
| **嚴重度** | High |

**根本原因**

`meetings.deleted_by` 有 FK → `users.ad_upn`。`bulk_delete_meetings` 直接將 `payload.requester_upn` 寫入 `deleted_by`，但沒有先確認該 user 存在於 `users` 表。  
User 紀錄只在建立會議時 upsert，從未在登入時自動建立。

**解決方案**

在 `apps/backend/app/routes/meetings.py` 新增：
```python
def _ensure_user_exists(db: Session, upn: str) -> None:
    if not upn:
        return
    user = db.query(User).filter(User.ad_upn == upn).first()
    if not user:
        db.add(User(id=str(uuid.uuid4()), ad_upn=upn, display_name=upn.split('@')[0]))
        db.flush()
```
在 `bulk_delete_meetings` 迴圈前呼叫：`_ensure_user_exists(db, payload.requester_upn)`

**部署版本**：`meetchi-backend-00005-jd9`

---

## INC-006 GCS CORS 設定消失

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-15 |
| **症狀** | 上傳仍失敗，確認 CORS 設定已不存在 |
| **服務** | GCS bucket `prj-ai-meetchi-du-meetchi-audio` |
| **嚴重度** | Medium |

**根本原因**

疑似 Terraform apply 或其他操作覆蓋了 bucket 設定，導致 CORS 消失。

**解決方案**

```bash
cat > /tmp/cors.json << 'EOF'
[{
  "origin": [
    "https://meetchi-frontend-atro34poxq-as.a.run.app",
    "https://meetchi-frontend-315688033208.asia-southeast1.run.app",
    "https://meetchi.chimei.com.tw",
    "http://localhost:3000"
  ],
  "method": ["GET", "PUT", "POST", "DELETE", "OPTIONS"],
  "responseHeader": ["Content-Type", "Authorization", "Content-Length", "X-Requested-With"],
  "maxAgeSeconds": 3600
}]
EOF
gsutil cors set /tmp/cors.json gs://prj-ai-meetchi-du-meetchi-audio
```

**注意**：每次需確認 CORS 設定未被自動清除：
```bash
gcloud storage buckets describe gs://prj-ai-meetchi-du-meetchi-audio --format="json(cors)"
```

---

## INC-007 上傳失敗 — 企業 Proxy 封鎖大型 HTTP Body

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-20 |
| **症狀** | 上傳顯示「因為網路問題無法上傳」；進度條跑完後仍失敗 |
| **服務** | `meetchi-frontend` / `meetchi-backend` / GCS |
| **嚴重度** | Blocker |

**根本原因**

奇美醫院內部企業 Proxy 封鎖超過一定大小（約數百 KB）的 HTTP Request Body。  
- `OPTIONS` 預檢（空 body）可通過  
- 實際 `POST /upload`（帶 audio file）被 Proxy 攔截/丟棄  
- 進度條顯示「已上傳」是因為瀏覽器的 `upload.onprogress` 反映的是「資料送達 Proxy」，非「送達伺服器」  
- Backend log 完全沒有收到 POST 紀錄

**解決方案**

實作 **Chunked Upload**：  
- 前端將音檔切成 **2MB chunks**，逐一 `POST /api/v1/meetings/{id}/upload-chunk`  
- 後端將 chunks 存為 GCS objects（`audio/_chunks/{id}/part_{index:06d}`）  
- 最後一個 chunk 送出後，後端呼叫 **GCS Compose API** 合併所有 parts  
- 並行上傳數量限制為 **2**（Proxy 對高並發亦有限制，見 INC-008）

**相關檔案變更**

| 檔案 | 變更內容 |
|------|---------|
| `apps/frontend/src/lib/api.ts` | 新增 `chunkedUpload()`；CHUNK_SIZE=2MB, CONCURRENCY=2, MAX_RETRIES=3 |
| `apps/backend/app/routes/meeting_ops.py` | 新增 `POST /{id}/upload-chunk` endpoint；`_compose_blobs()` 遞迴合併 helper |

**部署版本**：`meetchi-backend-00007-???`, `meetchi-frontend-00017-wk4`

---

## INC-008 Chunked Upload Chunk 遺失 — Proxy 高並發掉包

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-21 |
| **症狀** | 上傳 61 個 chunks，chunk 19 遺失；後端 compose 時 GCS 找不到該 chunk |
| **服務** | `meetchi-frontend` |
| **嚴重度** | High |

**根本原因**

初版 chunked upload 使用 4 路並行（CONCURRENCY=4）。企業 Proxy 對高並發請求不穩定，會不定期丟棄某些 chunk，但回傳假 200（前端誤以為成功）。

**解決方案**

降低並行數並加上重試機制：

```typescript
const CHUNK_SIZE = 2 * 1024 * 1024;  // 2MB
const CONCURRENCY = 2;               // 降為 2（Proxy 較穩定）
const MAX_RETRIES = 3;               // 每個 chunk 最多重試 3 次

// 指數退避：1s, 2s
await sleep(attempt * 1000);
```

**部署版本**：`meetchi-frontend-00017-wk4`（用戶確認上傳成功 ✅）

---

## INC-009 轉錄 500 — GPU ASR 403 Forbidden (缺少 OIDC Token)

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-06-03 |
| **症狀** | `POST /api/v1/tasks/transcription → 500`；log 顯示 `403 Forbidden` 呼叫 GPU ASR |
| **服務** | `meetchi-backend` |
| **嚴重度** | Blocker |

**根本原因**

`tasks.py` 以 `httpx` 呼叫 GPU ASR 時沒有附帶任何 Authorization header。Cloud Run IAM 設定只允許 `meetchi-cloudrun@` Service Account（`roles/run.invoker`），未帶 token 的請求一律 403。

**解決方案**

在 `apps/backend/app/tasks.py` 新增 OIDC token helper：

```python
def _get_cloud_run_id_token(audience: str) -> str:
    """Fetch OIDC identity token from GCP metadata server for service-to-service auth."""
    url = (
        "http://metadata.google.internal/computeMetadata/v1/instance"
        f"/service-accounts/default/identity?audience={audience}"
    )
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8")
```

並在兩個呼叫點套用：
1. `call_gpu_once()` — Parallel ASR 路徑（~line 126）
2. 單一音頻 httpx 呼叫路徑（~line 459）

**部署版本**：`meetchi-backend-00008-hsb`

**相關 IAM 設定**（已正確，勿修改）

```bash
# meetchi-cloudrun SA 有 GPU ASR 的 invoker 權限
gcloud run services get-iam-policy meetchi-gpu-asr \
  --region asia-southeast1 --project prj-ai-meetchi-du
# → serviceAccount:meetchi-cloudrun@prj-ai-meetchi-du.iam.gserviceaccount.com / roles/run.invoker
```

---

## INC-010 GPU ASR 404 — Ingress 設定為 internal

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-06-03 |
| **症狀** | GPU ASR 所有請求回傳 `404 Not Found`（HTML，非 JSON），包括 `/health`；容器本身正常啟動 |
| **服務** | `meetchi-gpu-asr` |
| **嚴重度** | Blocker |

**診斷過程**

1. 容器 log 顯示 GPU ASR 正常載入 Breeze-ASR-25 模型（`INFO - ASR model pre-loaded successfully`）
2. 404 回應是 **即時的**（非 cold-start），response header 顯示 `server: Google Frontend`（GFE），非 FastAPI
3. Unauthenticated 請求亦回 404（而非預期的 403）→ 表示 GFE 根本沒有轉發到容器
4. 確認服務狀態 `Ready: True`、GPU quota 足夠（`NVIDIA_L4_GPUS limit=32, usage=0`）
5. **關鍵發現**：`gcloud run services describe meetchi-gpu-asr --format "value(metadata.annotations['run.googleapis.com/ingress'])"` → `internal`

**根本原因**

GPU ASR 服務 Ingress 設定為 `internal`，Google Frontend 會對所有非 VPC 內部流量直接回 404，不轉發給容器。  
Backend（Cloud Run）與 GPU ASR 雖在同一 GCP 專案，但透過 HTTPS URL 呼叫屬於「外部」流量。

**解決方案**

```bash
# GPU ASR 已有 IAM 保護（只有 meetchi-cloudrun SA 可呼叫），安全地開放 all ingress
gcloud run services update meetchi-gpu-asr \
  --region asia-southeast1 \
  --project prj-ai-meetchi-du \
  --ingress all
```

同時設定 `min-instances=1` 避免 scale-to-zero 後 GPU node 排程延遲（在 Ingress=internal 時曾觀察到 scale-to-zero 後無法重新排程的現象）：

```bash
gcloud run services update meetchi-gpu-asr \
  --region asia-southeast1 \
  --project prj-ai-meetchi-du \
  --min-instances 1
```

**修復後驗證**（2026-06-03 08:24~08:26）

```
[ParallelASR] a5cb0793: split into 4 chunks (parallelism=2)
[ParallelASR] chunk 1/4 done attempt=1: 206 segments  ✅ HTTP 200
[ParallelASR] chunk 3/4 done attempt=1: 182 segments  ✅ HTTP 200
[ParallelASR] chunk 2/4 done attempt=1: 3 segments    ✅ HTTP 200
[ParallelASR] chunk 4/4 done attempt=1: 0 segments    ✅ HTTP 200
[ParallelASR] wrote 391 merged segments to DB
[ParallelASR] invoking summary generation (skip_asr=True)
```

**轉錄端到端測試通過 ✅**

**注意**：`min-instances=1` 每月約增加固定成本（L4 GPU 閒置費用）。若成本考量優先，可改回 0 但需接受 ~90s cold-start。

---

## INC-011 刪除後選取狀態殘留

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-05-22 |
| **症狀** | 批次刪除成功後，頁面仍顯示選取狀態與已刪除的會議數量 |
| **服務** | `meetchi-frontend` |
| **嚴重度** | Low |

**根本原因**

`DashboardView.tsx` 刪除按鈕 `onClick` 只呼叫 `onBulkDelete?.(...)` 但沒有呼叫 `clearSelection()`。

**解決方案**

```typescript
// 修改前
onClick={() => onBulkDelete?.(Array.from(selectedIds))}

// 修改後
onClick={() => { onBulkDelete?.(Array.from(selectedIds)); clearSelection(); }}
```

---

## INC-012 Cloud Run Job IAM 權限不足 — Scale Job 無法拉取 Image

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-06-03 |
| **服務** | Cloud Run Jobs (`gpu-asr-scale-up` / `gpu-asr-scale-down`) |
| **Severity** | Medium |

**症狀**

Cloud Run Job 執行失敗，分別出現兩個 PERMISSION_DENIED 錯誤：
1. `artifactregistry.repositories.downloadArtifacts`
2. `iam.serviceaccounts.actAs`

**根本原因**

Cloud Run Job 容器執行 `gcloud run services update --min-instances=N`。
即使是「metadata-only」的 min-instances 變更，GCP 仍會觸發新 revision 部署，
因此需要：
1. Artifact Registry Reader 才能拉取鏡像
2. `iam.serviceAccountUser` on self 才能讓 gcloud 呼叫 SA 讓 new revision 啟動

**解決方案**

```bash
# 授予 AR Reader
gcloud projects add-iam-policy-binding prj-ai-meetchi-du \
  --member="serviceAccount:meetchi-cloudrun@prj-ai-meetchi-du.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"

# 授予 actAs on self
gcloud iam service-accounts add-iam-policy-binding \
  meetchi-cloudrun@prj-ai-meetchi-du.iam.gserviceaccount.com \
  --member="serviceAccount:meetchi-cloudrun@prj-ai-meetchi-du.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# 同時：將 job task-timeout 從 120s → 300s（實際約需 2-3 分鐘）
gcloud run jobs update gpu-asr-scale-up \
  --task-timeout 300 --region asia-southeast1 --project prj-ai-meetchi-du
gcloud run jobs update gpu-asr-scale-down \
  --task-timeout 300 --region asia-southeast1 --project prj-ai-meetchi-du
```

---

## INC-013 Gemini MAX_TOKENS 截斷 — 長會議 Summary FAILED

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-06-03 |
| **服務** | Backend (`generate_summary_core`) |
| **Severity** | Critical |
| **影響會議** | `a5cb0793-39f2-4d1c-8cb7-42b1d0a9fcfd`（2h16m，391 segments） |

**症狀**

上傳 2h16m 錄音後，轉錄完成但摘要失敗，meeting status = FAILED。

**根本原因**

- Gemini 2.5 Flash Lite 最大輸出 token = 65,535（硬上限）
- 65,535 tokens × 2.25 chars/token ≈ 147,500 chars（JSON 含大量 ASCII 結構字元）
- 391 segments × 3 speakers/chunk × 7 chunks = 21 個 SPEAKER_NN_cM 標籤
- `COT_ROLE_INFERENCE_BLOCK` prompt 指示 Gemini 對每個標籤生成詳細 speaker_roles 分析
- 導致輸出佔滿全部 65,535 tokens → JSON 截斷 → parse fail

**解決方案**

將 `speaker_roles` 完全移出主要 summary call：

1. **`apps/backend/app/template_engine.py`**：
   - 移除 `{COT_ROLE_INFERENCE_BLOCK}` from system_prompt
   - 移除 `speaker_roles` from `build_schema_from_template()`

2. **`apps/backend/app/llm_utils.py`**：
   - `generate_summary()` 中動態建立不含 `speaker_roles` 的 stripped schema

3. **`apps/backend/app/tasks.py`**：
   - 改為永遠呼叫 `infer_speaker_roles()`（獨立小型 Gemini call，max_tokens=4096）

**結果**

- Response length: 147,500 → **46,556 chars**（降低 69%）
- `finish_reason: MAX_TOKENS` → **`finish_reason: STOP`** ✅
- Meeting status: FAILED → **COMPLETED** ✅
- 部署 revision: `meetchi-backend-00010-4qw`

---

## INC-014 regenerate-summary 誤觸發完整 ASR 流程

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-06-03 |
| **服務** | Backend route `/api/v1/meetings/{id}/regenerate-summary` |
| **Severity** | Medium |

**症狀**

呼叫 `POST /regenerate-summary` 時，系統重新執行完整 ParallelASR 轉錄流程，
浪費約 3-4 分鐘 GPU 時間，而非僅重新生成摘要。

**根本原因**

route 呼叫 `generate_summary_core()` 時未傳 `skip_asr=True`，
而 `generate_summary_core` 預設 `skip_asr=False`，有 `audio_url` 就會重跑 ASR。

**解決方案**

```python
# apps/backend/app/routes/meetings.py
background_tasks.add_task(
    generate_summary_core,
    meeting_id,
    request.template_name,
    request.context,
    "medium",
    "formal",
    True,   # skip_asr=True — segments already exist; re-run summary only
)
```

---

## 附錄：服務 URL 對照表

| 服務 | Hash-based URL（canonical） | Project-number URL（alias） |
|------|----------------------------|-----------------------------|
| Frontend | `https://meetchi-frontend-atro34poxq-as.a.run.app` | `https://meetchi-frontend-315688033208.asia-southeast1.run.app` |
| Backend | `https://meetchi-backend-atro34poxq-as.a.run.app` | `https://meetchi-backend-315688033208.asia-southeast1.run.app` |
| GPU ASR | `https://meetchi-gpu-asr-atro34poxq-as.a.run.app` | `https://meetchi-gpu-asr-315688033208.asia-southeast1.run.app` |

**Backend `GPU_ASR_SERVICE_URL` 環境變數使用 project-number URL**（兩者均可路由，IAM 以 SA token 驗證）

## 附錄：已知待辦事項

| 項目 | 狀態 | 說明 |
|------|------|------|
| MS OAuth | ⏳ 等待 | Azure AD App Registration 資源申請中（IT 負責） |
| LB + IAP | ⏳ 等待 | 等待 IT 提供 `meetchi.chimei.com.tw` DNS 設定 |
| Terraform 設定同步 | ⚠️ 待更新 | GPU ASR ingress、min-instances 設定尚未回寫 `terraform/cloudrun.tf` |
| Dashboard 拖選 Bug | ⚠️ 待修 | 錯誤訊息出現時滑鼠進入「拖選會議卡片」模式，無法複製錯誤文字（feedback ea742c88） |
| 長會議 map-reduce | ⚠️ 未來改善 | 目前 input 取樣策略；真正解法是 map-reduce summary（見 llm_utils.py 注解） |

---

## INC-015 GPU ASR inter_threads 錯誤參數名稱

| 欄位 | 內容 |
|------|------|
| **時間** | 2026-06-05 |
| **服務** | GPU ASR（meetchi-gpu-asr） |
| **Severity** | Medium（新功能錯誤，未影響現有服務）|

**症狀**

部署 revision `meetchi-gpu-asr-00016-xen` 後，啟動 log 出現：

```
WARNING - Failed to pre-load ASR model: ctranslate2._ext.Whisper() got multiple values for keyword argument 'inter_threads'
```

**根本原因**

`faster_whisper.WhisperModel` 的公開 API 不直接接受 `inter_threads` 參數；
它內部透過 `num_workers` 參數對應到 CTranslate2 的 `inter_threads`。
直接傳 `inter_threads=N` 導致 CTranslate2 C++ extension 收到重複的同名參數。

```python
# 錯誤寫法
WhisperModel(model, device=device, inter_threads=3)  # ❌ 重複
# 正確寫法
WhisperModel(model, device=device, num_workers=3)    # ✅ faster-whisper 公開 API
```

**解決方案**

`apps/backend/app/offline_asr.py` 修正：

```python
self._model = WhisperModel(
    self.config.model_name,
    device=device,
    compute_type=compute_type,
    num_workers=self.config.inter_threads,  # maps to CTranslate2 inter_threads
)
```

config 欄位仍命名為 `inter_threads`（語意清楚），只在 `_load_model()` 呼叫時轉換為 `num_workers`。

**結果**

- 修正後 log：`Breeze ASR model loaded successfully. (inter_threads=3)` ✅
- 部署 revision：`meetchi-gpu-asr-00017-woq`（containerConcurrency=3, ASR_INTER_THREADS=3）

