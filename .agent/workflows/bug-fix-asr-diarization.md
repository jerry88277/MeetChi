---
description: ASR Diarization Bug 修復流程 - 網路搜尋→第一性原理分析→交叉驗證→修復→重建部署→E2E 測試
---

// turbo-all

# ASR Diarization Bug Fix Workflow

當 GPU ASR Speaker Diarization 回傳 WARNING 或 ERROR 時，使用此流程系統性修復。

## 步驟 1：擷取完整錯誤訊息

```bash
gcloud logging read "resource.labels.service_name=meetchi-gpu-asr" \
  --limit=100 --freshness=30m --format="value(textPayload)" \
  | grep -i "diarization\|error\|warning\|failed"
```

記錄：
- 確切的 Exception class
- 出錯的 function 名稱
- 相關 library 和版本

## 步驟 2：網路搜尋 + 第一性原理分析

// turbo
### 搜尋策略（MECE）

1. **Library-specific 搜尋**：`{library_name} {error_message} fix 2024 2025`
2. **GitHub Issues**：搜尋 pyannote-audio / whisperx / huggingface_hub 的 issue tracker
3. **Breaking Changes 確認**：確認是否為版本升級導致的 API 變更

### 第一性原理分析清單
- [ ] 這個 API 參數為何被移除？（backward compatibility policy）
- [ ] 新的正確 API 為何？（官方文件確認）
- [ ] 有無 environment variable 替代方案？（`HF_TOKEN` 環境變數）
- [ ] 修復是否有副作用？（其他使用同 API 的地方）

### 交叉驗證
- GitHub Release Notes
- Official Migration Guide
- Community Issues (GitHub / HuggingFace Forums)

## 步驟 3：定位程式碼

```bash
# 在 offline_asr.py 搜尋相關用法
grep -n "use_auth_token\|hf_token\|DiarizationPipeline\|hf_hub_download" \
  apps/backend/app/offline_asr.py
```

## 步驟 4：最小修復原則

> **規則**：Bugfix 只改最小範圍，不重構。

常見修復模式：

| 問題類型 | 舊寫法 | 新寫法 |
|---------|--------|--------|
| HF Token 參數 | `use_auth_token=token` | `token=token` |
| torchaudio API | `torchaudio.AudioMetaData` | pin `torchaudio<2.9.0` |
| HF 認證 | 顯式傳參 | 設定 `HF_TOKEN` 環境變數 |

修復後同步確認 `requirements-gpu.txt` 版本 pin 是否需要調整。

## 步驟 5：重建 Docker Image

```bash
# 使用 GPU ASR 專用 cloudbuild 配置
gcloud builds submit apps/backend \
  --config apps/backend/cloudbuild-gpu-asr.yaml \
  --async

# 監控 Build 狀態
gcloud builds describe {BUILD_ID} --format="value(status)"
```

## 步驟 6：部署到 Cloud Run

```bash
gcloud run services update meetchi-gpu-asr \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/{PROJECT}/meetchi/meetchi-gpu-asr:latest
```

## 步驟 7：E2E 驗證

```bash
# 執行端到端測試
python test_upload.py

# 查閱 GPU ASR 日誌確認 diarization 成功
gcloud logging read "resource.labels.service_name=meetchi-gpu-asr" \
  --limit=50 --freshness=30m | grep -i "diarization done\|speakers detected"

# 確認 Meeting speakers 非空
curl https://{BACKEND_URL}/api/v1/meetings/{MEETING_ID} | jq '.transcript_segments[0].speaker'
```

成功條件：
- `[Breeze ASR] Diarization done: N speakers detected`（N > 0）
- `transcript_segments[].speaker` 欄位非空（如 `SPEAKER_00`, `SPEAKER_01`）

## 步驟 8：更新開發文件

執行 `/update-docs` 記錄：
- Root Cause 分析
- 修復方案
- Library 版本 pin 說明
- Lessons Learned

## 停止條件

✅ 日誌出現 `Diarization done: N speakers detected`
✅ API 回傳的 segments 含有非空 speaker 標籤
✅ 開發文件已更新
