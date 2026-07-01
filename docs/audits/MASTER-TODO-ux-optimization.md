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
| U-B4 | 「即時錄音」開發中→disabled/明確標示 | P1 | ⏸ | DashboardView.tsx（需產品決策：錄音功能是否可用） |
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

## 批次 2：ChiMemo（待批次1後）
見 `2026-06-29`/`2026-06-30-module-chimemo-4persona-audit.md`。P0：R-A1 歷史 citations。P1 群：meeting_ids 篩選+索引狀態、查無/錯誤引導、取消/重試、零會議空狀態、confidence/hint 區隔中文化、引用前後文、匯出複製、串流、術語白話化等。

## 批次 3：模板管理（待批次1後）
見 `2026-06-30-module-template-management-4persona-audit.md`。P0：T-A1（同 U-A2）。P1 群：getTemplates 同步、Tailwind purge、設為預設、建立/Fork 流程、編輯器驗證+500字、is_active 一致、系統模板停用、簡易模式、modal Esc/focus。

## 批次 4：Onboarding（冷啟動）
見 `2026-06-30-coldstart-onboarding-ux-audit.md`。P0：CS-1 導覽防跳過+常駐入口、CS-2 範例會議/詳情頁 coachmark。
