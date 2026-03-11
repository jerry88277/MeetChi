# GPU ASR Cloud Run - Model Loading & Diarization Fallback Analysis

## 症狀描述 (Symptoms)
1. **Model Download Latency**: 根據日誌，`meetchi-gpu-asr` 服務在接收到請求後，花費了約 30 秒從 HuggingFace 下載 `wav2vec2` 模型。這顯示模型並沒有被打包在 Container Image 內，而是「每次 Cloud Run Cold Start (冷啟動)」時才動態下載。
2. **Diarization Skipped**: 日誌顯示 `Warning: You are sending unauthenticated requests to the HF Hub` 以及多個 404 錯誤。這是因為該服務的環境變數 `HF_AUTH_TOKEN` 未被正確賦值。
3. **Fallback 失效假象**: 儘管缺乏 Token 導致 Pyannote 語者辨識機制被跳過 (Skipped)，但由於 Whisper 轉錄 (Transcription) 成功完成，服務最終仍回傳 `{"status": "completed"}` (只是缺少語者標記)。這導致主服務 (`meetchi-backend`) 以為完美成功，**不會觸發 Gemini 的 Fallback 機制**。

## 第一性原理與 MECE 分析

### 1. 資源與狀態面 (Resource & State - Model Loading)
- **基礎事實 (First Principle)**: Cloud Run 是**無狀態 (Stateless)** 且支援**縮放至零 (Scale-to-zero)** 的無伺服器架構。當無流量時，Instance 會被銷毀（包含本地 `/tmp` 或 `/root/.cache` 中的暫存檔）。
- **當前缺陷**: 每次新 Instance 啟動並接獲第一次推理請求時，`offline_asr.py` 才會呼叫 `WhisperModel(model_name)`，此時 Python 套件會自動從 HF 掛載下載點。3-4 GB 的模型下載會造成巨大的冷啟動延遲。
- **MECE 解決方案路徑**:
  - **A. Build-time baked (最佳)**: 在 `Dockerfile.gpu` 中新增一步，透過 python 腳本提前 `huggingface_hub.snapshot_download` 下載模型至 `/app/models`，並修改程式指向本地端徑。
  - **B. Runtime persistent volume**: 將 Cloud Run 掛載的 GCS bucket (`/mnt/gcs`) 切一個資料夾作為 `HF_HOME` 的環境變數，讓多個實例共享已經下載在 GCS 上的模型緩存 (會受限於 GCS 讀取速度，但省下網路外網下載)。

### 2. 邏輯與權限面 (Logic & Auth - Diarization Fallback)
- **基礎事實 (First Principle)**: 我們的 Fallback 機制 (`tasks.py`) 建立在「服務級別的成功與否 (status)」，而非「特徵級別的完整度 (lack of speakers)」。
- **當前缺陷**: GPU-ASR 因為無 HF Token 無法存取 Pyannote 模型，它優雅降級 (Graceful degradation) 回傳了沒有語者標記的純逐字稿。但這對 MEETCHI 的核心價值來說是不可接受的，而 Gemini 備援卻因為看到 `status=completed` 而置之不理。
- **MECE 解決方案路徑**:
  - **A. 前置防禦 (修復授權)**: 修正 `cloudrun-gpu-service.yaml`，將 `HF_AUTH_TOKEN` 補上。目前在 YAML 中 `value: ""` 是空值。
  - **B. 後置防禦 (強化 Fallback 條件)**: 在主服務 `tasks.py` 檢查 GPU 回傳的結果，如果 `asr_result.get("num_speakers", 0) <= 1` (且該會議長度或參與人數預期大於1)，則判定 GPU 服務降級，此時由 Gemini 介入進行「無語者逐字稿的後製分段」或「重新跑 Gemini Diarization」。

## Action Plan (建議的修補計畫)

1. **修正 YAML 配置 (Quick)**: 
   在 `apps/backend/cloudrun-gpu-service.yaml` 中，將 `env` 區塊的 `HF_AUTH_TOKEN` 填入實際的 HF Token (可參考 `terraform.tfvars`)，並重新 `gcloud run services replace`。
2. **優化 Image (Medium)**: 
   修改 `Dockerfile.gpu`，建置階段就將 `SoybeanMilk/faster-whisper-Breeze-ASR-25` 與 `pyannote/speaker-diarization-3.1` 下載至 Image 中，避免依賴外部網路且大幅提昇冷啟動速度。
3. **優化 Fallback (Short)**: 
   修改 `tasks.py`，當 GPU ASR 成功但回傳之 segments 全無 speaker 屬性時，也視為半殘狀態，此時應當啟動 Gemini 備用處理。
