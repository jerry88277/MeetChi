# Sprint 1 結案報告：核心轉錄管線

**日期**: 2025-12-08
**狀態**: 完成 (Pending Hardware Fix)

## 1. 執行摘要
本 Sprint 成功建立了 TranscriptHub MVP 的核心骨架，包括基於 FastAPI 的後端服務、基於 Next.js 的前端介面，以及兩者之間的即時 WebSocket 通訊通道。最關鍵的 ASR (WhisperX) 模型已成功整合至後端，並驗證了其轉錄能力。雖然前端麥克風擷取因本地硬體問題受阻，但透過「模擬模式」已充分驗證了系統架構的可行性。

## 2. 完成的功能與任務
*   **後端環境建置**:
    *   使用 Python 3.12 建立虛擬環境。
    *   解決了複雜的 PyTorch/WhisperX 依賴衝突，成功安裝 CUDA 支援版本。
    *   設定了 FastAPI 專案結構，並整合了 `uvicorn[standard]` 以支援 WebSocket。
    *   設定了 `python-dotenv` 以管理環境變數 (如 `DATABASE_URL`)。
    *   整合了 **Neon (Serverless Postgres)** 作為資料庫 (配置已就緒)。
*   **ASR 服務整合**:
    *   成功載入 `adi-gov-tw/Taiwan-Tongues-ASR-CE` 模型。
    *   實作了 `load_asr_model` 與 `get_transcription` 函式。
    *   在 FastAPI 啟動時預載入模型，避免請求延遲。
*   **WebSocket 轉錄管線**:
    *   建立了 `/ws/transcribe` 端點。
    *   實作了音訊緩衝機制 (Chunking)，將串流音訊切分為 10 秒片段送入模型。
    *   **除錯功能**: 實作了 `debug_audio.wav` 儲存功能，用於驗證接收到的音訊品質。
    *   **模擬模式**: 實作了從本地檔案讀取音訊並模擬即時串流的功能，用於繞過麥克風問題進行開發驗證。
*   **前端開發**:
    *   使用 Next.js 16 + Tailwind CSS 建立了現代化的錄音介面。
    *   實作了 WebSocket 客戶端，處理連線狀態 (Connecting, Recording, Error)。
    *   使用 `AudioContext` 與 `ScriptProcessorNode` 處理音訊擷取與降採樣 (16kHz PCM)。
    *   實作了即時逐字稿顯示區域。

## 3. 技術決策與變更
*   **資料庫**: 從本地 Docker Postgres 轉向使用 **Neon**，以簡化本地運維並接近生產環境。
*   **Celery/Redis**: 暫時註解掉相關代碼，因為 MVP 的核心即時轉錄功能不需要非同步任務隊列，簡化了啟動流程。
*   **CORS**: 添加了 `CORSMiddleware` 並允許所有來源 (`*`)，解決前後端埠號不同 (3000 vs 8000) 的連線問題。
*   **緩衝區策略**: 將音訊切分長度從 2 秒增加到 **10 秒**，以解決 WhisperX VAD 在短片段上無法檢測語音的問題。
*   **強制語言**: 強制指定 `language="zh"`，避免短片段語言檢測錯誤並提升速度。

## 4. 遇到的問題與解決方案
*   **PyTorch 版本衝突**: `whisperx` 依賴舊版 `torch`，導致安裝失敗。
    *   **解法**: 手動安裝 `torch 2.5.1+cu121`，然後使用 `--no-deps` 強制安裝 `whisperx`。
*   **WebSocket 404/Warning**: `uvicorn` 缺少 WebSocket 支援庫。
    *   **解法**: 安裝 `uvicorn[standard]`。
*   **路徑解析錯誤**: PowerShell 無法正確執行 `pip`。
    *   **解法**: 切換目錄並使用 `python -m pip` 或相對路徑執行。
*   **VAD 檢測失敗 (No active speech)**: 5 秒片段太短。
    *   **解法**: 增加緩衝區至 10 秒。
*   **前端麥克風靜音**: `Audio Amplitude` 接近 0，後端收到靜音。
    *   **診斷**: Windows 系統層級麥克風無訊號 (硬體/驅動問題)。
    *   **應變**: 啟用後端「模擬模式」，驗證了除麥克風外的所有軟體管線均正常工作。

## 5. 下一步 (Sprint 2)
*   **恢復模擬模式**: 為了繼續開發 LLM 潤飾功能，將保持後端在模擬模式，以便有穩定的文字輸入源。
*   **LLM 服務**: 建立 Flask API 運行 Breeze2 3B 模型。
*   **整合**: 在 FastAPI 中呼叫 LLM 服務，實現「轉錄 -> 潤飾 -> 前端更新」的完整流程。
