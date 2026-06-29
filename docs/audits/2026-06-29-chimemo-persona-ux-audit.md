# ChiMemo 三層 Persona UX 稽核報告

> 日期：2026-06-29  
> 範圍：ChiMemo 跨會議 AI 知識搜尋功能  
> 元件：Sidebar 入口 → RagWorkspace (全頁) / RagDrawer (快捷) → ChatPanel → ReferencePanel  
> 後端：`/api/v1/rag/ask`, `/api/v1/rag/greeting`, `/api/v1/rag/history`

---

## 🟢 新手 Persona（第一次使用的行政助理）

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| C-N1 | 「ChiMemo」名稱無法直覺聯想功能 | 流程可用性 | P2 | 新使用者看到 sidebar 上只有「ChiMemo」+ 聊天泡泡圖示，不知道這是做什麼的。需要看到 Tour 說明才能理解。TourOverlay 只觸發一次，之後再也看不到。 |
| C-N2 | 歡迎訊息過長，新手容易資訊過載 | 流程可用性 | P2 | Welcome message 有 7 行 + 4 個範例，新手還沒建立心智模型就被大量文字轟炸。容易跳過不看。 |
| C-N3 | 沒有明確的「空狀態」引導（零會議時） | 邊界/錯誤處理 | **P1** | 如果使用者還沒有上傳任何會議就進 ChiMemo，查詢必定回空。沒有任何提示告訴使用者「請先上傳會議」。 |
| C-N4 | Greeting Card 的 topic pills 不可點擊 | 流程可用性 | P2 | 顯示使用者最常討論的 topic（如 AI、KPI），但只是 `<span>` 標籤。新手直覺會以為可以點來搜尋。 |
| C-N5 | 錯誤訊息技術化，新手看不懂 | 信任/安全感 | P2 | 查詢失敗時顯示「⚠️ 這次查詢沒有順利完成」但沒有具體原因。也建議「左側邊欄回報問題」但新手可能找不到。 |
| C-N6 | 輸入框 placeholder 太長在手機上被截斷 | 非功能面 | P2 | `請輸入您的問題，例如：回顧昨天的行銷週會討論了什麼？` 在行動裝置上只看到前半段 |
| C-N7 | 「歷史查詢」按鈕位置不顯眼 | 流程可用性 | P2 | 放在 chat header 右上角，text-xs 且灰色，新手可能完全不知道有歷史功能 |
| C-N8 | RagDrawer 標題寫「智能助理」不是「ChiMemo」 | 一致性 | P1 | Sidebar 寫 ChiMemo、全頁寫 ChiMemo、但 Drawer 標題是「智能助理」→ 一致性斷裂 |

---

## 🟡 一般使用者 Persona（每週使用 3-5 次的業務經理）

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| C-U1 | 無法取消正在進行的查詢 | 效率 | P1 | 5-15 秒等待中無法中斷。如果問錯問題想修正，必須等到完成。 |
| C-U2 | 低信度回答的 hint 太冗長 | 流程可用性 | P2 | `💡 我沒有找到很精準的答案...` 後面列了 5 行，且嵌在 AI 回覆尾端不易區分。建議用摺疊或獨立卡片。 |
| C-U3 | 歷史查詢點擊後只載入問答，不載入 citations | 邊界/錯誤處理 | **P1** | 載入歷史對話時 `citations: []` 硬編空陣列（line 310-317），使用者看不到之前的來源引用，需重新發問。 |
| C-U4 | 引用 [來源N] 的數字與 citation list 對不上 | 信任/安全感 | P2 | AI 回覆中的 `[來源3]` 數字是基於 1-indexed，但如果 citations 陣列本身在渲染前被去重或重排，對應關係可能錯位。 |
| C-U5 | Greeting Card 的 pending_action_count 不可跳轉 | 效率 | P2 | 顯示「📌 您有 N 項待辦行動項目尚未完成」但沒有連結跳轉到行動項目列表。|
| C-U6 | Suggested questions 太 generic | 流程可用性 | P2 | 固定的「總結產品推廣提案與進度」對所有使用者相同。如果該使用者從未討論過產品推廣，這個建議點了會回空。 |
| C-U7 | 對話清除邏輯不直觀 | 邊界/錯誤處理 | P2 | 頁面 reload 會清除、30min 不活動會清除，但沒有手動「清除對話」按鈕。使用者想開新話題需要知道「重新整理頁面」。 |
| C-U8 | ReferencePanel 的「開啟新分頁」按鈕是 disabled 狀態 | 功能正確性 | **P1** | 按鈕存在但 `title="此功能即將推出"` 且 onClick 無動作。使用者會困惑為何按了沒反應。應隱藏或標記 Coming Soon。 |
| C-U9 | RagDrawer vs RagWorkspace 使用時機不清 | 流程可用性 | P2 | 兩個入口（Sidebar→全頁 / FAB→Drawer）但使用者不知道差異。Drawer 不能展示 ReferencePanel。 |

---

## 🔴 專業使用者 Persona（IT 管理員 / 深度使用的 PM）

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| C-P1 | 無法指定查詢範圍（日期/會議篩選） | 效率 | **P0** | API 有 `meeting_ids` 參數但前端沒有暴露任何篩選 UI。專業使用者想「只搜尋上個月的會議」無法做到。 |
| C-P2 | 無法看到 embedding 狀態 | 邊界/錯誤處理 | P1 | 新上傳的會議 transcript 需要 backfill embedding 才能被搜到。使用者不知道「為什麼剛完成的會議搜不到？」 |
| C-P3 | 相似度分數顯示但無解釋 | 信任/安全感 | P2 | Citation 顯示「72%」但使用者不知道什麼是好、什麼是差。沒有 benchmark reference。 |
| C-P4 | 歷史紀錄沒有刪除/搜尋功能 | 效率 | P2 | 90 天、50 筆歷史只能線性瀏覽，無法搜尋特定查詢或刪除敏感查詢紀錄。 |
| C-P5 | ReferencePanel 只顯示單一段落 | 功能正確性 | **P1** | 點引用只看到匹配的那一段（50-200 字），無法看到上下文（expand_with_context 的結果在前端被丟棄）。 |
| C-P6 | AI 回覆無 Markdown 渲染 | 流程可用性 | P1 | AI 回覆包含 `**粗體**`、列表等 Markdown 語法但前端只用 `whitespace-pre-wrap` 顯示原始文字。引用部分有特殊解析但其他 Markdown 被忽略。 |
| C-P7 | 無法匯出對話 | 效率 | P2 | 重要的跨會議分析結果無法複製為結構化格式（Markdown/PDF）帶到簡報中。|
| C-P8 | multi-turn context window 無限制 | 非功能面 | P2 | `history` 傳送所有歷史訊息（line 152-153），長對話會讓 token 爆掉或回應變慢，但使用者無警告。 |
| C-P9 | 無 keyboard shortcuts | 效率 | P2 | 沒有 Ctrl+K 快速開啟、沒有 Enter 以外的送出方式、Tab 切換 chat/reference 等。 |
| C-P10 | 聊天氣泡最大寬度 75% 在寬螢幕上太窄 | 非功能面 | P2 | `max-w-[85%] md:max-w-[75%]` 在 2560px 螢幕上 citation 段落仍被擠壓。 |

---

## 整合優先級

### P0（阻擋核心使用情境）

| # | 問題 | 建議修法 |
|---|------|---------|
| **C-P1** | 無法指定查詢範圍 | 新增日期 range picker + 可選會議清單 filter UI，對接已有的 `meeting_ids` API 參數 |

### P1（本週修復）

| # | 問題 | 建議修法 |
|---|------|---------|
| **C-N3** | 零會議空狀態 | 偵測使用者 meeting 數=0 時顯示引導卡「請先上傳一場會議」|
| **C-N8** | Drawer 標題不一致 | 改「智能助理」為「ChiMemo」，副標可保留「跨會議檢索」|
| **C-U1** | 無法取消查詢 | 加 AbortController + 取消按鈕（替換 Send 按鈕位置）|
| **C-U3** | 歷史不載入 citations | 後端 history API 應包含 citations JSON，前端載入時還原 |
| **C-U8** | 「開啟新分頁」假按鈕 | 隱藏按鈕或實作跳轉到 `/dashboard/meetings/{id}?t={start_time}` |
| **C-P2** | Embedding 狀態不透明 | Greeting Card 或 toast 提示「N 場最新會議尚未建立索引」|
| **C-P5** | ReferencePanel 單段落 | 顯示 expand_with_context 的前後 2-3 段，highlight 匹配段 |
| **C-P6** | AI 回覆無 Markdown | 整合 `react-markdown` 渲染 AI 回覆 |

### P2（Backlog）

| # | 建議 |
|---|------|
| C-N1 | Sidebar hover tooltip 加副標「跨會議 AI 搜尋」|
| C-N2 | 歡迎訊息改為可摺疊 accordion |
| C-N4 | Topic pills 改為 button，點擊自動搜尋 |
| C-N5 | 錯誤訊息加「可能原因 + 建議動作」|
| C-N6 | 短版 placeholder + aria-describedby 完整描述 |
| C-N7 | 歷史按鈕加 badge 數字提示 |
| C-U2 | Low confidence hint 用 Collapsible 獨立卡片 |
| C-U4 | Citation rendering 加 index validation |
| C-U5 | pending_action_count 加跳轉連結 |
| C-U6 | suggested questions 基於 greeting.suggested_questions 動態生成（底部固定按鈕應刪除或也動態化）|
| C-U7 | 加「清除對話」按鈕 |
| C-U9 | Drawer 加提示「展開全頁可查看原文」|
| C-P3 | 加相似度色彩閾值（>80% 綠、60-80% 黃、<60% 灰）|
| C-P4 | 歷史搜尋 + 刪除 |
| C-P7 | 加「匯出為 Markdown」按鈕 |
| C-P8 | 限制 history 最近 10 輪 + token 計數警告 |
| C-P9 | Ctrl+K 全域快捷鍵 |
| C-P10 | max-w 改用 `max-w-3xl` 或 `max-w-4xl` |

---

## MECE 維度覆蓋檢查

| 維度 | 覆蓋問題 |
|------|---------|
| 功能正確性 | C-U8, C-P5 |
| 流程可用性 | C-N1, C-N2, C-N4, C-N7, C-U2, C-U6, C-U7, C-U9, C-P6 |
| 邊界/錯誤處理 | C-N3, C-N5, C-U3, C-U4, C-U7, C-P2 |
| 一致性 | C-N8 |
| 信任/安全感 | C-P3, C-U4 |
| 效率 | C-U1, C-U5, C-P1, C-P4, C-P7, C-P9 |
| 非功能面 | C-N6, C-P8, C-P10 |

---

## 總結

```
ChiMemo 稽核結果：1 P0 + 8 P1 + 19 P2 = 28 issues
核心問題：功能已可用但缺乏「進階控制」(P0) 和「一致性/邊界處理」(P1)
UX 成熟度：β 階段 — 基本流程完整，但專業使用者需求、錯誤邊界、一致性仍需補強
```
