# 模組稽核：上傳 → 轉錄 → 逐字稿/結果（四角色）

> 日期：2026-06-30
> 範圍：上傳入口/表單 → 上傳進度 → 處理狀態 → 會議詳情（摘要/逐字稿/講者/匯出/機密）
> 角色：🟢新手 / 🟡一般 / 🔴專業 / 🧊冷啟動（零基礎、會跳過彈窗）
> 方法：MECE 六維 × 四角色，逐檔程式碼佐證（file:line）
> 主要檔案：`app/dashboard/page.tsx`、`components/DashboardView.tsx`、`components/UploadTray.tsx`、`hooks/useUploadQueue.ts`、`components/MeetingCard.tsx`、`components/DetailView.tsx`、`components/SecurityWrapper.tsx`、`types/meeting.ts`

---

## 0. 架構觀察（影響全模組）
- **兩套上傳機制並存**：舊 `useRecording`（全屏 overlay）＋新 `useUploadQueue`（右下 Tray），`page.tsx` 同時掛載 → 狀態來源分裂、UI 疊加。
- **假進度／假 ETA**：`MeetingCard` STAGE_CONFIG 進度寫死（queued15/transcribing50/diarizing65/summarizing85，MeetingCard ~97-110）；ETA 為前端公式推估（MeetingCard ProcessingEta、UploadTray `statusLabel` ~44-63），與後端真實進度無關。

---

## 1. 四角色旅程重點（碎念）
- 🧊冷啟動：點「上傳音檔」直接跳檔案選擇，**沒有任何模板/語言/情境確認步驟**；上傳後同時看到全屏 overlay＋右下 Tray＋左下膠囊三種狀態，困惑。完成後點「📄逐字稿已可查看」→ **詳情頁一片空白**（致命）。
- 🟢新手：「即時錄音」標「開發中」卻可點、點了真的進錄音頁；語言選單在 header 角落、標籤 `hidden sm:inline` 手機看不到。
- 🟡一般：批次上傳大檔**無法取消**；卡片失敗原因被 line-clamp-1 截斷；完成時間/排序仍弱。
- 🔴專業：機密會議掛 🔒 但**實際無任何複製/截圖防護**；浮水印是預設字串非使用者身分；`Status: QUEUED` 英文外洩；版本還原用整頁 reload。

---

## 2. 問題清單（依六維度；標 P0/P1/P2 + 角色 + 佐證 + 修法）

### A. 功能正確性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| U-A1 | **`transcribed` 狀態詳情頁空白**：卡片導引「點擊查看逐字稿」，但 DetailView 無 transcribed 分支，body 只剩 header＋底部時間 | **P0** | 新/一般/冷 | `types/meeting.ts:80` 有 transcribed；DetailView 區段 gate 在 pending/processing/failed/isCompleted（~828 逐字稿 gate isCompleted） | DetailView 新增 transcribed 分支：顯示逐字稿＋「摘要生成中」提示 |
| U-A2 | **上傳無法選模板/情境/機密**：props 傳入但 JSX 未渲染，永遠送 general/空/false | **P0** | 全 | `DashboardView.tsx:57,139-189`；`page.tsx:124,451` enqueue 帶預設 | 上傳前加輕量設定（模板下拉＋情境＋機密 toggle），或上傳後可改 |
| U-A3 | **機密保護形同虛設**：`<SecurityWrapper>` 未傳 isConfidential/userIdentifier，Ctrl+P 阻擋被預設 false gate；無 select-none/contextmenu/Ctrl+C 攔截 | **P0** | 專/一般 | `DetailView.tsx:1018`；`SecurityWrapper.tsx:18-28` | 傳入 isConfidential＋userIdentifier；補複製/右鍵/列印防護或移除誇大宣稱 |
| U-A4 | 浮水印用預設「MeetChi-Confidential」非使用者 email，opacity 0.04 幾不可見 | P1 | 專 | `SecurityWrapper.tsx:86-114` | 傳真實 user email；提高可見度（如 0.08） |
| U-A5 | 假進度條（寫死百分比），長任務卡同一數字 | P1 | 一般/新 | `MeetingCard.tsx:97-110` | 接後端真實 stage 或改為不顯示百分比、只顯示階段 |
| U-A6 | ETA 純前端公式，易與實際差距大 | P1 | 一般/專 | `MeetingCard` ProcessingEta；`UploadTray.tsx:44-63` | 接後端排隊深度/真實估時，或標「預估僅供參考」 |
| U-A7 | 版本還原用 `window.location.reload()`，整頁刷新丟失 SPA 狀態 | P2 | 專 | `DetailView.tsx:~165` | 改為 state 更新/重抓單會議 |
| U-A8 | 列表搜尋為 client 端 title+summary 比對，與 Enter 觸發的 server filter 行為不一致 | P2 | 一般/專 | `DashboardView.tsx:73-76` + onServerFilter | 統一搜尋來源（純 server 或純 client） |

### B. 流程可用性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| U-B1 | 上傳零確認步驟，選檔即送，無法在上傳當下設定 | P1 | 冷/新 | `page.tsx` triggerFileInput → enqueue | 加「上傳設定」步驟（與 U-A2 合併） |
| U-B2 | **進行中上傳無法取消** | P1 | 一般/新 | `useUploadQueue` removeTask 不移除 uploading/processing；`UploadTray.tsx:181-190` | 加取消鈕＋AbortController |
| U-B3 | 狀態指示三重疊（全屏 overlay＋Tray＋左下膠囊）訊息重複 | P1 | 新/冷 | `page.tsx:660-728,~940` | 收斂為單一上傳狀態來源（保留 Tray） |
| U-B4 | 「即時錄音」標開發中卻可點並切到錄音頁 | P1 | 新/冷 | `DashboardView.tsx:~166` | disabled 或明確「即將推出」並阻擋點擊 |
| U-B5 | 逐字稿預設折疊，從「逐字稿已可查看」期待直達卻被收合 | P1 | 一般/冷 | `DetailView.tsx:76` showTranscript 初值 false | transcribed/需求情境預設展開逐字稿 |
| U-B6 | 列表卡片改名僅右鍵選單，觸控裝置無入口 | P2 | 一般 | `MeetingCard.tsx:~270` | 卡片加顯式改名鈕 |

### C. 邊界與錯誤處理
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| U-C1 | **無檔案大小上限/前端校驗**，僅 >120 分鐘時長 confirm | P1 | 專/一般 | `page.tsx:~600-625` | 加大小上限提示與格式檢查 |
| U-C2 | 時長探測失敗(duration=0)或非 audio/video 直接略過大檔提醒 | P2 | 專 | `page.tsx:590-628` | fallback 用檔案大小估算 |
| U-C3 | 不支援格式無明確錯誤，只能等後端轉錄失敗 | P1 | 新/冷 | `accept="audio/*,video/*"` 無對應錯誤 | 前端擋下並提示支援格式 |
| U-C4 | failureReason 卡片 line-clamp-1 截斷 | P2 | 一般 | `MeetingCard.tsx:~417` | 卡片顯示摘要＋「查看詳情看完整原因」 |
| U-C5 | transcription task fire-and-forget，觸發失敗只 console.error，會議卡 pending | P1 | 一般/專 | `useUploadQueue.ts:147-151` | 失敗顯示 toast＋重試入口 |
| U-C6 | SecurityWrapper MutationObserver 可能誤判（擴充/廣告攔截改 DOM）→ 全屏「安全警報」中止 | P1 | 專/一般 | `SecurityWrapper.tsx:32-80` | 放寬偵測條件、避免誤殺正常工作階段 |

### D. 一致性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| U-D1 | 兩套上傳系統狀態來源不同，易顯示矛盾 | P1 | 專 | useRecording vs useUploadQueue 並存 | 收斂為單一上傳系統 |
| U-D2 | pending 詳情顯示英文 `Status: QUEUED`，其餘全中文 | P1 | 冷/新 | `DetailView.tsx:475` | 中文化「排隊中」 |
| U-D3 | 重新生成 UI 桌機/手機各寫一份，易維護漂移 | P2 | — | `DetailView.tsx:360-420` 與 ~745-770 | 抽共用元件 |
| U-D4 | 階段/狀態文案多處不統一（生成摘要中 vs AI 正在生成摘要…） | P2 | 一般 | MeetingCard STAGE_CONFIG vs DetailView | 統一文案常數 |

### E. 信任與安全感
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| U-E1 | **安全劇場**：🔒 機密 chip 與 title 宣稱保護，實際無防護（見 A3/A4） | **P0** | 專/一般 | `DetailView.tsx:316`（title「後續 Phase 將鎖複製」） | 補上真實防護或誠實標示「僅標記、未強制」 |
| U-E2 | 「資料安全保護」綠標宣稱「不外洩至任何第三方雲端」，但實際上傳 GCS | P1 | 專 | `DashboardView.tsx:~108` tooltip vs `useUploadQueue` GCS 上傳 | 修正文案為「儲存於公司專屬 GCP 私有環境」等與事實相符敘述 |
| U-E3 | 刪除訊息矛盾：批次刪 toast「保留30天可還原」vs 單筆 dialog「無法復原」 | P1 | 一般/專 | `page.tsx` bulkDelete toast vs ConfirmDialog | 統一刪除語意 |
| U-E4 | 假 ETA/假進度一旦被識破，整體信任下降 | P2 | 專/一般 | 見 A5/A6 | 同 A5/A6 |

### F. 非功能面（效能/RWD/A11y）
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| U-F1 | 語言/模板/情境 `<select>`/input 無 `<label for>` 關聯，僅 title | P2 | a11y | `DashboardView.tsx:128-142` | 補 label/aria |
| U-F2 | 講者改名 chip 為 `<span onClick>`、時戳 `<div onClick>`，無鍵盤可達 | P2 | a11y | `DetailView.tsx:850-915,880-900` | 改 button＋role＋keydown |
| U-F3 | 上傳 CTA 文字 `hidden sm:inline`，手機只剩 icon 語意流失 | P2 | RWD/新 | `DashboardView.tsx` CTA | 手機保留精簡文字或 aria 強化 |
| U-F4 | 右下 Tray／底部音檔播放器／左下膠囊小螢幕互相遮擋 | P2 | RWD | 多元件 fixed 定位 | 統一浮層管理避免重疊 |
| U-F5 | ProcessingHeartbeat 每秒 setState，多張卡片同時計時造成每秒重繪 | P2 | 效能 | `MeetingCard.tsx:237-262` | 用單一全域 ticker 或降頻 |
| U-F6 | 浮水印 SVG fixed + MutationObserver subtree 監看整棵 DOM 成本高 | P2 | 效能 | `SecurityWrapper.tsx:56-62` | 限縮監看範圍 |

---

## 3. 本模組整合優先級
- **P0（4）**：U-A1 transcribed 空白頁、U-A2 上傳無法選模板/機密、U-A3 機密保護失效、U-E1 安全劇場（A3/E1 同源）。
- **P1（~12）**：浮水印身分、假進度/ETA、上傳取消、狀態三重疊、即時錄音誤導、逐字稿預設展開、檔案大小校驗、格式錯誤提示、task 失敗無感知、SecurityWrapper 誤判、QUEUED 中文化、資料安全文案、刪除語意矛盾。
- **P2（~12）**：版本還原 reload、搜尋來源不一致、改名觸控入口、雙份重生 UI、文案統一、a11y（label/keyboard）、RWD 浮層重疊、心跳重繪、浮水印效能。

**最關鍵三項**：U-A1（功能斷裂）、U-A2（核心功能無法使用）、U-A3/E1（安全與信任風險）。
