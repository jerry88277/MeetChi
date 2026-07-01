# MeetChi UX 優化 Master TODO

> 建立：2026-06-30　來源：三份模組四角色稽核 + onboarding 稽核
> 狀態圖示：⬜ 未開始 / 🟧 進行中 / ✅ 完成 / ⏸ 暫緩
> 決策（2026-06-30 by user）：①先做上傳轉錄 ②機密走「補真防護」 ③建立本表 ④移除 Dashboard 綠標不實 tooltip

---

## 批次 1：上傳→錄音→轉錄 模組（進行中）

| ID | 項目 | 級 | 狀態 | 檔案 |
|----|------|----|------|------|
| #4 | 移除/修正 Dashboard 綠標「不外洩第三方雲端」不實宣稱 | P1 | ✅ | DashboardView.tsx |
| U-A2/T-A1 | 上傳設定 UI：選模板/語言/情境/機密（上傳前 step 2） | P0 | ✅ | page.tsx, UploadSettingsModal.tsx |
| U-A1 | DetailView 補 `transcribed` 狀態分支（顯示逐字稿+摘要生成中） | P0 | ✅ | DetailView.tsx |
| U-A3/U-E1 | 機密「補真防護」：SecurityWrapper 正確接線 + 複製/右鍵/列印/選取防護 + 真實浮水印身分 | P0 | ✅ | DetailView.tsx, SecurityWrapper.tsx |
| U-A4 | 浮水印用真實 user email + 提高可見度 | P1 | ✅ | SecurityWrapper.tsx |
| U-B4 | 「即時錄音」開發中→disabled/明確標示 | P1 | ✅ | DashboardView.tsx（停用+「待開發」徽章，阻擋點擊） |
| U-B5 | transcribed 情境逐字稿預設展開 | P1 | ✅ | DetailView.tsx |
| U-D2 | pending 詳情 `Status: QUEUED`→中文 | P1 | ✅ | DetailView.tsx |
| U-B2 | 上傳進行中可取消 | P1 | ✅ | useUploadQueue.ts, UploadTray.tsx, api.ts |
| U-C1/U-C3 | 檔案大小上限 + 格式不符前端提示 | P1 | ✅ | page.tsx |
| U-C5 | 轉錄 task 觸發失敗顯示 toast+重試 | P1 | ✅ | useUploadQueue.ts |
| U-B3/U-D1 | 收斂雙上傳系統 / 狀態三重疊 | P1 | ⏸ | page.tsx（架構級，獨立批次處理） |
| U-E3 | 刪除語意矛盾統一 | P1 | ✅ | page.tsx（單筆刪除改為 30 天可還原，與批次刪除/後端 soft-delete 一致） |
| U-A5/U-A6/U-E4 | 假進度/ETA 改善或標示 | P1 | ✅ | MeetingCard.tsx（假 % 進度條→indeterminate 動畫；ETA 標「（預估）」+ tooltip） |
| U-C6 | SecurityWrapper MutationObserver 誤判放寬 | P1 | ✅ | SecurityWrapper.tsx（batch1 已放寬為只觀察浮水印節點） |
| （P2 群組） | reload 還原、搜尋來源、改名觸控、雙份重生 UI、文案統一、a11y、RWD、心跳重繪、浮水印效能 | P2 | ⬜ | 多檔 |

## 批次 2：ChiMemo（跨會議 RAG）— 部分完成 ✅（2026-07-01 部署 backend-00095-yoz / frontend-00071-2rs）
見 `2026-06-30-module-chimemo-4persona-audit.md`。

已完成：
| ID | 項目 | 優先 | 狀態 | 檔案 |
| --- | --- | --- | --- | --- |
| R-A1 | 歷史對話還原 citations（後端 citations_json 欄位 + 前端還原） | P0 | ✅ | rag.py, main.py, ChatPanel.tsx, api.ts |
| R-E3 | 移除危險預設 upn，未登入直接擋 | P1 | ✅ | api.ts |
| R-B1 | 查詢進行中可取消（AbortController + 取消鈕） | P1 | ✅ | ChatPanel.tsx, api.ts |
| R-B2 | 查詢失敗「重試」鈕 | P1 | ✅ | ChatPanel.tsx |
| R-C1 | 錯誤氣泡內建「回報問題」（全域事件，手機可用） | P1 | ✅ | ChatPanel.tsx, page.tsx |
| R-C3 | 零會議專屬空狀態 | P1 | ✅ | ChatPanel.tsx |
| R-D2 | confidence 英文→中文（歷史 dropdown） | P1 | ✅ | ChatPanel.tsx |
| R-F6 | 術語白話化（welcome + 建議問句移除 RAG/ROI/KPI） | P1 | ✅ | ChatPanel.tsx |
| R-A5 | similarity 0 顯示（!= null 判斷） | P2 | ✅ | ChatPanel.tsx |

暫緩（架構級/後續）：R-A7+R-C4 meeting_ids 篩選+索引狀態、R-F2 SSE 串流、R-A4 引用逐段渲染重構、R-E1 引用前後文。

## 批次 3：模板管理 — 大部分完成 ✅（2026-07-01 部署 frontend-00072-t4x）
見 `2026-06-30-module-template-management-4persona-audit.md`。

已完成：
| ID | 項目 | 級 | 狀態 | 檔案 |
| --- | --- | --- | --- | --- |
| T-A1 | 上傳流程套用模板 | P0 | ✅（既有 UploadSettingsModal 已實作） | UploadSettingsModal.tsx |
| T-A2 | 建立/複製/刪除後跨畫面同步 | P1 | ✅（CustomEvent 廣播 + page/DetailView 監聽） | TemplateGallery.tsx, page.tsx, DetailView.tsx |
| T-A3/T-F4 | 動態 Tailwind color class purge | P1 | ✅（COLOR_MAP 靜態） | TemplateGallery.tsx |
| T-A4 | 從零建立新模板入口 | P1 | ✅（+ 新增模板→空白編輯器） | TemplateGallery.tsx |
| T-A5 | 編輯器開放 icon/color | P2 | ✅ | TemplateGallery.tsx |
| T-A6 | 搜尋 tag 大小寫/名稱說明 | P2 | ✅ | TemplateGallery.tsx |
| T-B1 | Fork 後 toast+立即編輯 | P1 | ✅ | TemplateGallery.tsx |
| T-B2 | 設為預設模板（localStorage，上傳帶入） | P1 | ✅ | TemplateGallery.tsx, page.tsx |
| T-B3 | 編輯儲存中/成功 toast | P1 | ✅ | TemplateGallery.tsx |
| T-B4/T-E2 | 刪除確認單一框帶使用數 | P1 | ✅ | TemplateGallery.tsx |
| T-C1 | 編輯器前端驗證（名稱/段落/output_key 空或重複） | P1 | ✅ | TemplateGallery.tsx |
| T-C2 | instruction 500 字計數+maxLength | P1 | ✅ | TemplateGallery.tsx |
| T-C3 | 取消編輯 dirty-check 離開確認 | P1 | ✅ | TemplateGallery.tsx |
| T-C5 | 空狀態分流+CTA | P2 | ✅ | TemplateGallery.tsx |
| T-D1 | Gallery 過濾 is_active 一致 | P1 | ✅ | TemplateGallery.tsx |
| T-D3 | 自訂模板「我的」徽章 | P2 | ✅ | TemplateGallery.tsx |
| T-E1 | 刪除語意誠實（30天內請IT還原） | P1 | ✅ | TemplateGallery.tsx |
| T-F1 | modal Esc 關閉（useEscape） | P1 | ✅ | TemplateGallery.tsx |
| T-F2 | 刪除鈕加文字 | P2 | ✅ | TemplateGallery.tsx |
| T-F3 | 編輯器窄螢幕改單欄 | P2 | ✅ | TemplateGallery.tsx |
| T-F5 | 預覽指令展開+友善輸出型別 | P2 | ✅ | TemplateGallery.tsx |
| T-F6 | usage_count 正規型別 | P2 | ✅ | TemplateGallery.tsx |

暫緩（架構級/IA/需後端偏好）：T-B5 dry-run 範例輸出（需後端）、T-B6 模板移工作區（IA）、T-D2 抽共用下拉元件、T-D4 語彙全面統一、T-E3 隱藏系統模板（偏好層）、T-E4 簡易模式（大改版）。

## 批次 4：Onboarding（冷啟動）— 完成 ✅（2026-07-01 部署 frontend-00073-6s9）
見 `2026-06-30-coldstart-onboarding-ux-audit.md`。

已完成：
| ID | 項目 | 優先 | 狀態 | 檔案 |
| --- | --- | --- | --- | --- |
| CS-1 | 導覽防跳過（complete/dismiss 三態）+ 零會議首頁常駐「觀看導覽」入口 | P0 | ✅ | TourOverlay.tsx, dashboard/page.tsx, DashboardView.tsx, config.ts |
| CS-2 | 上傳前先看 AI 成果範例（零狀態靜態範例卡：摘要/決策/待辦/風險） | P0 | ✅ | DashboardView.tsx |
| CS-3 | 登入頁補價值說明（錄音→AI 轉文字+摘要/決策/待辦） | P1 | ✅ | login/page.tsx |
| CS-4 | 導覽文案白話化（移除轉錄/RAG 裸詞） | P1 | ✅ | TourOverlay.tsx |
| CS-5 | 上傳選項引導（既有 UploadSettingsModal Info hint 已滿足） | P1 | ✅ | UploadSettingsModal.tsx |
| CS-6 | 詳情頁首開 coachmark（localStorage 一次性 banner） | P1 | ✅ | DetailView.tsx, config.ts |
| CS-7 | 常駐「使用說明」入口 + Help Modal（重播導覽 + FAQ） | P1 | ✅ | Sidebar.tsx |
| CS-9 | ChiMemo 側欄副標「跨會議 AI 搜尋」 | P2 | ✅ | Sidebar.tsx |
| CS-12 | spotlight 目標缺失時 fallback 提示 | P2 | ✅ | TourOverlay.tsx |

暫緩（P2）：
| ID | 項目 | 優先 | 狀態 |
| --- | --- | --- | --- |
| CS-8 | 擴充導覽步驟（更多細節） | P2 | ⏸ |
| CS-10 | 強制首次先到 dashboard | P2 | ⏸ |

驗證：tsc 0 錯誤、build 成功、生產冒煙 200（/, /api/health, backend /health）。
⚠️ 第四次流量鎖定：deploy 後手動 update-traffic 到 00073-6s9 才上線。
