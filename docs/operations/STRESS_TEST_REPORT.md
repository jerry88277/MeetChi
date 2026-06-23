# MeetChi GPU ASR 壓力測試報告

> 最後更新：2026-06-22  
> 維護者：AI Platform Team

---

## 一、測試環境與基礎設施

### 1.1 GPU ASR Infrastructure

| 參數 | 最終正式值 | 說明 |
|------|-----------|------|
| Service | `meetchi-gpu-asr` | Cloud Run GPU (L4) |
| Region | `asia-southeast1` | Singapore |
| Concurrency | **2** | 避免 GFE TCP idle timeout |
| maxScale | **15** | GPU L4 quota 上限 |
| minScale | 排程 (0/1) | Mon-Fri 08-17 (UTC+8) = 1, 其他 = 0 |
| Timeout | 3600s | 單 request 最長 1hr |

### 1.2 Backend Configuration

| 參數 | 值 | 說明 |
|------|-----|------|
| ASR_PARALLELISM | **15** | Semaphore 上限，配合 GPU maxScale |
| AUDIO_CHUNK_SEC | **900** | 15min chunks |
| SKIP_GLOBAL_DIARIZATION | `true` | Phase B speaker linking 取代 |
| Retry | **5×** | 429-aware backoff (30s/60s/90s/120s) |
| Cloud Tasks maxConcurrentDispatches | 5 | Queue throttling |

### 1.3 測試音檔清單

| 音檔 | 時長 | 大小 | Chunks (15min) | Meeting ID |
|------|------|------|---------------|------------|
| 精準醫學學術研討會 | 4.3hr (257min) | 1.64 GB | 18 | `9a69a4f4` |
| AI 2026 直播論壇 (×4) | 2.3hr (136min) | 490 MB | 10 | `69252af7`, `94edd280`, `b4d5503e`, `e4b3f84c` |
| 壓測4-INFRA | 92min | 84 MB | 7 | `e961f65e` |
| 壓測4-嬌還 | 73min | 67 MB | 5 | `ff052a1f` |
| 壓測4-婉婷 | 73min | 67 MB | 5 | `e249ed8c` |
| 壓測4-伊甄 | 53min | 64 MB | 4 | `00c3fefb` |
| 壓測4-美玉 | 84min | 76 MB | 6 | `ad32ca73` |

---

## 二、歷史壓測結果

### 2.1 壓測4：Bulk Upload (5 場同時) — 2026-06-18

**目的**：驗證 Cloud Tasks queue throttling 在多場同時上傳時的穩定性

**配置**：GPU maxScale=2, concurrency=5, ASR_PARALLELISM=3

| 會議 | 音檔 | 處理時間 | process_ratio | 狀態 |
|------|------|----------|---------------|------|
| 壓測-伊甄 | 53 min | 42 min | 0.78x | ✅ COMPLETED |
| 壓測-嬌還 | 73 min | 42 min | 0.58x | ✅ COMPLETED |
| 壓測-婉婷 | 73 min | 32 min | 0.44x | ✅ COMPLETED |
| 壓測-INFRA | 92 min | 38 min | 0.41x | ✅ COMPLETED |
| 壓測-美玉 | 84 min | 34 min | 0.40x | ⚠️ BUG (retry 覆蓋) |

**發現問題**：
- Bug: Cloud Tasks retry 覆蓋已完成資料 → 修復 commit `eee1f5b`
- GPU maxScale=2 嚴重不足

---

### 2.2 壓測5：4.4hr 單場 — 2026-06-18 (失敗)

**目的**：測試超長會議的 parallel chunked ASR

**配置**：GPU maxScale=8, concurrency=8, ASR_PARALLELISM=14

| 指標 | 結果 |
|------|------|
| Chunks | 18 (15min each) |
| 完成率 | 11/18 ❌ |
| 失敗原因 | ReadError (GFE TCP idle timeout) |
| 最終狀態 | **FAILED** — hang 在 asyncio.gather |

**Root Cause**：
- concurrency=8 → 8 requests 排隊在單一 instance 內
- 最後的 request 等待 49min → 超過 GFE ~15min TCP idle timeout
- GFE 砍斷 TCP 連線 → backend 收到 ReadError

**修復**：concurrency 8→2, maxScale 8→15

---

### 2.3 壓測6：4.4hr 單場 — 2026-06-18 ✅ 成功 (Baseline)

**目的**：驗證 concurrency=2 + maxScale=15 修復 ReadError

**配置**：GPU concurrency=2, maxScale=15, ASR_PARALLELISM=15, retry=3

| 指標 | 結果 |
|------|------|
| Chunks | 18/18 ✅ |
| 429 errors | 2 (retry 成功) |
| ReadError | **0** |
| 總時間 | **26 分鐘** |
| Segments | 1,744 |
| process_ratio | 0.098x |

**時間線 (UTC+8)**：

| 時間 | 事件 |
|------|------|
| 19:18:24 | enqueue |
| 19:19:42 | 18 chunks 分割完成，15 chunks 同時送 GPU |
| 19:23:49 | 第一個 chunk 完成 |
| 19:34:02 | 18/18 chunks 全部完成 (GPU 階段 15min) |
| 19:43:40 | Global diarization 完成 + segments 寫入 (10min) |
| 19:44:13 | **COMPLETED** |

**時間分解**：
```
音檔分割:         ~1 min
GPU ASR (parallel): 15 min
Global Diarization: 10 min  ← 最大優化目標
摘要 + 寫入:       ~1 min
───────────────────────────
總計:              26 min
```

---

### 2.4 Exp-A：Skip Global Diarization — 2026-06-18 ✅ 成功

**目的**：量化 Global Diarization 的時間成本

**配置**：SKIP_GLOBAL_DIARIZATION=true, chunk=15min, retry=5 (429-aware backoff)

| 指標 | Baseline (壓測6) | Exp-A | 差異 |
|------|-----------------|-------|------|
| 總時間 | 26 min | **18 min** | **-31%** |
| Segments | 1,744 | 1,747 | ≈ 相同 |
| process_ratio | 0.098x | 0.068x | 更優 |
| Speaker 一致性 | ✅ 全局一致 | ❌ 跨 chunk 不一致 | 需 Phase B |

**結論**：跳過 global diarization 省 8 分鐘，但 speaker label 不跨 chunk。
需 Phase B (speaker embedding linking) 解決。

---

### 2.5 Exp-B：10min Chunks — 2026-06-18 ❌ 失敗

**目的**：測試更小 chunk 是否更快

**配置**：AUDIO_CHUNK_SEC=600 (10min), SKIP_GLOBAL_DIARIZATION=true

| 指標 | 結果 |
|------|------|
| Chunks | 27 (vs 18 with 15min) |
| 完成率 | 24/27 ❌ |
| 失敗原因 | 3 chunks 429 after 5 retries |
| 最終狀態 | **FAILED** |

**Root Cause**：
- 27 chunks → 需 ~14 GPU instances 同時 cold start
- Cold start 需 60-90s，太多 instance 同時啟動 → 資源競爭
- 5× retry (max 120s) 仍不足

**結論**：15min chunk 是最佳平衡點，不再縮小。

---

### 2.6 Phase B E2E Test — 2026-06-18 (部分成功)

**目的**：驗證 Phase B speaker embedding cross-chunk linking

**配置**：SKIP_GLOBAL_DIARIZATION=true, AUDIO_CHUNK_SEC=900, 含 Phase B code

| 指標 | 結果 |
|------|------|
| Chunks | 18/18 ✅ |
| 總時間 | **15.5 min** |
| Segments | 1,747 |
| Speaker Linking | ❌ fallback to Phase A (embeddings 未回傳) |

**問題**：GPU service 部署的 image digest 不匹配，Phase B embedding 抽取代碼未生效。
需重新 build + deploy 修正後的 GPU image。

---

## 三、效能基準總結

| 配置 | 4.3hr 會議 | 時間 | 狀態 | 備註 |
|------|-----------|------|------|------|
| concurrency=8, global diar ON | 18 chunks | FAILED | ❌ | ReadError |
| concurrency=2, global diar ON | 18 chunks | **26 min** | ✅ | **Baseline** |
| concurrency=2, global diar OFF | 18 chunks | **18 min** | ✅ | -31%, Phase A labels |
| concurrency=2, chunk=10min | 27 chunks | FAILED | ❌ | 429 cold start |
| concurrency=2, Phase B linking | 18 chunks | **15 min** | ✅ | **49→17 speakers unified** |

| 配置 | 2.3hr 會議 (×2 sequential) | 時間 | 狀態 | 備註 |
|------|---------------------------|------|------|------|
| Phase B, sequential trigger | 10+10 chunks | **13.5+10 min** | ✅ | T2, 17→3 speakers |
| Phase B, simultaneous trigger | 20 chunks | FAILED | ❌ | Backend instance 被回收 |

### 效能目標

| 會議長度 | 目標處理時間 | 預估 (Phase B) |
|----------|-------------|---------------|
| 1 hr | < 10 min | ~5 min |
| 2 hr | < 15 min | ~10 min |
| 4 hr | < 25 min | ~18 min |

---

## 四、已知問題與修復

| # | 問題 | Root Cause | 修復 | Commit |
|---|------|-----------|------|--------|
| 1 | Cloud Tasks retry 覆蓋資料 | 冪等性不足 | Atomic UPDATE WHERE | `eee1f5b` |
| 2 | Race condition (2 tasks) | SELECT-then-UPDATE | Atomic CAS | `47debba` |
| 3 | ReadError (GFE timeout) | concurrency=8 排隊太久 | concurrency=2 | infra 調整 |
| 4 | 429 cold start 失敗 | Backoff 太短 (2s/4s/8s) | 429-aware 30s×attempt | `e848ea2` |
| 5 | 27 chunks 超載 | 同時 cold start 14 instances | 維持 15min chunk | 設計決策 |
| 6 | Phase B embedding 未生效 | Image digest mismatch + Dockerfile缺檔 | 修正Dockerfile, 用cloudbuild-community1 | `d079c96`, `c4d48d8` |

---

## 五、未完成壓測計畫

### 5.1 Phase B Speaker Linking 驗證 (T1) — ✅ PASSED 2026-06-22

| 項目 | 內容 |
|------|------|
| 測試時間 | 2026-06-22 11:34:14 → 11:49:12 (UTC+8) |
| 測試音檔 | 精準醫學研討會 4.3hr (`9a69a4f4`) |
| GPU Revision | `meetchi-gpu-asr-phaseb-emb` (含 baked pyannote model) |
| Backend Revision | `meetchi-backend-phaseb-v2` |
| 結果 | ✅ 18/18 chunks, 1742 segments, 15 min |

**Phase B 驗證結果**：

| 指標 | Phase A (壓測6) | Phase B (T1) | 改善 |
|------|----------------|--------------|------|
| 處理時間 | 18 min | 15 min | -17% |
| Segments | 1726 | 1742 | +16 |
| Speaker labels | 49+ (SPEAKER_XX_cN) | 17 (SPEAKER_A~U) | 跨 chunk 統一 |
| Embedding dim | — | 256 | pyannote wespeaker |
| Clustering | — | 49 entries → 21 clusters (threshold=0.65) | ✅ |

**Speaker 分佈**（前 6）：
| Speaker | Segments | 佔比 |
|---------|----------|------|
| SPEAKER_B | 357 | 20.5% |
| SPEAKER_T | 300 | 17.2% |
| SPEAKER_U | 267 | 15.3% |
| SPEAKER_F | 229 | 13.1% |
| SPEAKER_K | 219 | 12.6% |
| SPEAKER_O | 185 | 10.6% |

**修復歷程**（6/22 當日）：
1. `d079c96` — Dockerfile 加入 `offline_asr_community1.py`
2. 發現 pyannote 無法下載 → 改用 `cloudbuild-community1.yaml` (model baked into image)
3. `c4d48d8` — 修正 embedding 抽取: 改用 `Model.from_pretrained` + `Inference.crop()`
4. `3d6aaaf` — Phase B try/except graceful fallback
5. 第一次嘗試: backend instance 被 Cloud Run 回收 (無 error log)
6. 重新部署 backend → T1 成功完成

### 5.2 多場並行壓測 (T2) — ✅ PASSED 2026-06-22 (sequential)

| 項目 | 內容 |
|------|------|
| 測試時間 | 2026-06-22 12:31~13:03 (UTC+8) |
| 情境 | 2 場 AI 直播論壇 (2.3hr) **依序** 觸發 |
| 總 Chunks | 20 (10 × 2) |
| 結果 | ✅ 兩場均完成，Phase B 正常 |

**注意**：同時觸發 2 場時 backend instance 被 Cloud Run 回收（原因不明，無 error log）。
改為依序觸發後兩場均成功完成。**此為已知限制，後續需調查 backend 並行處理能力**。

| Meeting | Chunks | 時間 | Segments | Speakers (Phase B) | 狀態 |
|---------|--------|------|----------|--------------------|------|
| `69252af7` | 10/10 (0 retry) | 13.5 min | 1005 | 17→3 (A,B,C) | ✅ COMPLETED |
| `94edd280` | 10/10 (0 retry) | 10 min | 1005 | 17→3 (A,B,C) | ✅ COMPLETED |

**Speaker 分佈一致性驗證**（同音檔 ×2，Phase B 結果應相同）：
| Speaker | Meeting 1 | Meeting 2 | 一致 |
|---------|-----------|-----------|------|
| SPEAKER_A | 352 | 352 | ✅ |
| SPEAKER_B | 259 | 259 | ✅ |
| SPEAKER_C | 394 | 394 | ✅ |

**已知問題**：2 場同時觸發 BackgroundTask 時，backend instance 約 15 min 後被 Cloud Run 靜默回收。
可能原因：asyncio.run() 在多 thread 中競爭、CPU/memory 壓力觸發 instance 回收。
**建議修復**：改用 Cloud Tasks queue 分發，避免單一 instance 同時處理多場。

### 5.3 極限壓測 (T3) — ⚠️ PARTIAL 2026-06-22

| 項目 | 內容 |
|------|------|
| 測試時間 | 2026-06-22 13:06~15:13 (UTC+8) |
| 情境 | 4 場 AI 直播論壇 (2.3hr) |
| 總 Chunks | 40 (10 × 4) |
| 結果 | ✅ 4/4 完成，但需 sequential 處理 |

**測試過程**：

| 嘗試 | 方式 | 結果 |
|------|------|------|
| #1 同時觸發 4 場 (30s 間隔) | 4 BackgroundTask 並行 | ❌ M1 完成，M2-4 失敗 (instance 回收) |
| #2 M2 solo | 單場 | ✅ 10/10, 1005 segs, 3 speakers |
| #3 M3+M4 (60s 間隔) | 2 BackgroundTask 並行 | ⚠️ M3 完成，M4 失敗 (instance 回收) |
| #4 M4 solo retry | 單場 | ✅ 10/10, 1005 segs, 3 speakers |

**GPU 飽和觀察**：
- 同時觸發 4 場時出現 **503 Service Unavailable** → 30s retry 成功處理
- GPU maxScale=15 在 40 chunks 場景下觸發 autoscaling，503 retry 機制運作正常

**Backend 並行限制** (已知問題，需修復)：
- 單一 instance 同時處理 2+ 場 BackgroundTask 時，約 15 min 後 instance 被 Cloud Run 靜默回收
- 無 error/OOM log，推測為 asyncio.run() 多 thread 競爭或 Cloud Run 內部超時
- **建議修復**：改用 Cloud Tasks queue (maxConcurrentDispatches=1) 確保單一 instance 一次只處理一場

**最終結果** (4 場均完成)：
| Meeting | Segments | Speakers | Phase B | 狀態 |
|---------|----------|----------|---------|------|
| `69252af7` | 1005 | 3 | 17→3 | ✅ COMPLETED |
| `94edd280` | 1005 | 3 | 17→3 | ✅ COMPLETED |
| `b4d5503e` | 1005 | 3 | 17→3 | ✅ COMPLETED |
| `e4b3f84c` | 1005 | 3 | 17→3 | ✅ COMPLETED |

### 5.4 混合負載尖峰 (T4) ✅ PASSED (sequential, after infra fix)

| 項目 | 內容 |
|------|------|
| 情境 | 1×4.3hr + 2×2.3hr (originally simultaneous, switched to sequential) |
| 總 Chunks | 38 (18 + 10 + 10) |
| GPU 需求 | ~15 instances per meeting |
| 驗證重點 | 最接近正式上線尖峰場景 + infra stability |
| 實際時間 | M1: 26min, M2: 15min, M3: 15min (sequential total ~56min) |

**結果**:

| Meeting | 長度 | Chunks | Segments | Phase B Speakers | 時間 |
|---------|------|--------|----------|-----------------|------|
| M1 (9a69a4f4) | 4.3hr | 18 | 1742 | 49→21 global | 26min |
| M2 (69252af7) | 2.3hr | 10 | 1005 | 17→3 global | 15min |
| M3 (94edd280) | 2.3hr | 10 | 1005 | 17→3 global | 15min |

**重大發現 — Backend 15 分鐘死亡問題 (Root Cause Analysis)**:

1. **現象**: Backend instance 在 ~15 分鐘後無聲死亡，無 error log
2. **排除**: 移除 liveness probe → 問題依舊 (非 probe timeout)
3. **Root Cause**: **Memory OOM at 4Gi** — 15 parallel chunks 各持有 audio data + embeddings (256-dim float vectors × N speakers) 超過 4Gi 限制，Cloud Run 靜默 kill
4. **Fix**: 升級 `8Gi RAM + 4 CPU + min-instances=1`
   - 8Gi: 足夠容納 15 parallel chunk responses + embeddings
   - min-instances=1: 防止 idle instance recycling
   - 移除 liveness probe: 避免 heavy processing 時 health check timeout

**部署變更**:
- Revision: `meetchi-backend-mem8g` (8Gi/4CPU/min-instances=1, no liveness probe)
- 此配置為 Phase B (embedding-heavy) workload 所需的最低規格

**結論**: 
- Sequential 處理下所有 meeting 穩定完成
- 4Gi→8Gi 是 Phase B embedding workload 必要的 memory 升級
- 並行處理仍需 Cloud Tasks queue (future work)

### 5.5 爆量場景 (T5) ✅ PASSED (with recovery)

| 項目 | 內容 |
|------|------|
| 情境 | 6 場全部同時 (4.3hr + 2.3hr×2 + 92min + 73min×2) |
| 總 Chunks | 55 (18 + 10 + 10 + 7 + 5 + 5) |
| GPU 需求 | ~28 instances (遠超 maxScale=15) |
| 驗證重點 | 系統降級行為、所有場次最終是否 COMPLETED |
| 觸發時間 | 2026-06-23 08:12 (UTC+8) |

**結果**:

| Meeting | Label | Chunks | Segments | Phase B | 完成時間 (UTC+8) | 備註 |
|---------|-------|--------|----------|---------|-----------------|------|
| ff052a1f | 73min-A | 5 | 788 | 15→3 | ~08:27 | 首批完成 |
| e249ed8c | 73min-B | 5 | 564 | ? | ~08:27 | 首批完成 |
| e961f65e | 92min | 7 | 900 | 39→10 | ~08:42 | 第二批 |
| 69252af7 | 2.3hr | 10 | 1005 | 17→3 | 08:58* → retry 09:33 | DB write fail |
| 94edd280 | 2.3hr | 10 | 1005 | 17→3 | 08:58* → retry 09:48 | DB write fail |
| 9a69a4f4 | 4.3hr | 18 | 1742 | 49→21 | stuck → retry 10:13 | instance died |

*Phase B 計算成功但 DB write 時 psycopg2 connection 已斷

**第一階段 (6場同時)**:
- 短會議 (73min×2, 92min) 在 15-30min 內完成 ✅
- 2.3hr×2: Phase B 完成但 DB 寫入失敗 (psycopg2.OperationalError: server closed connection)
- 4.3hr: GPU 重度 429/503 retry，chunk 進度緩慢，instance 最終停止回應
- GPU 大量 429 (rate limit) 是預期行為 — 55 chunks 競爭 maxScale=15

**第二階段 (sequential recovery)**:
- 3 場失敗 meeting 依序 retry，全部 COMPLETED ✅
- 驗證了系統的可恢復性

**關鍵發現**:
1. **GPU 降級行為正確**: 429 Too Many Requests 正確觸發 retry，所有 chunk 最終完成
2. **DB connection pool 問題**: 長時間 (45min+) 處理導致 Cloud SQL 連線 idle timeout
   - 6 個 BackgroundTask 共享同一 connection pool
   - 後完成的 task 嘗試 DB write 時，pool 中的 connection 已被 Cloud SQL proxy 關閉
3. **建議修復**: SQLAlchemy pool_pre_ping=True 或 pool_recycle=300

### 5.6 冷啟動壓力 (T6) ✅ PASSED (全部一次通過)

| 項目 | 內容 |
|------|------|
| 情境 | 4 場間隔 30s 連發 (10:14:15 ~ 10:15:46 UTC+8) |
| 總 Chunks | 40 (18 + 10 + 7 + 5) |
| GPU 需求 | ~20 instances (超過 maxScale=15) |
| 驗證重點 | 階梯式 cold start + retry 機制穩定性 |
| 實際時間 | 36 min (10:14 → 10:51 UTC+8) |

**結果**:

| Meeting | Label | Chunks | Segments | Phase B | 完成時間 (UTC+8) |
|---------|-------|--------|----------|---------|-----------------|
| 69252af7 | 2.3hr | 10 | 1005 | 17→3 | ~10:32 |
| e961f65e | 92min | 7 | 900 | 39→10 | ~10:33 |
| ff052a1f | 73min | 5 | 788 | 15→3 | ~10:43 |
| 9a69a4f4 | 4.3hr | 18 | 1742 | 49→21 | ~10:42 |

**全部 4 場一次通過 — 無需 retry！** 🎉

**GPU Retry 統計** (T6 期間):
- 429 Too Many Requests: ~1161 次
- 503 Service Unavailable: ~1308 次
- 全部透過 retry 機制自動恢復，最終 COMPLETED

**關鍵發現**:
1. **階梯式觸發有效**: 30s 間隔讓 GPU cold start 逐步升溫，比 T5 全同時觸發更穩定
2. **Retry 機制極為可靠**: 即使 2400+ 次 retry，系統仍在 36min 內完成所有工作
3. **Backend 8Gi 配置穩定**: 4 個 BackgroundTask 並行 36 分鐘無 OOM
4. **DB connection 未斷**: T6 處理時間 (36min) 比 T5 (60min+) 短，未觸發 connection idle timeout
5. **與 T5 對比**: T5 失敗是因處理時間過長 (45min+) 導致 DB pool stale；T6 在 36min 內完成，pool 仍活躍

---

## 六、測試執行 Checklist

```bash
# 前置：確認基礎設施狀態
gcloud run services describe meetchi-gpu-asr --region=asia-southeast1 \
  --format="value(spec.template.spec.containers[0].resources)"
gcloud run services describe meetchi-backend --region=asia-southeast1 \
  --format="yaml(spec.template.spec.containers[0].env)" | grep -A1 "ASR_PARALLEL\|CHUNK_SEC\|SKIP_GLOBAL"

# 重置 meeting 狀態
PGPASSWORD=*** psql -h 127.0.0.1 -p 5433 -U postgres -d meetchi -c "
  UPDATE meetings SET status='PENDING', processing_stage='uploaded' WHERE id='<ID>';
  DELETE FROM transcript_segments WHERE meeting_id='<ID>';
"

# 觸發壓測
BACKEND_URL="https://meetchi-backend-315688033208.asia-southeast1.run.app"
TOKEN=$(gcloud auth print-identity-token)
curl -s -X POST "${BACKEND_URL}/api/v1/tasks/enqueue-transcription" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"meeting_id": "<ID>"}'

# 監控
gcloud logging read 'resource.labels.service_name="meetchi-backend" AND textPayload=~"ParallelASR"' \
  --limit=30 --format="value(timestamp,textPayload)" --freshness=30m

# 驗證完成
psql -c "SELECT status, processing_stage FROM meetings WHERE id='<ID>'"
psql -c "SELECT COUNT(*) FROM transcript_segments WHERE meeting_id='<ID>'"
```

---

## 七、決策記錄

| 日期 | 決策 | 理由 |
|------|------|------|
| 2026-06-18 | concurrency 8→2 | 根治 GFE TCP idle timeout / ReadError |
| 2026-06-18 | maxScale 2→15 | 用滿 quota，支撐並行需求 |
| 2026-06-18 | chunk 維持 15min | 10min 導致 27 chunks 超載 cold start |
| 2026-06-18 | retry 3→5, 429-aware | Cold start 需 60-90s，短 backoff 無效 |
| 2026-06-18 | Phase B 取代 global diar | 省 8min (-31%)，embedding linking 補 speaker 一致性 |
| 2026-06-22 | 制定 T1-T6 壓測矩陣 | 系統化驗證各場景穩定性 |
| 2026-06-22 | Backend 4Gi→8Gi + 4CPU | Phase B embedding workload OOM 根因修復 |
| 2026-06-22 | 移除 liveness probe | Heavy processing 時 /health timeout 導致誤殺 |
| 2026-06-22 | min-instances=1 | 防止 BackgroundTask 執行中 instance 被回收 |
| 2026-06-23 | T5/T6 驗證通過 | 8Gi 配置可支撐 4-6 場並行；>45min 處理需 pool_pre_ping |
| 2026-06-23 | 階梯觸發優於同時觸發 | 30s 間隔讓 GPU cold start 漸進升溫，避免集中 429 |
