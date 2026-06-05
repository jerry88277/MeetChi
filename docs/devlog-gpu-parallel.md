# GPU 平行推論開發日誌

> 紀錄 MeetChi GPU ASR 服務「單顆 GPU 平行處理多 chunk」功能的設計討論、
> 可行性分析與實作過程。

---

## 一、背景與問題

### 1.1 現有架構（實作前）

```
Backend tasks.py
  └─ _process_split_audio_sync()
       ├─ 切割音訊為 N chunks（每段 ~20 分鐘）
       ├─ Semaphore(2)：最多 2 個 chunk 同時送 GPU ASR
       └─ GPU ASR Cloud Run（containerConcurrency=1, max-instances=2）
            └─ 每個 instance 一次處理 1 chunk（CTranslate2 sequential）
```

**問題：** 處理 1 小時會議（4 chunks × 117s）需要約 4 分鐘，
且 Semaphore=2 意味 Cloud Run 自動 scale 到 2 個 instance，
每個 instance 各跑 1 個 chunk → 同時消耗 2 顆 GPU。

**成本壓力：** L4 GPU instance 費用較高，希望降低並行 instance 數。

### 1.2 成本vs效能分析

| 方案 | GPU 用量 | 時間 | 備註 |
|------|---------|------|------|
| 目前（Semaphore=2, max=2）| 2 instance | ~4 分鐘 | 週工作日 08:00-17:00 排程 |
| 改 min=0，其他不變 | 0→2 instance | ~4 分鐘 + 冷啟動 ~70s | 非使用時間節省費用 |
| 單 GPU 平行（本功能）| 1 instance | ~2 分鐘（理論）| 最理想，降成本又加速 |

---

## 二、GPU min-instances=0 風險討論

**時間：** 2026-06-05 討論

**若 min-instances 設為 0 的影響：**

1. **冷啟動延遲 ~70 秒**（L4 instance + Breeze-ASR-25 模型載入約 70-80s）
2. **使用者體驗：** 上傳後點選會議，最多等待 70s 才開始出現進度
3. **排程方案：** 工作日 08:00 scale-up to 1，17:00 scale-down to 0
   - 以工作日 9 小時計算：**9hr × 22工作日 = 198 GPU hr/月**
   - vs 全天常駐：**24hr × 30天 = 720 GPU hr/月**
   - **節省約 72%**
4. **風險：** 17:00 後有人上傳需等待冷啟動；可接受

**結論：** 採用排程方案，Cloud Scheduler 已設定。

---

## 三、平行推論可行性分析

**時間：** 2026-06-05 討論

### 3.1 四個方案討論

| 方案 | 原理 | 效果 |
|------|------|------|
| 1. 維持 max=2 | 現況 | 穩定，成本稍高 |
| **2. inter_threads（本方案）** | **單 GPU 多 CUDA stream** | **降成本 + 保速度** |
| 3. 更小 chunk | 每 chunk 更短 | 無實質加速 |
| 4. Batch endpoint（序列）| 同一 instance 序列處理 | 無加速，只解 TCP timeout 問題 |

### 3.2 Batch 方案為何無效（重要討論）

> 使用者提問：「batch 是先切割再依序由單一 GPU 處理，這樣跟沒有 batch 有什麼差別？」

**結論正確：** Batch = 序列 = 總時間 ≈ N × 單chunk時間。

Batch 唯一的效益是將 N 個 HTTP 連線合併為 1 個，
避免 GFE TCP idle-timeout（>30s 無活動關閉連線），
但無法降低推論時間。

### 3.3 CTranslate2 inter_threads 機制

CTranslate2 `WhisperModel(num_workers=N)` 的運作原理：
- **Model weights 只載一次**，存放在 GPU memory
- 建立 N 條 CUDA stream，每條 stream 有獨立的 KV-cache 與 activation buffer
- 多個 `transcribe()` 呼叫可真正同時執行（非 GIL 限制，CTranslate2 是 C++ extension）
- faster-whisper 的公開 API 是 `num_workers`，內部映射為 CTranslate2 `inter_threads`

### 3.4 VRAM 預算計算（L4 = 24GB）

| 組件 | VRAM |
|------|------|
| Breeze-ASR-25 weights（Whisper Large，float16）| ~3 GB |
| Per-thread activations（KV cache × N）| ~1.5 GB × N |
| pyannote diarization（1 instance，序列跑）| ~1.5 GB |
| WhisperX alignment（主要 CPU）| ~0.5 GB |
| 20% driver buffer | ~4.8 GB |

**公式：** `3 + 1.5N + 1.5 + 0.5 + 4.8 ≤ 24`
→ `N ≤ 9`（安全值取 **N=3**，VRAM 佔用約 57%）

> 使用者推算「保留 20% VRAM 最多 7 個 chunk」— 與計算吻合，
> N=3 是保守安全值，日後可視需求提升。

### 3.5 各步驟平行化難度

| 步驟 | 目前狀態 | 平行化 | 備註 |
|------|---------|--------|------|
| CTranslate2 transcribe | ✅ 正常 | ✅ `num_workers=N` 原生支援 | **Step 1 已完成** |
| WhisperX alignment | ❌ 生產環境失敗 | 可 `asyncio.to_thread` | 先修失敗問題 |
| pyannote diarization | ❌ 生產環境失敗 | 需 N 個 pipeline 實例或序列 | 先修 HF token 問題 |

**diarization 失敗原因：**
```
Could not download 'pyannote/speaker-diarization-3.1' pipeline
'NoneType' object has no attribute 'to'
```
推測 `HF_AUTH_TOKEN` 過期，或 pyannote gated model 需重新接受條款。

---

## 四、實作記錄

### 4.1 Step 1 — offline_asr.py inter_threads（已完成）

**時間：** 2026-06-05

**變更 `apps/backend/app/offline_asr.py`：**

1. `BreezeASRConfig` 新增欄位：
```python
# CTranslate2 concurrent inference streams (single GPU, shared weights)
inter_threads: int = field(default_factory=lambda: int(os.getenv("ASR_INTER_THREADS", "1")))
```

2. `_load_model()` 傳入 `num_workers`（faster-whisper 公開 API）：
```python
self._model = WhisperModel(
    self.config.model_name,
    device=device,
    compute_type=compute_type,
    num_workers=self.config.inter_threads,  # maps to CTranslate2 inter_threads
)
logger.info(f"Breeze ASR model loaded successfully. (inter_threads={self.config.inter_threads})")
```

**Cloud Run 配置變更：**

| 設定 | 舊值 | 新值 |
|------|------|------|
| `containerConcurrency` | 1 | 3 |
| `ASR_INTER_THREADS` | 未設定 | 3 |
| Revision | `meetchi-gpu-asr-00011-x2t` | `meetchi-gpu-asr-00017-woq` |

**中間問題（INC-015）：**
revision 00016 錯誤地傳 `inter_threads=3` 直接給 `WhisperModel`，
CTranslate2 報 `multiple values for keyword argument 'inter_threads'`。
修正為 `num_workers=3`，revision 00017 正常啟動。

**驗證：**
- `/health` → `gpu_available: true, asr_available: true` ✅
- 啟動 log → `Breeze ASR model loaded successfully. (inter_threads=3)` ✅

**Commit：** `3aa000a` — feat(gpu-asr): enable CTranslate2 inter_threads for single-GPU parallel inference

---

### 4.2 Step 2 — /asr/batch endpoint（待實作）

**目標：**
在 `gpu_service/main.py` 新增 `/asr/batch` endpoint，
接收多個 chunk 路徑，用 `asyncio.gather` 同時呼叫 `asyncio.to_thread(provider._transcribe_sync, ...)`，
真正利用 `num_workers=3` 的並行能力。

**設計草稿：**
```python
@app.post("/asr/batch")
async def asr_batch(request: ASRBatchRequest):
    # 下載所有 chunks
    chunk_paths = [download(url) for url in request.chunk_urls]
    # 並行轉錄（利用 inter_threads）
    results = await asyncio.gather(*[
        asyncio.to_thread(provider._transcribe_sync, path, request.language)
        for path in chunk_paths
    ])
    return results
```

**pyannote 線程安全問題：**
`DiarizationPipeline` 不是線程安全的（PyTorch model）。
選項：
- A. 載入 N 個 pipeline 實例（N × ~1.5GB VRAM）— 完全平行
- B. 序列跑 diarization，平行跑 transcription — 簡單，部分加速

建議先實作 B，待 diarization 修復後評估是否改 A。

### 4.3 Step 3 — tasks.py 切換到 /asr/batch（待實作）

`tasks.py` 新增 `USE_BATCH_ASR` env var 開關，
切換 `_process_split_audio_sync()` 使用 `/asr/batch` endpoint。

---

## 五、GitHub Enterprise 同步

**時間：** 2026-06-05

新增 remote `enterprise` 指向企業 GitHub：

```bash
git remote add enterprise https://github.com/JERRY-TAI_chimei/MeetChi
git push enterprise main
```

| Remote | URL | 說明 |
|--------|-----|------|
| `origin` | `https://github.com/jerry88277/MeetChi` | 個人開發 repo（此環境 token 無寫入權） |
| `enterprise` | `https://github.com/JERRY-TAI_chimei/MeetChi` | 企業內部 repo（當前 push 目標）|

> ⚠️ 此環境 GitHub token 是 `JERRY-TAI_chimei` 帳號，`origin (jerry88277)` 推送會 403。
> 日後若需同步個人 repo，需切換 token 或使用 SSH。

---

## 六、後續待辦

| 優先 | 項目 | 說明 |
|------|------|------|
| **高** | 修復 pyannote diarization | 確認 `HF_AUTH_TOKEN` 是否有效；至 huggingface.co 重新接受 `pyannote/speaker-diarization-3.1` 條款 |
| **高** | Step 2：`/asr/batch` endpoint | 讓 containerConcurrency=3 真正發揮效用 |
| **中** | Step 3：tasks.py 切換 | 以 `USE_BATCH_ASR` env var 控制開關 |
| **中** | 修復 WhisperX alignment | `jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn` 404 |
| **低** | 提升 inter_threads | 驗證 N=3 穩定後，可試 N=5 觀察 VRAM 與吞吐量 |
