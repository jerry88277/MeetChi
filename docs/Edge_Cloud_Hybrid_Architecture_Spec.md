# MeetChi Edge-Cloud 混合架構 (Pure Web) 開發設計書

## 1. 架構願景與核心目標

本計畫的最終願景為將 MeetChi 的核心語音辨識機制，從依賴 Tauri 殼層與「即時雲端串流推論 (Streaming to Cloud GPU)」的傳統作法，全面轉移為 **「Pure Web 邊緣預先計算 + 雲端非同步精修 (Draft-and-Enhance Pattern)」**。

**此架構解決了以下四大痛點：**
1. **雲端 GPU 成本暴增**：避免高併發連線長時間佔用 GCP 單卡 L4 GPU 的即時 VRAM，改為會後的批次 (Batch) 快速運算。
2. **VDI 與企業資安網段限制**：純網頁環境運行，錄音檔不透過 VDI 網卡即時傳流，避免 HDX/壓縮協定損壞音訊。
3. **沒有「錄不到」的風險**：OPFS 離線儲存機制能在網路中斷時確保留存原生音軌與草稿。
4. **硬體依賴解耦**：移除系統安裝型 App (Tauri) 的限制，瀏覽器打開即用 (PWA)。

---

## 2. 核心模組實作計畫 (Phases)

本開發計畫分為三個核心發展階段：

### Phase 1: Pure Web 錄音接管與沙盒離線暫存機制
**目標：確保使用者在無網路或受限網路連線下，也能開啟網頁並穩定錄音。**

*   **PWA 與 Service Worker 導入**
    *   全靜態資源與前端邏輯預先快取，使 Web App 支援離線秒開。
*   **Web MediaRecorder 架構**
    *   利用 `MediaRecorder API` 捕捉麥克風音訊，將串流分段儲存為 `webm` 或 `ogg` 的 Chunks。
*   **OPFS (Origin Private File System) 儲存層**
    *   **錄製中**：將擷取的 Audio Chunks 直接寫入 OPFS，即便長達 3 小時會議也不會造成瀏覽器記憶體 OOM。
    *   **備份觸發**：當會議結束，若系統偵測為離線/未核准連線狀態，自動透過 `Blob URl` 下載並將音檔強迫寫入使用者的實體「Download (下載)」資料夾。

### Phase 2: 模型轉換、加密佈署與 Web 推論引擎
**目標：賦予純 Web 端擁有執行中英夾雜 ASR 的算力。**

*   **Breeze ASR 25 量化工程 (ONNX)**
    *   將微調過的 Breeze ASR 模型導出為 `.onnx` 格式。
    *   實施 8-bit (或 4-bit) 量化，目標檔案大小壓制在 300MB ~ 500MB 以內，適配網頁傳輸極限。
*   **模型防盜加密預載 (IndexedDB + AES)**
    *   雲端先使用 AES-256 對 `.onnx` 打包加密。
    *   **預先下載層**：當用戶登入時透過 HTTP HEAD/ETag 比對版本號，未命中則下載至本地 `IndexedDB` 快照快取。
    *   推論前，向 GCP 取得金鑰，於記憶體 (`ArrayBuffer`) 中即時解密，阻絕 90% 基礎拖庫竊取。
*   **推論引擎 (onnxruntime-web)**
    *   **推論架構分級**：首先探測瀏覽器是否支援 `WebGPU`，若支援則啟用 GPU 硬體加速推論；若不支持，降配至 `WebAssembly (Wasm) + SIMD + Multi-threading` (使用 CPU 算力)。
    *   強制載入 **Initial Prompt (`"繁體中文，允許夾雜英文"`)** 限制小量化模型的中英夾雜幻覺。

### Phase 3: 端雲斷點續傳與 Enhance (雲端精修)
**目標：確保雲端能接收輕量化的結果，並提供企業級的高精確度後處理。**

*   **背景上傳 (Background Sync)**
    *   會議中不傳 Audio，會議結束或網路恢復時，Service Worker 啟動背景將 OPFS 的音軌與網頁端產出的草稿逐字稿，以 WebSocket 或 Chunk 方式非同步上傳至 GCP bucket。
*   **後端按需非同步推論 API (`/api/enhance-transcript`)**
    *   保留 GCP Cloud Run 的 L4 GPU 資源。當使用者點選「使用強大 AI 精修會議紀錄」時，觸發 Cloud Run Job 或非同步任務。
    *   GCP 呼叫 Whisper Large V3 / WhisperX (包含多語者分離 Diarization) 以 30x RT 效率批次處理，再透過 LLM 打包會議決策摘要。

---

## 3. 架構限制與風險管控 (Risk Management)

| 潛在風險 (Risks) | 緩解措施 (Mitigation) |
| :--- | :--- |
| **量化模型準確度下降** | 將 Edge 版本定位為「即時提示字幕與草稿」，並提供一鍵 Enhance 上流雲端的機制，引導對品質極度要求的客戶回到 GCP 進行事後算力修復。|
| **硬體耗能與散熱 (Thermal Throttling)** | 若使用者會議長達數小時，輕薄筆電純靠 CPU/WebGPU 運算會發熱降頻，未來需準備效能監控 API，當背壓 (Backpressure) 過大時動態關閉 Edge 計算。|
| **VDI 防火牆實體限制** | 需要由業務或預售工程師與採購企業 IT 溝通，務必在 VDI 通道上開放實體機瀏覽器的麥克風穿透存取權。|

---

## 4. 完成判定標準 (DoD)

依據專案 harness 準則，任何參與實作的工程師開發完畢後需通過：
1. **本地端驗證**：切斷網路後，成功使用 Edge 模型生成 10 分鐘以上的逐字稿，且 OPFS 完整保存記錄。
2. **斷網重連驗證**：網路恢復後 5 秒內，系統必須自動接續上拋任務並在 GCP Cloud SQL 留下完成標記。
3. **雲端效能審核**：經由測試，驗證按下 Enhance 功能後，單台 L4 Cloud Run 可在 30 秒內解算完 10 分鐘長度之會議音軌。
