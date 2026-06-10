# GPU ASR 平行轉錄優化方案

> 文件建立: 2026-06-10  
> 目前配置: 1× NVIDIA L4 GPU, maxScale=1, concurrency=3, ASR_PARALLELISM=3

---

## 現況架構

| 參數 | 當前值 | 說明 |
|------|--------|------|
| GPU 型號 | NVIDIA L4 (24GB VRAM) | Cloud Run GPU |
| Max Instances | 1 | GPU quota 限制 |
| Container Concurrency | 3 | 單 instance 同時處理 3 個請求 |
| ASR_PARALLELISM | 3 | Backend Semaphore 限流 |
| AUDIO_CHUNK_SEC | 900 (15 min) | 音源切片長度 |
| CPU/Memory | 8 vCPU / 32GB RAM | 配合 GPU 使用 |
| Min Instances | 1 | 避免 cold start |

### 實測效能（AI 2026 直播論壇, 2.27 小時音源）
- 10 chunks, parallelism=3
- ASR 耗時: ~9 分鐘
- 單 chunk 平均: ~147 秒（處理 15 分鐘音源）
- 吞吐率: ~15.3x 實時（realtime factor）

---

## 優化方向

### 1. 提高並行度 (Parallelism)

#### 方案 A: 提高 Concurrency（低風險）
| 配置 | Concurrency | 預期效果 | 風險 |
|------|-------------|---------|------|
| 當前 | 3 | ~9 min / 2.3h 音源 | — |
| 建議 | 4-5 | ~7 min / 2.3h 音源 | VRAM 壓力增加 |
| 極限 | 6 | ~6 min | 可能 OOM |

**L4 VRAM 分析（24GB）：**
- Whisper-large-v3 模型: ~3.1GB VRAM
- 每個 inference stream: ~2-3GB 額外 VRAM（含 KV cache + 解碼）
- 安全上限: 24GB ÷ (~3GB + 3GB×N) ≈ **4-5 concurrent streams**
- 建議先試 `concurrency=4, ASR_PARALLELISM=4`

**操作步驟：**
```bash
# 調整 Cloud Run concurrency
gcloud run services update meetchi-gpu-asr \
  --concurrency=4 \
  --region=asia-southeast1

# 同步調整 backend 環境變數
gcloud run services update meetchi-backend \
  --update-env-vars ASR_PARALLELISM=4 \
  --region=asia-southeast1
```

#### 方案 B: 增加 Max Instances（需 quota）
- 若 GCP 核准 GPU quota > 1，可設 `maxScale=2`
- 效果：吞吐量 ×2，但成本也 ×2
- 適合多用戶同時上傳場景
- **注意**: 目前 `minScale=1` 已確保無 cold start；若 maxScale=2，建議 `minScale=1` 維持

#### 方案 C: 混合精度 / 量化模型
- 使用 FP16/INT8 量化版 Whisper → VRAM 用量降 50%
- 可支撐 concurrency=6-8
- 代價：極少量精度損失（實測差異 < 1% WER）

---

### 2. 切片大小優化 (Chunk Size)

| AUDIO_CHUNK_SEC | Chunks 數 (2.3h) | 優點 | 缺點 |
|-----------------|-------------------|------|------|
| 600 (10 min) | 14 | 更快排空單次轉錄 | chunks 更多，merge overhead |
| **900 (15 min)** | 10 | **當前平衡** | — |
| 1200 (20 min) | 7 | 減少切邊損失 | 單 chunk 失敗重試代價高 |
| 1800 (30 min) | 5 | 最少 merge overhead | retry 代價極高 |

**建議維持 900 秒**：
- 15 分鐘在 L4 上處理約 150 秒（10:1 比），chunk 失敗重試可接受
- 切邊處已使用 `-c copy`（無重新編碼），無音質損失

---

### 3. Cold Start 優化

| 項目 | 當前 | 建議 |
|------|------|------|
| minScale | 1 | ✅ 已最佳化（無 cold start） |
| startup-cpu-boost | true | ✅ 已啟用 |
| Model preload | ✅ 服務啟動時載入 | 維持 |

目前已無 cold start 問題。若未來切為 `minScale=0`（省成本），cold start 約 45-60 秒。

---

### 4. 網路 I/O 優化

| 面向 | 當前 | 優化空間 |
|------|------|---------|
| Chunk 下載 | GCS → GPU instance | 已最佳化（同 region） |
| Result 回傳 | JSON over HTTP | 可考慮 gRPC streaming（但 ROI 低） |
| Audio 上傳 | Chunked upload → GCS | 已最佳化 |

---

### 5. 多用戶排隊策略

當多用戶同時上傳時：
- **當前**: 先到先處理，後者排隊等待
- **優化方案**: 
  - 短音源優先（< 5 min）→ 先快速處理
  - 長音源拆解 + 低優先 chunk 可被插隊
  - 使用 Cloud Tasks queue 搭配 priority

---

## 推薦行動（分階段）

### Phase 1（立即可做，零風險）
- [x] ~~minScale=1 避免 cold start~~ ✅ 已完成
- [ ] 監控 GPU VRAM 使用率（`nvidia-smi` in container logs）

### Phase 2（低風險，1 小時內完成）
- [ ] `concurrency=4, ASR_PARALLELISM=4`（預期 -20% 處理時間）
- [ ] 觀察 1-2 天是否 OOM

### Phase 3（中期，需要 quota 申請）
- [ ] 申請 GPU quota maxScale=2
- [ ] 實現優先級排隊（Cloud Tasks priority queue）

### Phase 4（長期優化）
- [ ] FP16/INT8 量化 → concurrency 翻倍
- [ ] 若轉 Whisper-v4 或 distil-whisper → 更快推理
- [ ] gRPC streaming result 減少 long-polling

---

## 成本估算

| 配置 | 月成本（概估） | 說明 |
|------|-------------|------|
| 當前 (1×L4, minScale=1) | ~$720/月 | 24/7 常駐 |
| maxScale=2 | ~$720-$1,440/月 | 第二台按需 |
| 若改 minScale=0 | ~$200-$400/月 | 按使用量計（含 cold start） |

> 若日均轉錄量 < 2 小時音源，可考慮 `minScale=0` 省 50%+ 成本（接受 45s cold start）
