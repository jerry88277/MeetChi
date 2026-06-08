# MeetChi Design-Advisor UX/UI Audit

## ✅ What Works

1. **整體基調有對**：暖白底、深藍側欄、克制陰影，符合企業內部工具而不是 SaaS 行銷站。Evidence: `src/app/globals.css:47-56`, `src/components/Sidebar.tsx:43-45`, `src/components/MeetingCard.tsx:120-124`.
2. **系統狀態可見性不錯**：上傳 overlay、會議卡狀態、側欄連線狀態，讓使用者知道「系統正在做什麼」。Evidence: `src/app/dashboard/page.tsx:595-635`, `src/components/MeetingCard.tsx:152-179`, `src/components/Sidebar.tsx:140-146`.
3. **會議詳情的資訊架構是合理的**：TL;DR → 決策/待辦/風險 → 完整摘要 → 引言 → 逐字稿，符合員工讀取會議產出的工作流。Evidence: `src/components/DetailView.tsx:52-56`, `src/components/DetailView.tsx:479-675`.

## 🔴 Critical Problems

### 1) 生產登入頁混入「測試帳號」主路徑
- **Problem:** 對企業內部員工來說，登入頁的主任務應該是「用公司帳號進系統」。現在真實 SSO 與 UAT 測試帳號並列，且 `UAT_ENABLED = true` 固定開啟，會讓第一次使用者不確定自己該走哪條路，也提高誤登入與信任感下降的風險。
- **Evidence:** `src/app/login/page.tsx:11`, `src/app/login/page.tsx:162-211`.
- **Fix:** 生產環境只保留單一主入口「使用奇美帳戶登入」；Google/UAT 收到次層（管理員入口、query flag、或獨立 `/login/uat`）。這會把 3-second test 變清楚：員工一眼就知道該怎麼進系統。
- **Priority:** P0

### 2) 核心入口被做成「超載下拉選單」
- **Problem:** MeetChi 的主工作是「上傳音檔 → 得到摘要」。但目前「新增會議記錄」把即時錄音、上傳音檔、摘要模板、機密開關、背景提示、甚至未完成的補充資料功能都塞進同一個 dropdown。這不是在幫使用者開始工作，而是在開始前先要求他做一串判斷。
- **Evidence:** `src/components/DashboardView.tsx:127-239`.
- **Fix:** 拆成明確主次操作：主按鈕直接做「上傳音檔」；次按鈕做「即時錄音」；模板/機密/背景提示移到上傳後的 step 2 或側邊設定；把「開發中」功能從主流程拿掉。這能明顯降低 friction，符合 Idea First / Audience + JTBD / Error Prevention。
- **Priority:** P0

### 3) 核心互動不符合鍵盤與焦點可用性
- **Problem:** 會議卡是可點擊 `div`，外層又用另一層 `div` 接管 click；同時全域把 `button:focus` outline 拿掉。結果是：桌機鍵盤使用者幾乎沒有可靠的 focus feedback，也不能用標準方式瀏覽主要內容。
- **Evidence:** `src/components/MeetingCard.tsx:118-126`, `src/components/DashboardView.tsx:319-345`, `src/app/globals.css:231-237`.
- **Fix:** 把會議卡改成語意化 `button` 或 `a`，提供 `Enter/Space` 可操作與 `focus-visible` 樣式；恢復所有按鈕的可見焦點，不要只處理 `input`。這是 Accountability 問題，不只是細節。
- **Priority:** P0

## 🟡 Secondary Issues

### 1) 搜尋框承諾的能力，系統其實沒做到
- **Problem:** placeholder 寫「搜尋會議標題、關鍵字或參與者」，但實際只 filter `title` 和 `summary`。這會造成「我明明照你的提示搜，為什麼找不到」的信任斷裂。
- **Evidence:** `src/components/DashboardView.tsx:76-79`, `src/components/DashboardView.tsx:271`.
- **Fix:** 要嘛把搜尋真的擴到 participants / keywords；要嘛把 placeholder 改成真實能力描述。
- **Priority:** P1

### 2) Empty state 太弱，沒有把人推向下一步
- **Problem:** Dashboard 與 Detail 的空狀態都只有圖示加一句話，缺少 CTA、範例、或下一步引導。對企業工具來說，空狀態應該是 onboarding，而不是靜態告示牌。
- **Evidence:** `src/components/DashboardView.tsx:353-360`, `src/components/DetailView.tsx:809-817`.
- **Fix:** Dashboard 空狀態加入主 CTA（上傳第一場會議 / 開始錄音）、簡短流程說明；Detail 無摘要時直接提供「立即生成摘要」按鈕。
- **Priority:** P1

### 3) RAG 入口重複，搶走不該有的視覺主導權
- **Problem:** 側欄已經有「跨會議知識庫」，右下又再放一顆大型 FAB。眼睛會先被浮動按鈕抓走，而不是先看會議列表與上傳入口。
- **Evidence:** `src/components/Sidebar.tsx:37-39`, `src/app/dashboard/page.tsx:646-657`.
- **Fix:** Desktop 保留一個入口即可；若要保留 FAB，只在特定空狀態或完成摘要後作 contextual suggestion，而不是全域常駐。
- **Priority:** P1

### 4) 側欄導覽缺少清楚分組，active 規則也不一致
- **Problem:** 「所有會議 / 知識庫 / 模板 / 設定」全部長得像同一層級，但其實工作性質不同；同時 dashboard 的 active 樣式與其他項目不同，造成系統規則不穩。
- **Evidence:** `src/components/Sidebar.tsx:36-41`, `src/components/Sidebar.tsx:76-83`.
- **Fix:** 分成「工作區」與「系統設定」兩組；active 樣式統一，只用一套高亮規則，不要 dashboard 特例化。
- **Priority:** P2

### 5) 關鍵錯誤只寫 console，沒有回到 UI
- **Problem:** RAG 歷史載入失敗只 `console.error`；聊天失敗只回一段 generic 文案。使用者看不到是網路問題、權限問題、還是查無資料。
- **Evidence:** `src/components/rag/ChatPanel.tsx:72-87`, `src/components/rag/ChatPanel.tsx:139-144`, `src/components/Sidebar.tsx:142-146`.
- **Fix:** 在歷史 dropdown 與 chat composer 旁提供 inline error / retry；把系統連線狀態和動作失敗更明確串起來。
- **Priority:** P1

### 6) 原生 confirm 打斷整體設計語言
- **Problem:** 上傳超長音檔與批次上傳仍使用 `window.confirm()`，這和其餘已經自訂化的確認對話框不一致，也很像工程訊息而不是產品流程。
- **Evidence:** `src/app/dashboard/page.tsx:364-389`.
- **Fix:** 改用與刪除流程一致的自訂 ConfirmDialog，清楚說明「預估時間 / 可否背景處理 / 取消後果」。
- **Priority:** P2

### 7) 詳情頁頂部工具列偏擁擠，主要閱讀被次要操作干擾
- **Problem:** 返回、模板、重新生成、匯出、回報、刪除都擠在同一條 header。對閱讀型頁面來說，使用者應先吸收內容，再做操作。
- **Evidence:** `src/components/DetailView.tsx:225-360`.
- **Fix:** 把危險與低頻操作收進 overflow menu；header 只保留返回、標題、1 個主要動作。
- **Priority:** P2

## Checklist
- [ ] Navigation — 側欄分組與 RAG 入口去重，建立單一路徑
- [ ] Forms — 登入與新增會議流程減少前置判斷
- [ ] Feedback — 將 RAG / 搜尋 / 上傳失敗回到可見 UI
- [ ] A11y — 恢復 button focus、卡片語意化、補齊鍵盤操作
- [ ] Empty States — Dashboard / Detail 加上明確 CTA 與範例
- [ ] Error States — 用產品化對話框取代原生 confirm / generic error
- [ ] Mobile — 雖然主場景是桌機，仍需驗證 FAB、側欄、detail header 不互相打架

## One-liner verdict
**方向是對的，但目前仍像「功能已齊、主流程未收斂」的內部工具；先把登入、新增會議、可達性三個基礎面收乾淨，整體體驗才會真正成熟。**
