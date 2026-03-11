# Troubleshooting: Audio Transcription Pipeline (50MB+ Files)

## 症狀描述 (Symptoms)
使用者上傳 50MB 左右的大型音檔至 MeetChi 平台，前端顯示 Upload Network 成功 (HTTP 200/201)，但會議狀態卻顯示完成，且**沒有產生任何逐字稿與摘要**。

## MECE 故障點拆解分析

針對此問題，我們使用 MECE 切入點探究了上傳與處理管線：

1. **Frontend Upload Flow**
   - 獲取 Signed URL (`upload-url`): 正常運作。
   - 上傳至 GCS: 正常運作。
   - 觸發處理流水線 (`process-full-pipeline`): 正常觸發 (回傳 200 OK)，啟動了 `asyncio.to_thread` 背景執行。

2. **Backend Processing Pipeline (`generate_summary_core`)**
   - **Audio Download:** GCS 下載正常。
   - **GPU ASR Refinement (Root Cause 1):** 系統嘗試呼叫專屬 GPU 服務 (`meetchi-gpu-asr`) 進行高精度轉錄，但卻發生 HTTP 404 錯誤，因為環境變數 `GPU_ASR_SERVICE_URL` 預設值為 `localhost`。雖然 Terraform 已經正確配置，但如果服務冷啟動失敗或超時，會回傳 `{"status": "failed"}`。
   - **Gemini Fallback Logic (Root Cause 2):** 在 `tasks.py` 第 292 行，設計了當 GPU 服務不可用時，退回使用 Gemini Diarization。然而，判斷條件僅允許 `{"status": "skipped"}` 觸發，遺漏了處理 `"failed"` 狀態的情境。這導致沒有任何 Transcript Segment 生成，管線直接中止。
   - **狀態更新錯誤 (Root Cause 3):** 由於逐字稿為空，程式提早 `return`，但它**沒有將狀態改為 FAILED**，反而保留了 GPU 呼叫前預設的狀態，加上 GPU 捕捉異常時將會議設為 `COMPLETED`，導致前端以為處理完畢。
   - **GPU ASR 轉錄時的語法錯誤 (Root Cause 4 - 最新發現):** 當 `GPU_ASR_SERVICE_URL` 配置完成，成功觸發了 `meetchi-gpu-asr` 的推論排程後，又發現在 `offline_asr.py` 處理 `faster-whisper` 回傳結果時出現致命錯誤。程式試圖存取 `seg.avg_log_prob` 來記錄轉錄信心水準，但 `faster-whisper` 套件中的正確屬性名稱為 **`avg_logprob`** (無底線)。這導致服務中斷回傳 500 錯誤，進而觸發前項所修復好的 Fallback 機制。

## 解決方案 (Solutions implemented)

1. **修正 Fallback 判斷邏輯**:
   將 `if asr_result.get("status") == "skipped":` 修改為 `if asr_result.get("status") in ["skipped", "failed"]:`，確保任何服務異常 (Timeout, 404, 500 等) 發生時，皆能順利啟用強大的 Gemini 備援進行語音轉錄。

2. **強化 Empty Transcript 錯誤捕捉**:
   當經過 GPU 和 Gemini 兩階段轉錄皆未產生任何段落時，強制將資料庫中 `meeting.status` 設置為 `MeetingStatus.FAILED`，並確保狀態有 `db.commit()`。這避免了前端使用者看到空白白板而不知所措。

3. **基礎架構配置**:
   驗證了 Terraform 設定中的 `gpu_asr_service_url` (`https://meetchi-gpu-asr-wfqjx2j42q-as.a.run.app`) 並透過 `gcp-deploy` 腳本將新版後端映像檔 `v27` 推送至 Cloud Run。

4. **修正 GPU 服務的轉錄屬性錯誤**:
   定位到 `meetchi-gpu-asr` 服務中的 `d:\Side_project\MeetChi\apps\backend\app\offline_asr.py`，將第 244 行的錯誤屬性讀取 `confidence=seg.avg_log_prob` 修正為 `confidence=seg.avg_logprob`，讓大檔 GPU ASR 推論結果能順利封裝回傳不再拋錯。重新佈署含有此修復內容的 `v2-stateless` GPU Image。

**結果**:
修正完畢並重新部署 Cloud Run 後，50MB 以上的大檔案上傳與處理都能妥善被接住。現階段：
1. 若調用 GPU 服務成功，能順利取回 Faster-Whisper + Diarization 高品質轉錄 (且無 AttributeError)。
2. 若缺少 GPU 資源或其他異常拋錯，也能無縫切換到 Gemini 產生完整的逐字稿與會議紀錄。
