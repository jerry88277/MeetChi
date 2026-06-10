# MeetChi UI/UX 全面審查報告

> 審查日期：2026-06-10  
> 審查範圍：上傳錄音、跨會議知識庫(RAG)、會議摘要 三大功能  
> 審查方法：API 功能測試 + 程式碼逐行審查 + Design Advisor + Taste Skill  
> 品牌規範：奇美藍 (#003B7A)、企業級乾淨風格、全中文 UI

---

## 審查摘要

| 功能模組 | CRITICAL | IMPORTANT | NICE-TO-HAVE |
|---------|----------|-----------|--------------|
| 上傳錄音 | 2 | 6 | 5 |
| 跨會議知識庫 (RAG) | 0 | 6 | 5 |
| 會議摘要 | 0 | 5 | 5 |
| **合計** | **2** | **17** | **15** |

---

## 一、上傳錄音流程 (Upload Recording)

### API 功能測試結果

| 測試項目 | 結果 | 備註 |
|---------|------|------|
| 建立會議 POST /meetings | ✅ PASS | 回傳 PENDING 狀態 |
| 取得上傳 URL | ✅ PASS | 回傳 signed URL |
| 307 重導向處理 | ⚠️ NOTE | 需 follow redirect 或移除尾斜線 |
| 帳號隔離 | ✅ PASS | 僅顯示該帳號的會議 |

### [CRITICAL] 嚴重問題

#### C1. 無防重複上傳保護
- **位置**：`useRecording.ts:58-63`
- **問題**：`uploadFile()` 被呼叫時無「已在上傳中」的前置檢查。快速雙擊或多次選取檔案可觸發平行上傳，造成重複會議
- **建議**：
  ```tsx
  if (uploadState !== 'idle') return; // 加在 uploadFile 最前面
  ```

#### C2. 上傳失敗無就地恢復機制
- **位置**：`useRecording.ts:123-139`, `RecordingView.tsx:491-496`
- **問題**：失敗時只設 `uploadState='error'` 並顯示 toast，overlay 無重試/取消按鈕。使用者必須自行推斷如何恢復
- **建議**：overlay 加入「重新上傳」和「取消」按鈕，保持 file reference 供重試

### [IMPORTANT] 重要改善

| # | 問題 | 位置 | 建議 |
|---|------|------|------|
| I1 | 上傳 overlay 不區分 uploading vs processing | RecordingView:491-496 | 顯示進度百分比 + 當前階段文字 |
| I2 | 無 ARIA live-region / 語意標記 | RecordingView:491-496 | 加 `role="status"` + `aria-live="polite"` |
| I3 | 返回按鈕無 aria-label | RecordingView:500-504 | 加 `aria-label="返回"` |
| I4 | 批次上傳使用 window.confirm | dashboard/page:407-409 | 改用品牌風格 Modal 元件 |
| I5 | 大檔案警告 UX 脆弱 | dashboard/page:373-397 | 加進度預估 + 媒體解析失敗 fallback |
| I6 | 網路中斷無 resumable upload | useRecording:96-107 | 實作分段續傳或提供重試按鈕 |

### [NICE-TO-HAVE] 優化建議

- N1: Overlay 顯示檔名 + 大小 + 進度百分比（state 已存在，只需 render）
- N2: 加入取消/重試 action 按鈕
- N3: Overlay 行動裝置適配（`max-w-sm` + padding）
- N4: 開啟 overlay 時 focus trap，關閉時還原 focus
- N5: 原生 confirm 替換為奇美品牌風格 Modal

---

## 二、跨會議知識庫 (RAG Cross-Meeting Q&A)

### API 功能測試結果

| 測試項目 | 結果 | 備註 |
|---------|------|------|
| 基本問答 | ✅ PASS | confidence: high, 8 citations |
| Follow-up 追問 (history context) | ✅ PASS | 正確延續話題 |
| 無關問題 (明天天氣) | ✅ PASS | confidence: no_answer，正確拒答 |
| 最短問題 (1 字) | ✅ PASS | 422 驗證攔截 |
| 歷史紀錄 endpoint | ✅ PASS | 回傳 5 筆歷史 |
| Greeting endpoint | ✅ PASS | 顯示 5 場會議 + 3 組建議問題 |
| Summary search (A1) | ✅ PASS | 勤崴國際 → high confidence |
| 跨會議比較 | ✅ PASS | 正確引用多場會議 |

### [IMPORTANT] 重要改善

| # | 問題 | 位置 | 建議 |
|---|------|------|------|
| I1 | 建議問題 chip 只填入 input，不自動送出 | ChatPanel:192-196, 439-449 | 改為 `setInput(q)` 後自動 `handleSend()` |
| I2 | 歷史面板無鍵盤操作 | ChatPanel:273-296 | `<li>` 改 `<button>` + tabIndex + aria-expanded |
| I3 | 歷史載入失敗無可見回饋 | ChatPanel:116-118 | 加 error state + retry 按鈕 |
| I4 | Citation 解析依賴固定格式 `[來源n]` | ChatPanel:201-235 | 加 regex fallback + 後端欄位式引用 |
| I5 | RAG 長時間等待無進度提示 | ChatPanel:425-430 | 加「正在搜尋 N 個段落」+ 逾時提示 |
| I6 | 錯誤回覆無重試按鈕 | ChatPanel:181-186 | 加「重新提問」按鈕，保留原始問題 |

### [NICE-TO-HAVE] 優化建議

- N1: Greeting card 在使用者首次提問後自動收合
- N2: Citation chip 把相似度移到 tooltip，避免小螢幕換行
- N3: Input 加 placeholder 提示「按 Enter 送出」
- N4: 空狀態改為更視覺化的卡片式引導（參考 ChatGPT 首頁）
- N5: Auto-scroll 只在使用者已在底部時觸發（加 threshold 判斷）

---

## 三、會議摘要詳情頁 (Meeting Summary Detail)

### API 功能測試結果

| 測試項目 | 結果 | 備註 |
|---------|------|------|
| 會議列表載入 | ✅ PASS | 5 場會議正確顯示 |
| Summary JSON 品質 | ✅ PASS | 所有 COMPLETED 會議均有 summary_json |
| Summary embedding | ✅ PASS | 所有會議已嵌入 |
| Glossary 整合 | ✅ PASS | MeetingGlossaryPanel 正確渲染 |

### [IMPORTANT] 重要改善

| # | 問題 | 位置 | 建議 |
|---|------|------|------|
| I1 | 行動裝置無法選擇模板再重新生成 | DetailView:250-295, 601-610 | 手機版加 dropdown 或 bottom sheet |
| I2 | Speaker mapping 儲存觸發整頁 reload | DetailView:117-145 | 改局部 state 更新，避免 context 丟失 |
| I3 | 逐字稿折疊 + Audio player 分離 | DetailView:684-815, 862-879 | 首次載入提示「展開逐字稿可搭配音檔播放」 |
| I4 | 跨會議關聯被埋在頁面下方 | DetailView:589-592 | 移至 TL;DR 下方或加 anchor 快速跳轉 |
| I5 | 行動項目扁平化為純文字 | DetailView:515-524 | 改為表格/list 顯示 assignee + due date + status |

### [NICE-TO-HAVE] 優化建議

- N1: 完整摘要可考慮移到更上方位置，或加「AI 結論 / 原文」tab
- N2: 匯出完成後加 toast 回饋（目前靜默完成）
- N3: Transcript 講者編輯在手機寬度時改為 bottom sheet
- N4: Transcript 行加明確的「播放此段」hover affordance
- N5: 版本歷史預設收合，僅顯示「N 個版本」badge

---

## 四、Design Advisor 品牌一致性審查

### ✅ 符合規範

| 項目 | 狀態 |
|------|------|
| 奇美藍 (#003B7A) 作為 primary color | ✅ |
| 中文介面文案一致性 | ✅ |
| 字體預設 110% (useFontSize) | ✅ |
| Card-based layout pattern | ✅ |
| Sidebar 雙層 profile 架構 | ✅ |

### ⚠️ 需要改善

| 項目 | 問題 | 建議 |
|------|------|------|
| Native dialogs | `window.confirm` 不符品牌風格 | 統一改用自訂 Modal |
| 錯誤訊息風格不統一 | 部分用 toast、部分用 inline、部分用 console.log | 統一 Error 元件 |
| 空狀態設計缺插圖 | 多數空狀態只有文字 | 加品牌風格 illustration |
| Loading 動畫統一性 | 混用 Loader2 spinner 和 skeleton | 建立 Loading 規範 |

---

## 五、Taste Skill 互動品質評估

### 評分 (1-5 星)

| 維度 | 評分 | 說明 |
|------|------|------|
| **First impression** | ⭐⭐⭐⭐ | 登入後 dashboard 清爽，Greeting 有溫度 |
| **Core task flow** | ⭐⭐⭐½ | 上傳→等待→看摘要 順暢，但中間等待 UX 薄弱 |
| **Error recovery** | ⭐⭐½ | 多數錯誤只有 toast，缺乏就地恢復 |
| **Delight / polish** | ⭐⭐⭐ | RAG greeting 有心意，但整體缺少微動畫 |
| **Enterprise trust** | ⭐⭐⭐⭐ | 機密標記、MemPlace 隔離、Admin 管理完善 |
| **Mobile** | ⭐⭐½ | 基本可用但多處 UX 妥協（confirm、小寬度排版） |

### 整體評語

> MeetChi 在「功能完整度」和「企業安全性」表現優異，核心 pipeline (上傳→轉錄→摘要→RAG) 端到端流暢。
> 主要優化空間在於**狀態回饋**（uploading/processing 的即時感）和**錯誤恢復**（就地重試而非 generic toast）。
> 如果補上這兩塊，加上建議問題自動送出、行動項目結構化、Native dialog 品牌化，
> UX 品質可從 3.5★ 提升到 4.5★ 水準，接近 ChatGPT/Gemini 的互動體驗。

---

## 六、優先改善路線圖 (建議)

### Phase 1: Quick Wins (1-2 天)

| # | 項目 | 影響度 | 工時 |
|---|------|--------|------|
| 1 | 上傳防重複 guard | CRITICAL | 15 min |
| 2 | RAG 建議問題 chip 自動送出 | IMPORTANT | 10 min |
| 3 | Auto-scroll threshold 優化 | IMPORTANT | 20 min |
| 4 | Upload overlay 顯示進度 + 階段 | IMPORTANT | 30 min |
| 5 | 錯誤訊息加「重試」按鈕 | IMPORTANT | 30 min |

### Phase 2: UX Polish (3-5 天)

| # | 項目 | 影響度 | 工時 |
|---|------|--------|------|
| 6 | Native confirm → 品牌 Modal | IMPORTANT | 1 hr |
| 7 | 歷史面板鍵盤+ARIA 修正 | IMPORTANT | 1 hr |
| 8 | Action items 結構化顯示 | IMPORTANT | 2 hr |
| 9 | Speaker mapping 局部更新 | IMPORTANT | 2 hr |
| 10 | Mobile template selector | IMPORTANT | 1.5 hr |

### Phase 3: Delight (5-10 天)

| # | 項目 | 影響度 | 工時 |
|---|------|--------|------|
| 11 | 空狀態品牌插圖 | NICE-TO-HAVE | 3 hr |
| 12 | Resumable upload | NICE-TO-HAVE | 4 hr |
| 13 | Loading 微動畫統一 | NICE-TO-HAVE | 2 hr |
| 14 | Greeting auto-collapse | NICE-TO-HAVE | 30 min |
| 15 | 跨會議關聯提升可見性 | NICE-TO-HAVE | 1 hr |

---

## 附錄：測試環境

- Frontend: `meetchi-frontend-00044-t6g` (rev 00044)
- Backend: `meetchi-backend-00021-px6` (rev 00021)
- Database: Cloud SQL PostgreSQL (pgvector enabled)
- 測試帳號: jerry_tai@mail.chimei.com.tw (admin)
