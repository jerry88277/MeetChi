# 會議處理進度顯示與通知方案

> 建立日期：2026-06-25  
> 狀態：已規劃，待實作  
> 目標：讓使用者直觀瞭解處理進度、預估等待時間，並在完成時主動通知

---

## 一、設計原則

| # | 原則 | 理由 |
|---|------|------|
| 1 | 給範圍，不給精確數字 | 人對「5-10分鐘」容忍度遠高於「7分鐘」但實際花9分鐘 |
| 2 | 分階段揭露 | Plan B 架構天然支持：逐字稿→摘要分離，感知等待減半 |
| 3 | 系統能算就算 | chunk 完成數、排隊深度都已在後端，零額外成本 |
| 4 | 無排隊時不增加認知負擔 | queue=0 時隱藏排隊資訊 |

---

## 二、等待時間組成（第一性原理）

```
總等待時間 = 上傳時間 + 排隊等待 + 轉錄處理 + 摘要生成
              (秒級)    (0~5min)   (主要)      (1~3min)
```

### MECE 拆解

| 維度 | 使用者可控? | 系統可預測? | 影響幅度 |
|------|:---------:|:---------:|---------|
| ① 音訊長度 | ✅ 已知 | ✅ 精確 | 主要決定因子 |
| ② 當前排隊深度 | ❌ | ✅ 即時可查 | 1~3x 乘數 |
| ③ GPU 冷啟動 | ❌ | ⚠️ 部分可測 | +1~2min |
| ④ 摘要複雜度 | ❌ | ⚠️ | 1~3min 固定 |

---

## 三、預估公式（後端計算）

```python
def estimate_wait(audio_duration_min: int, queue_depth: int) -> tuple[int, int]:
    """回傳 (min_minutes, max_minutes) 預估範圍"""
    
    # 基礎轉錄時間（含摘要）
    base_ratio_low = 0.10   # 最佳情況 (solo, warm GPU)
    base_ratio_high = 0.15  # 保守估計
    
    base_low = max(3, int(audio_duration_min * base_ratio_low))
    base_high = max(5, int(audio_duration_min * base_ratio_high))
    
    # 排隊附加時間
    # 每場排隊中的會議 ≈ 增加 3~5 分鐘（基於 stagger 30s + 共享 GPU）
    queue_low = queue_depth * 3
    queue_high = queue_depth * 5
    
    # 摘要固定成本
    summary_min, summary_max = 2, 3
    
    total_low = base_low + queue_low + summary_min
    total_high = base_high + queue_high + summary_max
    
    return (total_low, total_high)
```

### 預估對照表（使用者可見版本）

| 會議長度 | 沒人排隊 | 有 2~3 場排隊 | 有 5+ 場排隊 |
|---------|:-------:|:-----------:|:-----------:|
| 30分鐘以下 | 3~5 分鐘 | 8~15 分鐘 | 15~25 分鐘 |
| 30~90分鐘 | 5~12 分鐘 | 12~25 分鐘 | 20~35 分鐘 |
| 90~180分鐘 | 12~20 分鐘 | 20~35 分鐘 | 30~45 分鐘 |
| 180分鐘以上 | 20~30 分鐘 | 30~45 分鐘 | 40~60 分鐘 |

> 實測數據基礎：T9b 壓測 (2026-06-25)，0.08x~0.33x 壓縮比

---

## 四、前端 UI 方案

### 4.1 上傳後預估卡片

```
┌─────────────────────────────────────────────┐
│  📝 AI 2026 直播論壇 (2小時16分)             │
│                                             │
│  預估處理時間：15 ~ 25 分鐘                   │
│  ├─ 逐字稿：約 12 ~ 20 分鐘                  │
│  └─ 智慧摘要：逐字稿完成後 +2~3 分鐘          │
│                                             │
│  💡 逐字稿完成後會先通知您，不必等摘要完成      │
│                                             │
│  ⏳ 目前前方有 2 場會議排隊中 (+5~10 分鐘)     │
└─────────────────────────────────────────────┘
```

### 4.2 處理中進度條（階段式）

```
上傳完成 ✓ → [排隊中...] → 轉錄中 → 摘要生成 → 完成
              ↑ 你在這裡
              前方 2 場，預計 5~10 分鐘後開始
```

```
上傳完成 ✓ → 排隊完成 ✓ → [轉錄中 ██████░░░░ 62%] → 摘要生成 → 完成
                            已處理 11/18 段，約剩 8 分鐘
```

```
上傳完成 ✓ → 排隊完成 ✓ → 逐字稿完成 ✓ → [摘要生成中...] → 完成
                           📄 可先查看逐字稿              約 2~3 分鐘
```

### 4.3 完成通知

- **站內通知** (即時): WebSocket / polling 偵測狀態變更
- **Email 通知** (異步): 轉錄完成時寄信（見第六節）
- **逐字稿先行**: TRANSCRIBED 狀態即可查看，不需等摘要

---

## 五、後端 API 設計

### 5.1 進度查詢 Endpoint

```
GET /api/v1/meetings/{id}/progress

Response:
{
  "meeting_id": "69252af7-...",
  "stage": "transcribing",        // uploaded | queued | transcribing | summarizing | completed | failed
  "chunks_done": 11,
  "chunks_total": 18,
  "percent": 61,
  "queue_position": 0,            // 0 = 正在處理, >0 = 排隊中
  "estimated_remaining_sec": 480, // 預估剩餘秒數 (null if unknown)
  "transcript_ready": false,      // true → 可先查看逐字稿
  "started_at": "2026-06-25T10:13:23Z",
  "updated_at": "2026-06-25T10:20:45Z"
}
```

### 5.2 批量進度查詢（前端 dashboard）

```
POST /api/v1/meetings/progress/batch
Body: { "meeting_ids": ["id1", "id2", ...] }

Response: { "meetings": [ {...}, {...} ] }
```

### 5.3 資料來源

| 欄位 | 來源 |
|------|------|
| stage | `meetings.processing_stage` 欄位 |
| chunks_done/total | GPU semaphore stats 或 DB 新增欄位 |
| queue_position | `gpu_semaphore.get_stats()` → 推算 |
| estimated_remaining | `estimate_wait()` 公式 |
| transcript_ready | `meetings.status == 'TRANSCRIBED'` |

---

## 六、Email 通知方案

### 6.1 觸發時機

| 事件 | 通知內容 | 優先級 |
|------|---------|--------|
| 逐字稿完成 (TRANSCRIBED) | 「您的會議逐字稿已準備好」 | P0 (核心) |
| 摘要完成 (COMPLETED) | 「智慧摘要已生成完畢」 | P0 |
| 處理失敗 (FAILED) | 「處理遇到問題，我們正在重試」 | P1 |

### 6.2 技術方案

- **SMTP 寄信**：透過企業 SMTP 伺服器發送
- **寄件者**: `meetchi-noreply@<domain>` 或指定寄件人
- **收件者**: 會議上傳者的 email（從 user profile 取得）
- **範本**: HTML email，含會議標題、完成時間、直接連結

### 6.3 所需資訊（待確認）

見下方 SMTP 需求清單。

---

## 七、實作優先級

| 階段 | 功能 | 工作量 |
|------|------|--------|
| Phase 1 | Progress API + 前端進度條 | 2-3天 |
| Phase 2 | Email 通知 (SMTP) | 1-2天 |
| Phase 3 | 預估時間公式調參 | 0.5天 |
| Phase 4 | WebSocket 即時推播 | 3-5天 |

---

## 八、驗收標準

- [ ] 使用者上傳後 1s 內看到預估時間
- [ ] 進度條每 10s 更新一次
- [ ] 逐字稿完成立即可查看（不等摘要）
- [ ] Email 在狀態變更後 30s 內送達
- [ ] 預估時間實際誤差 < ±30%
