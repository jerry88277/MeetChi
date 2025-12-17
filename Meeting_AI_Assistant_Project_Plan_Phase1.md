# 會議 AI 助理專案規劃：第一階段 - 廣泛調查

**文件版本:** 1.0
**日期:** 2025-12-03
**負責人:** BMAD Master Agent (專案經理)

## 1. 專案啟動與團隊分工

本文件為「會議 AI 助理」專案的第一階段（廣泛調查）的成果總結與行動計畫。此階段，我們以 Deep Research 模式，分析了指定的開源專案，並對關鍵技術進行了可行性評估。

**此階段各角色關注點與初步結論：**

*   **系統架構師**:
    *   **關注點**: 評估六個參考專案的架構，找出可重用的模式。
    *   **結論**: 混合式微服務架構是最佳選擇。一個用於即時處理（WebSockets + Streaming ASR），一個用於非同步任務（檔案上傳、批次摘要）。

*   **AI 開發工程師**:
    *   **關注點**: `Taiwan-Tongues-ASR-CE` 模型特性，以及 LLM 在潤飾與結構化摘要的應用。
    *   **結論**: `Taiwan-Tongues` 適合部署為獨立服務。LLM Prompt Engineering 是實現高品質結構化會議記錄的關鍵，`x-meet` 的 `prompt.md` 提供了絕佳的參考起點。

*   **GCP 部署工程師**:
    *   **關注點**: 如何在 GCP 上高效部署 `Taiwan-Tongues-ASR-CE`。
    *   **結論**: **Vertex AI Endpoints** 是首選。其為自定義容器提供內建的自動擴展、日誌記錄和監控，大幅降低了 MLOps 的複雜性，比手動管理 GKE 叢集更有效率。

*   **全端工程師**:
    *   **關注點**: `Next.js` 與 `Python` 後端的即時通訊方案，以及前端使用者體驗。
    *   **結論**: 採用 **Next.js + FastAPI + WebSockets** 的技術棧。`meetingmind` 專案（使用 Next.js, Tailwind CSS）是我們前端開發的優秀範本。

*   **資安工程師**:
    *   **關注點**: 語音資料傳輸與儲存的安全性。
    *   **結論**: 必須全程使用 `WSS` (WebSocket Secure) 協議。所有持久化資料（錄音檔、逐字稿）在靜態時需進行加密。

*   **風險分析師**:
    *   **關注點**: 開源專案的授權與資料隱私。
    *   **結論**: 多數專案採用 MIT 或 Apache 2.0 授權，商業使用風險較低。需在使用者條款中明確告知 PII 處理方式。

---

## 2. GitHub 專案分析 (第一性原理 & MECE)

我們將每個專案解構成最小功能單元，以便理解其核心構成。

| 專案名稱 | 核心功能 | 解構 (最小理解單位) |
| :--- | :--- | :--- |
| **1. TranscriptHub** | 企業級的轉錄任務管理平台 | - **UI**: Go 語言模板 + Material-UI<br>- **Backend**: Node.js API Gateway<br>- **Transcription**: WhisperX (獨立 Worker)<br>- **Database**: SQL<br>- **特色**: 任務排程、負載平衡 |
| **2. meeting-minutes** | 注重隱私的本地桌面會議記錄工具 | - **UI**: Next.js (打包在 Tauri 中)<br>- **Backend**: Rust (本地執行)<br>- **Transcription**: 本地 Whisper/Parakeet<br>- **LLM Service**: 本地 Ollama 或 API (Claude, Groq)<br>- **特色**: 隱私優先、跨平台、系統音訊混合 |
| **3. VideoCaptioner** | 專業影片字幕生成與優化工具 | - **UI**: Python GUI<br>- **Backend**: Python<br>- **Transcription**: fasterWhisper<br>- **LLM Service**: API (OpenAI, DeepSeek) 用於校正、翻譯<br>- **特色**: 語音活動檢測 (VAD)、LLM 輔助標點與分句 |
| **4. WhisperLiveKit** | 超低延遲的即時語音轉文字伺服器 | - **UI**: 簡單的 HTML/JS<br>- **Backend**: Python (FastAPI)<br>- **Transcription**: Streaming Whisper 變體<br>- **特色**: **即時串流處理**、即時說話者分離 (Diart) |
| **5. meetingmind** | AI 驅動的會議洞察提取 Web App | - **UI**: **Next.js**, **Tailwind CSS**<br>- **Backend**: Next.js API Routes + Langflow<br>- **Transcription**: Groq API<br>- **LLM Service**: OpenAI (透過 Langflow)<br>- **特色**: 結構化資訊提取 (任務、決策、風險等) |
| **6. x-meet** | 本地優先的 AI 會議記錄桌面軟體 | - **UI**: Electron (HTML/CSS/JS)<br>- **Backend**: Node.js (Electron runtime)<br>- **Transcription**: 未指定本地 AI<br>- **LLM Service**: 未指定本地 AI<br>- **特色**: 離線工作、本地儲存、**優秀的 Prompt 範例** |

---

## 3. 核心概念重構 (Reconstruction)

綜合上述分析，並根據我們的三大使用者情境，我們重構出以下微服務架構：

```plaintext
+--------------------------------+
|      Frontend (Next.js)        |
| - Real-time Transcript Display |
| - Audio/Video Upload UI        |
| - Meeting Minutes View         |
+--------------------------------+
      |         ^
(WebSocket) |         | (REST API)
      v         |
+--------------------------------+
|   Backend Gateway (Python/FastAPI) |
| - WebSocket Handler            |
| - Auth & User Management       |
| - REST API Endpoints           |
+--------------------------------+
      |         |         |
(gRPC/HTTP) |         | (gRPC/HTTP)
      v         v         v
+-------------+  +-------------+  +-------------------+
| ASR Service |  | LLM Service |  | File Proc. Service|
| (Taiwan-     |  | (Python)    |  | (Python)          |
|  Tongues on  |  | - Summarize |  | - Upload Handling |
|  Vertex AI)  |  | - Sanitize  |  | - Format Convert  |
+-------------+  +-------------+  +-------------------+
```

**設計理念**:
1.  **分離關注點**:
    *   **Frontend**: 只負責使用者互動和畫面渲染。
    *   **Backend Gateway**: 處理所有外部請求、驗證和路由，是系統的交通警察。
    *   **ASR Service**: 一個專門、可獨立擴展的語音轉文字服務。
    *   **LLM Service**: 處理所有與大型語言模型相關的任務（潤飾、摘要）。
    *   **File Processing Service**: 處理非即時的檔案上傳、轉檔等耗時任務。
2.  **滿足三大情境**:
    *   **情境 1 (即時)**: `Frontend -> Gateway (WebSocket) -> ASR Service -> Gateway -> Frontend`
    *   **情境 2 (摘要)**: 使用者在 `Frontend` 觸發 -> `Gateway (REST)` -> `LLM Service` 處理已有的逐字稿。
    *   **情境 3 (上傳)**: `Frontend` 上傳檔案 -> `Gateway (REST)` -> `File Proc. Service` 進行轉檔與預處理 -> `ASR Service` -> `LLM Service`。

---

## 4. 特定調查任務報告

### 4.1. CrewAI + Next.js + Python 實作評估

*   **CrewAI 特性**: CrewAI 是一個用於**協調多個自主 AI Agent** 的框架，它適用於需要多步驟、複雜推理與工具使用的**非同步長時任務**。例如：「請分析這份會議記錄，上網搜尋相關資料，並撰寫一份市場分析報告」。
*   **即時轉錄需求**: 即時轉錄的核心是**低延遲、高吞吐的串流資料處理**。
*   **結論**:
    *   **不適合**: 將 CrewAI 用於處理即時語音串流的路徑。這會引入不必要的延遲和複雜性。
    *   **非常適合**: 用於**第二和第三使用者情境**的後處理。例如，我們可以設計一個 "會議分析 Crew"，包含 "摘要 Agent"、"待辦事項提取 Agent"、"風險分析 Agent" 等，在會議結束後非同步地深度處理逐字稿。
    *   **建議**: 採用**混合方法**。即時路徑使用我們重構的架構，後處理任務則透過 Gateway 觸發一個 CrewAI 流程。

### 4.2. 前端相關資訊調查 (`meetingmind` & `x-meet`)

*   **`meetingmind`**:
    *   **技術棧**: Next.js, Tailwind CSS, Framer Motion, Prisma。
    *   **啟示**: 這是一個非常現代且高效的 Web App 技術棧。它的 UI/UX 設計和元件化思想是我們開發網頁介面的絕佳參考。我們應直接採用類似的技術棧。
*   **`x-meet`**:
    *   **技術棧**: Electron。
    *   **啟示**: 雖然我們不開發桌面應用，但其 `prompt.md` 檔案對於如何引導 LLM 生成結構化會議記錄非常有價值。AI 開發工程師應詳細研究其 Prompt 設計。

### 4.3. MVP 規劃 (以「即時字幕」為核心)

**MVP 目標**: 專注於實現**使用者情境 1** 的核心：使用者能在網頁上點擊「開始錄音」，麥克風的聲音被即時轉錄成逐字稿並顯示在畫面上。

**MVP 架構**:
`Browser (JS Audio API)` -> `WSS` -> `FastAPI Gateway` -> `gRPC` -> `Vertex AI ASR Endpoint` -> `gRPC` -> `FastAPI Gateway` -> `WSS` -> `Next.js UI`

**MVP 任務分配**:

*   **系統架構師**:
    *   [完成] 定義 MVP 的 C4 架構圖 (Container Level)。
    *   [進行中] 設計 FastAPI Gateway 與 ASR Service 之間的 gRPC 介面 (`.proto` file)。

*   **GCP 部署工程師**:
    *   [待辦] 將 `Taiwan-Tongues-ASR-CE` 模型打包成一個 Docker Image，其中包含一個 gRPC 伺服器來接收音訊串流。
    *   [待辦] 編寫 Terraform 或 `gcloud` CLI 腳本，將上述 Docker Image 部署為一個 Vertex AI Endpoint。
    *   [待辦] 進行初步的壓力測試，確保 Endpoint 的延遲和擴展性符合基本要求。

*   **全端工程師**:
    *   [待辦] **後端**: 建立 FastAPI 專案，並實作 WebSocket 端點 (`/ws`) 來處理與前端的雙向通訊。
    *   [待辦] **後端**: 實作 gRPC Client，以便從 Gateway 連接到 GCP 上的 ASR Service。
    *   [待辦] **前端**: 建立 Next.js 專案，使用 `react-media-recorder` 或類似庫來獲取麥克風原始音訊串流 (PCM a-law)。
    *   [待辦] **前端**: 實作 WebSocket Client，將音訊區塊 (audio chunks) 即時發送到後端，並接收回傳的逐字稿以更新 UI。

*   **AI 開發工程師**:
    *   [待-支援] 支援 GCP 部署工程師，提供 `Taiwan-Tongues` 模型所需的 Python 環境和依賴項。
    *   [待辦] 在此階段，研究 LLM 潤飾逐字稿的 prompt，為下一階段做準備。暫不納入 MVP。

*   **資安工程師**:
    *   [待辦] 確保 Gateway 使用 `WSS`。
    *   [待辦] 與 GCP 工程師合作，確保 Vertex AI Endpoint 的網路安全設置（例如，僅允許從 Gateway 訪問）。

*   **風險分析師**:
    *   [完成] 確認 MVP 所用開源庫 (e.g., FastAPI, Next.js) 的授權。

---

## 5. 下一階段展望

當 MVP 成功交付並驗證後，我們將進入 **第二階段：需求訪談**。

*   我們將邀請內部使用者測試 MVP，收集他們對於即時轉錄準確性、延遲、UI/UX 的回饋。
*   與產品經理訪談，細化**情境 2 和 3** 的具體需求，特別是「使用者自定義提示詞模板」的詳細規格。

完成需求訪談後，進入 **第三階段：功能模組設計與規劃**，屆時將產出更詳細的資料庫 Schema、API 規格文件以及包含 LLM Service 和 File Processing Service 的完整架構設計。

---
**文件結束**
