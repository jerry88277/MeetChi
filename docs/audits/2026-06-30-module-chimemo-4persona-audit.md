# 模組稽核：ChiMemo（跨會議 RAG 搜尋）（四角色）

> 日期：2026-06-30
> 範圍：入口（Sidebar/Drawer/Workspace）→ ChatPanel → Greeting → Citations/ReferencePanel → History → 查詢範圍
> 角色：🟢新手 / 🟡一般 / 🔴專業 / 🧊冷啟動
> 主要檔案：`components/rag/ChatPanel.tsx`、`RagWorkspace.tsx`、`RagDrawer.tsx`、`ReferencePanel.tsx`、`Sidebar.tsx`、`app/dashboard/page.tsx`、`lib/api.ts`

---

## 0. 架構觀察
- 桌機走全頁 `RagWorkspace`（含右側 ReferencePanel）；手機走 `RagDrawer`（頂欄 MessageSquare 開啟）。FAB 已移除（`page.tsx:750`），但 `RagDrawer.tsx:18` 註解仍寫「從 FAB 召喚」→ 語意漂移。
- 同一個 `ChatPanel`，引用點擊行為兩入口不同：Drawer→跳會議詳情並關抽屜（`RagDrawer.tsx:36-39`）、Workspace→右側開原文面板（`RagWorkspace.tsx:78`）。
- Markdown 有渲染（ReactMarkdown）；但有引用時逐段切割各自獨立渲染（`ChatPanel.tsx:228-280`）。

---

## 1. 四角色旅程重點
- 🧊冷啟動：Sidebar 看到「ChiMemo」品牌字（非 primary，視覺權重低）；歡迎詞與 chip 直接出現「RAG 架構/ROI/KPI」術語，看不懂用途。零會議時無專屬空狀態（greeting 失敗整卡隱藏）。
- 🟢新手：查詢失敗訊息叫去「左側邊欄回報問題」，但手機 Drawer 看不到 sidebar；相似度顯示 41% 無脈絡易不信任。
- 🟡一般：查詢 5-15 秒不可取消、無重試鈕；載入歷史對話後引用全消失無法再點原文。
- 🔴專業：無日期/會議範圍篩選（後端 meeting_ids 能力 UI 未用）；引用只給單一片段非前後文；無匯出/複製；多輪上下文用截斷預覽污染。

---

## 2. 問題清單（六維度；P0/P1/P2 + 角色 + 佐證 + 修法）

### A. 功能正確性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| R-A1 | **載入歷史對話後 citations 強制清空**，無法再開原文 | **P0** | 一般/專 | `ChatPanel.tsx:320-336`（citations:[]） | 後端 history 回傳 citations JSON，前端還原 |
| R-A2 | 多輪歷史把 `answer_preview`(截斷) 當完整 AI 回答回傳後端 | P1 | 專 | `ChatPanel.tsx:158-160,330` | 多輪只送完整 answer 或標記摘要；後端容忍 |
| R-A3 | ReferencePanel「open in new tab」用 ExternalLink 圖示但實為同分頁 router.push | P1 | 一般/專 | `ReferencePanel.tsx:24-27,46-53` | 真正開新分頁(window.open)或換 icon＋正名 |
| R-A4 | 行內 `[來源N]` 逐段獨立 ReactMarkdown，跨引用清單/粗體被切斷、序號重置 | P1 | 一般/專 | `ChatPanel.tsx:228-280` | 改 remark plugin 在 AST 層處理引用，避免切字串 |
| R-A5 | 相似度 0 不顯示（`{cite.similarity && …}`） | P2 | 專 | `ChatPanel.tsx:445`；`ReferencePanel.tsx:124` | 改 `similarity != null` 判斷 |
| R-A6 | 低信心 hint 僅在「有 citations」時觸發；完全查無時無引導 | P1 | 新/冷 | `ChatPanel.tsx:180` | 查無 citations 時也給「找不到，試試其他關鍵字/先確認會議已建索引」 |
| R-A7 | ChatPanel 從不傳 meeting_ids，後端 scoping 能力 UI 無法使用 | P1 | 專 | `ChatPanel.tsx:164` vs `api.ts:793-803` | 加日期/會議篩選 UI 串 meeting_ids |
| R-A8 | RagDrawer 文件/設計仍假設 FAB（已移除） | P2 | — | `RagDrawer.tsx:18`、`page.tsx:750` | 更新註解/設計，移除死碼語意 |

### B. 流程可用性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| R-B1 | **查詢進行中無法取消**（5-15 秒不可中斷） | P1 | 一般/新 | `ChatPanel.tsx:479,486` 無 abort | 加 AbortController＋取消鈕 |
| R-B2 | 查詢失敗無「重試」鈕，需手動重打 | P1 | 新/一般 | `ChatPanel.tsx:202-207` | 失敗氣泡加「重試」 |
| R-B3 | 歷史無搜尋、無刪除（唯讀） | P2 | 專 | `ChatPanel.tsx:301-344` | 加歷史搜尋＋刪除 |
| R-B4 | pending_action_count 不可點，無跳轉 | P2 | 一般/專 | `ChatPanel.tsx:401-408` | 連結到待辦/相關會議 |
| R-B5 | 桌機無快捷鍵呼出 ChiMemo，需離開當前會議切全頁 | P2 | 專 | 無全域 hotkey | 加 Ctrl/⌘+K 開啟 |
| R-B6 | greeting card 收合狀態不持久，每次重載又展開 | P2 | 一般/專 | `ChatPanel.tsx:357` | 收合狀態存 localStorage |
| R-B7 | ChiMemo 在 Sidebar 非 primary，發現性低 | P2 | 新/冷 | `Sidebar.tsx:45` | 提權重或加副標 |

### C. 邊界與錯誤處理
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| R-C1 | 錯誤訊息叫點「左側邊欄回報問題」，手機 Drawer 看不到 sidebar | P1 | 一般/新 | `ChatPanel.tsx:204` | 錯誤訊息內直接放回報入口 |
| R-C2 | 網路/逾時/500 不分流，統一一句話 | P2 | 一般/專 | `ChatPanel.tsx:202-207` | 區分錯誤類型給對應指引 |
| R-C3 | **零會議無專屬空狀態**；greeting 失敗整卡隱藏，只剩通用歡迎詞 | P1 | 冷/新 | `ChatPanel.tsx:111` | 偵測 meeting_count=0 顯示「請先上傳會議」引導 |
| R-C4 | 剛上傳/未建索引的會議查不到時無 index 狀態提示 | P1 | 新/一般/冷 | 全模組無 embedding status UI | 顯示「N 場會議建立索引中，稍後可查」 |
| R-C5 | sessionStorage 寫入失敗靜默忽略，對話可能悄悄不保存 | P2 | 一般 | `ChatPanel.tsx:84-86` | 失敗時提示或降級 |

### D. 一致性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| R-D1 | 兩入口對同一引用行為不同（跳會議 vs 開原文面板） | P1 | 一般/專 | `RagDrawer.tsx:36` vs `RagWorkspace.tsx:78` | 統一行為（如都先開原文預覽再可跳轉） |
| R-D2 | confidence 原始英文（high/low/no_answer）直接顯示 | P1 | 一般 | `ChatPanel.tsx:341` | 中文化（高/中/低/查無） |
| R-D3 | 前端拼接 hint 與 LLM 回答同氣泡無區隔 | P1 | 專 | `ChatPanel.tsx:180-200` | 拆成獨立提示卡 |
| R-D4 | ExternalLink 圖示語意不一致（見 A3） | P2 | 一般 | `ReferencePanel.tsx:46` | 同 A3 |
| R-D5 | ReferencePanel「相關會議」有 Calendar 圖示卻無日期值 | P2 | 一般 | `ReferencePanel.tsx:96-98` | 補會議日期 |

### E. 信任與安全感
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| R-E1 | 引用只給單一片段非完整上下文，難驗證是否斷章取義 | P1 | 專 | `ReferencePanel.tsx:120` | 顯示前後 2-3 段並 highlight |
| R-E2 | 前端加工 answer（低信心 hint）讓人誤以為是 AI 原話 | P1 | 專 | `ChatPanel.tsx:198` | 區隔系統提示 vs AI 回答 |
| R-E3 | `askRag` 預設 userUpn `'global_test@company.com'` 危險預設 | P1 | 專/安全 | `api.ts:793` | 移除預設，未登入直接擋 |
| R-E4 | 相似度原始 cosine % 無說明，低分易引發不信任 | P2 | 新/一般 | `ReferencePanel.tsx:124`、`ChatPanel.tsx:445` | 加色階閾值＋「相關度」白話標籤 |
| R-E5 | 歷史保留（前端90天/後端10年）未告知使用者長期留存 | P2 | 一般/專 | `api.ts:782` | 隱私說明透明化 |

### F. 非功能面（效能/RWD/A11y）
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| R-F1 | **無匯出/複製對話或單則回答/引用** | P1 | 一般/專 | 全模組無 clipboard/export | 加「複製回答」「匯出 Markdown」 |
| R-F2 | 無串流輸出，一次等 5-15 秒才出整段 | P1 | 一般/專 | `ChatPanel.tsx:164` | 後端 SSE 串流＋前端逐字渲染 |
| R-F3 | 單行 input 無多行輸入 | P2 | 專 | `ChatPanel.tsx:476` | 改 textarea，Shift+Enter 換行 |
| R-F4 | 每次成功查詢清空 history cache，下次重抓 50 筆 | P2 | 效能 | `ChatPanel.tsx:209` | 增量更新 cache |
| R-F5 | messages 全量寫 sessionStorage，長對話撞 quota（靜默失敗） | P2 | 一般 | `ChatPanel.tsx:79-87` | 限制保存輪數 |
| R-F6 | 「ChiMemo」「RAG」術語對零知識使用者無上下文 | P1 | 冷/新 | welcome/chip `:35-39,:471` | nav 副標＋歡迎詞白話化、移除 RAG 字眼 |
| R-F7 | 鍵盤快捷/focus-trap 驗證不足（Drawer 有 aria-modal 未見 trap） | P2 | a11y | `RagDrawer.tsx:55-58` | 補 focus trap |

---

## 3. 本模組整合優先級
- **P0（1）**：R-A1 歷史 citations 清空（功能殘缺）。
- **P1（~16）**：meeting_ids 篩選、查無引導、多輪上下文失真、引用渲染破版、open-new-tab 語意、取消/重試、零會議空狀態、索引狀態、錯誤指引手機失效、confidence/hint 區隔與中文化、引用前後文、危險預設 upn、匯出複製、串流、術語白話化。
- **P2（~13）**：歷史搜尋刪除、待辦跳轉、快捷鍵、greeting 收合持久、相似度 0/色階、隱私說明、多行輸入、cache、quota、focus trap、FAB 死碼。

**最關鍵三項**：R-A1（歷史殘缺）、R-A7+R-C4（範圍篩選與索引狀態＝查得到的前提）、R-F6（零知識使用者看不懂用途）。
