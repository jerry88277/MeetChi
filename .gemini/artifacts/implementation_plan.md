# MeetChi: vLLM 架構升級研究報告與實施計畫
**目標**: 將 Whisper-MLA 導入 vLLM 實現 PagedAttention Continuous Batching，以滿足單卡 (L4) 日均 100 場會議的高吞吐量 (High Throughput) 需求。

## User Review Required
> [!IMPORTANT]
> 此份報告涵蓋了架構升級中極具挑戰的「自定義模型適配」風險與失敗退路規劃。請審閱其中的 `Rollback` 策略與 `Edge CPU` 的備案，確認是否符合成本效益後，再授權執行後續開發。

---

## 1. 核心技術重構：vLLM & Continuous Batching 規劃

由於 `whisper-mla` 內帶有客製化的 Multi-Head Latent Attention (MLA) 結構，且原始 vLLM 僅對「標準 Whisper」有原生支援，我們需要進行深度二次開發：

### A. 模型介接 (Custom Model Registry)
要利用 vLLM 的 PagedAttention 記憶體極限壓縮能力，我們必須將 `Breeze-ASR-MLA` 的底層算力邏輯註冊進 vLLM 框架：
1. 取代原有 `inference.py` 內單純的 PyTorch Eager Sequential 推理。
2. 開發 `vllm_model_wrapper.py`，手動映射 KV 邏輯使其符合 vLLM 可以解析與管理 Paged KV block 的格式。
3. 建立基於 FastAPI / Uvicorn 的 ASGI 伺服器，將傳入的音訊進行非同步排隊 (Async Queue)，送入 `vLLM Engine` 讓其發動 Continuous Batching 計算。

### B. Cloud Run 部署參數極限化
要實現單卡百場的並發，Cloud Run 必須進行以下強制調校（將透過 Terraform 或 gcloud 寫入佈署腳本）：
- **Concurrency**：提升至 `100` (強制不輕易 Scale-out，讓 100 個 Request 擠爆同一張 L4 GPU 來發揮 KV Cache 分攤效能)。
- **Memory**：提升至至少 `32GiB` (預防 vLLM 初始化 Paged Pointers 以及大音頻讀取時在 System RAM 發生 `OOM Kill`)。
- **CPU Boost**：固定分配 `8 vCPU` 且開啟 `--cpu-boost` 以打破 vLLM 極度耗時的 Kernel Compilation 冷啟動瓶頸。

---

## 2. 壓力測試規劃 (Stress-Test Plan)

在完成 vLLM 改造後，我們不能憑空相信其穩定度，必須進行高強度逼搶測試。

### 測試工具與策略：`Locust` 或 `k6`
1. **負載模型 (Load Profile)**：設計一個爬坡測試 (Ramp-up)，分別在 1 分鐘內湧入 10 個、50 個，最後 100 個併發的音檔解析請求 (\`/transcribe\`)。
2. **音檔混和 (Data Mix)**：模擬真實運營，混入 80% 的 10 分鐘短視訊 (`Hermes.wav` 級別) 以及 20% 的 2 小時巨型長會議 (`Maldives.wav` 級別)。
3. **觀測重點與健康指標**：
   - **GCP Cloud Monitoring**：嚴密觀測 GPU VRAM 走勢是否在並發來到 100 時仍被死磕在 24GB 以下 (無溢出崩潰)。
   - **TTFB 與 RTF 分佈**：確認 `Batch=100` 狀態下，請求是否被過度延遲 (Timeout > 3600s)。
   - **錯誤率分析**：抓取任何 HTTP 500、503 及 504 響應。

---

## 3. 備案評估：Edge CPU 方案比較

如果在極端商業考量下不願租用 L4 雲端 GPU，抑或是希望推行「本地桌面版 MeetChi」，就必須考慮無 GPU 的 Edge CPU 推論策略。

| 方案 | 適用裝置 | 精度 / 速度 | 優勢與定位 | 劣勢 |
|---|---|---|---|---|
| **Whisper.cpp (GGML)** | 低階筆電、甚至是強效手機 | 利用 INT4 / INT8 量化，速度可接受 | **極限成本壓縮**，完全無依賴的 C++ 執行檔，對記憶體佔用極低。本地部署首選。 | 會有明顯的精確度 (WER) 損失，難以執行高強度的連續 Batching。 |
| **OpenVINO (Intel)** | GCP N2, C2 架構的 Intel 伺服器 CPU | 高精度 (FP16/INT8) | 基於 Intel 晶片神經元優化，比純 PyTorch 快 2~4 倍。適合拿來降級運行 GCP 便宜的純 CPU 雲端實例。 | 若用戶不在 Intel 體系下效益低；模型須經深度 IR 格式轉換。 |
| **ONNX Runtime** | 通用伺服器、跨平台終端 | 中等精度 | 生態系豐富，支援 CPU / GPU 多重後端自動落腳。 | Optimization Graph 調校困難，記憶體佔用稍高。 |

> **結論策略**：針對 Cloud Run 架構如果要 Cost-down，推薦選用 **Intel OpenVINO** 作為無 GPU 時的運算引擎。若計畫推行跨平台的 App 客戶端，請走 **Whisper.cpp**。

---

## 4. 防災與失敗的 RollBack 機制 (Fail-Safe)

替換推理核心屬於心臟級手術，萬一 `Whisper-MLA` 無法穩定融合 `vLLM` 或是發生大量長度幻覺，系統必須具備立即止血能力。

### 部署層面 (Blue / Green Deployment)
1. **Traffic Splitting (流量切割)**：
   我們在 Cloud Run 發布時不會一次將舊版蓋掉。預設維持原有的 `faster-whisper` (CTranslate2 版本) 作為主要修訂版本 (Revision A，路由佔 95%)。將最新的 `vllm-mla` 版本作為 Canary 版本 (Revision B，路由佔 5%)。
2. **自動警報與回滾**：
   在 GCP Metrics 中加入監控（Error Rate > 5% 或 HTTP 504 數量激增）。一旦觸發警報，利用 `gcloud run services update-traffic` 指令，將 100% 流量秒切回舊版 Revision A，實現零停機 (Zero-downtime) 回滾。

### 應用程式防護 (Fallback Endpoint)
1. 在 Backend FastAPI 內部，建立**熔斷機制 (Circuit Breaker)**。
2. 當後台發現 vLLM 引擎的 API 長達 10 分鐘沒有回傳（或丟出 OOM Exception）時，後端主動將任務重新調度分派給仍掛載著 `faster-whisper` 的備用 Instance 進行單機消化，保證客戶最遲一定能拿到語音稿。

---

## 5. 後續執行授權
若上述研究及評估符合您的業務訴求：
1. 我們可以在下一階段開始起草 `locust_stress_test.py` 的建置。
2. 同時我將開始嘗試將 `Whisper-MLA` 的架構剖析並準備轉換給 `vLLM` 使用。
3. 或者是您可以決定先暫緩，轉為開發 **Edge CPU (如 Whisper.cpp)** 以進一步推演本地化計畫。

請給予您的決定。
