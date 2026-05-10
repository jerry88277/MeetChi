# Frontend User Flow Audit — 2026-05-10

> **Scope**：MeetChi frontend 全部頁面的使用者流程完整性審查（loading / error / empty / back / confirm / disabled / mobile / a11y）
> **方法**：Read 每個 page/view component，依 8 個 dimension 打分，標 P0/P1/P2 嚴重度
> **跨會議知識庫 (RAG) 頁面已知問題另行處理**，本 audit 不重複盤點

---

## Executive Summary

- **7 pages audited**: DashboardView / DetailView / RecordingView / SettingsView / TemplateGallery / Login / Dashboard orchestrator
- **21 issues found**: P0=3 / P1=10 / P2=8
- **Top 3 problems**:
  1. **DetailView 刪除無確認**（P0）— ConfirmDialog 已存在但未接上
  2. **RecordingView 錄音中關閉無 beforeunload 警告**（P0）— MediaRecorder 沒收尾，IDB backup 是 best-effort
  3. **RecordingView 麥克風權限拒絕無區分顯示**（P0）— `NotAllowedError` 未識別，使用者看不懂

---

## Per-Page Findings

### DashboardView ([components/DashboardView.tsx](../../apps/frontend/src/components/DashboardView.tsx))

| Dimension | Status | Severity | Note |
|---|---|---|---|
| Loading | ✅ | — | Spinner + 文字置中 (line 217–221) |
| Error | ✅ | — | inline banner with AlertCircle 可恢復 (line 184–192) |
| Empty | ✅ | — | 清楚 CTA 提示 (line 240–246) |
| Back nav | ✅ | — | sidebar 處理 |
| Confirm-on-destroy | ⚠️ | P1 | DashboardView 自身無刪除動作，刪除在 detail 頁觸發 |
| Disabled feedback | ⚠️ | P2 | refresh 按鈕 disabled 沒 tooltip 解釋（line 84–87） |
| Mobile | ✅ | — | `md:` breakpoint 有 |
| A11y | ⚠️ | P1 | menu button (ChevronDown) 無 aria-label；search icon 沒語意 (line 206) |

### DetailView ([components/DetailView.tsx](../../apps/frontend/src/components/DetailView.tsx))

| Dimension | Status | Severity | Note |
|---|---|---|---|
| Loading | ✅ | — | pending/processing 有 skeleton (line 287–334) |
| Error | ⚠️ | P1 | failed state 給兩個按鈕但**沒解釋為何失敗** (line 337–369) |
| Empty | ✅ | — | completed 但無 summary 顯示 CTA (line 647–655) |
| Back nav | ✅ | — | sticky header back 按鈕 (line 189–190) |
| **Confirm-on-destroy** | ❌ | **P0** | 刪除按鈕 (line 271–278) **無確認**；ConfirmDialog 在 dashboard/page.tsx:628–642 存在但未串接 |
| Disabled feedback | ✅ | — | Regenerate 按鈕 disabled + spinner |
| Mobile | ⚠️ | P2 | 模板選擇器在 mobile 隱藏 (line 202)；mobile 專屬 regenerate 增加雜亂 (line 435–444) |
| A11y | ⚠️ | P1 | export dropdown 用 `group:hover` (line 249–269) — 鍵盤無法存取；transcript timestamp 只有 `title` 沒 aria-label (line 610) |

### RecordingView ([components/RecordingView.tsx](../../apps/frontend/src/components/RecordingView.tsx))

| Dimension | Status | Severity | Note |
|---|---|---|---|
| Loading | ✅ | — | 上傳中 overlay spinner (line 467–473) |
| Error | ⚠️ | **P0** | **麥克風權限被拒絕無區分**：`DOMException` + `NotAllowedError` (line 344–348) 顯示通用訊息，沒指引「去瀏覽器設定打開麥克風」 |
| Empty | ⚠️ | P2 | context input 標 `(可選)` 但表單看起來像必填 (line 508–531) |
| Back nav | ⚠️ | P1 | back 按鈕 (line 477–478) 直接停錄音返回，**錄音中無確認** |
| **Confirm-on-destroy** | ❌ | **P0** | **錄音中或上傳中關閉 tab/瀏覽器無 beforeunload 警告**；MediaRecorder 在 unmount 才收尾 (line 448–458)；IDB backup (line 405) 是 best-effort 不可靠 |
| Disabled feedback | ⚠️ | P2 | record 按鈕 disabled 無「準備中…」文字 (line 576) |
| Mobile | ✅ | — | 設計就是垂直全螢幕單欄 |
| A11y | ⚠️ | P1 | volume meter 視覺 only；transcript 自動 scroll 沒 aria-live；Web Speech API 狀態 silent |

### SettingsView ([components/SettingsView.tsx](../../apps/frontend/src/components/SettingsView.tsx))

| Dimension | Status | Severity | Note |
|---|---|---|---|
| Loading | ⚠️ | P2 | isConnected prop 從外傳，無 loading skeleton |
| Error | ⚠️ | P2 | health check 失敗無 retry 機制 |
| Empty | — | — | N/A |
| Back nav | ✅ | — | 有 back button (line 19–21) |
| Confirm-on-destroy | — | — | 無破壞性動作 |
| Disabled feedback | ✅ | — | ASR 設定 disabled toggle 有 tooltip「此設定尚未開放調整」(line 101) |
| Mobile | ✅ | — | `max-w-4xl` 容器；垂直佈局 |
| A11y | ⚠️ | P1 | **theme toggle 是 `<div>` 不是 `<button>`** (line 78–85)；無 aria-label / aria-checked |

### TemplateGallery ([components/TemplateGallery.tsx](../../apps/frontend/src/components/TemplateGallery.tsx))

| Dimension | Status | Severity | Note |
|---|---|---|---|
| Loading | ✅ | — | spinner + text (line 166–171) |
| Error | ✅ | — | inline banner (line 158–163)；無 retry 按鈕 |
| Empty | ✅ | — | icon + text (line 236–241) |
| Back nav | ⚠️ | P2 | **主 gallery 視圖沒 back 按鈕**（line 121–285）；只接到 `onBack` prop 但 UI 沒 render；子視圖 (editor) 也沒 back |
| Confirm-on-destroy | ✅ | — | 刪除確認 dialog 有 (line 272–283) |
| Disabled feedback | ✅ | — | move 按鈕 boundary disabled (line 396–400) |
| Mobile | ⚠️ | P2 | grid `grid-cols-1 md:grid-cols-2` 卡片高度不一致；preview modal `max-w-lg` 在 mobile 可能溢出 |
| A11y | ⚠️ | P1 | icon button (Preview/Fork/Edit/Delete) 無 aria-label (line 200/206/214/220)；section 上下移動只有滑鼠，無鍵盤替代 |

### Login ([app/login/page.tsx](../../apps/frontend/src/app/login/page.tsx))

| Dimension | Status | Severity | Note |
|---|---|---|---|
| Loading | ✅ | — | Suspense fallback spinner (line 70–76) |
| Error | ⚠️ | P1 | OAuth callback 失敗無 UI 回饋；`signIn("google")` 錯誤 silent |
| Empty | — | — | N/A |
| Back nav | — | — | N/A（入口頁） |
| Confirm-on-destroy | — | — | N/A |
| Disabled feedback | ⚠️ | P2 | Google button 無 disabled/loading state；連點兩次可能開兩個 popup |
| Mobile | ✅ | — | `max-w-md` |
| A11y | ⚠️ | P1 | Google SVG 無 alt/aria-label；法律條款無 checkbox 同意機制只有純文字 (line 54–56) |

### Dashboard Orchestrator ([app/dashboard/page.tsx](../../apps/frontend/src/app/dashboard/page.tsx))

| Dimension | Status | Severity | Note |
|---|---|---|---|
| Loading | ✅ | — | view-specific spinner |
| Error | ⚠️ | P1 | 全域錯誤處理不一致：upload error 用 inline banner (line 425)；regenerate error 沒明確顯示 (line 261)；toast vs banner 混用 |
| Empty | ✅ | — | 各 view 各自處理 |
| Back nav | ✅ | — | `handleBackToDashboard` (line 274–277) |
| Confirm-on-destroy | ✅ | — | ConfirmDialog 有用 (line 628–642 / 644–658) |
| Disabled feedback | ✅ | — | CTA 上傳中 disabled + spinner |
| Mobile | ⚠️ | P2 | mobile header 邏輯複雜 (line 360, 372)；FAB (line 341–350) z-40；processing queue indicator z-50 — mobile 可能重疊 |
| A11y | ⚠️ | P1 | FAB 有 `title` 但無 aria-label；mobile menu 按鈕無 aria-label (line 384) |

---

## Cross-Cutting Concerns

1. **錯誤處理不一致**：DashboardView / TemplateGallery 用 inline banner；dashboard.tsx 用 toast。沒有統一的 `<ErrorState>` component。
2. **A11y 全面缺**：大量 icon-only button 沒 aria-label；自製 toggle 是 div 不是 native button；export dropdown 用 `group:hover` 鍵盤無法存取。
3. **確認對話框**：DetailView 刪除無確認；RecordingView 錄音中關閉無警告。ConfirmDialog component 已存在但用得不夠廣。
4. **Mobile 重疊**：FAB + processing queue indicator 在小螢幕沒 z-index 管理；DetailView transcript `max-h-[60vh]` 在直立螢幕可能不夠。
5. **缺 Back 入口**：TemplateGallery 主視圖無 back；RecordingView back 邏輯危險。
6. **Loading state 缺**：Login OAuth 錯誤沒回饋；SettingsView 不假設 isConnected 已載入。
7. **表單可選欄位不清**：RecordingView context input 看起來像必填即使標了「(可選)」。

---

## Recommended Follow-Up PRs (Ordered by ROI)

### P0 — 立刻
1. **DetailView 刪除接 ConfirmDialog** — 包現有 ConfirmDialog 即可（line 271–278）
2. **RecordingView beforeunload 警告** — `useEffect` 加 listener 防止錄音/上傳中關閉
3. **RecordingView 麥克風權限友善訊息** — 區分 `NotAllowedError` 顯示「請到瀏覽器設定打開麥克風」+ 連結

### P1 — 高 ROI
4. **全 icon button 補 aria-label** — DashboardView / DetailView / SettingsView / TemplateGallery / RecordingView
5. **SettingsView ThemeToggle 改 native button** — `<button type="button" aria-pressed={...}>`
6. **抽 `<ErrorState>` 統一錯誤顯示** — 取代 inline banner / toast 混用
7. **TemplateGallery 主視圖補 back 按鈕** — render `onBack` prop 在 header
8. **DetailView export dropdown 改鍵盤可存取** — `group:hover` → state-driven `<button>`
9. **SettingsView connection status loading skeleton**
10. **Login OAuth 錯誤回饋**

### P2 — Nice to have
11. DetailView 逐字稿 mobile 折疊優化
12. TemplateGallery grid equal height
13. 表單可選欄位視覺區分
