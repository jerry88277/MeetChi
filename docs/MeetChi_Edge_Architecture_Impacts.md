# MeetChi 方案 C (Edge-Cloud Hybrid) 系統衝擊與情境泳道圖

## 一、方案 C 導入對現有系統的重大更動 (System Impacts)

全面實施 **方案 C (邊緣預計算)** 將會對目前 MeetChi 的前後端架構進行翻天覆地的「責任重組」。以下為具體的工程更動點：

### 1. 前端 (Frontend / Browser) 重大更動
* **核心依賴引入**：必須導入 `@huggingface/transformers.js` 或 `onnxruntime-web`，並實作 **Web Worker** 來處理推論，避免 ASR 計算阻塞 React/UI 主執行緒。
* **模型管理快取層**：新增對 `.onnx` 模型檔的下載進度條與 IndexedDB 存取邏輯。
* **Audio Context 重組**：
  * **(現有)** 拿麥克風串流直接透過 WebSocket 噴給後端。
  * **(方案 C)** 必須在瀏覽器實作前端 **VAD (語音活動偵測)**，確認有人聲才把音軌切割 (Resample 至 16kHz) 餵給本地 WebGPU 模型。
* **全新權限獲取**：支援捕捉系統音效 (`getDisplayMedia`)，以適應「側錄線上研討會」的新情境。
* **OPFS 離線儲存系統**：前端須負責將收音持續寫入硬碟沙盒，並在網路斷線時處理續傳狀態機。

### 2. 後端 (Backend / Cloud Run) 重大更動
* **WebSocket 退居二線**：後端 WebSocket 的職責從「接音檔轉錄」降級為「純接收前端傳來的草稿文字並寫入 DB」。ASR 算力負載直接歸零。
* **新增按需處理腳本 (Enhance API)**：實作 `/api/enhance-transcript`，當前端拋上完整音軌與 OPFS 憑證時，才啟動大模型 (如 Whisper Large V3) 進行高質量校對。

---

## 二、情境泳道圖 (Sequence Diagrams)

### 情境一：標準麥克風會議 (Edge WebGPU 正常運行)
當使用者的電腦硬體足以支撐 WebGPU，全程零伺服器 ASR 成本運作的情境。

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant B as Browser (UI Thread)
    participant W as Web Worker (Transformers.js)
    participant OPFS as Local OPFS Storage
    participant S as MeetChi Backend (DB/WS)

    U->>B: 點擊開始會議
    B->>W: 載入 ASR 模型 (從 IndexedDB 或網路)
    W-->>B: 模型載入完畢 (WebGPU Ready)
    B->>U: 要求麥克風權限 (getUserMedia)
    U->>B: 授權麥克風
    
    loop 每一段語音 (VAD 偵測到人聲)
        B->>OPFS: 寫入原始 Audio Chunk 備份
        B->>W: 傳送音訊陣列至 Worker 計算
        W->>W: 執行 WebGPU 推論
        W-->>B: 回傳逐字稿草稿片段
        B->>U: 顯示即時草稿字幕
        B->>S: 透過 WebSocket 上送草稿文字 (不送語音)
        S-->>S: 寫入資料庫
    end
```

### 情境二：低端設備防護 (硬體不足或當機，靜默降級至雲端)
使用者使用舊手機或是無 GPU 支援的電腦，系統發動 Progressive Enhancement 防禦機制。

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant B as Browser (UI Thread)
    participant OPFS as Local OPFS Storage
    participant S_WS as Cloud WebSocket (vLLM/CT2)

    U->>B: 點擊開始會議
    B->>B: 偵測 navigator.gpu 或 VRAM
    Note over B: 發現硬體不支援或 RAM < 4GB
    B->>B: 觸發 Fallback，放棄啟動 Web Worker
    B->>U: 要求麥克風權限
    
    loop 持續會議中
        B->>OPFS: 寫入原始 Audio Chunk 備份 (保持不變)
        B->>S_WS: 降級：透過 WebSocket 將「語音 Chunk」送上雲端
        Note right of S_WS: 雲端承接龐大算力負載
        S_WS-->>B: 回傳伺服器轉錄文字
        B->>U: 顯示即時字幕
    end
```

### 情境三：側錄線上研討會 / YouTube (擷取系統音效)
這是全新的被動使用情境，使用者主要不是說話，而是「偷錄」電腦上正在播放的直播或外語教學影片。

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant OS as OS / YouTube / Zoom Web
    participant B as MeetChi Browser
    participant W as Web Worker (Edge ASR)
    participant S as MeetChi Backend

    U->>B: 點擊「側錄系統音訊」
    B->>U: 觸發螢幕分享權限 (getDisplayMedia)
    Note over U,B: 使用者必須勾選「分享系統音訊(Share System Audio)」
    U->>B: 授權特定分頁或全螢幕音訊
    
    OS->>B: 源源不絕的系統發言 (單向音訊流)
    
    loop 直播進行中
        B->>B: AudioContext 合併聲軌 (過濾掉影像，只抓音頻)
        B->>W: 將 YouTube 音軌送給 Edge ASR 推論
        W-->>B: 產出高頻率之字幕草稿
        B->>U: 即時打出研討會逐字稿
        B->>S: 透過 WebSocket 將文字同步存檔
    end
    
    U->>B: 研討會結束，停止錄製
    B->>U: 提示「是否使用強大 AI 做會後總結？」
```

### 情境四：會後精修 (Draft-and-Enhance Pattern)
利用邊緣端產出的「有瑕疵草稿」無法滿足正式會議紀錄，使用者觸發 Phase 3 的斷點續傳與雲端大模型精修。

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant B as Browser (UI Thread)
    participant OPFS as Local OPFS Storage
    participant S as MeetChi API (Cloud Run GPU)

    U->>B: 點擊「產生正式決策紀錄 (Enhance)」
    B->>OPFS: 讀取這場 1 小時完整的 `.webm` 音檔
    B->>S: 透過 Background Sync 完整上傳 Blob 音檔
    
    Note over S: 收到檔案，非同步啟動 L4 GPU
    S->>S: 使用 WhisperX 進行 Diarization (語者分離)
    S->>S: 產出高精確度、帶講者的逐字稿
    S->>S: 呼叫 Gemini API 產生執行摘要
    
    S-->>B: 伺服器推播完成通知 (SSE 或 WebSocket)
    B->>U: 顯示完美的最終版會議紀錄
```
