# Google AI Edge Eloquent 技術底層剖析與 MeetChi 混合架構 (Edge-to-Cloud) 研究報告

## 1. Google AI Edge Eloquent 真實技術原理 (第一性原理拆解)
經過網路與 GitHub 開源庫調查，我們必須先釐清一個關鍵：**Eloquent 本身並非一個開源框架**，它是 Google 發佈的一支 iOS 閉源展示型 App，用來火力展示 **"Google AI Edge"** 解決方案。

其底層第一性原理在於：**不依賴雲端伺服器 (Zero Cloud Ping)，直接在終端設備的硬體 (NPU/GPU) 上完成「收音 $\rightarrow$ 語音識別 (ASR) $\rightarrow$ 語意潤飾 (Gemma SLM)」的嚴密閉環。**
核心技術堆棧 (開源層) 包含：
*   **LiteRT (原 TensorFlow Lite)**：負責將百億參數的 Gemma 語言模型進行極端量化 (Quantization)，使其能在行動裝置上限縮記憶體佔用。
*   **MediaPipe**：負責 Audio Stream 的無縫擷取與硬體加速流水線 (Pipeline) 構建。

---

## 2. MECE 分析：哪些模組概念可以整合至 MeetChi？
若將 Eloquent 所揭示的 Edge AI 概念套用至 MeetChi，我們可將系統切分為「邊緣 (Edge)」與「雲端 (Cloud)」模組，並且「借鏡」其概念：

1.  **[Edge 端] WebAssembly / WebGPU 的零延遲靜音偵測 (VAD)**
    *   **現狀**：MeetChi (Tauri) 可能會向 GCP 傳送大量含有無效靜音的音檔，浪費上下行頻寬。
    *   **整合**：在使用者端導入 WebAssembly 編譯的 VAD 引擎。在聲音尚未離開實體設備前，就精準濾除背景噪音，只有偵測到有效人聲才打包成 Chunk 傳輸上 GCP。
2.  **[Edge 端] 個人化語彙熱掛載 (Personal Context Dictionary)**
    *   **整合**：Eloquent 允許在本地建置「私有詞典」。MeetChi 可將企業或專案的專有縮寫存於使用者電腦的 LocalStorage，當語音準備傳送（或本地推論）時，動態將該詞典作為 Prompt 掛載，而無需修改龐大的原始模型。
3.  **[Cloud/Edge 端] 語義潤飾大腦 (Speech-to-Prose)**
    *   **整合**：模仿 Eloquent 透過端側小語言模型 (SLM) 剔除贅字的作法。MeetChi 在產生最終總結或字幕前，加一層輕量的文字清理程序，讓「逐字稿」進化為「會議散文」。

---

## 3. 模型思維 (Model-Thinking)：端雲混合架構解決 VDI 與 Teams 的挑戰

**核心提問：在 VDI / Teams 環境下，能否先載入離線模型，利用使用者硬體做到「中英夾雜」的轉錄，再傳至 GCP？**

**思維模型：Distributed Architectures & Fat Client 模型 (邊緣終端/雲端協作)。**

這在技術上 **完全可行，且是解決 VDI (桌面虛擬化) 與遠距音訊失真痛點的「終極解法」**。

### A. 第一性原理：為什麼在 VDI (如 Citrix/VMware) 環境需要這麼做？
在 VDI 架構下，使用者的「物理硬體」與「虛擬桌面環境 (Teams)」是切割的。如果我們在虛擬桌面上截取音訊傳給 GCP，音訊勢必已經被 VDI 協定 (如 HDX Audio) 給嚴重壓縮、加上破音與延遲。
*   **根本解法**：讓轉錄軟體 (MeetChi Client) 直接運行在使用者「實體的物理機 (瘦客戶端或筆電)」上。直接攔截乾淨無損的麥克風收音，**利用本地硬體資源轉錄為文字 (JSON) 後，將「極低頻寬」的文字資料送進 VDI 或繞道直上 GCP**。這徹底解決了 VDI 癱瘓頻寬的問題。

### B. 技術路線：在本地硬體實踐「中英夾雜」轉錄
1.  **WebGPU 與 Whisper.cpp 整合**：利用最新的 WebGPU 標準，將經過 4-bit 量化的輕量 Whisper 模型 (如 `whisper-base` 或 `Moonshine` 模型，僅約 100MB-300MB) 於瀏覽器網頁端或 Tauri 殼層載入。
2.  **記憶體快取 (Model Delivery)**：用戶初次連線頁面時，將這 300MB 的權重快取在 IndexedDB。之後會議時，完全不需重新下載，直接調用本地顯示卡硬體加速進行純離線推論。
3.  **雲端融合 (Sync to GCP)**：本地端這時扮演「智慧收音筒」，只輸出帶有時間戳 (Timestamp) 的逐字稿 Text，再透過 WebSocket 傳給 GCP Cloud Run 進行重算力需求的大型 LLM 處理 (洞察分析、會議決議萃取)。

---

## 4. SWOT 架構分析：MeetChi 轉向 Edge-Cloud Hybrid (端雲協同)

| 維度 | 詳細說明 |
| :--- | :--- |
| **優勢 (Strengths)** | 1. **破壞性的雲端降本 (10x Saving)**：原先依賴 GCP Cloud Run GPU 的高昂即時推論算力，轉嫁給使用者的高階筆電硬體 (M 系列晶片/RTX 顯卡)。<br>2. **VDI 與極致隱私完美適配**：繞開 VDI 的音訊壓縮，且「原音檔」絕不離開實體設備，徹底打趴法規嚴格的金融業資安顧慮。 |
| **劣勢 (Weaknesses)** | 1. **「中英夾雜」的準確度妥協**：手機或筆電無法跑高達幾十億參數的本地語言特化模型 (如 Whisper Large V3)。對於深度中英夾雜 (Code-Switching) 與台語，Edge 輕量模型的錯誤率會從 5% 暴增至 15% 以上。<br>2. **初始啟動摩擦力**：前端網頁首次需載入百 MB 級的 Wasm 與權重檔，影響「秒入會議」的使用者體驗 (UX)。 |
| **機會 (Opportunities)** | 1. **WebNN 與 WebGPU 標準化**：近期 Chrome 全面支援在地硬體加速 API，這表示開發「瀏覽器內建高效 ASR」的門檻正在急速斷崖式下降。<br>2. **成為企業內網的首選**：真正 Air-Gapped 的錄音層將使 MeetChi 在競爭激烈的 SaaS ASR 脫穎而出。 |
| **威脅 (Threats)** | 1. **用戶實體硬體碎片化 (Fragmentation)**：企業若發放 10 年前的無獨顯文書筆電，該架構將導致瀏覽器爆記憶體 (OOM) 崩潰，讓服務完全停擺。<br>2. **系統音訊攔截困難**：Windows/Mac 的權限管理日益嚴格，跨軟體 (Teams) 攔截本機端放線出來的揚聲器音訊將遭到防毒阻擾。 |

---

## 5. 未考量到的隱藏盲區 (Blind Spots & Risks)

透過「系統性思考 (Systems Thinking)」，除了上述討論的運算分配外，還存在三個我們可能遺漏的致命地雷：

1. **講者辨識 (Speaker Diarization) 在 Edge 端的災難**
   *   您或許能在本地輕鬆識別「自己」說的話。但如果透過系統混音收錄了 Teams 裡面「包含其他 5 個人的聲音」，要直接在 Edge 端做講者聲紋分割是極度消耗 CPU/RAM 的行為。如果把 Diarization 放在本地，普通筆電絕對會當機。這意味著「辨識誰在說話」的工作可能還是得依賴雲端。
2. **模型智財遭逆向工程 (Model Extraction/Theft)**
   *   如果未來 MeetChi 辛辛苦苦微調出了一個「超精準的台灣中英夾雜特化模型」，只要該模型被轉成 ONNX 或 WASM 送至使用者的瀏覽器端執行，競品對手就可以直接從 Network 面板把它存檔帶走，失去技術護城河。
3. **設備散熱降頻陷阱 (Thermal Throttling)**
   *   一場會議動輒 1 到 2 小時。若讓輕薄筆電透過 WebGPU 全速執行連續一小時的 Whisper 推論，筆電溫度會飆升，處理器為自我保護會強制降頻 (Throttling)。最終會導致轉錄的延遲越來越長，直到 CPU 鎖死而延遲超過十幾秒鐘。

## 行動方案結論 (Actionable Insight)

將 MeetChi 的 ASR 算力透過 WebGPU 或 Tauri 移轉至使用者設備來適應 VDI，是一個**極度性感且成本效率極高**的路線，但也是一把雙面刃。
為了避免硬體災難，建議導入 **雙引擎動態降配機制 (Dynamic Fallback Architecture)**：
當 App 開啟時，先偵測物理機是否有合格的獨立顯示卡或 Apple Silicon，**若有則啟動 Edge ASR 攔截音源；若設備跑得太喘導致轉錄積壓，或根本無法負荷，則無縫切換，將工作退回原始的「發送 PCM Chunk 給 GCP Cloud Run GPU 處理」的雲端模式**。藉此既能發揮分散式計算優勢，又保證任務絕對不中斷。
