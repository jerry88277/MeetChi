# TranscriptHub MVP 系統啟動指南 (Startup Guide)

本文件說明如何在本機環境中啟動 TranscriptHub MVP 的各個服務元件。

## 1. 系統架構概覽

系統由三個主要服務組成：
1.  **Frontend (前端)**: Next.js 應用程式 (Port 3000)
2.  **Backend (後端)**: FastAPI 應用程式，負責 WebSocket 連線與 ASR 轉錄 (Port 8000)
3.  **LLM Service (模型服務)**: Flask 應用程式，負責 Breeze2 模型推論與文字潤飾 (Port 5000)

## 2. 前置準備 (Prerequisites)

確保您的系統已安裝以下工具：
*   **Python 3.10+** (建議使用 3.10 或 3.12)
*   **Node.js v18+**
*   **Git**
*   **CUDA Toolkit** (若要使用 GPU 加速，強烈建議)

---

## 3. 啟動步驟

建議開啟三個終端機視窗，分別啟動以下服務。

### 步驟一：啟動 LLM 服務 (LLM Service)

此服務負責載入 Breeze2-8B 模型，啟動時間較長，建議最先啟動。

1.  開啟終端機，進入 `apps/llm_service` 目錄：
    ```bash
    cd apps/llm_service
    ```

2.  啟動虛擬環境 (若尚未建立，請參考 `README.md` 建立)：
    *   **Windows (PowerShell)**:
        ```powershell
        .\.venv\Scripts\Activate.ps1
        ```
    *   **Mac/Linux**:
        ```bash
        source .venv/bin/activate
        ```

3.  執行服務：
    ```bash
    python app.py
    ```

4.  **驗證**: 等待看到 `Running on http://0.0.0.0:5000` 訊息，且模型載入完成 (Log 顯示 `LLM model loaded successfully`)。

### 步驟二：啟動後端服務 (Backend)

此服務負責 ASR 轉錄與 WebSocket 通訊。

1.  開啟新終端機，進入 `apps/backend` 目錄：
    ```bash
    cd apps/backend
    ```

2.  啟動虛擬環境：
    *   **Windows (PowerShell)**:
        ```powershell
        .\.venv\Scripts\Activate.ps1
        ```
    *   **Mac/Linux**:
        ```bash
        source .venv/bin/activate
        ```

3.  設定環境變數 (若未設定 `.env`)：
    確保 `.env` 檔案中包含資料庫連線資訊與 LLM 服務位址。
    ```env
    DATABASE_URL=postgres://... (或使用預設 SQLite)
    LLM_SERVICE_URL=http://localhost:5000
    ```

4.  啟動 FastAPI 服務：
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```

5.  **驗證**: 瀏覽器開啟 `http://localhost:8000/docs`，應能看到 API 文件。

### 步驟三：啟動前端應用 (Frontend)

1.  開啟新終端機，進入 `apps/frontend` 目錄：
    ```bash
    cd apps/frontend
    ```

2.  安裝依賴 (若首次執行)：
    ```bash
    npm install
    ```

3.  啟動開發伺服器：
    ```bash
    npm run dev
    ```

4.  **驗證**: 瀏覽器開啟 `http://localhost:3000`，應能看到 TranscriptHub 的首頁。

---

## 4. 常見問題排除 (Troubleshooting)

*   **Port 衝突**: 若 Port 8000 或 3000 被佔用，請修改啟動指令中的 Port 或關閉佔用程式。
*   **模型載入失敗 (OOM)**: 若 GPU 記憶體不足 (VRAM < 8GB)，請嘗試在 `apps/backend/scripts/transcribe_sprint0.py` 或 `apps/llm_service/app.py` 中將 `device` 設為 `cpu`，或改用量化版本模型。
*   **WebSocket 連線失敗**: 檢查後端是否已啟動，並確認前端瀏覽器主控台 (F12) 的錯誤訊息。
*   **LLM 回應超時**: 若使用 CPU 推論，LLM 回應可能較慢。可在 `apps/backend/app/main.py` 中增加 `httpx` 的 `timeout` 設定。
