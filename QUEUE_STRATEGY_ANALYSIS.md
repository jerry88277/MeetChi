# 多用戶排隊策略分析

> 建立日期: 2026-06-10  
> 適用: MeetChi GPU ASR 轉錄服務

---

## 現況架構

```
User Upload → Backend (Cloud Run) → GPU ASR Service (Cloud Run GPU)
                                     ├── maxInstances: 2
                                     ├── concurrency: 5
                                     └── 有效吞吐: 10 concurrent streams
```

### 目前排隊邏輯
- Backend 收到轉錄請求後，直接同步呼叫 GPU ASR（`_process_split_audio_sync`）
- 使用 `asyncio.Semaphore(ASR_PARALLELISM=5)` 限流
- 長音源切成 10-15 分鐘 chunks，平行送出
- **無優先級機制**：先到先服務（FIFO）

---

## 方案分析

### 方案 A: Cloud Tasks Queue + Priority（推薦）

**架構**:
```
Upload → Backend → Cloud Tasks Queue → Backend Worker → GPU ASR
                   (priority 0-9)        (rate limiting)
```

**實作方式**:
- 使用 Google Cloud Tasks 建立 task queue
- 每個轉錄任務帶 priority 參數
- Cloud Tasks 支援 `max_dispatches_per_second` 和 `max_concurrent_dispatches`
- 短音源（< 5 min）設 priority=1（高優先）
- 長音源（> 20 min）設 priority=5（低優先）
- VIP 用戶可設 priority=0

**優點**:
- Cloud Tasks 原生支援 retry、rate limiting、priority
- 解耦 upload 與 transcription（上傳即返回，不佔 backend worker）
- 可觀測性佳（Cloud Console 直接看 queue depth）

**缺點**:
- 增加架構複雜度
- Cloud Tasks 的 priority 是相對的（非嚴格排序）
- 額外延遲 ~1-3 秒（task dispatch latency）

---

### 方案 B: 本地 Redis Queue + Worker（備選）

**架構**:
```
Upload → Backend → Redis Queue (sorted set by priority) → Worker Process → GPU ASR
```

**優點**: 精確控制排序、無外部依賴延遲  
**缺點**: 需維運 Redis instance、single point of failure

---

### 方案 C: 維持現狀（Semaphore 限流）

**優點**: 簡單、無額外基礎設施  
**缺點**: 無優先級、大量用戶同時上傳時體驗差

---

## 塞車機率計算

### 假設參數

| 參數 | 值 | 來源 |
|------|------|------|
| 日均轉錄需求 | 5 場會議/天 | 目前使用量 |
| 平均音源長度 | 1.5 小時 | AI 2026 + 一般會議平均 |
| 單場處理時間 | 12 分鐘 | AI 2026 實測（2.3h → 12min） |
| 工作時段 | 8:00-17:00（9 小時） | 奇美上班時間 |
| GPU 吞吐量 | 10 concurrent streams（2 instances × 5） | 新配置 |
| 單 chunk 處理時間 | ~150 秒 | 15 min 音源 → 150s 處理 |

### 情境 1: 目前使用量（5 場/天，2 用戶）

**到達率 λ**: 5 場 / 9 小時 = 0.556 場/小時  
**服務率 μ**: 60 min / 12 min = 5 場/小時（單一 pipeline 可處理）  
**利用率 ρ** = λ / μ = 0.556 / 5 = **11.1%**

**排隊機率（Erlang-C）**:
- 伺服器數 c = 1（一次處理一場會議的完整 pipeline）
- P(排隊) = ρ^c / (1 - ρ) × ... 
- 簡化: 以 M/M/1 模型，P(queue > 0) = ρ = **11.1%**
- **結論: 幾乎不會塞車** ✅

### 情境 2: 成長期（20 場/天，10 用戶）

**到達率 λ**: 20 / 9 = 2.22 場/小時  
**服務率 μ**: 5 場/小時  
**利用率 ρ** = 2.22 / 5 = **44.4%**

**M/M/1 排隊指標**:
- P(系統忙碌) = 44.4%
- 平均等待時間 Wq = ρ / (μ(1-ρ)) = 0.444 / (5 × 0.556) = **9.6 分鐘**
- P(等待 > 10 min) ≈ e^(-μ(1-ρ)×10/60) = e^(-0.463) = **63%** 有等待但多數 < 10min

**結論: 偶爾需等待，體驗尚可** ⚠️

### 情境 3: 尖峰時段（同時 5 人上傳，每人 1.5h 音源）

**瞬時負載**: 5 場 × 10 chunks/場 = 50 chunks 同時到達  
**GPU 處理速度**: 10 concurrent streams × 150s/chunk  
**消化時間**: 50 chunks ÷ 10 streams × 150s = **750 秒 ≈ 12.5 分鐘**

**但**: 第一批 10 chunks 立即開始，最後一批需等 ~10 分鐘
- 第 1 位用戶（最先到）: 完整處理 ~12 分鐘
- 第 5 位用戶（最後到）: 等待 + 處理 ≈ **12-15 分鐘**

**無優先級時**: 所有人平均等待 ~10 分鐘  
**有優先級時**: 短音源（5 min）在 1-2 分鐘內完成，長音源等 15 分鐘

**結論: 引入優先級能顯著改善短音源用戶體驗** ⚠️→✅

### 情境 4: 極端情況（50 場/天，20 用戶）

**到達率 λ**: 50 / 9 = 5.56 場/小時  
**服務率 μ**: 5 場/小時  
**利用率 ρ** = 5.56 / 5 = **111%** > 100%

**結論: 系統過載，queue 無限增長** ❌

**解法**: 
- 提高 maxScale=3（15 concurrent streams → μ=7.5 場/hr → ρ=74%）
- 或啟用 minScale=0 的第三台做 burst capacity

---

## 塞車機率匯總表

| 情境 | 日均場次 | 利用率 | P(等待>5min) | P(等待>15min) | 建議 |
|------|---------|--------|-------------|--------------|------|
| 現在 | 5 | 11% | <5% | <1% | 不需排隊機制 |
| 成長期 | 20 | 44% | ~30% | ~10% | 建議加入優先級 |
| 尖峰 | 同時5人 | burst | ~60% | ~20% | 需要優先級+buffer |
| 極端 | 50 | >100% | 100% | ~80% | 需擴容 |

---

## Cloud Tasks Priority 實作方案

### Queue 配置
```yaml
# cloud-tasks-queue.yaml
queue:
  name: meetchi-transcription
  rate_limits:
    max_dispatches_per_second: 2    # 最多每秒 dispatch 2 個 task
    max_concurrent_dispatches: 3    # 最多 3 個同時在處理
  retry_config:
    max_attempts: 3
    min_backoff: 10s
    max_backoff: 300s
```

### Priority 策略

| 音源長度 | Priority (0=最高) | 預期等待 | 理由 |
|---------|-------------------|---------|------|
| < 5 min | 0 | < 1 min | 短會議，快速回饋 |
| 5-30 min | 3 | 1-5 min | 一般會議 |
| 30-60 min | 5 | 5-10 min | 中型會議 |
| > 60 min | 7 | 10-20 min | 大型會議，用戶預期等較久 |
| VIP 用戶 | 0 | 最低 | 管理層/付費用戶 |

### 比較: Cloud Tasks vs Redis Queue

| 面向 | Cloud Tasks | Redis Queue |
|------|-------------|-------------|
| 基礎設施 | 無需維運（GCP managed） | 需 Redis instance |
| 優先級支援 | ✅ 原生（task scheduling） | ✅ Sorted Set |
| 精確排序 | 相對（非嚴格 FIFO within priority） | 精確 |
| 可觀測性 | Cloud Console 原生 | 需自建 dashboard |
| 延遲 | 1-3 秒 dispatch | < 100ms |
| 成本 | 免費（< 1M tasks/月） | ~$30-50/月 (Redis) |
| 可靠性 | 99.95% SLA | 依部署方式 |

**推薦: Cloud Tasks**（無需額外維運、免費、足夠精確）

---

## 實施建議

### Phase 1（現在不需要）
目前 5 場/天，利用率 11%，**暫不實施**排隊機制。

### Phase 2（當日均 > 15 場時啟動）
1. 建立 Cloud Tasks queue
2. Backend upload 完成後 → 建立 task（含 priority）
3. Worker endpoint 接收 task → 呼叫 GPU ASR
4. 前端顯示 queue position

### Phase 3（當日均 > 40 場）
- 考慮 maxScale=3-4
- 或 API 混合架構（短音源走 GPT-4o-mini API，長音源走本地 GPU）

---

## 結論

**以目前 5 場/天的使用量，塞車機率 < 5%，不需要引入排隊機制。**

當成長至 15-20 場/天時（利用率接近 40-50%），建議引入 Cloud Tasks Priority Queue，可將短音源的等待時間從平均 10 分鐘降至 < 2 分鐘，大幅提升使用者體驗。

投資報酬率: Cloud Tasks 免費 + 開發約 1 天 → 在 20+ 場/天時有效避免塞車。
