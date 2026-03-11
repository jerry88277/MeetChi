---
description: 部署後端到端驗證 — 上傳音檔 → 轉錄 → 摘要完整 Happy Path 驗證
---

# /e2e-test — 部署後 E2E 驗證

// turbo-all

## 前置條件
- Backend 和 GPU ASR 已部署成功
- `gcloud auth` 有效

## Step 1: 搜索並確認使用現有腳本

**嚴禁重新撰寫測試腳本**。先確認 `scripts/e2e/` 下有可用的測試腳本：

```bash
dir scripts\e2e\
```

## Step 2: 執行 E2E 測試

使用 `scripts/e2e/test_upload.py`，可傳入自訂音檔路徑：

```bash
# 用預設測試音檔
python scripts/e2e/test_upload.py

# 用指定音檔
python scripts/e2e/test_upload.py "d:\Side_project\MeetChi\GCP_app_test_audio\馬爾地夫屎蛋介紹.m4a"
```

> 腳本會自動完成：建立會議 → 上傳 GCS → 觸發轉錄（同步等待） → 驗證結果

## Step 3: 驗證 Pass 條件

腳本輸出應包含：
- ✅ `GCS upload OK`
- ✅ `HTTP 200` from `/tasks/transcription`
- ✅ `Status: COMPLETED`
- ✅ `Segments: > 0`
- ✅ `Summary: Yes`
- ✅ `E2E PASSED`

## Step 4: 若失敗，查 Log

```bash
# 查 GPU ASR 最近 30 分鐘 log
python scripts/logs/fetch_logs.py --service meetchi-gpu-asr --since 30m

# 查 Backend ERROR
python scripts/logs/fetch_logs.py --service meetchi-backend --severity ERROR --since 30m
```

## Step 5: 報告結果

簡潔報告：
- 音檔名稱和大小
- 總處理時間
- 是否通過（PASSED / FAILED / PARTIAL）
- 失敗原因（如有）
