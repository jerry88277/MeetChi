# MeetChi 維運手冊（Operations Runbook）

> 本文件聚焦**日常 / 故障 / 維護**操作。**首次部署**請看 [DEPLOYMENT.md](./DEPLOYMENT.md)。

## 📚 目錄
- [完整環境變數參考](#-完整環境變數參考)
- [Admin / Maintenance Endpoints](#-admin--maintenance-endpoints)
- [常見故障處理](#-常見故障處理)
- [災難恢復 SOP](#-災難恢復-sop)
- [週期性維護](#-週期性維護)
- [監控與配額](#-監控與配額)

---

## ⚙️ 完整環境變數參考

### Backend (`meetchi-backend`)

**DB / Infra**
| Env | 預設 | 用途 |
|---|---|---|
| `DATABASE_URL` | TF 自動拼接 | Cloud SQL via `/cloudsql/{instance}` |
| `GCS_BUCKET` | TF 自動填 | 音檔上傳 bucket |
| `BACKEND_PUBLIC_URL` | TF 寫死 | 對外 URL，Cloud Tasks callback 用 |
| `CLOUD_TASKS_QUEUE` | TF 自動填 | transcription queue 名 |

**Gemini LLM**
| Env | 預設 | 用途 |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Summary LLM |
| `GEMINI_LOCATION` | `us-central1` | Vertex AI endpoint（`asia-southeast1` 不支援 Gemini） |
| `GEMINI_MAX_OUTPUT_TOKENS` | `65535` | LLM output 上限；超出會被 clamp |
| `GEMINI_API_KEY` | 空 | 若用 AIStudio key 才填，留空走 ADC（Vertex AI） |
| `GCP_PROJECT` | TF 自動填 | ADC 用 |
| `GCP_LOCATION` | TF 自動填 | Cloud Tasks region（與 Gemini location 不同） |

**Phase A.1 平行 ASR**
| Env | 預設 | 用途 |
|---|---|---|
| `GPU_ASR_SERVICE_URL` | TF 寫死 | Backend → GPU 內網 URL |
| `LONG_AUDIO_THRESHOLD_SEC` | `1200` (20 min) | 超過此長度觸發切片 |
| `AUDIO_CHUNK_SEC` | `1200` (20 min) | 切片大小 |
| `ASR_PARALLELISM` | `2` | 同時 in-flight 的 chunk 數，**對齊 GPU max-instances quota**；quota 開到 4 後可調 |

**安全 / Admin**
| Env | 預設 | 用途 |
|---|---|---|
| `SECRET_KEY` | Secret Manager `meetchi-secret-key` | JWT 簽章 |
| `ADMIN_TOKEN` | 空 | 設了才需 `X-Admin-Token` header 才能用 `/admin/*` |
| `HF_AUTH_TOKEN` | Secret Manager `meetchi-hf-token` | HuggingFace（pyannote diarization）|

**通知**
| Env | 預設 | 用途 |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | 由 `var.discord_webhook_url` 透傳 | 處理完成 / 失敗的 Discord 通知 |

### Frontend (`meetchi-frontend`)

> 全部是 **build-time** 變數，runtime 沒 env。改變後必須 rebuild image。

| Build arg | 預設 | 用途 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | prod backend URL | 烙進 JS bundle |

設定位置：`apps/frontend/cloudbuild-frontend.yaml` 的 `args` 內 `--build-arg`。

### GPU ASR (`meetchi-gpu-asr`)

| Env | 預設 | 用途 |
|---|---|---|
| `HF_AUTH_TOKEN` / `HF_TOKEN` | Secret Manager | 雙寫因不同套件讀不同名 |
| `DIARIZATION_MODEL` | `community-1` | pyannote 模型版本 |

---

## 🧰 Admin / Maintenance Endpoints

### `POST /api/v1/admin/backfill-participants?user_upn=<email>`
**用途**：把所有未刪除 meeting 加入指定 user 為 owner participant。歷史 meeting owner 是 `test@company.com` 但實際使用者用真實 email 登入時，RAG 查不到任何會議 → 用這個一次性批次補。

```bash
curl -X POST -d '' \
  "https://meetchi-backend-${PROJECT_NUMBER}.asia-southeast1.run.app/api/v1/admin/backfill-participants?user_upn=USER_EMAIL@example.com"
```

**回傳**：`{inserted, total_meetings, message}`。Idempotent — 已綁定的會跳過。

### `POST /api/v1/meetings/{meeting_id}/regenerate-summary`
**用途**：重跑 Gemini summary（不重新 ASR）。schema 改動 / prompt 更新 / 失敗 meeting 救回用。

```bash
curl -X POST \
  "https://meetchi-backend-${PROJECT_NUMBER}.asia-southeast1.run.app/api/v1/meetings/<MID>/regenerate-summary?template_type=general"
```

### `POST /api/v1/meetings/bulk-delete`
**用途**：批次軟刪 N 筆會議。前端拖曳框選後呼叫，也可手動 curl。

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"meeting_ids": ["id1","id2"], "requester_upn": "admin@example.com"}' \
  "https://meetchi-backend-${PROJECT_NUMBER}.asia-southeast1.run.app/api/v1/meetings/bulk-delete"
```
單次上限 100 筆；soft delete 30 天保留。

### `DELETE /api/v1/meetings/{meeting_id}?requester_upn=<email>`
**用途**：軟刪單筆。同上保留 30 天。

### `GET /api/v1/rag/history?user_upn=<email>&days=90&limit=100`
**用途**：列出指定 user 過去 N 天的 RAG 查詢紀錄（前端 90 天上限）。後端保留 10 年供稽核。

### `POST /api/v1/rag/backfill`
**用途**：一次性把所有缺 embedding 的 transcript_segments / summary 補上 vector。新 deploy / RAG schema 升級用。

```bash
curl -X POST -d '' \
  "https://meetchi-backend-${PROJECT_NUMBER}.asia-southeast1.run.app/api/v1/rag/backfill"
```

### `GET /api/v1/rag/status`
**用途**：查看 RAG 索引覆蓋率（多少 segments / meetings 已 embed）。

### `GET /api/v1/feedback?user_upn=<email>&limit=50`
**用途**：使用者本人查自己的 feedback 歷史。

### `GET /api/v1/feedback/all?requester_upn=<admin_email>&limit=50&status=open`
**用途**：admin 查所有 feedback（只有 `users.is_admin=true` 才有權限）。

---

## 🆘 常見故障處理

### 1. Meeting 卡在 `processing` 永不變化
**症狀**：上傳完 30+ 分鐘還是 `processing`
**可能原因**：
- Cloud Tasks queue 卡住（看 GCP Console > Cloud Tasks > meetchi-transcription-queue）
- GPU 服務 cold start 失敗（看 `gcloud run services logs read meetchi-gpu-asr`）
- Backend revision 在 ASR / summary 階段崩潰

**處理**：
```bash
# 1. 查最新狀態 + log
gcloud logging read 'resource.type="cloud_run_revision" textPayload:"<MID>" severity>=WARNING' \
  --limit=20 --freshness=2h --format='value(timestamp,severity,textPayload)'

# 2. 看 meeting record
curl https://meetchi-backend-.../api/v1/meetings/<MID>

# 3. 強制重跑（已有 transcript 時用 regenerate-summary；沒有時用 regenerate-transcript）
curl -X POST https://meetchi-backend-.../api/v1/meetings/<MID>/regenerate-summary
```

### 2. RAG 查不到任何結果
**症狀**：`未找到與您問題相關的段落`
**可能原因 MECE**：
- A. user_upn 沒對應的 meeting_participants 紀錄 → 跑 `/admin/backfill-participants`
- B. Meeting 沒被 embed → 跑 `/rag/backfill`
- C. 查詢真的沒匹配（低分） → Y3 已有 fallback hint

### 3. Frontend 呼叫 Backend 時 CORS 錯誤 / 打到 localhost
**原因**：build-time `NEXT_PUBLIC_API_URL` 沒對到 prod
**處理**：檢查 `apps/frontend/cloudbuild-frontend.yaml` 的 `--build-arg`，重 build + redeploy frontend。

### 4. db-migrate-v19 失敗
**症狀**：job execution status=Failed
**可能原因**：
- alembic version 衝突（新增 revision 沒接好 `down_revision`）
- DB connection 失敗（service account 缺 `cloudsql.client`）

**處理**：
```bash
# 看 job 最新執行 log
gcloud run jobs executions list --job=db-migrate-v19 --region=asia-southeast1
gcloud run jobs executions describe <EXEC_ID> --region=asia-southeast1
```

### 5. Gemini 400 INVALID_ARGUMENT
- `maxOutputTokens value of XXX...` → `GEMINI_MAX_OUTPUT_TOKENS` 設超出 [1, 65535]
- `too many states for serving` → response_schema 巢狀 maxItems 過多（先檢查最近的 Pydantic Field 改動）

### 6. Feedback 模組顯示「pjerry…」開頭 email
**原因**：使用者用該帳號登入。實際是真實 email，沒 bug。

---

## 🔥 災難恢復 SOP

### 場景 A：Cloud Run 服務全炸（image 損毀 / IAM 設錯）

```bash
# 1. 回滾到上一個 revision
gcloud run services update-traffic meetchi-backend \
  --to-revisions=meetchi-backend-00150-xxx=100 \
  --region=asia-southeast1

# 2. 找最近綠燈 revision
gcloud run revisions list --service=meetchi-backend --region=asia-southeast1 --limit=10
```

### 場景 B：Cloud SQL 出狀況

```bash
# 1. 取得最新自動備份點
gcloud sql backups list --instance=meetchi-db-pg

# 2. PITR 回到某個時間點
gcloud sql backups restore <BACKUP_ID> --restore-instance=meetchi-db-pg

# ⚠️ 30 天 soft-deleted meeting 仍在 DB，不必走 backup
```

### 場景 C：誤刪 meeting

```sql
-- soft delete 30 天內可救
UPDATE meetings SET deleted_at = NULL, deleted_by = NULL
WHERE id = '<MID>' AND deleted_at > NOW() - INTERVAL '30 days';
```

### 場景 D：TF state 損毀

```bash
# state 存 gs://meetchi-terraform-state；GCS bucket 有版本控管
gsutil ls -a gs://meetchi-terraform-state/terraform/state/default.tfstate
gsutil cp gs://meetchi-terraform-state/terraform/state/default.tfstate#<GEN> \
  ./recovered.tfstate
terraform state push ./recovered.tfstate
```

---

## 🔄 週期性維護

| 任務 | 頻率 | 操作 |
|---|---|---|
| 清 30 天前的 soft-deleted meetings | 月 | SQL `DELETE FROM meetings WHERE deleted_at < NOW() - INTERVAL '30 days'` |
| 清 10 年前的 `rag_query_logs` | 年 | SQL `DELETE FROM rag_query_logs WHERE created_at < NOW() - INTERVAL '10 years'` |
| 旋轉 HF token | 半年 | `terraform apply -target=google_secret_manager_secret_version.hf_token` |
| 旋轉 db password | 半年 | `gcloud sql users set-password postgres ...` + 對應 secret version |
| 檢視 GCS audio bucket | 季 | bucket 已設 365 天 lifecycle 自動刪除；定期看是否該調整 |
| 檢視 GPU 配額使用率 | 月 | Console > IAM > Quotas → L4 GPU |

---

## 📊 監控與配額

| 監控目標 | 哪裡看 |
|---|---|
| Cloud Run revision 健康 | `gcloud run services list --region=asia-southeast1` |
| Cloud Run 4xx/5xx 比例 | GCP Console > Cloud Run > 服務 > Metrics |
| Cloud SQL CPU / Disk | GCP Console > SQL > meetchi-db-pg > Operations |
| Cloud Tasks 待處理數 | GCP Console > Cloud Tasks > queues |
| L4 GPU 配額使用 | Console > IAM > Quotas（搜尋 `Total Nvidia L4 GPU allocation`） |
| Gemini API 用量 | Console > APIs & Services > Quotas |
| Discord webhook 失敗 | backend log `[Notify] Discord returned ...` |

**警報建議**（GCP Cloud Monitoring）：
- backend 5xx > 5/min → email
- Cloud SQL CPU > 80% (5min) → email
- GPU revision 連續 cold start fail → email
- Gemini 4xx > 10/min → email（schema / token 問題）
