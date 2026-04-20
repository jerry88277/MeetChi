# 🚀 MeetChi 終極端雲混合架構白皮書 (Ultimate Edge-Cloud Hybrid Architecture Spec)
**基準與願景**：支撐每日百場連線規模，並從純粹的「即時雲端串流推論」演進至「Pure Web 邊緣預先計算 + 雲端非同步精修 (Draft-and-Enhance)」。
**分析方法論**：First Principles (第一性原理), MECE (不重疊不遺漏原則), SWOT 分析, Model-thinking。

---

## 第一部：系統負載極限與後端推論引擎推演

在討論任何端雲架構前，我們必須先回歸「物理法則」與「基礎排隊理論」來建置雲端算力模型。

### 1-A. Concurrency (並發數) 模型推算
若在 9 小時內均勻消化 100 場 1 小時會議：
* **常態並發量 (Average)**：約 11~12 路同時收音。
* **尖峰並發量 (Peak)**：考慮 09:00 或 14:00 群聚效應，系統必須容忍至少 20 路並行 (20 Streams)。

### 1-B. 雲端主流推論方案大檢閱

#### 方案 A：傳統擴展 `CT2 Faster-Whisper`
*   **特性**：單機 4.4G VRAM 足跡穩定。`CTranslate2` 將 GPU VRAM 消耗降低了 2~3 倍，提升推理速度 6~8 倍，極適合「低延遲」。
*   **劣勢**：單一機器承受超過 5 路同步時會引發延遲堆疊。20 路尖峰需長出 4 ~ 5 台 L4 GPU，成本疊加昂貴，且閒置浪費算力。

#### 方案 B：前沿武裝 `Whisper MLA + vLLM` (連續 Batching 兵器)
*   **特性**：將 20 路音訊透過 Triton kernel 合併。根據《Whisper-MLA》文獻，Latent Space 壓縮**精確減少了 87.5% 的 KV Cache 記憶體足跡**。極限情境 `[Batch=64, SeqLen=2048]` 下，原版 Whisper 破 24G OOM，MLA 版穩固於 15.4 GB。這是一台 L4 單卡扛下百場會議的物理基石。
*   **劣勢**：MLA 本質是「以算力換取記憶體」，解碼需 4 倍矩陣操作。目前 vLLM 尚未支援 Whisper 字組級時間戳，客製開發難度極高，且面臨嚴峻的 OOM 單點失效風險。

---

## 第二部：降維打擊 — Pure Web 端雲混合架構深潛 (Edge-Cloud Hybrid)

為徹底解耦基礎設施成本與並發壓力，架構將走向「邊緣預處理 (Edge) + 雲端增強 (Cloud)」。此舉一舉消滅四大痛點：(1) 雲端 GPU 成本暴漲、(2) VDI 網段防火牆限制、(3) 斷網沒有留下音軌的風險、(4) 免去任何系統層級安裝，實現真正的「跨平台、瀏覽器打開即用 (Zero-install PWA)」。

### Phase 1: Pure Web 錄音接管與沙盒離線暫存
**目標：確保無網路也可開啟網頁穩定錄製原音與推論。**
*   **PWA 與 Service Worker**：全靜態資源預先快取，使 Web App 支援離線秒開。
*   **OPFS (Origin Private File System) 儲存層**：利用 `MediaRecorder API` 以 Chunk 分段儲存為 `webm/ogg` 寫入 OPFS。長達 3 小時的會議也不會造成瀏覽器 RAM OOM。會後若偵測離線，自動強迫將原音寫入使用者的實體「Download」資料夾。

### Phase 2: 模型量化加密與 Web 推論引擎
**目標：賦予純 Web 端執行中英夾雜 ASR 的本地算力。**
*   **Breeze ASR 25 量化工程 (ONNX)**：實施 8-bit/4-bit 量化，將原模型壓制在 300~500MB，適配網頁秒載。
*   **IndexedDB + AES 防盜預載**：雲端對 `.onnx` 打包加密，用戶預載入 IndexedDB 快取。推論前才於 `ArrayBuffer` 即時解密，阻絕基礎盜取風險。
*   **推論引擎架構分級 (onnxruntime-web)**：優先試探 `WebGPU`；若不支持，降配至 `WebAssembly (Wasm) + SIMD + Multi-threading`。強力賦予 Initial Prompt (`"繁體中文，允許夾雜英文"`) 抑制輕量級模型產生的中英夾雜幻覺。

### Phase 3: 端雲斷點續傳與 Enhance (雲端精修)
**目標：輕量化本機結果，按需調用企業級後端算力。**
*   **背景上傳 (Background Sync)**：會後或網路恢復時，Service Worker 將 OPFS 的音軌與草稿逐字稿，非同步上傳至 GCP bucket。
*   **按需非同步增強 (`/api/enhance-transcript`)**：只有當使用者點擊「使用 AI 精修會議」時，才觸發 Cloud Run L4 GPU，呼叫 Whisper Large V3 / WhisperX (附帶 Diarization) 以 30x RT 效率批次處理，產出高精度決策紀錄。

---

## 第三部：🛑 盲點與防禦性設計 (Blind Spot Solutions)

我們透過 Model-thinking 審視以上藍圖，發現並導入了防禦機制以對抗現實破壞力：

1. **排隊理論「驚群效應 (Thundering Herd)」**
   * **挑戰**：會議大多在整點 (09:00:00) 準時開始，瞬間連線會癱瘓伺服器。
   * **防禦**：WebSocket 入口處強制導入 Token Bucket / Pub-Sub 非同步緩衝隊列；前端加上 Jitter 延遲重試以削弱波峰。
2. **資訊理論「訊噪與幻覺放大 (Noise & Hallucination)」**
   * **挑戰**：行動網路造成的封包遺失，會讓丟進模型的不完整音訊誘發嚴重幻覺（例如瘋狂重複產生「......」）。
   * **防禦**：廢除單純按秒切割。前端導入超輕量 VAD，確有真實停頓始送出音檔，且切片間強制保留 `500ms 重疊 (Overlap)` 免去上下文斷層。
3. **微觀經濟學「Cloud Run GPU 待機稅 (Always-on Trap)」**
   * **挑戰**：為免冷啟動而設定 `min-instances=1`，L4 GPU 空轉計費將高得嚇人。
   * **防禦**：導入 Wake-on-Demand (會前 5 分鐘 Scheduler 自動 Ping 醒)，或採 Event-driven：前 60 秒聲音先拋給無冷啟動的純 CPU 原力版處理 (Warm-up buffer fallback)。
4. **FMEA 分析「邊緣計算硬著陸 (WebGPU 崩潰)」**
   * **挑戰**：`Transformers.js` 在 WebGPU 跑長音頻存在 Issue #860 Tensor KV Cache 未回收之記憶體洩漏風險；設備不足也會直接使分頁掛點。
   * **防禦**：必須升級至 `>= 3.0.0-alpha.19` 修復版。同時實作 **「漸進式增強 (Progressive Enhancement)」動態路由**，無 GPU 或是 VRAM 極度貧脊之設備，直接無感靜默 fallback 至雲端 WebSocket 備用通道。

---

## 第四部：🎯 架構師最終演化與執行藍圖

| 評量維度 (1-5分) | 方案 A (CT2 後端堆疊) | 方案 B (MLA+vLLM 極限降本) | 方案 C (端雲混合架構) |
|---|:---:|:---:|:---:|
| **開發時程與風險** | **5 (馬上能用)** | 1 (底層重寫度極高) | 2 (前端生態尚須驗證) |
| **品質精確度 (WER)** | 5 (滿血大模型) | 5 (滿血大模型) | 2 (嚴重降維與量化限制) |
| **伺服器擴展成本** | 2 (疊加極端昂貴) | **5 (極大化資本效率)** | **5 (完全零散發成本)** |

### 🧭 三階段戰略推演 (Evolutionary Architecture)

1. **短期護城河 (Phase 1, 0~3 個月)**：
   優先採用 **方案 A (CT2 Faster-Whisper)** 上線。利用 Cloud Run Scale-out 換取最珍貴的「系統穩定度」與「高準確率」，容忍前期日均 10 場以內的基礎成本。
2. **中期利潤防護 (Phase 2, 突破 50 場日均門檻)**：
   啟動研發 **方案 B (Whisper MLA)**。當高併發壓力讓雲端帳單飆升時，以 Canary Deployment 抽出 10% 流量至 vLLM 驗證 PagedAttention 極限，最終替換為單卡百場後端架構。
3. **長期去中心化終型 (Phase 3, Edge-Cloud Hybrid 平民化)**：
   全面實施 **方案 C (Pure Web)**。為免費使用者端出利用他們自己硬體算力的 Wasm/WebGPU 版本；只為付費企業級用戶保留後端高品質算力，實現零伺服器成本無限吸納免費流量的終極商業模式。

### 📋 完成判定標準 (Definition of Done)
1. **韌性驗證**：切斷網路後，成功使用 Edge 模型生成 10 分鐘以上草稿，且 OPFS 完整保存 `webm` 記錄不遺失。
2. **斷聯重整驗證**：網路恢復 5 秒內，自動接續背景上傳任務，於 GCP Cloud SQL 留下完成標記。
3. **增強效能驗證**：請求 Enhance 雲端精修功能後，單台 L4 Cloud Run 可穩固在 30 秒以內解算完 10 分鐘長度之會議。
