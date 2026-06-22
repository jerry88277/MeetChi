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

### 5.2 多場並行壓測 (T2)

| 項目 | 內容 |
|------|------|
| 情境 | 2 場 AI 直播論壇 (2.3hr) 同時觸發 |
| 總 Chunks | 20 (10 × 2) |
| GPU 需求 | ~10 instances |
| 驗證重點 | 多場互不干擾、無 race condition |
| 預期時間 | ~12 min (單場 2.3hr ≈ 10 chunks × 4min/chunk ÷ 5 parallel) |

### 5.3 極限壓測 (T3)

| 項目 | 內容 |
|------|------|
| 情境 | 4 場 AI 直播論壇 (2.3hr) 同時觸發 |
| 總 Chunks | 40 (10 × 4) |
| GPU 需求 | ~20 instances (超過 maxScale=15) |
| 驗證重點 | maxScale=15 飽和行為、429 retry 最終全成功 |
| 預期時間 | ~25 min (queue + retry overhead) |

### 5.4 混合負載尖峰 (T4)

| 項目 | 內容 |
|------|------|
| 情境 | 1×4.3hr + 2×2.3hr 同時觸發 |
| 總 Chunks | 38 (18 + 10 + 10) |
| GPU 需求 | ~19 instances |
| 驗證重點 | 最接近正式上線尖峰場景 |
| 預期時間 | ~30 min |

### 5.5 爆量場景 (T5)

| 項目 | 內容 |
|------|------|
| 情境 | 6 場全部同時 (4.3hr + 2.3hr×2 + 92min + 73min×2) |
| 總 Chunks | 55 (18 + 10 + 10 + 7 + 5 + 5) |
| GPU 需求 | ~28 instances (遠超 maxScale=15) |
| 驗證重點 | 系統降級行為、所有場次最終是否 COMPLETED |
| 預期時間 | ~45-60 min (大量 retry) |

### 5.6 冷啟動壓力 (T6)

| 項目 | 內容 |
|------|------|
| 情境 | 4 場間隔 30s 連發 |
| 總 Chunks | 40 |
| 驗證重點 | 階梯式 cold start + retry 機制穩定性 |
| 預期時間 | ~25-30 min |

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
