# MeetChi 三層 Persona UX 稽核報告 v2 — P0 修復後覆核

> 日期：2026-06-29  
> 前次稽核：2026-06-25（P0 修復前）  
> 本次目的：驗證 P0 修復效果 + 發現新問題  
> 範圍：完整前後端（Dashboard → MeetingCard → DetailView → 後端 API）

---

## 修復驗證矩陣（vs 2026-06-25 稽核）

| 原始 P0 | 修復狀態 | 殘留問題 |
|---------|:--------:|---------|
| F1: 無心跳反饋 | ✅ 已修 | `ProcessingHeartbeat` 即時秒數 + 脈動燈 |
| F2: 離開頁面無通知 | ✅ 已修 | Tab title `(N 完成 / M 處理中) MeetChi` |
| F3: Failed 無原因 | ✅ 已修 | MeetingCard 顯示 `failureReason` + 失敗階段 |

**新增功能效果：**
- ✅ TRANSCRIBED CTA：「📄 逐字稿已可查看」+ 脈動動畫
- ✅ diarizing 階段：前端 STAGE_CONFIG 已補
- ✅ Polling 10s：比 60s 快 6 倍，使用者感知更即時

---

## 🟢 新手 Persona 覆核

> 角色同前：第一次使用的行政助理

### 已解決的問題

| 原問題 | 現狀 |
|--------|------|
| N2: 處理中無心跳 | ✅ 有秒數計時器 + 脈動燈，明確知道系統在跑 |
| N3: ETA 不遞減 | ⚠️ 部分解決 — 10s polling 時重新計算，但仍是靜態估算 |
| N4: TRANSCRIBED 無通知 | ✅ 卡片顯示「📄 逐字稿已可查看」CTA |

### 新發現的問題

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| N8 | DetailView processing 狀態的步驟條缺少 `diarizing` | 一致性 | **P1** | MeetingCard 有 4 步（含辨識講者），DetailView 仍只有 3 步 |
| N9 | DetailView processing 標題缺 `diarizing` case | 功能正確性 | P1 | `meeting.processingStage === 'diarizing'` 時顯示「AI 正在處理中...」（fallback） |
| N10 | 心跳計時器從 `createdAt` 開始算，非實際開始處理時間 | 信任/安全感 | P2 | 如果上傳後 5 分鐘才開始處理，顯示「已處理 5 分 00 秒」不準 |
| N11 | UploadTray 的 processing 狀態無心跳/秒數 | 一致性 | P2 | UploadTray 只顯示「AI 處理中（約 X 分鐘）」，MeetingCard 有秒數計時 |

---

## 🟡 一般使用者 Persona 覆核

> 角色同前：每週用 3-5 場的業務經理

### 已解決的問題

| 原問題 | 現狀 |
|--------|------|
| U1: 離開頁面無通知 | ✅ Tab title 有即時狀態 |
| U6: TRANSCRIBED 無 CTA | ✅ 有明確「可先查看」提示 |

### 新發現的問題

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| U7 | Tab title 在非 dashboard 頁面不更新 | 功能正確性 | P1 | 如果使用者在 `/dashboard/meetings/{id}` 詳情頁，Tab title logic 不執行（只在 page.tsx） |
| U8 | Polling 10s 但 API response 有 `failure_reason` 殘留 | 邊界/錯誤處理 | **P0** | meeting `9a69a4f4` 狀態 COMPLETED 但仍帶舊的 failure_reason → 卡片不顯示失敗（因為 status=completed），但若重新進入 failed 又會顯示過時的錯誤訊息 |
| U9 | `completed_at` 欄位存在但前端未使用 | 功能正確性 | P2 | 後端有 completed_at，前端 MeetingCard 只顯示 createdAt（上傳日期） |
| U10 | meeting 9a69a4f4 status=COMPLETED 但 summary 為空 | 邊界/錯誤處理 | **P0** | Plan B 邏輯問題：transcription 成功後 status 被標為 COMPLETED，但 summary 生成失敗時沒有保留 TRANSCRIBED 狀態 |
| U11 | 前端 `api.ts` 的 processing_stage type 未包含 `diarizing` | 一致性 | P1 | TypeScript 類型定義與後端不一致，IDE 會報類型警告 |

---

## 🔴 專業使用者 Persona 覆核

> 角色同前：IT 管理員 / 專案 PM

### 已解決的問題

| 原問題 | 現狀 |
|--------|------|
| P3: Failed 無原因 | ✅ MeetingCard + DetailView 都顯示 failureReason |
| P4: diarizing 前端缺失 | ⚠️ MeetingCard 有，DetailView 未同步 |

### 新發現的問題

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| P9 | `failure_reason` 未被清除（COMPLETED 時仍殘留） | 邊界/錯誤處理 | **P0** | 後端在成功重新處理後未 clear failure_reason → 可能讓管理者誤判 |
| P10 | DetailView 的 stage progress bar 硬編碼 3 步 | 一致性 | P1 | 與 MeetingCard 4 步不一致；如果後端將來加更多階段會持續不同步 |
| P11 | GPU Queue Stats 仍未接入前端 | 功能正確性 | P2 | `/admin/gpu-queue-stats` API ready，前端仍無「排隊深度」顯示 |
| P12 | Polling 10s 對已完成的 dashboard 有不必要的 API 負載 | 非功能面 | P2 | 沒有 processing meetings 時 10s interval 不會啟動（needsSafetyNet=false） ✅ OK — 但如果有 1 場在跑，所有 meetings 都會 refetch |
| P13 | email 通知仍未上線（Cloud Run port 25 blocked） | 非功能面 | P1 | 需要 SMTP relay 配置才能啟用 |

---

## 🏆 整合：新 P0 問題（立即需修復）

| # | 問題 | 影響 | 建議修法 |
|---|------|------|---------|
| **U8/P9** | `failure_reason` 成功後未清除 | COMPLETED 會議帶殘留錯誤訊息，管理者誤判 | 後端 tasks.py 成功時 `UPDATE meetings SET failure_reason = NULL` |
| **U10** | meeting COMPLETED 但 summary 為空 | 使用者進入詳情頁看到空摘要 + 「生成摘要」按鈕 | 確認 Plan B 邏輯：只有 transcription 成功 + summary 成功才設 COMPLETED；否則應是 TRANSCRIBED |

---

## P1 問題（本週修復）

| # | 問題 | 建議修法 |
|---|------|---------|
| **N8/N9/P10** | DetailView processing steps 缺 diarizing | 同步 STAGE_CONFIG 邏輯到 DetailView（加 diarizing case） |
| **U7** | Tab title 只在 dashboard page 生效 | 將 title logic 提升到 layout.tsx 或用 custom hook |
| **U11** | api.ts processing_stage type 缺 diarizing | 更新 TypeScript 類型定義 |
| **P13** | Email 通知未上線 | 等待 SMTP relay 配置 |

---

## 與上次稽核的 Delta 摘要

```
2026-06-25 稽核: 3 P0 + 7 P1 + 5 P2 = 15 issues
2026-06-29 覆核: 
  - 原 3 P0: 全部修復 ✅
  - 新 2 P0: failure_reason 殘留 + COMPLETED 但 summary 空
  - 新 4 P1: DetailView diarizing 同步、tab title scope、type def、email
  - 新 4 P2: 心跳起算點、UploadTray 一致性、completed_at、queue stats

  淨改善: -3 P0 +2 P0 = 少 1 個 P0 (進步)
  總殘留: 2 P0 + 4 P1 + 4 P2 = 10 issues
```

---

## 建議修復優先級

1. **立即** (30min): 後端清除 failure_reason on success + 確認 Plan B status 邏輯
2. **今天** (1hr): DetailView 同步 diarizing + api.ts type fix
3. **本週**: Tab title hook 提升 + email SMTP relay
4. **Backlog**: GPU queue 前端接入 + completed_at 顯示
