# MeetChi Known Issues & Remediation Plan

## Issue #1: GPU ASR ReadError on Long-Running Parallel Chunks

**Severity**: High  
**Status**: ✅ RESOLVED — concurrency=2 + maxScale=15 + 3-retry (壓測6 驗證通過)  
**Discovered**: 2026-06-18 壓測5（4.4hr 長影片壓力測試）  
**Resolved**: 2026-06-18 壓測6 — 18/18 chunks 完成，26 分鐘處理 4.4hr 會議  
**Affected Component**: `apps/backend/app/tasks.py` → `_process_split_audio_sync()`

---

### 現象

當 18 chunks 同時送往 GPU ASR（parallelism=14），部分 chunks 處理完成後 backend 收到 `ReadError`（空錯誤），導致：
- `asyncio.gather` 中對應的 future 失敗
- Retry (attempt=2) 重新發送，但部分 retry 也 hang
- 最終 11/18 chunks 成功，7/18 stuck 直到 httpx 3600s timeout

### 時間軸（壓測5 實際觀測）

```
09:30:43  18 chunks 分割完成，14 chunks 同時送出
09:35:00  前 6 chunks 完成（attempt=1，~5min/chunk）
09:35:13  chunk 8 收到 429 Too Many Requests → retry attempt=2
09:40:27  chunks 6,11,14,16,17 全部 ReadError → retry
09:43:36  chunk 16 retry 成功（唯一一個 retry 成功）
09:49:27  GPU 完成 chunk_013，但 backend 已無法接收回應
09:55+    Backend asyncio.gather hanging，無新 log
```

### Root Cause 分析

```
┌─────────────────────────────────────────────────────────────┐
│                    Cloud Run GFE (Google Frontend)            │
│                                                              │
│  TCP idle timeout = ~15 min                                  │
│  HTTP/2 stream timeout = variable                            │
│                                                              │
│  當 GPU instance 內部排隊等待 >15min 時：                      │
│  GFE 斷開 TCP 連線 → backend 收到 ReadError (空)              │
└─────────────────────────────────────────────────────────────┘

Timeline:
1. Backend 送 14 chunks → GPU (concurrency=8, maxScale=8)
2. GPU instance 1 收 8 requests，instance 2 收 6 requests
3. Instance 內部串行處理（每個 ~7-10min）
4. 排在第 2-3 位的 request 等待 14-21min
5. 超過 GFE idle timeout → 連線被斷
6. GPU 處理完回傳時，TCP 已不存在
7. Backend 的 httpx client 收到 ReadError
```

### 關鍵數據

| 參數 | 值 | 問題 |
|------|------|------|
| GPU concurrency | 8 | 太高 — 8個 request 在同一 instance 排隊 |
| ASR_PARALLELISM | 14 | 一次送太多 → queue 堆積 |
| GFE TCP idle timeout | ~15min (不可配置) | Cloud Run 平台限制 |
| 每 chunk GPU 處理時間 | 7-10min | 排第 2 位要等 14-20min |
| httpx timeout | 3600s | 不是問題 — 但 GFE 先斷了 |

### 為什麼 429 也會出現

- 14 requests 同時到達，超過 GPU maxScale 的瞬間承受力
- Autoscaler 需要 1-2 分鐘擴容新 instance
- 第一波被拒絕的 request 收到 429

---

### 修復方案

#### 方案 A：降低 GPU concurrency（推薦）

```
GPU concurrency: 8 → 2
```

**效果**：
- 14 requests 需要 7 instances（14÷2=7）
- 每 instance 最多排 2 個，最大等待 = 1 chunk = 10min
- 在 GFE 15min timeout 安全範圍內
- maxScale=8 足以支撐

**風險**：
- 需要更多 instances（成本微增，但 GPU quota=15 足夠）
- Cold start 時間增加（新 instance 啟動 ~90s）

#### 方案 B：增加 retry 次數 + exponential backoff

```python
# 現行：1 次 retry，固定 2s 延遲
async def call_gpu_with_retry(sem, chunk_url, offset, idx):
    for attempt in range(1, 4):  # 3 次嘗試
        try:
            return await call_gpu_once(chunk_url, offset, idx, attempt)
        except Exception as e:
            if attempt == 3:
                raise
            delay = 2 ** attempt  # 2s, 4s, 8s
            await asyncio.sleep(delay)
```

**效果**：
- ReadError 後有更多機會成功
- 但如果根因是 GFE timeout，retry 可能也會超時

#### 方案 C：分批發送（推薦搭配 A）

```python
# 不一次送 14 個，分 2-3 批
# 第一批 6 chunks → 等第一批完成一半 → 送第二批
ASR_PARALLELISM: 14 → 6
```

**效果**：
- 減少瞬間 request 數 → 減少 429
- 每批完成後才送下一批 → 避免 queue 堆積
- GPU autoscaler 有時間 scale up

#### 推薦組合

| 變更 | 值 | 理由 |
|------|------|------|
| GPU concurrency | 8 → **2** | 強制更多 instance，避免長排隊 |
| ASR_PARALLELISM | 14 → **8** | 降低瞬間 burst |
| Retry 次數 | 1 → **3** | ReadError 是暫時性 |
| Retry backoff | 2s → **2/8/30s** | exponential |

---

### 驗證計畫

修復後重新執行壓測5（同一影片）：
1. 確認 18/18 chunks 全部完成
2. 確認無 429 或 ReadError
3. 記錄總處理時間（預期 ~25-30min for 4.4hr）
4. 確認 segments 正確寫入 DB

### 暫時 Workaround

對於目前已部署的版本，如果遇到長影片處理失敗：
1. 等待 meeting 自動進入 FAILED 狀態
2. 從前端點「重新處理」重新觸發
3. 由於 idempotency guard，重新觸發是安全的

---

## Issue #2: Cloud Tasks Zombie Tasks

**Severity**: Medium  
**Status**: Mitigated — atomic idempotency prevents damage  
**Discovered**: 2026-06-18 壓測2

### 現象

Cloud Tasks 對 HTTP 504/503 的 task 會自動 retry，即使 backend 已在處理中。過去這會造成重複處理和資料覆蓋。

### 修復狀態

- ✅ Atomic idempotency guard（commit `47debba`）阻止重複 dispatch 生效
- ✅ 即使有 zombie tasks retry，第二次 dispatch 會被 skip
- ⚠️ Zombie tasks 仍佔用 `maxConcurrentDispatches` slots（降低吞吐量）

### 後續改進

- 設定 Cloud Tasks `maxRetryAttempts: 2`（目前使用 default 10+）
- 考慮 task deadline 設定（30min timeout）

---

## Issue #3: gcloud --set-env-vars 破壞性覆蓋

**Severity**: Critical (操作性)  
**Status**: Documented — 永遠不再使用  
**Discovered**: 2026-06-18

### 現象

`gcloud run services update --set-env-vars` 會 **替換** 所有環境變數，而非新增。

### 規則

```
❌ NEVER: gcloud run services update --set-env-vars KEY=VAL
✅ ALWAYS: gcloud run services update --update-env-vars KEY=VAL
```

已記錄於 `agents.md` 安全規則 §3。
