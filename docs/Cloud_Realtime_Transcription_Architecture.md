# 雲端即時會議轉錄與翻譯系統架構部署白皮書：基於 GCP Cloud Run GPU 與資料不落地策略

## 1. 執行摘要與戰略總覽

本研究報告旨在為企業級「即時會議轉錄與翻譯系統」提供一份詳盡的 Google Cloud Platform (GCP) 部署架構藍圖。本計畫的核心目標在於滿足高規格的會議記錄需求，同時嚴格遵守「資料不落地」（Data Residency）的資安政策，確保所有敏感的會議語音與文字資料僅在台灣（asia-east1）境內進行處理與儲存，絕不跨境傳輸。

針對使用者提出的需求，本報告提出了一套整合「桌面端即時字幕」與「網頁版會議記錄回顧」的雙軌制解決方案。在運算核心方面，我們建議採用 GCP Cloud Run 搭配 NVIDIA L4 GPU 的無伺服器架構。此方案不僅滿足了「最小化維運資源」（NoOps）的營運目標，更透過最新的 Sidecar 容器模式，解決了傳統微服務架構在即時語音處理鏈中常見的延遲問題。

針對模型部署，本報告深入分析了如何將 Hugging Face 開源模型——特別是聯發科創新基地（MediaTek Research）開發的 Breeze ASR 25 與 Breeze 2 LLM——高效地部署於雲端環境。透過動態提示工程（Dynamic Prompt Engineering），系統可靈活應對主講者在中英夾雜（Code-switching）情境下的「原文」顯示，以及針對目標受眾的「譯文」輸出，並支援即時的語言方向互換（如：主講者切換為英文，譯文即時切換為中文）。

在前端技術選型上，針對桌面版字幕應用，本報告強烈建議採用 Tauri 框架取代傳統的 Electron。Tauri 基於 Rust 的後端架構不僅大幅降低了記憶體佔用，更提供了底層作業系統視窗管理的強大能力，能夠實現穩定且高效的「滑鼠穿透」（Click-through）透明視窗功能，確保使用者在觀看字幕的同時，不影響對其他應用程式的操作。

針對資料合規性，本架構引入了 GCP 的 VPC Service Controls，在 asia-east1 區域周圍建立虛擬安全邊界，從網路層級技術性地阻斷任何資料外流的可能性。此外，針對雲端服務常見的「冷啟動」（Cold Start）問題，我們提出結合「最小執行個體」（Min Instances）與「承諾使用折扣」（Committed Use Discounts, CUDs）的成本優化策略，在確保服務隨時待命的同時，有效控制長期營运成本。

### 系統架構高層次資料流敘述

為了讓讀者對整體系統有一個清晰的宏觀認識，以下將透過文字詳細描述端到端的資料流向與安全邊界設計，此架構設計直接回應了資料不落地的核心訴求：

*   **用戶端層（Data Plane - Client）**：
    *   **Desktop Client (Tauri)**: 桌面應用程式負責採集音訊。為了降低傳輸延遲與頻寬消耗，用戶端內建了輕量級的語音活動偵測（VAD）模組，僅在偵測到有效語音時才建立連線。
    *   **Protocol**: 採用 gRPC 雙向串流（Bidirectional Streaming）協定，透過 HTTP/2 進行傳輸，確保低延遲與高並發能力。

*   **邊緣接入層（Ingress Layer）**：
    *   **Cloud Load Balancing**: 全球外部應用負載平衡器接收來自用戶端的 gRPC 請求，並負責 SSL/TLS 卸載。此層級配置了嚴格的 Cloud Armor 安全政策，僅允許授權的 IP 來源存取。

*   **核心運算層（Compute Layer - The "Sidecar" Monolith）**：
    *   **Cloud Run Service (asia-east1)**: 這是系統的心臟。單一 Cloud Run 執行個體內部署了兩個容器（Sidecar 模式）：
        *   **Controller Container**: 負責處理 gRPC 連線、音訊緩衝與業務邏輯。
        *   **Inference Container**: 搭載 NVIDIA L4 GPU，運行 Breeze ASR 與 Breeze LLM 模型。
        *   **Localhost Communication**: 兩個容器透過本地迴路（localhost）進行微秒級通訊，消除了傳統微服務間的網路延遲。

*   **資料持久層（Storage Layer）**：
    *   **Cloud SQL (PostgreSQL)**: 儲存會議元數據（Metadata）、使用者資訊與權限設定。
    *   **Cloud Storage (GCS)**: 儲存會議錄音檔與完整的 JSON 轉錄檔。
    *   **Data Residency Enforcement**: 所有儲存資源均強制設定為 Region: asia-east1。

*   **安全邊界（Security Boundary）**：
    *   **VPC Service Perimeter**: 一個虛擬的防火牆邊界將上述所有 GCP 資源包裹其中。任何未經授權的 API 呼叫（即使擁有正確的 IAM 憑證）若來自邊界外部，均會被 VPC Service Controls 直接阻斷，從根本上杜絕資料外洩風險。

## 2. 基礎設施規劃與區域選擇策略

在規劃 GCP 部署資源時，首要考量是滿足「資料不落地」的政策紅線以及「降低延遲感」的使用者體驗需求。這兩者在物理層面上是指向同一解決方案的：選擇地理位置最接近使用者的 GCP 機房。

### 2.1. 區域選擇：深耕 asia-east1 (台灣彰化)

GCP 在全球擁有多個區域（Regions），但針對本專案，asia-east1 (台灣彰化) 是唯一合規且合理的選擇。

*   **資料主權與合規性**： 使用者明確指出需要符合「資料不落地」政策。這意味著資料的處理（運算）與靜態儲存（Storage）都必須限制在台灣境內的伺服器上。選擇 asia-east1 可以確保所有暫存記憶體內容與持久化硬碟資料都不會離開台灣司法管轄區 [1]。
*   **物理延遲最小化**： 對於即時字幕應用，網路傳輸延遲（Network Latency）是構成總延遲的重要部分。光速在光纖中的傳播速度是有限的，若將服務部署在 asia-northeast1 (東京) 或 us-central1 (愛荷華)，將分別增加約 30-40ms 與 140-160ms 的來回傳輸時間 (RTT)。部署於彰化機房，台灣本地用戶的 RTT 可控制在 10ms 以內，這對於營造「同步感」至關重要。
*   **硬體資源可獲得性**： 並非所有 GCP 區域都提供各類型的 GPU。根據最新的 GCP 資源矩陣，asia-east1 區域已支援 NVIDIA L4 GPU [1]。這一點至關重要，因為 L4 是目前針對 AI 推論（Inference）性價比最高的選擇，若該區域僅有舊款 T4 或昂貴的 A100，將迫使我們在效能與成本間做出艱難妥協。

### 2.2. 運算載體評估：Cloud Run vs. GKE vs. GCE

在決定了「在哪裡跑」之後，下一個問題是「用什麼跑」。使用者的需求中提到「最小化維運資源」，這強烈指向 Serverless（無伺服器）或 Managed Service（託管服務）的解決方案。

| 特性比較                  | Cloud Run (Gen 2)                       | Google Kubernetes Engine (GKE)              | Compute Engine (GCE)                           |
| :------------------------ | :-------------------------------------- | :------------------------------------------ | :--------------------------------------------- |
| GPU 支援                  | 支援 NVIDIA L4 [4]                      | 完整支援所有 GPU 類型                     | 完整支援所有 GPU 類型                        |
| 維運負擔                  | 極低 (NoOps)                            | 中高 (需管理節點池、升級)                   | 高 (需管理 OS、驅動、資安補丁)                 |
| 冷啟動處理                | 透過 min-instances 解決                 | 需維持常駐節點                              | 需維持常駐 VM                                  |
| 網路延遲                  | 支援 gRPC 串流 [5]                      | 極低 (Cluster IP)                           | 極低 (Internal IP)                             |
| 擴展性                    | 自動 0-N 擴展                           | 自動節點擴展 (較慢)                         | 透過 MIG 擴展 (最慢)                           |
| 計費模式                  | 按秒計費 (閒置可不計費)                   | 按節點運作時間計費                          | 按 VM 運作時間計費                           |

**決策分析**：雖然 GKE 提供了最強大的控制力，適合複雜的微服務編排，但對於本專案相對單純的「音訊輸入 -> 文字輸出」管線而言，維護一個 K8s Cluster 的人力成本過高。Compute Engine (VM) 則需要手動處理驅動程式更新與 OS 層級的資安，違背了最小化維運的初衷。

**Cloud Run (Gen 2)** 是最佳選擇。它結合了容器化的靈活性與 Serverless 的免維運特性，且近期推出的 Sidecar 支援與 GPU 支援，使其成為部署輕量級 AI 推論服務的理想平台。特別是 Cloud Run 支援 HTTP/2 與 gRPC 的雙向串流，完美契合即時語音傳輸的需求 [5]。

### 2.3. GPU 硬體選型：NVIDIA L4 的必要性

在 Cloud Run 上，我們主要面臨 NVIDIA T4 與 L4 的選擇。雖然 T4 成本較低，但本專案包含「LLM 重寫與翻譯」的需求，而不僅僅是 ASR。

*   **ASR 需求**： Whisper 模型對 GPU 算力要求相對溫和，T4 尚可應付。
*   **LLM 需求**： Breeze 2 (3B 參數) 雖然是輕量級模型，但在進行即時翻譯與重寫時，需要極高的 Token 生成速度（Tokens per Second, TPS）以跟上人類的語速（約每秒 3-4 字）。
*   **效能數據**： 根據基準測試，L4 基於 Ada Lovelace 架構，其 FP16 推論效能是 T4 的 2-4 倍，且記憶體頻寬更高（300 GB/s vs ~300 GB/s，但 L4 的快取架構更優）[6]。更重要的是，L4 支援 BF16 格式，這對於現代 LLM（如 Llama 3 架構的 Breeze 2）的精度保持更為有利。

**結論**： 為了避免翻譯跟不上語音的「堆積延遲」（Backlog Latency），強烈建議採用 NVIDIA L4 GPU。

## 3. 系統架構設計：微服務 vs. 模組化單體

使用者詢問：「微服務的架構是否可行？」答案是：可行，但對於極致低延遲的即時語音場景，傳統的微服務（Microservices）是效能殺手。

### 3.1. 傳統微服務的延遲陷阱

若採用標準微服務架構，資料流將如下所示：
音訊串流進入 ASR Service（容器 A）。
ASR Service 將轉錄文字序列化（JSON/Protobuf），透過內部網路發送給 Translation Service（容器 B）。
Translation Service 處理後，再透過網路傳回前端或聚合層。

在 asia-east1 區域內，雖然內部 VPC 延遲極低（<1ms），但這裡的成本不僅是網路傳輸時間（RTT），還包括：

*   **序列化/反序列化開銷 (Serialization Overhead)**: 頻繁的資料打包與解包。
*   **排隊延遲 (Queuing Delay)**: 下游服務（翻譯）的 Autoscaler 可能反應不及，導致請求在隊列中堆積。
*   **GPU 記憶體碎片化**: 若將 ASR 與 LLM 拆開，需要兩個 GPU 實例，這不僅增加了成本（兩個 L4 比一個貴），也浪費了顯存（VRAM），因為 Breeze 2 3B 與 Whisper Large V2 完全可以共存於單張 24GB VRAM 的 L4 卡上。

### 3.2. 推薦架構：基於 Sidecar 的「管線化單體」(Pipeline-in-a-Pod)

為了兼顧微服務的「職責分離」與單體架構的「低延遲」，我們建議利用 Cloud Run 的 **多容器 (Sidecar) 功能** [8]。

**架構詳解**：
在同一個 Cloud Run 執行個體（Instance）中，我們定義兩個容器：

*   **Ingress/Controller Container (Golang 或 Rust)**:
    *   **職責**： 作為對外的 gRPC 伺服器，負責維持與 Desktop Client 的長連線。
    *   **功能**： 接收音訊、進行二級緩衝（Jitter Buffer）、管理 VAD 狀態，並協調後端模型的呼叫順序。
    *   **優勢**： 使用編譯型語言處理高併發網路 I/O，效能最佳。

*   **Inference Container (Python)**:
    *   **職責**： 專注於模型推論。
    *   **環境**： 預載 PyTorch/TensorRT 環境，掛載 NVIDIA L4 GPU。
    *   **服務**： 運行 vLLM 或 Faster-Whisper Server，並透過 localhost 暴露 HTTP 或 gRPC 介面。

**通訊機制**：兩個容器共享同一個網路命名空間（Network Namespace）。Controller 呼叫 Inference 模型時，走的是 Loopback (localhost) 介面。這種通訊方式的延遲幾乎可以忽略不計（微秒級），且無需經過外部負載平衡器，確保了資料在記憶體中的快速流動。

## 4. Hugging Face 開源模型部署與優化策略

本專案選用聯發科創新基地（MediaTek Research, MR）的開源模型，這對於處理台灣在地的語言習慣（Taiwanese Mandarin）以及中英夾雜（Code-switching）場景具有顯著優勢。

### 4.1. 部署 Breeze ASR 25 (語音轉文字)

**Breeze ASR 25** 是基於 whisper-large-v2 進行微調的模型，特別強化了繁體中文與中英混用的辨識能力 [9]。

*   **部署挑戰**： Whisper 原生設計是針對 30 秒的音訊塊（Chunk）進行批次處理，這與「即時串流」的需求相悖。
*   **解決方案**：
    *   **串流切分策略 (Streaming Segmentation)**
        *   我們不能依賴固定時間（如每 5 秒）切分，這會切斷單字。必須結合 VAD (Voice Activity Detection)。
        *   **流程**： 系統持續緩衝音訊，當 VAD 偵測到短暫停頓（如 300ms 的靜音）時，視為一個「語句邊界」，立即將緩衝區內的音訊送入 ASR 模型。若使用者長篇大論不停頓，則設定強制切分閾值（如 5 秒），並利用重疊視窗（Overlapping Window）技術來修正邊界切斷的單字。
    *   **推論引擎優化**：
        *   不要直接使用 Hugging Face 的 transformers pipeline，其效能較低。
        *   建議使用 Faster-Whisper (基於 CTranslate2)。它支援 INT8 量化，能在幾乎不損耗精度的情況下，將記憶體佔用從 10GB 降至約 3-4GB，並提昇 4 倍以上的推論速度 [11]。
    *   **部署實作**： 在 Dockerfile 建置階段，預先下載 Breeze-ASR-25 模型權重並轉換為 CTranslate2 格式，封裝進容器映像檔 (/app/models)。這能徹底避免執行時從 Hugging Face Hub 下載模型導致的冷啟動延遲與潛在的網路不穩定。

### 4.2. 部署 Breeze 2 LLM (重寫與翻譯)

**Breeze 2** 是基於 Llama 3 架構的輕量級模型，擁有優秀的繁體中文理解力 [12]。

*   **任務定義**： LLM 在此扮演「潤飾者」與「翻譯者」。
    *   **Input**: 來自 ASR 的原始逐字稿（可能包含贅字、語氣詞、中英夾雜）。
    *   **Output**: 語意通順的目標語言文字。
*   **中英互換邏輯設計 (Source/Target Swapping Logic)**：
    *   使用者要求「主講者使用語言與翻譯目標語言可直接對調」。這意味著 LLM 的行為必須是動態可控的。
    *   我們不需要部署兩個不同的模型，而是利用 System Prompt (系統提示詞) 的動態注入。
    *   **場景 A（預設）**：主講者中英夾雜 -> 譯文為英文
        *   System Prompt: "You are a professional simultaneous interpreter. Your task is to translate the user's spoken text into concise, professional English. The source audio may contain mixed Mandarin and English; handle code-switching naturally."
    *   **場景 B（對調）**：主講者全英文 -> 譯文為中文
        *   System Prompt: "You are a professional simultaneous interpreter. Your task is to translate the user's spoken text into fluent Traditional Chinese (Taiwan). The source text is in English."
    *   **實作方式**： Desktop Client 在發送 gRPC 請求的 Metadata Header 中帶上 `x-translate-mode: zh-to-en` 或 `x-translate-mode: en-to-zh`。Controller 容器根據此 Header，在呼叫 LLM 時動態插入對應的 System Prompt。
*   **量化與顯存管理**：
    *   為了讓 Breeze 2 (3B) 能與 ASR 共存於單張 L4 GPU (24GB VRAM)，我們必須進行量化。建議使用 AWQ (Activation-aware Weight Quantization) 4-bit 量化。這能將 3B 模型的顯存需求壓低至約 2.5GB [14]。
*   **vLLM 引擎**：
    *   使用 vLLM 作為推論伺服器。vLLM 專為 Llama 架構優化，支援 PagedAttention，能極大化並發處理能力（Throughput）。
*   **顯存算術**：
    *   Whisper (CTranslate2 INT8): ~4 GB
    *   Breeze 2 (vLLM AWQ 4-bit): ~3 GB
    *   KV Cache (vLLM 預留): ~10 GB
    *   PyTorch Overhead: ~2 GB
    *   **總計**：~19 GB < 24 GB (L4 容量)。此配置是安全且高效的。

## 5. 桌面端前端工程：Tauri 實踐低延遲與透明視窗

針對「桌面版前端僅有逐字稿字幕需求」且需要「降低延遲感」與「透明背景」，Tauri 是超越 Electron 的最佳選擇。

### 5.1. 為何選擇 Tauri？

*   **資源佔用**： Tauri 使用作業系統原生的 WebView (Windows 上是 WebView2, macOS 上是 WebKit)，編譯後的執行檔極小（<10MB），且記憶體佔用極低（~30MB vs Electron 的 ~200MB+）[16]。這對於一個需要「常駐」且不應干擾主會議軟體（如 Teams/Zoom）的輔助工具來說至關重要。
*   **安全性**： Tauri 的後端採用 Rust，提供了記憶體安全保障，且預設封鎖了許多危險的 API，符合企業資安要求。

### 5.2. 實現「滑鼠穿透」(Click-through) 與透明視窗

使用者需要在看字幕的同時操作下方的視窗（如 PPT 翻頁）。這需要視窗具備「忽略滑鼠事件」的能力。

*   **技術實作**：在 Tauri v2 中，我們可以透過 Rust 後端直接調用作業系統 API 來修改視窗屬性。
    *   **Windows**: 修改 `GWL_EXSTYLE` 加入 `WS_EX_TRANSPARENT` 與 `WS_EX_LAYERED` 屬性 [18]。
    *   **macOS**: 設定 `ignoresMouseEvents` 為 true。
*   **互動設計**： 我們不能讓視窗永遠穿透，否則使用者無法移動字幕或更改設定。解決方案： 設計一個「控制列」（Control Bar）。當滑鼠游標懸停在控制列區域時，Tauri 前端發送事件給 Rust 後端，暫時關閉穿透屬性 (`set_ignore_cursor_events(false)`)；當滑鼠離開控制列進入純字幕區域時，重新開啟穿透 (`set_ignore_cursor_events(true)`) [19]。

### 5.3. 用戶端延遲優化策略

為了極致降低延遲，我們不能依賴雲端來做所有的判斷。

*   **Client-side VAD (端側語音活動偵測)**:
    *   不要將「靜音」也串流到雲端。這不僅浪費頻寬，也會增加 Cloud Run 的處理成本。
    *   在 Tauri 的 Rust 後端整合 Silero VAD (透過 `ort` crate 執行 ONNX 模型) [20]。
    *   **機制**： 只有當 VAD 判定為「有人說話」時，才開啟 gRPC Stream 發送音訊。這能大幅過濾背景噪音並減少無效請求。
*   **gRPC 實作**：
    *   不要在 WebView 的 JavaScript 層跑 gRPC (gRPC-Web 效能較差且有 CORS 問題)。
    *   利用 Tauri 的 Rust 主進程使用 `tonic` crate 建立原生的 gRPC HTTP/2 連線 [22]。
    *   音訊從麥克風擷取後，直接在 Rust 層緩衝並發送，完全繞過瀏覽器的單執行緒限制。

## 6. 網頁版會議記錄與資料持久化架構

針對「未來會議記錄之使用情境」的網頁版，我們採用分離式架構。

### 6.1. 資料庫與儲存設計

*   **Cloud SQL for PostgreSQL (asia-east1)**: 用於儲存結構化資料，如會議 ID、參與者清單、時間戳記、以及逐句的轉錄文字索引。
*   **Cloud Storage (asia-east1)**: 用於儲存非結構化資料，即原始錄音檔（若政策允許）與完整的 JSON 格式轉錄檔。
*   **生命週期管理 (Lifecycle Policy)**: 設定 Bucket 的生命週期規則，例如「30 天後自動轉入 Coldline 儲存」，以節省成本。

### 6.2. 網頁端架構

*   **前端託管**： 由於資料不落地的限制，我們不能使用全球 CDN (如 Cloudflare 或預設的 Firebase Hosting CDN) 進行快取，因為這可能導致資料暫存在台灣以外的節點。
    *   **解決方案**： 使用 Cloud Run 部署一個輕量級的 Web Server (Nginx 或 Node.js)，負責提供靜態檔案與 API。並在 Cloud Load Balancing 上設定 Cloud CDN，但透過設定限制快取區域，或者完全關閉 CDN，僅作為反向代理使用。
*   **安全性**： 網頁版僅能在企業內網或透過 IAP (Identity-Aware Proxy) 存取，確保只有授權員工能查看會議記錄。

## 7. 網路與資安層：落實資料不落地

這是本計畫最核心的合規性防線。

### 7.1. VPC Service Controls (VPC-SC)

單純選擇 asia-east1 區域是不夠的，必須防止人為錯誤導致資料被複製到外部 Bucket。

*   **實作**： 在 GCP Organization 層級建立一個 Service Perimeter (服務邊界)。
*   **納管資源**： 將本專案的所有 Project、Cloud Run 服務、Cloud Storage Buckets、Cloud SQL 實例全部納入此邊界。
*   **規則**：
    *   **Egress Rule (出站規則)**: 預設拒絕所有出站流量。僅開放必要的 Google Private Access (如呼叫 Google NLP API，若有需要)。嚴格禁止對外網的資料傳輸。
    *   **Ingress Rule (入站規則)**: 僅允許來自企業 VPN Gateway 的 IP 範圍或特定的 Service Account 存取邊界內的 API [23]。
*   **效果**： 即使擁有 Owner 權限的帳號，若嘗試從非授權網路環境執行 `gsutil cp` 下載資料，也會被 VPC-SC 直接阻斷。

### 7.2. 傳輸加密

用戶端與伺服器端的 gRPC 連線強制使用 TLS 1.3 加密。雖然 GCP 預設會加密靜態資料，但為了更高的合規性，建議啟用 CMEK (Customer-Managed Encryption Keys)，由企業自行管理加密金鑰 (Cloud KMS)，並將金鑰同樣儲存於 asia-east1。

## 8. 營運優化：避免冷啟動與成本控制

### 8.1. 解決冷啟動 (Cold Start)

使用者特別關心「是否需要避免服務冷啟動」。對於即時字幕，答案是絕對肯定的。L4 GPU 實例啟動加上模型載入記憶體，可能需要 20-40 秒，這對於使用者體驗是毀滅性的 [4]。

*   **策略**：
    *   **Min-Instances (最小執行個體)**: 設定 Cloud Run 服務的 `--min-instances` 為 1（或根據尖峰使用量設定更高）。
        *   **效果**： 確保隨時至少有一個容器是「熱」的（模型已載入 VRAM），隨時可處理請求。
    *   **CPU Allocation**: 設定 `--no-cpu-throttling` (CPU 總是分配)。這確保在音訊傳輸的間隙（使用者思考時），容器不會被凍結，維持 VAD 與連線的活性。

### 8.2. 成本優化：承諾使用折扣 (CUDs)

維持 `min-instances=1` 意味著這台 GPU 機器是 24 小時運作的，成本不菲。

*   **Cloud Run 成本結構**： CPU/Memory 費用 + GPU 掛載費用。
*   **優化方案**：
    *   **承諾使用折扣 (CUDs)** [26]。購買 1 年或 3 年的 Resource-based CUD，指定在 asia-east1 區域。這可以為 CPU/Memory 帶來約 40% 的折扣，為 GPU 資源帶來顯著的費率優惠（具體折扣需視當下 GCP 對 L4 的 CUD 政策而定，通常 GPU 的 CUD 折扣幅度在 30-50% 之間）。
    *   **Spot Instances?** 不建議用於生產環境的即時會議。Spot 實例隨時可能被回收，會導致會議中斷，風險過高。

## 9. 結論

本部署計畫書提出了一個高度整合、安全且高效的架構方案。透過 Cloud Run Sidecar 模式，我們在保持模組化開發優勢的同時，消除了微服務的延遲弊病；透過 Tauri 與 Rust 的深度整合，我們解決了桌面端透明視窗與高效能採集的難題；最重要的是，透過嚴格的區域選擇與 VPC Service Controls，我們為企業構築了一道堅不可摧的資料防線。此方案不僅滿足了當下的即時字幕需求，也為未來的會議資產管理奠定了穩固的雲端基礎。
