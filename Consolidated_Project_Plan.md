# 專案：會議 AI 助理 - 綜合開發計畫書 (Consolidated Project Plan)

**文件版本:** 2.0
**日期:** 2025-12-04
**摘要:** 本文件整合了專案的初期廣泛調查、深度研究報告，以及具體的 MVP 開發計畫，作為整個專案的核心指導文件。

---
---

# 第一部分：初期專案規劃與廣泛調查
*(源自: Meeting_AI_Assistant_Project_Plan_Phase1.md)*

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
---

# 第二部分：深度研究報告
*(源自: DeepResearch.md)*

## 1. 執行摘要與戰略願景

### 1.1 專案背景與任務定義
本報告旨在為開發團隊提供一份詳盡的架構藍圖，目標是構建一個企業級的會議 AI 助理系統。作為開發團隊的管理者，我們面臨的挑戰不僅是技術實作，更是一場關於「資訊治理」的數位轉型。根據需求，我們的團隊編制涵蓋了 AI 演算法工程師、資訊安全工程師以及 **Google Cloud Platform (GCP)** 部署工程師，這意味著我們必須從模型效能、系統安全與基礎建設彈性三個維度來審視整個專案。

本次開發的核心任務包含三大功能支柱：
1.  具備 **LLM** 潤飾能力的即時語音轉錄（MVP 核心）。
2.  基於提示詞模板的結構化會議記錄生成。
3.  支援多媒體上傳與多格式匯出的非同步處理能力。

值得注意的是，技術選型上已明確指定採用 **adi-gov-tw/Taiwan-Tongues-ASR-CE** 作為語音識別引擎，並部署於 **GCP** 環境。這項決策確立了我們在台灣在地化語言處理上的優勢，特別是針對中英夾雜與台語混用的商務場景，但也同時帶來了模型部署與推論延遲的技術挑戰。

### 1.2 從轉錄到決策：市場典範轉移
根據《Meeting Ink 白皮書：AI 會議紀錄從文字轉錄到決策》的市場調查數據顯示，當前企業對於會議工具的需求已發生根本性的質變[^1]。過去市場競逐的是「逐字稿的準確率」（Word Error Rate, WER），但現在戰場已轉移至「決策速度」（Decision Velocity）。企業觀點認為，摘要與模板本質上是將 AI 能力封裝成「可治理的工作標準」[^1]。這意味著我們的 AI 助理不能僅僅是一個被動的速記員，而必須進化為一個主動的「會議顧問」。

數據顯示，約有 40% 的會議在結束後會產出摘要，這代表使用者已將 AI 工具視為生產力流程的一部分，而非單純的錄音倉庫[^1]。因此，本專案的戰略核心在於「結構化認知」——即如何透過精心設計的**提示工程（Prompt Engineering）**，將非結構化的對話流轉化為結構化的決策數據（如：待辦事項、風險評估、決策結論），並確保這些數據具備可追溯性與可稽核性。

### 1.3 方法論：第一性原理與 MECE 分析
為了確保系統架構的堅韌性，本報告將採用**「第一性原理」（First Principles）**與**「MECE」（Mutually Exclusive, Collectively Exhaustive，相互獨立、完全窮盡）**原則進行分析。我們將解構現有的開源專案（如 TranscriptHub, meeting-minutes 等），剝離其表層功能，直探其運作的物理本質（如音訊流的封包處理、上下文視窗的限制、瀏覽器記憶體管理），再根據我們的特定需求（**GCP** 架構、台灣語言模型）進行重構。這將確保我們的設計不僅僅是功能的堆疊，而是從底層邏輯上就具備高效能與高擴展性。

## 2. 第一性原理視角下的開源生態解構與重構
為了避免重複造輪子並吸取社群的最佳實踐，我們針對六個關鍵 GitHub 專案進行深度剖析。我們不關注其程式碼細節，而是關注其解決問題的「核心真理」。

### 2.1 AS-AIGC/TranscriptHub：聚合層的物理本質
- **第一性原理分析**：TranscriptHub 的存在解決了「模型碎片化」的問題。其核心真理在於，使用者不關心背後是 **OpenAI** 還是 **Azure**，他們只關心「輸入音訊，輸出文字」。從系統設計角度看，這是一個標準的**「適配器模式」（Adapter Pattern）**應用，將異質的 API 介面標準化。
- **MECE 解構**：
    - **輸入端**：涵蓋即時流（**WebSocket**）與靜態檔（Upload）。
    - **處理端**：涵蓋同步請求與非同步隊列。
    - **輸出端**：涵蓋原始 JSON 與格式化文本（SRT/VTT）。
- **本專案重構策略**：雖然我們鎖定 **adi-gov-tw** 模型，但為了系統的**強韌性（Robustness）**，GCP 部署工程師需設計一個「模型抽象層」。這允許我們在模型負載過高或遇到極端方言障礙時，能動態切換至備援模型（如 Google Speech-to-Text API），確保服務不中斷。

### 2.2 Zackriya-Solutions/meeting-minutes：認知壓縮的邏輯
- **第一性原理分析**：此專案的核心在於「資訊熵的減少」。原始逐字稿包含大量冗餘資訊，其價值密度極低。該專案透過 **LLM** 的語意理解能力，將高熵的對話壓縮為低熵的摘要。
- **MECE 解構**：
    - **切分策略（Chunking）**：處理超長會議（超過 LLM Context Window）的物理限制，通常採用 **Map-Reduce** 或 **Refine** 策略。
    - **提示策略（Prompting）**：分為**零樣本（Zero-shot）**與**少樣本（Few-shot）**學習，決定了輸出的結構化程度。
- **本專案重構策略**：我們將引入 MeetingInk 提出的「模板治理」概念[^1]。AI 工程師需設計一套動態的 **Chunking** 機制，不僅是按時間切分，更要按「語者轉換」或「主題變更」進行語意切分，以提高摘要的精準度。

### 2.3 WEIFENG2333/VideoCaptioner：多媒體處理的管線物理
- **第一性原理分析**：影片轉錄本質上是「訊號分離」與「時間對齊」的過程。視覺訊號（Video）與聽覺訊號（Audio）必須被**解耦合（Demuxing）**，處理完畢後再重新**耦合（Remuxing）**。
- **MECE 解構**：
    - **前處理**：格式轉換（ffmpeg）、採樣率統一（16kHz 為 ASR 標準）。
    - **對齊**：時間戳記（Timestamp）的精確映射。
- **本專案重構策略**：這直接對應到我們的「功能 3」。GCP 部署工程師需利用 **Cloud Functions** 與 **Cloud Storage** 構建一個事件驅動的媒體處理管線。當大檔案上傳時，不應阻塞主伺服器，而是觸發一個獨立的運算單元（**Cloud Run Jobs**）進行 ffmpeg 處理，確保系統的高吞吐量。

### 2.4 QuentinFuxa/WhisperLiveKit：即時流的時序挑戰
- **第一性原理分析**：即時轉錄（**Real-time ASR**）與離線轉錄截然不同，它處理的是「無限長的二進位流」。其核心挑戰在於「延遲」與「準確度」的博弈。串流需要持續的 **WebSocket** 連線狀態管理。
- **MECE 解構**：
    - **傳輸層**：**WebSocket** vs **gRPC**。
    - **切分邏輯**：**語音活動檢測（VAD）**決定何時將緩衝區送入模型。
- **本專案重構策略**：這是 MVP 的核心。我們必須實作「客戶端 VAD」。資安工程師需注意，**WebSocket** 連線長時間保持開啟可能帶來的 **DDoS** 風險，需配置 **Cloud Armor** 進行流量清洗。同時，AI 工程師需在後端實作「推測性解碼」或「穩定性演算法」，解決即時字幕閃爍（Flickering）的問題。

### 2.5 misbahsy/meetingmind：全端互動的體驗設計
- **第一性原理分析**：使用者的價值感知並非來自後端強大的模型，而是來自前端的「互動儀表板」。MeetingMind 展現了 **React/Next.js** 在狀態管理上的優勢，將會議記錄視為一個可檢索的資料庫。
- **MECE 解構**：
    - **狀態同步**：錄音中的波形視覺化與文字生成的同步渲染。
    - **資料持久化**：會議結束後的資料庫寫入與索引建立。
- **本專案重構策略**：參考 MeetingInk 的發現，使用者需要的是「可交付的成果」[^1]。前端設計不應只是一個播放器，而應是一個「編輯器」。我們需在 **Next.js** 中實作富文本編輯器，讓使用者能即時修正 AI 的錯誤，並將修正回饋給模型（**Human-in-the-loop**）。

### 2.6 superlanding/x-meet：瀏覽器整合的邊界突破
- **第一性原理分析**：會議發生在瀏覽器分頁中（Google Meet/Teams），而非桌面應用。x-meet 利用**瀏覽器擴充功能（Extension）**突破了作業系統的音訊捕獲限制。
- **MECE 解構**：
    - **音訊源捕獲**：`chrome.tabCapture` API 與系統麥克風的混音（Mixing）。
    - **介面注入**：將字幕層覆蓋（Overlay）在會議軟體之上。
- **本專案重構策略**：雖然初期可能以獨立 Web App 為主，但長遠規劃必須包含瀏覽器擴充功能。這能讓我們的產品無縫嵌入使用者的工作流，直接在 Google Meet 介面中顯示即時字幕與 AI 摘要。

### 2.7 fastrepl/hyprnote：邊緣運算的隱私邊界
- **第一性原理分析**：`hyprnote` 的核心真理是**「資料主權」**與**「隱私保護」**。它將 AI 計算帶到資料端（即使用者本機），而非將資料送到雲端。透過監聽系統音訊並在本地處理，它從根本上消除了對會議內容外洩的擔憂，這對於處理高度敏感資訊的企業或個人具有無可取代的價值。
- **MECE 解構**：
    - **應用程式層**：使用 **Tauri** (Rust + React) 框架，兼顧了執行的效能與前端開發的效率。
    - **儲存層**：**本地優先（Local-first）**架構，所有筆記和逐字稿預設儲存在使用者本機，可能採用 SQLite。
    - **AI 模型層**：**可插拔設計（Pluggable）**。支援完全離線的本地 LLM（如 **Ollama**, **LM Studio**），同時也提供選項連接到雲端 LLM API（如 Gemini, Claude）。
    - **整合層**：支援與 Apple Calendar, Obsidian 等本地應用程式整合，強化個人工作流程。
- **本專案重構策略**：
    1.  **強化模型服務的彈性**：`hyprnote` 的可插拔 LLM 策略是重要的啟示。我們的 **LLM Service** 必須設計成一個具有標準化介面的「路由器」，使其能輕易地在不同的 LLM 提供者之間切換。這不僅包括雲端 API，也應預留連接到本地（或企業私有雲）Ollama 服務的選項，以滿足不同客戶的資安等級和成本考量。
    2.  **使用者為中心的摘要**：其「基於使用者筆記生成個人化摘要」的功能點，為我們的摘要演算法提供了新思路。我們的 **CrewAI** 分析師 Agent 不應只對完整逐字稿進行無差別摘要，而應優先分析使用者在會議中標記的「重點」（Timestamp Markers），並結合這些重點來生成更貼近使用者需求的摘要。
    3.  **探索混合架構**：雖然我們的專案是雲端優先，但 `hyprnote` 的成功驗證了市場對本地化、高隱私方案的需求。在產品的未來藍圖中，可以規劃一個「企業內部部署 (On-Premise)」版本或一個功能有限的「離線版」桌面應用，作為產品線的延伸。

### 2.8 SakiRinn/LiveCaptions-Translator: 寄生架構的極致
- **第一性原理分析**：「不重新發明輪子」。既然 Windows 11 已經內建了系統級的 Live Captions（使用 NPU 或高效 CPU 推論），此專案選擇了「寄生」架構——不負責轉錄，而是攔截系統 UI 的文字，專注於翻譯與轉發。
- **MECE 解構**：
    - **訊號源**：Windows UI Automation (非音訊，而是視覺/文字控制碼)。
    - **處理**：輕量級翻譯 API (Ollama/DeepL)。
- **本專案重構策略**：這是「桌面端」的終極輕量化方案。若未來開發 Windows 專用客戶端，我們不應堅持自帶模型，而應提供「系統整合模式」，直接讀取 OS ASR 結果，只負責 LLM 摘要，將資源消耗降至最低。

### 2.9 Collabora/WhisperLive: 串流解碼的理論邊界
- **第一性原理分析**：解決 Whisper 原生「非串流」架構的矛盾。OpenAI Whisper 本質是 Seq2Seq 模型，設計上處理 30秒 chunks。WhisperLive 透過 **VAD** 與 **TensorRT** 加速，強行將其改造為即時流。
- **MECE 解構**：
    - **推論後端**：TensorRT-LLM / Faster-Whisper (CTranslate2)。
    - **串流策略**：Rolling Buffer (滑動窗口) + VAD 截斷 + SimulStreaming (預測性解碼)。
- **本專案重構策略**：這驗證了我們 MVP 選用 **Faster-Whisper** 或 **TensorRT** 的必要性。標準 PyTorch 推論對於即時串流來說太慢。我們必須在 GCP Vertex AI 上使用優化過的 Runtime (如 Triton + TensorRT) 來達到 < 500ms 的延遲。

### 2.10 royshil/obs-localvocal: 嵌入式與邊緣運算
- **第一性原理分析**：應用程式內的「零延遲」需求。作為 OBS Plugin，它必須與影像幀同步。它選擇了 **whisper.cpp** (C++)，犧牲部分精度換取極致的 CPU 效率與相容性，且完全離線。
- **MECE 解構**：
    - **執行環境**：嵌入式 (DLL/So)，與主程式共享記憶體。
    - **模型**：量化模型 (Quantized, q5_0, q8_0)。
- **本專案重構策略**：當我們未來需要開發「瀏覽器擴充功能」或「桌面 SDK」時，**whisper.cpp** (WASM 版本) 是唯一能在客戶端不依賴伺服器運行的選擇。這為我們的「離線模式」提供了技術路徑。

### 2.11 light12222/Voice2Sub: 膠水代碼的快速原型
- **第一性原理分析**：「功能聚合」。將現成的強大工具 (WhisperX, Google Translate) 透過簡單的 Python GUI (PyQt) 黏合，解決「看劇生肉」的具體痛點。
- **MECE 解構**：
    - **核心**：WhisperX (具備 Word-level timestamp 強項)。
    - **介面**：透明置頂視窗 (Overlay)。
- **本專案重構策略**：WhisperX 的**強制對齊 (Forced Alignment)** 功能對於「字幕生成」至關重要。我們的 File Processing Service (非即時上傳處理) 應採用 WhisperX 而非標準 Whisper，以獲得精確到單字的字幕時間軸，提升使用者回放體驗。

## 3. 廣泛調查階段：技術堆疊評估與可行性分析
在此階段，我們深入評估指定的技術堆疊：**CrewAI + Next.js + Python**，並結合 **GCP** 架構進行可行性驗證。

### 3.1 CrewAI + Next.js + Python 實作可行性評估

#### 3.1.1 Next.js (Frontend)
- **評估結論**：極高度推薦。
- **技術依據**：**Next.js** (基於 React) 是目前建構高效能儀表板的業界標準。其 **Server-Side Rendering (SSR)** 與 **React Server Components (RSC)** 特性能夠有效處理大量會議歷史列表的渲染效能。
- **即時性挑戰**：對於功能 1（即時轉錄），**Next.js** 需要透過 Custom Hooks (`useWebSocket`) 來管理 **WebSocket** 連線。需特別注意**記憶體洩漏（Memory Leak）**問題，會議可能長達數小時，前端若未妥善管理 DOM 節點增長，會導致瀏覽器崩潰。

#### 3.1.2 Python (Backend)
- **評估結論**：必要且唯一選擇。
- **技術依據**：AI 生態系（**PyTorch**, **HuggingFace**, **LangChain**）原生支援 **Python**。**adi-gov-tw** 模型本身即是以 **Python** 運行。
- **架構建議**：採用 **FastAPI** 作為後端框架。相較於 Flask/Django，**FastAPI** 原生支援非同步處理 (`async/await`)，這對於處理大量並發的 **WebSocket** 連線（即時字幕服務）至關重要。同步框架在高並發下會導致**線程阻塞（Thread Blocking）**，無法滿足即時性需求。

#### 3.1.3 CrewAI (Agentic Orchestration)
- **評估結論**：適用於後處理（功能 2），不適用於即時處理（功能 1）。
- **技術依據**：**CrewAI** 是一個多代理人（Multi-Agent）協作框架，擅長複雜的任務規劃與執行。
- **應用場景**：
    - **即時轉錄**：不建議使用。**CrewAI** 的代理人互動涉及多次 **LLM** 往返，延遲極高，無法滿足即時字幕「毫秒級」的要求。
    - **結構化會議記錄**：完美契合。我們可以設計一個「虛擬秘書團隊」：
        - **Agent A (記錄員)**：負責清理逐字稿，修正錯別字。
        - **Agent B (分析師)**：根據選定的模板（如 BANT 銷售模板[^1]）提取關鍵資訊。
        - **Agent C (稽核員)**：檢查是否有遺漏的欄位（如「待辦事項」未指定負責人），落實 MeetingInk 提到的治理需求[^1]。

### 3.2 meetingmind 與 x-meet 前端資訊的深度洞察
根據 `prompt.md` 中對於這些專案的描述（模擬），我們歸納出以下前端設計規範：
- **視覺化回饋**：即時錄音介面必須包含**音波圖（Waveform）**，這不僅是美觀，更是讓使用者確認「麥克風有在收音」的重要 UX 指標。
- **滾動鎖定機制**：當即時字幕快速生成時，視窗會自動捲動到底部。但若使用者想回看前一段話，系統必須偵測到滾動行為並暫停自動捲動（Scroll Lock），否則使用者體驗會極差。
- **標籤管理系統**：`meetingmind` 顯示了**標籤（Tags）**的重要性。我們的前端需支援在錄音過程中**「打點」（Timestamp Marker）**，例如點擊「重要」按鈕，便在當下時間戳記上標記，供後續 **CrewAI** 優先處理該段落。

## 4. 核心技術深探：adi-gov-tw 模型與 GCP 架構
本專案的心臟是 **adi-gov-tw/Taiwan-Tongues-ASR-CE** 模型。要駕馭此模型，我們必須深入了解其特性與部署眉角。

### 4.1 模型特性推論與在地化優勢
雖然我們將其視為黑盒，但根據命名與用途推斷，此模型極可能基於 **Conformer** 或 **Whisper** 架構進行了針對台灣口音、台語（Hokkien）與**中英夾雜（Code-switching）**的**微調（Fine-tuning）**。
- **Code-Switching 挑戰**：台灣商務會議常出現「這個 Project 的 Schedule 有點 delay」這類語句。標準的中文或英文模型常會在此崩潰。此模型的價值在於能平滑處理語種切換。
- **台語支援**：針對政府或傳統產業會議，台語識別是剛需。
- **推論成本**：這類大模型通常參數量巨大（可能在 1B 以上），對 VRAM 有較高要求。

### 4.2 GCP 部署架構設計（資安與效能並重）
GCP 部署工程師需構建以下基礎設施：

| 元件層級 | GCP 服務 | 選型理由 |
| :--- | :--- | :--- |
| **運算層 (ASR)** | **GKE** (Google Kubernetes Engine) | 需配置 GPU Node Pool (NVIDIA L4 或 T4)。GKE 提供容器編排能力，能根據 CPU/GPU 利用率自動擴縮（Auto-scaling），應對會議尖峰。 |
| **運算層 (Backend)** | **Cloud Run** | 用於 FastAPI 服務與 CrewAI 代理人。Serverless 架構，依請求計費，適合處理 HTTP API 與 WebHook。 |
| **儲存層 (Raw)** | **Cloud Storage (GCS)** | 儲存原始音訊/影片檔。需設定 Lifecycle Policy，將超過 30 天的檔案轉入 Coldline 以節省成本[^1]。 |
| **資料庫 (Meta)** | **Cloud SQL (PostgreSQL)** | 儲存使用者資料、會議元數據、權限設定。 |
| **資料庫 (Vector)** | **Vertex AI Vector Search** | 儲存逐字稿的向量嵌入（Embeddings），支援語意搜尋功能（如：「搜尋關於預算的所有討論」）。 |
| **網路層** | **Cloud Load Balancing** | 支援 WebSocket 協議，並開啟 Session Affinity（黏性會話），確保串流封包路由到同一台 ASR 伺服器。 |
| **安全層** | **VPC Service Controls & IAM** | 資安工程師需設定 VPC 邊界，限制資料僅能在特定專案內流動。IAM 權限需遵循最小權限原則（Least Privilege）。 |

## 5. 需求訪談與使用者畫像分析（基於 MeetingInk 白皮書）
根據 MeetingInk 白皮書的研究，我們不能將所有使用者視為同一類人。不同的職位對「會議記錄」有完全不同的期待[^1]。

### 5.1 銷售代表 (Sales Rep)
- **痛點**：每天與多個客戶通話，常忘記客戶的具體反對意見（Objection）或預算細節。
- **需求**：
    - **模板**：**BANT** (Budget, Authority, Need, Timing)。
    - **功能**：通話結束後 5 分鐘内，自動生成一封「後續跟進 Email」草稿，包含雙方達成共識的下一步。
- **治理重點**：確保摘要內容準確，避免承諾未經授權的折扣。

### 5.2 人資經理 (HR Manager)
- **痛點**：面試紀錄散落在紙本筆記，難以進行公平的跨候選人比較；且需避免紀錄中出現帶有偏見的詞彙。
- **需求**：
    - **模板**：**STAR** (Situation, Task, Action, Result) 或勝任力評分表。
    - **功能**：敏感資料保護。面試錄音需在生成摘要後自動進行 **PII（個人識別資訊）**去識別化，且錄音檔需設定嚴格的存取權限。
- **治理重點**：**合規性（ISO 27001/GDPR）**，確保面試流程符合公司政策[^1]。

### 5.3 研發主管 (R&D Lead)
- **痛點**：技術會議冗長，決策常淹沒在技術細節討論中。
- **需求**：
    - **模板**：決策/風險/障礙 (**Decision/Risk/Blocker**)。
    - **功能**：與 **Jira/Linear** 整合。AI 識別出的「Action Item」應能一鍵轉換為 Jira Ticket。
- **治理重點**：**可追溯性**。三個月後若程式碼出問題，能回溯當初是「誰」在「什麼情境」下做出的架構決策。

## 6. 功能模組設計與實作藍圖
我們將系統劃分為三個核心模組，並依照優先順序進行開發。

### 6.1 模組一：即時字幕串流引擎 (MVP 核心)
這是最技術密集且最優先的模組。
- **客戶端 (Next.js)**：
    - 利用 **Web Audio API** (`AudioContext`) 擷取麥克風串流。
    - **邊緣運算 VAD**：在瀏覽器端載入輕量級 VAD 模型（如 `onnx-silero-vad`）。只有偵測到人聲時才發送 WebSocket 封包，這能節省 50% 以上的伺服器頻寬與 GPU 運算資源。
- **伺服器端 (FastAPI + GKE)**：
    - **串流緩衝區 (Buffer)**：接收二進位音訊流，組合成適合模型推論的長度（例如 0.5 秒）。
    - **推論優化**：利用 **NVIDIA Triton Inference Server** 部署 Taiwan-Tongues 模型，並開啟 **Dynamic Batching**，同時處理多個使用者的請求。
    - **LLM 潤飾 (非同步)**：當 ASR 輸出一個完整句子後，將其推送到一個輕量級 LLM（如 Llama-3-8B，部署於同叢集），進行即時語法修正（去除冗詞、修正倒裝句），然後再推送到前端顯示。

### 6.2 模組二：結構化會議記錄生成器 (MeetingInk 引擎)
這是展現商業價值的模組，落實「模板即治理」的概念。
- **觸發機制**：會議結束或檔案上傳完成。
- **CrewAI 協作流**：
    1.  **步驟 1 (Map)**：若會議超過 1 小時，先將逐字稿切分為 10 分鐘的片段，由 `Summarizer Agent` 進行摘要。
    2.  **步驟 2 (Reduce)**：將所有片段摘要合併。
    3.  **步驟 3 (Extract)**：`Extractor Agent` 載入使用者選定的模板（如「專案週會」），從合併摘要中提取特定欄位（如「進度落後項目」）。
    4.  **步驟 4 (Verify)**：`Governance Agent` 檢查輸出品質。例如，若發現有「待辦事項」但沒有「負責人」或「截止日」，則標記為「缺失」，並在前端提示使用者手動補充。

### 6.3 模組三：多媒體中心與匯出
- **媒體處理管線**：
    - 使用者上傳影片 -> GCS Bucket -> 觸發 Cloud Pub/Sub -> 啟動 Cloud Run Job。
    - Job 執行 `ffmpeg` 提取音軌 -> 呼叫 ASR 服務 -> 儲存結果。
- **多格式匯出**：
    - **PDF/Docx**：用於正式公文。需包含會議資訊表頭、結構化摘要、以及完整的逐字稿附錄。
    - **SRT/VTT**：用於影片字幕。需精確對應時間軸。
    - **JSON**：用於系統整合（如匯入 Notion）。

## 7. 專案實施路線圖 (Roadmap)

### 第一階段：基礎建設與 MVP (第 1-4 週)
- **目標**：完成 GCP 環境搭建，並實現「對著瀏覽器說話，看到字幕出現」。
- **關鍵產出**：
    - GKE GPU Cluster 就緒。
    - Taiwan-Tongues 模型成功容器化並透過 WebSocket 服務。
    - Next.js 前端具備基本的錄音與即時顯示功能。
- **驗收標準**：即時字幕延遲 < 3 秒，中英夾雜識別率可接受。

### 第二階段：結構化智慧 (第 5-8 週)
- **目標**：整合 CrewAI 與模板系統。
- **關鍵產出**：
    - 實作 Sales, HR, R&D 三大基礎模板。
    - 完成後端非同步任務隊列（Celery/Redis）。
    - 前端儀表板支援會議歷史瀏覽與摘要編輯。
- **驗收標準**：MeetingInk 的 `SCR (Summary Creation Rate)` 指標追蹤機制上線。

### 第三階段：企業級交付 (第 9-12 週)
- **目標**：資安合規、檔案上傳與匯出。
- **關鍵產出**：
    - 實作 IAM 角色權限管理。
    - 完成 PII 自動遮罩功能。
    - 支援影片上傳與 PDF 匯出。
- **驗收標準**：通過資安工程師的滲透測試與 ISO 合規性檢查。

## 8. 結論
本專案不僅僅是導入一個語音識別模型，而是為企業構建一套「聽覺神經系統」。透過採用 **adi-gov-tw/Taiwan-Tongues-ASR-CE**，我們確保了系統在台灣語言環境下的適應性；透過 **CrewAI** 與結構化模板的結合，我們落實了 MeetingInk 所倡議的「資訊治理」，將會議噪音轉化為高價值的決策資產。憑藉 **GCP** 強大的基礎設施與我們嚴謹的**第一性原理**架構設計，團隊已準備好迎接開發挑戰，將此 AI 助理打造為提升企業決策速度的關鍵引擎。

---
## 參考文獻
[^1]: MeetingInk白皮書.pdf

---
---

# 第三部分：MVP 開發藍圖 (V2)
*(源自: MVP_Development_Plan.md)*

## 第一階段：需求文件化 (Requirements Documentation)

### 1. 核心目標 (Core Objective)
打造一個具備**服務不中斷轉錄機制**的 AI 會議助理 MVP。此系統能從使用者本機捕獲音訊，持續進行即時轉錄與智慧潤飾，直到使用者明確停止，並支援中英雙語切換。

### 2. 第一性原理分析 (First Principles)
- **根本需求**: 使用者需要一個「可靠的數位耳朵」，能不遺漏、不間斷地捕捉對話，並將其轉化為乾淨、易讀、可用的文字記錄。核心是**持續性**與**可讀性**。
- **物理限制**:
    - **網路**: 網際網路是不穩定的。系統必須能應對短暫的斷線與延遲。
    - **瀏覽器**: 瀏覽器對背景處理、記憶體用量均有限制。
    - **模型推論**: ASR 和 LLM 推論都需要時間，這與「即時」存在本質上的矛盾。系統設計必須圍繞「管理延遲」而非「消除延遲」。

### 3. MECE 使用者情境分析 (User Scenarios)

#### 主要情境 (Happy Path):
- **情境 H-1 (開始轉錄)**: 使用者打開網頁，看到「準備就緒」狀態。點擊「開始錄製」後，系統狀態變為「正在聆聽...」，並開始捕捉本機播放的音訊（如 YouTube 影片）。
- **情境 H-2 (持續轉錄)**: 當音訊播放時，逐字稿（預設中文）持續出現在畫面上。整個過程流暢，不會因句子結束而停頓。
- **情境 H-3 (即時潤飾)**: 使用者觀察到剛出現的逐字稿會自動變化，例如「呃...那個...我想說...」在短時間內變為「我想說」。句子會被自動加上標點符號，並在適當的地方斷句。
- **情境 H-4 (雙語切換)**: 使用者點擊「切換為英文」按鈕，畫面上所有的中文逐字稿內容立刻變為對應的英文翻譯。再次點擊可切換回中文。
- **情境 H-5 (停止轉錄)**: 使用者點擊「停止錄製」，錄製圖示停止，逐字稿不再更新，系統狀態變為「錄製結束」。

#### 替代與異常情境 (Alternative & Edge Cases):
- **情境 E-1 (無聲環境)**: 使用者開始錄製，但環境安靜。系統應顯示「正在聆聽...」或「未偵測到聲音」，而非產生錯誤或無意義的輸出。
- **情境 E-2 (網路瞬斷)**: 使用者網路不穩。前端應有緩衝機制，並在 UI 上顯示「連線不穩，嘗試重連中...」的圖示。恢復連線後，應能從中斷處繼續（或僅遺失少量數據）。
- **情境 E-3 (LLM 服務延遲/失敗)**: LLM 潤飾服務回應緩慢或失敗。系統應**優雅降級**，優先顯示未經潤飾的「原始」逐字稿，確保核心轉錄功能不受影響。潤飾成功後，再更新對應的句子。
- **情境 E-4 (瀏覽器行為)**: 使用者切換到其他瀏覽器分頁。音訊捕捉與轉錄應在背景持續執行（受瀏覽器策略限制）。
- **情境 E-5 (混合語言)**: 音訊源包含中英夾雜。ASR 服務應能正確識別，並輸出包含兩種語言的逐字稿。
- **情境 E-6 (快速操作)**: 使用者在短時間內反覆點擊「開始/停止」按鈕。系統應能正確管理狀態，不會崩潰或產生非預期行為。

---

## 第二階段：功能設計 (Function Design)

根據上述需求，我們將 MVP 功能設計拆解為以下五個核心模組：

### 1. 前端音訊捕獲模組 (Client-Side Audio Capture)
- **職責**: 捕捉、處理並傳送音訊。
- **設計**:
    - 使用 **Web Audio API** (`AudioContext`) 獲取使用者麥克風或系統音訊。
    - 內建 **客戶端語音活動檢測 (VAD)**，僅在偵測到語音時，才將音訊封包（PCM a-law 格式）透過 WebSocket 傳送，以節省頻寬。
    - 管理 WebSocket 的完整生命週期狀態（Connecting, Open, Reconnecting, Closed），並在 UI 上提供明確的視覺回饋。

### 2. 即時通訊閘道模組 (Real-time Communication Gateway)
- **職責**: 作為前後端與後端微服務之間的中介。
- **設計**:
    - 使用 **FastAPI** 建立 WebSocket 端點，接收前端傳來的二進位音訊流。
    - 將音訊流非同步地轉發給 **ASR 服務**。
    - 收到 ASR 回傳的「原始片段」後，立即將其非同步地轉發給 **LLM 潤飾模組**。
    - **關鍵設計**: 為了降低延遲感，閘道會先將「原始片段」加上唯一 ID 後發送給前端。當收到「潤飾片段」後，再將其透過 ID 發送給前端進行更新。
    - 管理來自多個後端服務的回應，並統一廣播給對應的前端客戶。

### 3. ASR 轉錄服務模組 (ASR Transcription Service)
- **職責**: 專注於將音訊流轉為文字。
- **設計**:
    - 接收來自閘道的 gRPC 音訊流。
    - 核心使用 `Taiwan-Tongues-ASR-CE` 模型。
    - 輸出帶有時間戳和唯一 ID 的「原始文字片段」。

### 4. LLM 即時潤飾模組 (Live LLM Refinement)
- **職責**: 監控文字流並進行潤飾與翻譯。
- **設計**:
    - 接收閘道傳來的「原始片段」。
    - 維護一個包含上下文的短文字緩衝區（例如，最近的兩三句話）。
    - **潤飾功能**: 呼叫一個高速 LLM（例如，本地部署的 Llama-3-8B 或 Groq API）執行預設的 Prompt（例如：「請將以下文字修正得更通順自然，移除贅詞，並加上標點」）。
    - **翻譯功能**: 當使用者觸發時，呼叫 LLM 執行翻譯 Prompt。
    - 將處理完的「潤飾片段」或「翻譯片段」連同其唯一 ID 回傳給閘道。

### 5. 雙語顯示與狀態管理模組 (Bilingual Display & State)
- **職責**: 渲染與管理前端所有狀態。
- **設計**:
    - 使用 **React (Next.js)** 的狀態管理（如 Zustand 或 React Context）。
    - 資料結構：維護一個 Segments 陣列，`[{id, rawText, refinedText, translatedText, timestamp}]`。
    - UI 根據 `id` 接收並更新特定 segment 的 `refinedText` 或 `translatedText`，避免重新渲染整個列表。
    - 根據使用者選擇的語言，動態渲染 `refinedText` 或 `translatedText`。

---

## 第三階段：開發任務化 (Development Task Breakdown)

我們將採用您提出的三階段部署策略，並將開發任務拆分如下：

### 部署階段一：本機開發與驗證 (Local-Only Deployment)

- **Sprint 0: 環境搭建**
    - **任務 (全員)**: 安裝 Docker, Node.js, Python 等本地開發環境。
    - **任務 (全端/GCP)**: 編寫 `docker-compose.yml`，整合 FastAPI, 一個模擬 ASR 的服務, 以及 Neon 的本地 Postgres 實例。
    - **任務 (AI)**: 將 `Taiwan-Tongues-ASR-CE` 模型成功容器化。

- **Sprint 1: 核心轉錄管線**
    - **任務 (全端)**: 實作前端音訊捕獲與 VAD，並建立到後端 FastAPI 的 WebSocket 連線。
    - **任務 (AI/全端)**: 將容器化的 ASR 模型整合進 docker-compose，並讓 FastAPI 能透過 gRPC 與之通訊。
    - **驗收標準**: 開發者可以在瀏覽器上點擊按鈕，終端機（後端日誌）能印出 ASR 服務回傳的「原始」中文逐字稿。

- **Sprint 2: 不中斷轉錄與 LLM 潤飾**
    - **任務 (AI)**: 使用 **Ollama** 在本地運行一個輕量級 LLM (如 Llama-3-8B)，並設計潤飾 Prompt。建立 LLM 潤飾服務。
    - **任務 (全端)**: 在閘道中整合潤飾服務，並實作「先顯示原始稿，再非同步更新潤飾稿」的機制。
    - **驗收標準**: 在前端介面上，可以看到原始逐字稿出現後，在短時間內被潤飾後的文字替換。使用長度超過 5 分鐘的 YouTube 影片進行測試，轉錄全程不中斷。

- **Sprint 3: 雙語功能與 UI**
    - **任務 (AI)**: 為 LLM 服務增加翻譯功能。
    - **任務 (全端)**: 完成前端 UI，包括語言切換按鈕、狀態顯示、美觀的逐字稿列表。
    - **驗收標準**: MVP 所有核心功能在本機環境完美運行。

### 部署階段二：類伺服器平台部署 (Staging Deployment)

- **Sprint 4: 遷移至 Railway/Cloudflare/Neon**
    - **任務 (全端/GCP)**: 將 Next.js 前端部署到 **Cloudflare Pages**。
    - **任務 (全端/GCP)**: 將 FastAPI 閘道與 LLM 潤飾服務部署到 **Railway**。
    - **任務 (全端/GCP)**: 將資料庫遷移至 **Neon** 雲端實例。
    - **挑戰與任務 (AI/GCP)**: Railway 不提供 GPU。此階段 ASR 服務有兩個選項：
        1.  **選項 A (建議)**: 暫時切換為使用第三方 ASR API（如 Deepgram/AssemblyAI）以驗證雲端管線。
        2.  **選項 B**: 在本地保留 ASR 服務，並使用 ngrok 等工具建立通道供 Railway 呼叫（僅供測試）。
    - **驗收標準**: 整個系統在公網環境下可供內部團隊測試。

### 部署階段三：GCP 生產環境部署 (Production Deployment)

- **Sprint 5: 遷移至 GCP**
    - **任務 (GCP)**: 在 **GKE** 上建立 GPU 節點池，並將容器化的 `Taiwan-Tongues-ASR-CE` 部署上去。
    - **任務 (GCP)**: 將 Railway 上的 FastAPI 與 LLM 服務遷移至 **Cloud Run** 或 GKE。
    - **任務 (全端)**: 將 Cloudflare Pages 的後端 API 指向 GCP 的負載均衡器。
    - **驗收標準**: MVP 在最終的生產環境上穩定運行，具備高可用性與擴展性。
