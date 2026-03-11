---
description: Pipeline 斷點定位 — 用 11 個 MECE checkpoint 跨服務勾稽 Cloud Run log，精確找出程式斷點
---

# /debug-pipeline — Pipeline 斷點勾稽

用 meeting_id 跨 3 個 Cloud Run 服務拉 log，自動比對 11 個 checkpoint 哪一環缺失。

> **原理**：pipeline 是因果鏈，每步輸出是下步輸入。找到「最後存在的 log」= 定位斷點。

// turbo-all

## Step 1: 取得 Meeting ID

從用戶提供或最近的 E2E 測試取得 meeting_id。若未提供：

```python
# 查最近的 meetings
python -c "import requests; r=requests.get('https://meetchi-backend-705495828555.asia-southeast1.run.app/api/v1/meetings?limit=5',timeout=30); [print(f'{m[\"id\"]} | {m[\"status\"]} | {m[\"title\"]}') for m in r.json()]"
```

## Step 2: 查 Meeting 當前狀態

```python
python -c "import requests,json; r=requests.get('https://meetchi-backend-705495828555.asia-southeast1.run.app/api/v1/meetings/{MEETING_ID}',timeout=30); d=r.json(); print(f'Status: {d.get(\"status\")}'); print(f'Segments: {len(d.get(\"transcript_segments\",[]))}'); s=d.get('summary_json'); print(f'Summary: {\"Yes\" if s else \"No\"}')"
```

## Step 3: 11 Checkpoint 勾稽（MECE）

用 Observability MCP `list_log_entries` 逐一搜索。每個 checkpoint 的 filter 格式：

```
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE}"
textPayload:"{KEYWORD}"
textPayload:"{MEETING_ID}"
timestamp>="{START_TIME}"
```

### Phase A: 觸發（Backend）

| # | Checkpoint | 搜索關鍵字 | 服務 |
|---|-----------|-----------|------|
| 1 | 收到轉錄請求 | `Received transcription task` | meetchi-backend |
| 2 | 啟動處理 | `Starting CORE meeting processing` | meetchi-backend |
| 3 | 設定 PROCESSING | `Set meeting.*status to PROCESSING` | meetchi-backend |

### Phase B: GPU ASR（GPU ASR）

| # | Checkpoint | 搜索關鍵字 | 服務 |
|---|-----------|-----------|------|
| 4 | GPU 收到請求 | `[ASR Refine] Received request` | meetchi-gpu-asr |
| 5 | ASR 處理完成 | `Processed` + `of audio` | meetchi-gpu-asr |
| 6 | Callback 發送 | `[ASR Refine] Sending callback` | meetchi-gpu-asr |

### Phase C: Callback → 入隊（Backend）

| # | Checkpoint | 搜索關鍵字 | 服務 |
|---|-----------|-----------|------|
| 7 | Backend 收到 callback | `[Callback] Received ASR done` | meetchi-backend |
| 8 | DB 寫入完成 | `[Callback] Updated DB` | meetchi-backend |
| 9 | 摘要入隊成功 | `Successfully enqueued summarization` | meetchi-backend |

### Phase D: 摘要生成（Backend）

| # | Checkpoint | 搜索關鍵字 | 服務 |
|---|-----------|-----------|------|
| 10 | Gemini 摘要成功 | `Successfully generated summary` | meetchi-backend |
| 11 | 狀態 COMPLETED | `status.*COMPLETED` 或 DB 查詢 | meetchi-backend |

## Step 4: 同步拉 ERROR log

```
resource.type="cloud_run_revision"
(resource.labels.service_name="meetchi-backend" OR resource.labels.service_name="meetchi-gpu-asr")
severity="ERROR"
textPayload:"{MEETING_ID}"
timestamp>="{START_TIME}"
```

## Step 5: 產出勾稽表

輸出格式（必須完整填寫每個 checkpoint）：

```markdown
## Pipeline 勾稽結果 — Meeting {MEETING_ID}

| # | Phase | Checkpoint | 狀態 | 時間戳 | 備註 |
|---|-------|-----------|------|--------|------|
| 1 | A | 收到轉錄請求 | ✅/❌ | HH:MM:SS | |
| 2 | A | 啟動處理 | ✅/❌ | | |
| 3 | A | 設定 PROCESSING | ✅/❌ | | |
| 4 | B | GPU 收到請求 | ✅/❌ | | |
| 5 | B | ASR 處理完成 | ✅/❌ | | |
| 6 | B | Callback 發送 | ✅/❌ | | |
| 7 | C | 收到 callback | ✅/❌ | | |
| 8 | C | DB 寫入完成 | ✅/❌ | | |
| 9 | C | 摘要入隊成功 | ✅/❌/⚠️ | | Cloud Tasks or BackgroundTasks |
| 10 | D | Gemini 摘要成功 | ✅/❌ | | |
| 11 | D | 狀態 COMPLETED | ✅/❌ | | |

### 斷點判定
- **最後 ✅**: Checkpoint #X
- **第一個 ❌**: Checkpoint #Y
- **斷點區間**: Phase X → Y

### ERROR log
(列出找到的 ERROR)

### 根因分析
(基於證據的分析)
```

## Step 6: 判定規則

| 最後 ✅ | 第一個 ❌ | 根因方向 |
|---------|----------|---------|
| #3 | #4 | GPU ASR 未收到請求 → 確認 GPU_ASR_SERVICE_URL / httpx timeout |
| #6 | #7 | Callback 未送達 → 確認 BACKEND_PUBLIC_URL / 網路問題 |
| #8 | #9 | Cloud Tasks 入隊失敗 → 確認 GCP_LOCATION / queue 是否存在 |
| #9 | #10 | Gemini 調用失敗 → 確認 GEMINI_MODEL / API 權限 / 配額 |
| #5 | #6 | GPU ASR 完成但 callback 發送失敗 → 確認 callback_url |
| #7 | #8 | Callback 收到但 DB 寫入失敗 → 確認 DB 連線 / schema |

## Fallback 路徑注意

當 Cloud Tasks 入隊失敗（#9 ❌），會走 BackgroundTasks fallback：
- 搜索 `falling back to BackgroundTasks` → 確認 fallback 是否觸發
- 搜索 `skip_asr=True` / `Skipping summarization` → 確認 fallback 參數
