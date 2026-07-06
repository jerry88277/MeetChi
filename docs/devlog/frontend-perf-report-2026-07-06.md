# 前端各模組操作效能量化報告 — 2026-07-06

## 方法（可重複）
Playwright headless + CDP，UAT 帳號實登，量測：
- 各模組 JS 傳輸量 / DOMContentLoaded / load / DOM 節點數
- 輸入延遲：Event Timing API（keydown/input event duration = 事件→下一次 paint）
- Long Tasks 數量與最大值
- CPU throttling（Emulation.setCPUThrottlingRate）模擬 VDI/弱端
Harness：`frontend-perf-harness.mjs`（`CPU=4 node frontend-perf-harness.mjs`）

## 結果

### 各模組載入（CPU x4）
| 模組 | JS | DCL | load | DOM |
|---|---|---|---|---|
| dashboard | ~1.5MB | 1521ms | 1906ms | 241 |
| rag | 同一包 | 393ms | 881ms | 241 |
| templates | 同一包 | 334ms | 864ms | 441 |
| settings | 同一包 | 542ms | 803ms | 261 |
| admin | 同一包 | 166ms | 624ms | 255 |
→ 單一 ~1.5MB monolithic bundle，所有 view 共用；首屏成本集中在 dashboard。

### 輸入延遲（打字，p75）
| 欄位 | CPU x1 | x4 | x6 |
|---|---|---|---|
| dashboard 搜尋（基準） | — | 32ms | — |
| 回報模組 問題描述 | 336ms | 424ms | 432ms |
→ 回報模組比基準慢 8–15 倍；且 x1 已 288ms、隨 CPU 幾乎不變 → 非純運算瓶頸。

## 根因（A/B 驗證）
1. **全螢幕 backdrop-blur**（FeedbackModal 第 251 行 `backdrop-blur-sm`）：
   每次按鍵重繪都要對整個視窗重新模糊 → paint 昂貴、與 CPU 幾乎無關。
   實測即時移除：p50 272ms → 152ms（改善 ~44%）。
2. **整個 modal 每次按鍵全量重繪**：欄位為 controlled，setState 觸發整個
   33KB modal（選項格、lucide 圖示、截圖預覽）重繪。移除 blur 後仍殘留 ~150–280ms。

## 建議修正
- A. 移除/降級 backdrop-blur（改純半透明 dim 或改為不隨內容重繪的獨立圖層）。
- B. 將各輸入欄位抽成 memo 化子元件（或 uncontrolled + ref），讓打字只重繪當前欄位。
- C.（載入面）對 1.5MB bundle 做 route-level code-split / dynamic import 重元件。

---

## 實作與實測（2026-07-06，frontend-00085-kr5）
A（移除 backdrop-blur）+ B（記憶化選項格）+ C（next/dynamic code-split）三案已一次實作並部署至生產。

**Before → After（CPU x4，Playwright + Event Timing）**
- 回報模組打字 p75 延遲：**~424ms → 56 / 64ms**（兩次量測）
- dashboard 搜尋 baseline p75：32ms → 40 / 32ms
- 主 bundle：單一巨型 bundle → 拆為 30 個 chunk（重元件延後載入）

結論：回報模組打字延遲由 baseline 的 8–15 倍降至約 1.5–2 倍，使用者感受到的「卡、重」大幅改善。
