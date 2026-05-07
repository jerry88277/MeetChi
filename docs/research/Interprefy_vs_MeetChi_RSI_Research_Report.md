# 遠端同步口譯 (RSI) 平台 Interprefy 技術架構拆解與 MeetChi 整合評估報告

基於第一性原理 (First Principles)、MECE 原則與模型思維 (Model-Thinking)，本報告深度拆解 Interprefy 的技術架構，評估開源替代方案 (如 LiveKit)，並對照 MeetChi 現有架構進行差異與 SWOT 分析，為後續 MVP 開發提供戰略指引。

---

## 1. 第一性原理分析：Interprefy 核心架構拆解 (Reverse Engineering)

同步口譯的「第一性原理」是：**在最極端的網路條件下，確保口譯員與聽眾的聽覺延遲低於人耳可察覺的閥值 (<200ms)，並保持多語種通道的絕對隔離與動態切換。**

### 1.1 協議選擇與超低延遲實現
* **協議核心：WebRTC SFU (Selective Forwarding Unit)**
  Interprefy **不使用**傳統的 MCU (會增加混音運算延遲) 或單純的 P2P (無法擴展)，而是採用 WebRTC SFU 架構。SFU 只負責「路由」封包而不轉碼，將發言者的單一串流發佈至伺服器後，再分發給所有訂閱者，將延遲壓縮至 Sub-500ms 甚至更低。
* **Jitter (抖動) 與同步**
  WebRTC 原生具備 RTP Timestamp 與自適應的 Jitter Buffer 管理。透過動態頻寬估計 (Target Bitrate Allocation, GCC) 機制應對跨國網路波動。對於 RSI 而言，發言者畫面與口譯音軌的同步，是透過客戶端接收到的 RTP 時間戳記 (NTP 基準) 在瀏覽器端重新對齊播放。

### 1.2 翻譯中繼 (Relay) 邏輯
* **樞紐語言機制 (Pivot Interpreting)**
  當某位口譯員聽不懂原音講者語言時，系統提供軟體控制台。一位口譯員將原音轉為「樞紐語言」(例如：日文 -> 英文)，第二位口譯員訂閱此「英文頻道」作為來源，再翻譯成目標語言 (例如：英文 -> 德文)。
* **音軌隔離與混合**
  這並非物理線路混合，而是基於發佈/訂閱 (Pub/Sub) 模式。每個口譯員實質上是在 WebRTC Room 中發佈自己對應 language-tag 的專屬 Track。聽眾端則透過 UI 切換，向 SFU 請求訂閱對應的 Track。

### 1.3 外部平台整合 (Zoom / Teams / Webex)
* **非 Virtual Audio Cable (虛擬音源線) 機制**
  Interprefy **並非**使用虛擬音效卡，這在雲端擴展性上行不通。
* **Smart Participant (Interprefy Agent)**
  他們開發了基於 SIP 或 WebRTC 的無頭機器人 (Headless Bot)。只需將 Agent Email 加入會議邀請，Bot 就會作為參與者自動加入 Zoom/Teams 會議，抓取「原音 (Floor)」並推流至 Interprefy 的雲端 SFU。這類似錄影機器人邏輯，大幅降低物理整合難度。如果需要將聲音注回 (Inject)，則是 Bot 取回對應的翻譯語音，推流至 Zoom 原生的語言頻道 API 中。

---

## 2. MECE 架構：開源技術選項與評估

要自建虛擬口譯間，必須將系統拆解為「傳輸層」、「處理層」與「轉錄翻譯層」，三者彼此獨立。

### 2.1 媒體伺服器 (RSI 的命脈)
* **LiveKit (首選推薦)**：目前社群最推崇的 WebRTC SFU 框架，由 Go 語言編寫，提供開箱即用的跨平台 SDK (React, iOS, Android)，以及完善的 Room/Track 路由管理，極度適合構建「多語種頻道選擇」邏輯。
* **Mediasoup**：效能最極致的底層 C++/Node.js 函式庫。擁有封包等級的控制權，但沒有內建 Room API，開發成本極高。
* **Janus**：老牌模組化伺服器，對 SIP 整合支持強大，但架構較舊。

### 2.2 音訊處理與客戶端混音
* 開發「虛擬口譯間」時，網頁端需運用 **Web Audio API** 進行多軌分離。例如，讓口譯員左耳聽原音，右耳聽其他同儕的 Relay 音訊。
* 伺服器端存檔使用 **FFmpeg** 進行即時串流側錄 (Side-car recording)。

---

## 3. MeetChi vs RSI：關鍵維度差異分析

MeetChi 當前的優勢在於**音轉文 (ASR/LLM)** 與 **非同步重點摘要**，這與即時 Speech-to-Speech (STS) 有本質上的區別。

| 維度 | MeetChi (會議記錄應用) | RSI / AI 同步口譯 |
| :--- | :--- | :--- |
| **延遲容忍度** | 3-5 秒。可以等待一個完整的語意切分 (VAD Silero) 來獲得翻譯高準確率。 | **極致苛求 (<200ms-1s)**。超過 1 秒聽眾會感到畫面與聲音嚴重錯亂。 |
| **底層傳輸架構** | **WebSocket 傳輸 PCM 塊**。搭配 Cloud Tasks 與 GPU 異步處理。 | **WebRTC SFU 全雙工**。必須維持穩定的 UDP 串流傳輸。 |
| **運算負載邏輯** | 音轉文 (WhisperX)。後端為 Text Dispatcher，無高頻寬轉發壓力。 | 音轉音 (需結合 Streaming ASR + LLM + Fast TTS)，伺服器有大量封包轉發壓力。 |
| **架構複雜度** | 一次性處理與校正 (Smith-Waterman 對齊)。 | 高度併發處理：需應付多語種平行輸出與多軌道訂閱。 |

---

## 4. SWOT 分析：Interprefy vs MeetChi

### 目標：探討將 Interprefy 特性融入 MeetChi 的價值

* **優勢 (Strengths - MeetChi)**
  * 開發靈活，完全掌控資料主權 (Data Sovereignty)，無 SaaS 外部隱私風險。
  * 已具備堅實的 Google OAuth 與 GPU 異步摘要框架 (Cloud Run/Cloud Tasks)。
  * 高精準度雙模型 ASR (WhisperX + Breeze-ASR-25) 處理在地化台語與中英混雜極佳。
* **劣勢 (Weaknesses - MeetChi)**
  * 現行基於 WebSocket PCM chunking 的架構，本質上無法達成真正的連續超低延遲串流。
  * 尚無即時雙向語音路由的基礎設施 (缺 SFU)。
* **機會 (Opportunities - 整合特性)**
  * **引進 LiveKit**：可作為 MeetChi 的「Real-Time 模組」，保留現有的非同步摘要，另闢一條即時翻譯與字幕的快速通道。
  * **Interprefy Agent 模式**：開發一隻輕量 Bot 加入 Zoom/Teams 以獲取音軌，取代現在必須從本機 Tauri 攔截音訊的方案，徹底擴大商業應用場景。
* **威脅 (Threats)**
  * 若要實現高質量 AI Speech-to-Speech，目前的 LLM 生成極度容易產生延遲抖動。
  * OpenAI Realtime API 和 Gemini Live API 開放後，若是採用直接呼叫，流量與 API 成本將成倍暴增。

---

## 5. 自開發可行性評估 (RSI MVP 發展藍圖)

如果決定開發基於 AI 的即時語音翻譯與字幕 (RSI 雛形)，其優先級與決策路徑如下：

1. **核心順序：音訊穩定性 (WebRTC) > 平台整合 (Agent) > 翻譯準確度 (LLM)**
   * RSI 首重**持續性**與**不中斷**。文字翻譯錯了可以修正，但延遲飆高或語音斷斷續續將完全毀滅體驗。
2. **Phase 1: 基礎 SFU 與字幕建置 (LiveKit MVP)**
   * 部署開源 **LiveKit Server**。
   * 前端引入 LiveKit SDK。利用 LiveKit 提供的 `DataChannel` 同步廣播即時語音識別 (Streaming API / Whisper) 的文字字幕。
3. **Phase 2: 會議平台 Agent 整合**
   * 研究並開源部署一隻無頭 Puppeteer 或 WebRTC Bot，自動加入 Google Meet/Teams 並將音訊推至 LiveKit SFU (此即 Interprefy 的不傳之秘)。
4. **Phase 3: AI 重建語音 (Text-to-Speech)**
   * 當 ASR 完成了一小段翻譯，立即呼叫低延遲 TTS (如 ElevenLabs 或內建輕量模型)，推流至翻譯專屬 Track 中，完成真正的 AI 同步口譯。

## 結論

Interprefy 這類軟體的護城河不在於 AI 演算法，而是在於其在全球佈建了一套極低延遲的 **WebRTC 音訊轉發網路**，以及能靈活接入各大會議軟體的 **Agent 系統**。對於 MeetChi 而言，將「會議記錄 (非同步分析)」擴展至「即時雙向字幕與翻譯 (即時互動)」，是完全合理的戰略演進方向；而第一步的破局點，就是**使用 LiveKit (首選) 替換或補強目前的 WebSocket 架構**。
