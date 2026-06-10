# MeetChi UI/UX 第二次全面審查報告

> **審查日期**：2026-06-10  
> **距上次審查**：2 天（首次審查 2026-06-08）  
> **審查方法**：Design-Advisor + Taste-Skill + 第一性原理 + MECE 盤點  
> **審查範圍**：全系統端到端（登入 → Dashboard → 上傳 → 轉錄 → 摘要 → RAG → 管理後台）  
> **版本**：Frontend rev 00049 / Backend rev 00030 / GPU-ASR rev 00017  

---

## 審查哲學

### 第一性原理（First Principles）

MeetChi 的本質是什麼？回到最基本：

> **使用者花 30 秒上傳一段會議錄音，系統花 15 分鐘處理，使用者在未來任何時刻能在 5 秒內找到任何過去會議的任何結論。**

因此，所有 UI/UX 決策應服務於三個核心真理：
1. **上傳的摩擦力必須趨近於零** — 任何多餘的選項、確認、選擇都是阻力
2. **等待期間使用者不該需要「盯著系統看」** — 離開再回來，狀態必須清晰
3. **搜尋/問答的答中率決定產品信任** — 找不到 = 系統沒用

### MECE 盤點框架

將 UX 拆分為 6 個互斥且完整的維度：

| # | 維度 | 定義 |
|---|------|------|
| A | 資訊架構 (IA) | 導航、頁面層級、使用者如何找到功能 |
| B | 核心任務流 (Task Flow) | 上傳、等待、閱讀、提問、管理 的端到端順暢度 |
| C | 視覺設計 (Visual) | 排版、色彩、空間、動態、品牌感 |
| D | 互動品質 (Interaction) | 回饋、過渡、錯誤恢復、loading 狀態 |
| E | 可及性與信任 (A11y & Trust) | 鍵盤、螢幕閱讀器、安全感知、權限 |
| F | 後端 API-UX 適配 (API↔UI) | API 回應是否充分支撐前端 UX 需求 |

---

## 首次審查改善追蹤

| 首次問題 | 狀態 | 備註 |
|---------|------|------|
| C1 防重複上傳 | ⚠️ 部分改善 | 上傳佇列機制已加，但 RecordingView 路徑仍缺 guard |
| C2 上傳失敗無恢復 | ⚠️ 部分改善 | UploadTray 有重試，但 error detail 不足 |
| P0 登入頁 UAT 混淆 | ❌ 未修 | UAT_ENABLED 仍為常開 |
| P0 新增會議超載下拉 | ✅ 已改善 | 拆為「即時錄音」+「上傳音檔」兩明確按鈕 |
| P0 鍵盤焦點 | ❌ 未修 | focus-visible 全域仍被壓制 |
| P1 搜尋 placeholder 超出能力 | ❌ 未修 | 仍寫「搜尋標題、關鍵字或參與者」 |
| P1 Empty state 太弱 | ❌ 未修 | 無 CTA 引導 |
| P1 RAG 入口重複 | ❌ 未修 | 側欄 + FAB 雙重入口 |
| P1 Card 視覺噪音（多色 chip） | ❌ 未修 | 5-6 種色相同時出現 |
| transition-all 性能 | ❌ 未修 | 多處仍用 transition-all |

**結論**：首次審查 34 項建議中，僅 3 項已實施或部分改善。本次審查將整合未完成項目，重新排序並深化分析。

---

## A. 資訊架構 (Information Architecture)

### A1. 導航模型碎片化 ⬛ P0

**現況分析**：

系統存在 4 種平行導航概念，相互競爭使用者注意力：

```
┌─ 側欄 tab（所有會議 / ChiMemo / 模板 / 設定 / 維運）
├─ URL path routing（/dashboard, /dashboard/meetings/[id]）
├─ 內部 view state（detail, recording, rag-workspace）
└─ 浮動入口（FAB → RagDrawer, 右鍵 → ContextMenu）
```

**問題**：
- 側欄已有 ChiMemo 入口，右下 FAB 再加一個，認知負載重複
- Detail page 同時可被「card click」和「URL 直連」觸發，但兩路徑的 state 管理不同步
- 管理頁面（系統維運）和使用者頁面（所有會議）在同一層級，但用途完全不同

**第一性原理推導**：
- 使用者 80% 的時間在做兩件事：(1) 看已完成的會議 (2) 問問題
- 導航應反映這兩個主任務，其他都是配角

**建議**：
```
工作區（主）
  ├─ 我的會議（含搜尋/篩選）
  └─ ChiMemo（唯一入口，移除 FAB）

系統（次）
  ├─ 模板管理
  ├─ 設定
  └─ 系統維運（僅 admin 可見）
```

### A2. 頁面層級平坦，缺乏 Hub-and-Spoke ⬛ P1

**現況**：Dashboard / Detail / RAG / Settings / Admin 全是同一層，切換時整個 content area 替換。

**問題**：使用者在 RAG 問答時想回去看某會議詳情，但切換後 RAG context 消失。

**建議**：
- RAG 使用 side-panel/drawer 模式（已有 RagDrawer），但應成為**唯一入口**，不再有獨立 workspace 頁
- Detail 頁應保留 breadcrumb「我的會議 > AI 2026 直播論壇」讓使用者定位

### A3. Admin 與使用者功能交織 ⬛ P2

**現況**：`OpsAdminPanel` 透過 sidebar 的「系統維運」進入，但 super_admin 的「完整內容」功能和一般 admin 的「維運監控」混在同一介面。

**建議**：
- Admin 視圖分為 2 個 tab：「系統監控」（所有 admin）+「內容管理」（僅 super_admin）
- 考慮獨立 `/admin` 路由而非塞在 dashboard 內

---

## B. 核心任務流 (Task Flow)

### B1. 上傳流程仍有不必要的前置決策 ⬛ P0

**現況**（`DashboardView.tsx:127-239`）：

使用者點「上傳音檔」前/後需要面對：
- 選擇檔案（必要）
- 設定會議名稱（可延後）
- 選擇摘要模板（可延後）
- 機密標記開關（可延後）
- 背景提示輸入（可延後）

**第一性原理**：上傳的唯一必要動作是「選檔案」。其他都可以在轉錄完成後設定。

**建議「0-friction」流程**：
```
Step 1: 選檔案（drag-drop 或 click）→ 立即開始上傳
Step 2: 自動用檔名作為會議名稱（使用者可稍後改）
Step 3: 上傳/轉錄期間，在 Upload Tray 提供「編輯詳情」展開面板
         → 可設名稱、模板、機密、背景提示
Step 4: 若不編輯，使用預設值完成整個流程
```

### B2. 等待期狀態感知不足 ⬛ P0

**現況**：
- 上傳佇列有 `UploadTray` 顯示進度
- 但從 "上傳完成" → "轉錄中" → "摘要生成中" 的中間狀態，使用者在 dashboard 看到的只是 `MeetingCard` 的 `PROCESSING` badge

**問題**：
- 無法知道轉錄進度（0%? 50%? 90%?）
- 無法知道排在第幾個
- 轉錄完成到摘要生成之間沒有過渡提示
- 使用者「再次進入系統」時，看到 PROCESSING 不知道已等了多久

**建議**：
```
MeetingCard 處理中狀態應顯示：
┌──────────────────────────────────────┐
│ 📝 AI 2026 直播論壇                    │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄│
│ 🔄 轉錄中 (3/10 chunks)  ~5 分鐘      │
│ ████████░░░░░░░░ 30%                   │
│ 開始時間：14:32                         │
└──────────────────────────────────────┘
```

**API 需求**：需後端提供 `/api/v1/meetings/{id}/progress` 端點，回傳 chunk 進度。

### B3. 會議搜尋/篩選實際能力與 UI 承諾不符 ⬛ P1

**現況**：
- Placeholder：「搜尋會議標題、關鍵字或參與者」
- 實際：只搜 `title` 的 ILIKE
- 日期篩選：已有 `date_from`/`date_to` UI，但需手動按「套用」

**問題**：使用者搜「張經理」找不到任何結果（因為只搜 title）→ 信任斷裂

**建議**：
1. **短期**：Placeholder 改為「搜尋會議名稱」（誠實溝通能力邊界）
2. **中期**：擴展搜尋至 `summary_json` 全文 + `participants`
3. **長期**：全文檢索索引（pg_trgm 或 dedicated search）

### B4. RAG 答中率低導致信任崩潰 ⬛ P0

**現況**（引用使用者測試結果）：
- 使用者問「鴻才會議討論什麼」→ 得到「無法回答」
- 但系統中確實有「鴻才討論」這個會議
- 相似度分數：最高 59%，「鴻才討論」只得到 48%

**根因分析**：
1. Vector search 將「鴻才會議討論什麼」與每個 **transcript segment** 比對，而非 meeting title
2. 當使用者用會議名稱提問時，segment-level embedding 語義距離大
3. `title-match injection` 邏輯已存在（`rag.py:697-885`），但 threshold 太嚴

**建議（按優先順序）**：
1. **Title fuzzy match 前置**：當 query 與任何 meeting title 的 Levenshtein 距離 < 3，直接注入該會議全部 top-K segments
2. **降低 confidence threshold**：目前 >0.6 才算 match，對中文短文本偏嚴；調至 0.45
3. **Hybrid retrieval**：BM25 keyword + vector，加權融合 (RRF)
4. **UI 層**：即使 confidence=no_answer，若有相關會議，應直接鏈接到該會議詳情頁供使用者自行查閱

### B5. 逐字稿點擊無法跳轉對應時間軸 ⬛ P1

**現況**：
- DetailView 底部有逐字稿段落
- 每段有時間標記
- 但點擊段落不會讓 audio player 跳到對應時間

**問題**：使用者看到有趣段落想聽原音，必須手動拖曳播放器

**建議**：
- 逐字稿每段加 `onClick={() => audioRef.current.seek(startTime)}`
- 確保時間對齊考慮前處理偏移（若有 VAD trimming，需加回 offset）

### B6. 會議名稱修改入口已加但缺乏即時回饋 ⬛ P2

**現況**：
- 右鍵 context menu 有「重新命名」
- Detail 頁標題旁有鉛筆 icon
- 但修改後 toast 過於簡短，且 card 列表不會立即更新

**建議**：
- 成功後 optimistic update card title（不等 refetch）
- Toast 改為「已儲存」而非「修改成功！」（taste-skill：去掉驚嘆號）

---

## C. 視覺設計 (Visual Design)

### C1. 標題層級壓縮仍未修正 ⬛ P1

**現況**（延續首次審查 T1）：
- Dashboard h1 = `text-2xl font-bold`（24px）
- Card title = `font-bold`
- 兩者視覺差距不足

**taste-skill 建議**：
```css
/* 全域標題系統 */
.page-title { @apply text-3xl font-bold tracking-tight; }     /* 30px */
.section-title { @apply text-xl font-semibold; }               /* 20px */
.card-title { @apply text-base font-semibold; }                /* 16px */
.label { @apply text-sm font-medium text-muted-foreground; }   /* 14px */
```

### C2. MeetingCard 視覺密度過高 ⬛ P1

**現況**（`MeetingCard.tsx:150-279`）：
- 狀態色邊 + 標題 + 日期 + 時長 + TL;DR + 模板 chip + 計數 chips + 機密 badge
- 一張卡片最多 8 種視覺元素同時出現

**taste-skill「One accent per surface」原則**：

**建議**：
```
Level 1 (必見)：標題 + 狀態色邊
Level 2 (掃描)：日期 + 時長（合併為一行灰色 meta）
Level 3 (進入)：TL;DR 2 行預覽（hover 展開或始終顯示前 2 行）
Level 4 (隱藏)：模板/計數/機密 → 收到 hover 才顯示，或用 micro-badge
```

### C3. 背景色溫不一致 ⬛ P1

**現況**：
- `globals.css`：`--color-surface: #FAFAF8`（微暖），`--color-background: #ffffff`（冷白）
- 主頁面用 `background`（冷白），Login 用 `surface`（微暖）

**建議**：
- 統一 `--color-background: #FAFAF8`
- Card 保留 `#ffffff`，形成卡片浮起的層次感

### C4. Shadow 缺乏品牌色相 ⬛ P2

**現況**：`hover:shadow-lg` = 純黑 rgba(0,0,0,0.1)

**建議**：
```css
--shadow-card: 0 4px 24px -4px rgba(0, 59, 122, 0.08);  /* 品牌藍色調 shadow */
--shadow-card-hover: 0 8px 32px -4px rgba(0, 59, 122, 0.14);
```

### C5. 動態品質缺乏「呼吸感」 ⬛ P2

**現況**：
- 無卡片列表進場動畫
- 無頁面切換過渡
- Loading 時直接替換內容

**建議（成本極低）**：
```tsx
// 卡片 stagger 進場
<div style={{ animationDelay: `${index * 50}ms` }}
     className="animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
```

### C6. Admin Panel 過於資料工具化 ⬛ P2

**現況**：OpsAdminPanel 3 個 tab 全是表格，無視覺化圖表。

**建議**：
- Overview tab 加 sparkline 趨勢圖（每日上傳/轉錄量）
- 用 color-coded status badges 替代純文字
- 加 summary cards：今日上傳數、平均等待時間、GPU 使用率

---

## D. 互動品質 (Interaction Quality)

### D1. 錯誤恢復機制薄弱 ⬛ P0

**全系統錯誤處理盤點**：

| 場景 | 目前行為 | 應有行為 |
|------|---------|---------|
| 上傳失敗 | UploadTray 顯示紅色文字 | 就地重試按鈕 + 失敗原因（網路/格式/大小） |
| 轉錄失敗 | Card 變紅 + badge「失敗」 | Card 內提供「重新轉錄」按鈕 + 失敗原因 |
| RAG 回答失敗 | 顯示 generic 文案 | 提供「重新提問」按鈕 + 具體錯誤類型 |
| API 503 (Gemini 不可用) | console.error | 用戶可見的「AI 暫時忙碌」inline 提示 + auto retry |
| 歷史載入失敗 | 靜默失敗 | dropdown 內顯示 error + retry |
| WebSocket 斷線 | 無明確恢復 | 提示「連線中斷」+ auto-reconnect indicator |

### D2. Loading 狀態不統一 ⬛ P1

**現況**：
- Dashboard：使用 `Loader2` spinner
- Detail：使用完整 loading overlay
- RAG：使用 pulsing dots
- Admin：使用 console 靜默
- Settings：使用 skeleton

**建議統一規範**：
```
短等待 (<2s)：skeleton shimmer（不打斷閱讀流）
中等待 (2-10s)：inline progress indicator + 文字
長等待 (>10s)：step-by-step progress bar + 預估時間
```

### D3. Native `window.confirm` 仍存在 ⬛ P1

**位置**：`dashboard/page.tsx:364-389`（批次上傳大檔案確認）

**問題**：打斷品牌體驗，像工程 debug 訊息

**建議**：統一使用已有的 `confirm-dialog.tsx` 元件

### D4. RAG 建議問題 chip 只填入不送出 ⬛ P2

**現況**：點擊建議問題 chip 只 setInput，使用者還需手動按 Enter

**建議**：改為 `setInput(q); setTimeout(() => handleSend(), 100);`

### D5. Tooltip/Hover 資訊未善用 ⬛ P2

**現況**：大量 icon-only 按鈕無 tooltip（Detail 頁 header 的 regenerate、export、report、delete）

**建議**：所有 icon-only 按鈕加 `title` 或自定義 tooltip

---

## E. 可及性與信任 (Accessibility & Trust)

### E1. 全域 focus outline 被壓制 ⬛ P0

**位置**：`globals.css:231-237`

**問題**：鍵盤使用者完全無法感知 focus 位置，違反 WCAG 2.4.7

**建議**：
```css
/* 移除現有的 focus 壓制 */
/* 改為 */
:focus-visible {
  outline: 2px solid var(--color-brand-cta);
  outline-offset: 2px;
}
```

### E2. MeetingCard 非語意化互動元素 ⬛ P0

**現況**：Card 是 `<div onClick>` 而非 `<button>` 或 `<a>`

**問題**：
- 螢幕閱讀器不會宣告為可互動
- Tab 鍵無法到達
- Enter/Space 無法觸發

**建議**：改為 `<button>` 或包裝在 `<a href="/dashboard/meetings/${id}">`

### E3. SecurityWrapper 過度限制 ⬛ P1

**現況**（`SecurityWrapper.tsx:12-32`）：
- 禁止右鍵
- 禁止選取文字
- 禁止複製
- 禁止列印

**問題**：
- 企業使用者需要複製摘要到其他文件（週報、email）
- 右鍵禁用與「會議名稱右鍵重新命名」功能衝突
- 對 accessibility 工具產生干擾

**建議**：
- 移除「全域禁止選取/複製」
- 僅在「機密會議」詳情頁限制匯出和列印
- 使用 watermark 而非禁止操作

### E4. TourOverlay 缺乏鍵盤導航 ⬛ P2

**現況**：首次使用導覽需要點擊才能前進，無 Esc 退出

**建議**：加入 Esc 退出 + Enter 下一步 + focus trap

### E5. 登入頁 UAT/正式入口混淆 ⬛ P1

**現況**：UAT_ENABLED = true 常開，測試帳號與正式 SSO 並列

**影響**：企業員工第一次使用會困惑「我該用哪個」

**建議**：
- Production 環境 UAT_ENABLED = false
- 或將 UAT 入口移至 `/login?mode=uat` 隱藏路由

---

## F. 後端 API-UX 適配 (API ↔ UI Gap Analysis)

### F1. 列表 API 缺乏分頁 metadata ⬛ P1

**現況**：所有 list 端點回傳純 Array，無 `total`、`has_more`、`next_cursor`

**影響**：
- 前端無法顯示「第 1-20 筆，共 156 筆」
- 無法實作 infinite scroll 或 page indicator
- Admin 表格無法顯示總數

**建議**：
```json
{
  "items": [...],
  "total": 156,
  "skip": 0,
  "limit": 20,
  "has_more": true
}
```

### F2. 無即時轉錄進度 API ⬛ P0

**現況**：前端只能 polling `Meeting.status`（PENDING/PROCESSING/COMPLETED/FAILED）

**影響**：使用者在等待期間無法知道進度

**建議方案**：
- **短期**：`GET /api/v1/meetings/{id}/progress` 回傳 `{stage, chunks_done, chunks_total, elapsed_seconds, estimated_remaining}`
- **中期**：WebSocket push progress events
- **長期**：SSE (Server-Sent Events) 與 Cloud Tasks callback 整合

### F3. 錯誤訊息不夠結構化 ⬛ P1

**現況**：HTTPException detail 是純字串，如 `"Meeting not found"`

**建議**：
```json
{
  "error": {
    "code": "MEETING_NOT_FOUND",
    "message": "找不到指定的會議",
    "details": {"meeting_id": "abc-123"},
    "retry_allowed": false
  }
}
```

### F4. RAG 回應缺乏「實際引用」標記 ⬛ P1

**現況**：回傳 `citations` 列表是「搜尋到的段落」，但 LLM 回答實際用了哪些段落無法得知

**影響**：前端 highlight 所有 citations，但部分其實未被 LLM 使用，造成雜訊

**建議**：在 response 增加 `used_citation_indices: [0, 2, 4]`

### F5. 缺乏「首頁聚合」API ⬛ P2

**現況**：Dashboard 需要打 3+ 個 API 才能組合出完整首頁

**建議**：
```
GET /api/v1/dashboard
→ {
    recent_meetings: [...top5],
    processing_count: 2,
    failed_count: 0,
    rag_segments_total: 1234,
    last_upload_at: "...",
    suggested_actions: ["有 1 場會議轉錄失敗，點擊查看"]
  }
```

---

## 綜合評分（Taste-Skill 維度）

| 維度 | 首次評分 | 本次評分 | 變化 | 說明 |
|------|---------|---------|------|------|
| First Impression | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | → | Login UAT 問題未修，但 dashboard 結構清晰 |
| Core Task Flow | ⭐⭐⭐½ | ⭐⭐⭐½ | → | 上傳佇列改善，但等待 UX 仍薄弱 |
| Error Recovery | ⭐⭐½ | ⭐⭐½ | → | 未有改善 |
| Delight / Polish | ⭐⭐⭐ | ⭐⭐⭐ | → | 缺動畫/微互動，但功能穩定 |
| Enterprise Trust | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | → | Admin 系統已上線，SecurityWrapper 仍偏激 |
| Mobile | ⭐⭐½ | ⭐⭐½ | → | Admin 表格不友善，detail header 擁擠 |
| **RAG 信任度** | ⭐⭐⭐ | ⭐⭐½ | ↓ | 使用者實測答中率不足，title match 邏輯待強化 |
| **整體** | **3.3★** | **3.2★** | ↓0.1 | RAG 信任度下降拉低整體，功能面持平 |

---

## 優先改善路線圖 V2

### 🔴 Phase 0: Must-Fix（阻礙上線，1-3 天）

| # | 項目 | MECE 維度 | 影響 | 預估工時 |
|---|------|-----------|------|---------|
| 1 | RAG title fuzzy match 加強 + threshold 調降 | B4 | 直接決定產品信任 | 4 hr |
| 2 | 恢復 focus-visible outline | E1 | WCAG 合規 | 30 min |
| 3 | MeetingCard 改為語意化 button/link | E2 | A11y 基礎 | 1 hr |
| 4 | 轉錄進度 API + 前端顯示 | B2/F2 | 等待焦慮 | 4 hr |
| 5 | 上傳/轉錄/RAG 錯誤就地恢復 | D1 | 使用者無法自救 | 3 hr |

### 🟡 Phase 1: High Impact（上線品質門檻，3-7 天）

| # | 項目 | MECE 維度 | 影響 | 預估工時 |
|---|------|-----------|------|---------|
| 6 | 搜尋 placeholder 誠實化 + 擴展搜尋範圍 | B3 | 信任 | 3 hr |
| 7 | 導航分組（工作區 / 系統） + 移除 FAB | A1 | 認知清晰 | 2 hr |
| 8 | 標題層級 + 背景色溫統一 | C1/C3 | 視覺品質 | 1 hr |
| 9 | native confirm → 品牌 Modal | D3 | 一致性 | 1 hr |
| 10 | SecurityWrapper 降級（允許選取/複製） | E3 | 使用性 | 30 min |
| 11 | API 分頁 metadata | F1 | 大資料量支撐 | 2 hr |
| 12 | Loading 狀態統一規範 | D2 | 一致性 | 2 hr |
| 13 | 逐字稿點擊跳轉音檔時間軸 | B5 | 核心互動 | 3 hr |
| 14 | Login UAT 入口隔離 | E5 | 首次體驗 | 1 hr |

### 🟢 Phase 2: Polish（品質提升，7-14 天）

| # | 項目 | MECE 維度 | 影響 | 預估工時 |
|---|------|-----------|------|---------|
| 15 | Card 視覺精簡（降色相、移 border） | C2 | 掃描效率 | 2 hr |
| 16 | 品牌色相 shadow | C4 | 精緻感 | 30 min |
| 17 | 卡片 stagger 進場動畫 | C5 | 呼吸感 | 1 hr |
| 18 | Empty state CTA + illustration | D/B | 引導感 | 3 hr |
| 19 | RAG 建議問題自動送出 | D4 | 減少點擊 | 15 min |
| 20 | Tooltip 全面補齊 | D5 | 可發現性 | 1 hr |
| 21 | Admin 加 sparkline + status badges | C6 | 資訊密度 | 3 hr |
| 22 | transition-all → 精確 transition | C/效能 | 效能 | 30 min |
| 23 | TourOverlay 鍵盤化 | E4 | A11y | 1 hr |
| 24 | RAG used_citation_indices | F4 | 精確度 | 2 hr |
| 25 | Dashboard 聚合 API | F5 | 效能 | 3 hr |

### 🔵 Phase 3: Delight（差異化競爭力，14-30 天）

| # | 項目 | 說明 |
|---|------|------|
| 26 | Hybrid retrieval (BM25 + Vector RRF) | 大幅提升 RAG 答中率 |
| 27 | SSE real-time progress push | 消除 polling，即時進度 |
| 28 | 0-friction upload（drag → auto-start） | 極致上傳體驗 |
| 29 | Breadcrumb + 保留 RAG context | 多任務不丟失 context |
| 30 | Mobile-first admin redesign | 主管行動端查看 |
| 31 | Dark mode 完整驗證 | 現有 token 驗證 + 硬碼色修正 |
| 32 | Resumable upload (tus protocol) | 大檔案/弱網路 |
| 33 | 結構化錯誤碼系統 | 前端精準處理每種錯誤 |

---

## 設計原則建議（Design Advisor 總結）

基於本次審查，MeetChi 應遵循以下 5 條設計原則：

### 1. 「誠實的介面」原則
> 不要在 UI 中承諾系統做不到的事（搜尋 placeholder、RAG 引導語）。
> 當找不到答案時，提供退路而非空白。

### 2. 「漸進式複雜度」原則
> 簡單任務（上傳）0 個前置決策。
> 進階功能（模板、機密）在使用者需要時才出現。

### 3. 「等待不焦慮」原則
> 超過 3 秒的等待，必須顯示：(1) 正在做什麼 (2) 預估多久 (3) 完成後通知。
> 使用者離開再回來，狀態必須一眼可知。

### 4. 「錯誤即引導」原則
> 每個錯誤狀態都必須提供：(1) 發生了什麼 (2) 為什麼 (3) 怎麼恢復。
> 不允許 dead-end 錯誤。

### 5. 「一個重點」原則（taste-skill）
> 每個畫面只有一個主要行動呼籲。
> 每張卡片只有一個強調色。
> 每個入口只有一條路徑。

---

## 附錄：審查環境

| 項目 | 值 |
|------|-----|
| Frontend | meetchi-frontend-00049-ftn |
| Backend | meetchi-backend-00030-dhj |
| GPU ASR | meetchi-gpu-asr-00017-woq |
| Database | Cloud SQL PostgreSQL + pgvector |
| 測試帳號 | jerry_tai@mail.chimei.com.tw (super_admin) |
| 首次審查 | MeetChi_UX_AUDIT_REPORT.md (2026-06-10 v1) |
| 設計審查 | docs/design/design-audit-2026-06-08.md |
| Design-Advisor | docs/design/design-advisor-audit-2026-06-08.md |

---

## 與首次審查的差異

| 面向 | 首次審查重點 | 本次審查重點 |
|------|-------------|-------------|
| 方法 | 功能測試 + 程式碼審查 | 第一性原理 + MECE 全面盤點 |
| 深度 | 問題列舉 | 根因分析 + 設計原則推導 |
| 範圍 | 上傳/RAG/摘要 三模組 | 6 維度全覆蓋（IA/Flow/Visual/Interaction/A11y/API） |
| 新增關注 | — | RAG 信任度、等待期 UX、API-UI gap |
| 輸出 | Quick wins 列表 | 分階段路線圖 + 設計原則 |

---

*本報告為 MeetChi 第二次全面 UI/UX 審查，建議每 2 週進行一次追蹤審查，確認 Phase 0 項目完成率。*
