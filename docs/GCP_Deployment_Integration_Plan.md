# GCP 部署整合計畫 (GCP Deployment Integration Plan)

**日期**: 2025-12-22
**版本**: 1.0
**狀態**: 規劃中

本文件詳細說明如何將 TranscriptHub MVP 的本地開發環境遷移至 Google Cloud Platform (GCP)，特別是針對 **Cloud Run (Sidecar)** 架構的實作細節。

## 1. 部署架構 (Deployment Architecture)

根據 `Cloud_Realtime_Transcription_Architecture.md`，我們採用 **Cloud Run Sidecar** 模式，將核心業務邏輯與 AI 推論服務部署在同一個無伺服器實例中，以極小化延遲。

```mermaid
graph TB
    subgraph "Client Side"
        Tauri[Tauri Desktop App]
    end

    subgraph "GCP Cloud Run (Service: transcript-hub-backend)"
        direction LR
        LB[Load Balancer] --> Ingress
        
        subgraph "Instance (Sidecar Pattern)"
            Ingress[Ingress Container (FastAPI)]
            Model[Inference Container (LLM Service)]
            
            Ingress -- "HTTP (localhost:5000)" --> Model
        end
    end

    subgraph "GCP Managed Services"
        GCS[Cloud Storage (Audio)]
        SQL[Cloud SQL (Metadata)]
    end

    Tauri -- "WebSocket (wss://...)" --> Ingress
    Ingress -- "Read/Write" --> GCS
    Ingress -- "SQL" --> SQL
```

## 2. 容器化策略 (Containerization Strategy)

我們需要為兩個後端服務分別建立 Dockerfile。

### 2.1 Backend Gateway (FastAPI)
*   **路徑**: `apps/backend/Dockerfile`
*   **基礎映像**: `python:3.10-slim`
*   **關鍵依賴**: `fastapi`, `uvicorn`, `websockets`, `sqlalchemy`, `google-cloud-storage`.
*   **特殊配置**: 需安裝 `ffmpeg` (如果 VAD/ASR 預處理需要)。
*   **啟動指令**: `uvicorn app.main:app --host 0.0.0.0 --port 8080` (Cloud Run 預設 Port)。

### 2.2 LLM Service (Inference)
*   **路徑**: `apps/llm_service/Dockerfile`
*   **基礎映像**: `nvidia/cuda:12.1.0-runtime-ubuntu22.04` (需支援 GPU)。
*   **關鍵依賴**: `torch`, `transformers`, `accelerate`, `flask`.
*   **模型載入**: 
    *   **方案 A (推薦)**: 在 Docker build 階段預下載模型 (Baked-in)。優點是啟動快，缺點是 Image 巨大。
    *   **方案 B**: 啟動時從 GCS/HuggingFace 下載。優點是 Image 小，缺點是冷啟動極慢。
    *   **建議**: 採用 **方案 B + GCS Mount** 或 **GCP Artifact Registry** 的緩存機制。對於 MVP，若模型 < 5GB，可嘗試方案 A。
*   **啟動指令**: `python app.py` (監聽 Port 5000)。

## 3. Cloud Run 服務定義 (Service Definition)

我們將使用 `service.yaml` 或 Terraform 來定義包含 Sidecar 的服務。

### 3.1 關鍵配置 (service.yaml 範例)

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: transcript-hub-backend
  annotations:
    run.googleapis.com/launch-stage: BETA # Sidecar 需 BETA 或 GA
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/execution-environment: gen2 # 必須使用二代執行環境
        run.googleapis.com/cpu-throttling: "false"     # 即時應用不應被節流
    spec:
      containers:
        # --- Container 1: Ingress (FastAPI) ---
        - name: backend-gateway
          image: gcr.io/PROJECT_ID/backend-gateway:latest
          ports:
            - containerPort: 8080
          env:
            - name: LLM_SERVICE_URL
              value: "http://localhost:5000" # Sidecar 通訊
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-connection-url
                  key: latest
          resources:
            limits:
              cpu: "1000m"
              memory: "512Mi"

        # --- Container 2: Sidecar (LLM) ---
        - name: llm-service
          image: gcr.io/PROJECT_ID/llm-service:latest
          # No port exposed to internet, only localhost access
          env:
            - name: MODEL_NAME
              value: "MediaTek-Research/Breeze2-3B-Instruct"
          resources:
            limits:
              cpu: "4000m"
              memory: "16Gi"
              nvidia.com/gpu: "1" # Request 1 L4 GPU
          startupProbe: # 確保模型載入完成才導流
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 30
            periodSeconds: 10
```

## 4. 前端配置與建置 (Frontend Integration)

Tauri 應用程式需要知道後端的 WebSocket URL。

### 4.1 環境變數注入
Tauri 建置時 (Build Time) 變數。

1.  **修改 `apps/tauri-client/src/app/page.tsx`**:
    將硬編碼的 `ws://127.0.0.1:8000` 替換為環境變數讀取。
    ```typescript
    const WEBSOCKET_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8000/ws/transcribe";
    ```
    *注意*: 由於我們現在是在 Rust (`audio_processor.rs`) 建立連線，變數需要傳遞給 Rust。

2.  **傳遞策略**:
    *   **方案 A (Compile Time)**: 在 Rust `build.rs` 中讀取 `WS_URL` 環境變數，並將其編譯進 binary (使用 `env!`).
    *   **方案 B (Runtime Config)**: 前端讀取 `NEXT_PUBLIC_WS_URL`，並透過 `start_audio_command` 的參數傳給 Rust。
    *   **建議**: **方案 B**。這樣 Rust 邏輯更純粹，由前端控制配置。

3.  **Rust 介面修改 (`lib.rs` / `audio_processor.rs`)**:
    *   `start_audio_command` 增加 `backend_url: String` 參數。
    *   前端呼叫時傳入 `WEBSOCKET_URL`。

### 4.2 CI/CD 建置流程
在 GitHub Actions 或 Cloud Build 中：
1.  部署後端至 Cloud Run。
2.  獲取 Cloud Run URL (e.g., `wss://transcript-hub-xyz.run.app`).
3.  設定 `NEXT_PUBLIC_WS_URL` = `wss://transcript-hub-xyz.run.app/ws/transcribe`.
4.  執行 `npm run tauri build`。

## 5. 執行步驟清單 (Action Items)

1.  [ ] **Dockerization**: 為 `backend` 和 `llm_service` 撰寫 Dockerfile 並測試本地構建。
2.  **Code Update**: 修改 `page.tsx` 和 `audio_processor.rs` 以支援動態 WebSocket URL。
3.  **GCP Setup**: 
    *   啟用 Cloud Run, Artifact Registry, Cloud SQL API。
    *   申請 GPU Quota (asia-east1, L4)。
4.  **Deployment**: 推送 Image 並部署 Cloud Run Service。
5.  **Validation**: 使用本地 Tauri 連線至 Cloud Run URL 進行測試。
