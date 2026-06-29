# 模板管理 三層 Persona UX 稽核報告

> 日期：2026-06-29  
> 範圍：模板管理功能（Template Gallery + Template Editor + Upload 模板選擇 + DetailView 重生模板選擇）  
> 元件：Sidebar 入口 → TemplateGallery → TemplateEditor / Preview Modal  
> 後端：`/api/v1/templates` (CRUD) + `template_engine.py` (system templates)  
> 資料模型：`SummaryTemplateModel` (DB) + `TemplateSchema` (code-defined)

---

## 架構概要

- **系統模板（9 個）**：general, sales_bant, hr_star, rd, project_review, brainstorm, standup, retrospective, client_requirements, training — 程式碼定義，不可修改
- **自訂模板**：使用者透過 Fork 系統模板建立，存 DB，可 CRUD
- **使用者權限**：⚠️ **完全沒有** — API 無 auth、無 owner 檢查、所有使用者共享所有模板

---

## 🟢 新手 Persona（第一次使用的行政助理）

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| T-N1 | 「Fork」一詞對非技術使用者完全陌生 | 流程可用性 | **P0** | 按鈕寫「Fork」（Git 術語），行政助理不知道是什麼意思。應改為「複製為我的版本」或「建立副本」。 |
| T-N2 | 不知道模板的用途是什麼 | 流程可用性 | **P1** | 進入模板管理頁面只看到一堆卡片，頁面描述「選擇適合會議類型的摘要模板，或 Fork 建立客製版本」，但新手不懂「摘要模板」是什麼概念。缺乏一段 2-3 句的說明：「不同類型的會議，AI 會用不同的框架整理摘要。例如業務會議用 BANT 框架、面試用 STAR 法則。」 |
| T-N3 | 操作按鈕預設隱藏（hover 才出現） | 流程可用性 | P2 | 行動操作 (預覽/Fork/編輯/刪除) 需要 hover 才能看見 (`opacity-0 group-hover:opacity-100`)。觸控裝置用戶永遠看不到。新手甚至不知道可以對模板做什麼。 |
| T-N4 | 預覽 Modal 內容太技術化 | 流程可用性 | **P1** | 預覽顯示 `output_key`（如 `action_items`）和 `output_type`（如 `list`），這些是開發者術語。新手只需看到「這個模板會產出：✓ 會議摘要 ✓ 行動項目 ✓ 關鍵決議」。 |
| T-N5 | 沒有「這個模板產出長什麼樣」的範例 | 流程可用性 | P2 | 使用者無法預覽「用這個模板實際跑出來的摘要會長什麼樣」。只看到指令文字，無法做選擇決策。 |
| T-N6 | 搜尋框在上方，分類 tab 在下方，頁面層次不清 | 流程可用性 | P2 | 搜尋與分類是兩種篩選維度但沒有視覺分隔，容易混淆。 |
| T-N7 | 「自訂」分類與「建立自訂模板」是不同概念但文字相同 | 一致性 | P2 | Category tab 有「自訂」（顯示已建立的 custom 模板），Fork 動作也產出「自訂」模板。使用者搞混「查看 vs 建立」。 |

---

## 🟡 一般使用者 Persona（每週使用的業務經理）

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| T-U1 | Fork 產出的模板名稱 `template_name_custom_1719...` 不友善 | 邊界/錯誤處理 | **P1** | Fork 自動命名 `${template.name}_custom_${Date.now()}`，產出如 `general_custom_1719619200000`。使用者必須進入編輯才能改名。應該在 Fork 時彈窗讓使用者命名。 |
| T-U2 | 無法知道「我目前上傳用的是哪個模板」 | 一致性 | **P1** | 模板管理頁面與上傳頁面之間沒有明確的連結。使用者在模板頁看到 10 個模板，但不知道哪個是「預設」的。 |
| T-U3 | 刪除模板不會檢查是否有會議正在使用 | 邊界/錯誤處理 | **P1** | 如果刪除一個 custom 模板，已經用該模板生成摘要的會議在 DetailView 的「重新生成摘要」下拉選單中會找不到原模板。summary_versions 表的 template_name 會變成 orphan。 |
| T-U4 | 編輯器沒有「取消編輯」確認 | 邊界/錯誤處理 | P2 | 使用者在 TemplateEditor 改了一堆東西後按「取消」，直接丟失所有修改，沒有「確定要放棄修改嗎？」確認。 |
| T-U5 | 編輯器中「段落標題」與「output_key」的關係不清楚 | 流程可用性 | P2 | 業務經理不理解為何同一段落要填「段落標題」又要填「output_key」。output_key 是給程式用的，使用者不該接觸。 |
| T-U6 | 模板卡片上沒有顯示「已被幾場會議使用」 | 效率 | P2 | 無法判斷哪個模板最常用/最有價值，難以做管理決策。 |
| T-U7 | Fork 系統模板後進入編輯器，但使用者可能只想「使用」不想「修改」 | 流程可用性 | P2 | Fork 完立刻跳進編輯器 (line 80: `setEditingTemplate(forked)`)，使用者可能只想先試用看看效果。應該是 Fork 後留在列表，可選擇後續再編輯。 |
| T-U8 | 上傳時的模板選擇器與模板管理頁沒有互通 | 一致性 | P2 | 上傳 modal 有一個模板下拉選單，但如果使用者剛建了新模板，需要重新整理頁面才能在上傳選單中看到。 |
| T-U9 | 模板管理頁面沒有「設為預設」功能 | 效率 | **P1** | 每次上傳都要手動選模板。業務經理最常用的是 `sales_bant`，但系統永遠預設 `general`。應允許使用者設定自己的預設模板。 |

---

## 🔴 專業使用者 Persona（IT 管理員 / 深度使用的 PM）

| # | 問題 | 維度 | 嚴重度 | 說明 |
|---|------|------|--------|------|
| T-P1 | **模板 API 完全沒有使用者權限控制** | 信任/安全感 | **P0** | `/api/v1/templates` 的 CRUD 無任何 auth。任何人可以：(1) 看到所有人建的模板 (2) 編輯/刪除別人的模板 (3) 建立無限模板。DB model 有 `created_by` 欄位但從未使用。 |
| T-P2 | 所有使用者看到所有自訂模板（無租戶隔離） | 信任/安全感 | **P0** | list API 回傳所有 `is_active=True` 的 DB 模板。A 使用者建的模板，B 使用者也能看到並修改。在企業環境中需要：(1) 個人模板 (2) 部門共享模板 (3) 全域系統模板三層。 |
| T-P3 | 無操作日誌/版本歷史 | 邊界/錯誤處理 | P1 | 模板被修改或刪除後無法追溯是誰改的、改了什麼。`updated_at` 只記時間不記人。 |
| T-P4 | DB model 有 `created_by` 但 API 從未填值 | 功能正確性 | **P1** | `SummaryTemplateModel.created_by` 欄位永遠是 NULL。create API (line 155-195) 沒有從 session 取得使用者身分。 |
| T-P5 | 模板名稱 `name` 欄位 unique constraint 可能衝突 | 邊界/錯誤處理 | P1 | Fork 產生的 name = `{template.name}_custom_{timestamp}` 用毫秒時間戳避免碰撞，但如果兩人同時 Fork 同一模板（雖機率極低），DB 會 500 而非友善錯誤。 |
| T-P6 | 系統模板無法「停用」 | 效率 | P2 | 9 個系統模板全部顯示。如果公司只用 2-3 種會議類型，其他 6-7 個是噪音。應允許管理員停用不需要的系統模板。 |
| T-P7 | 刪除是硬刪除（DELETE） | 邊界/錯誤處理 | P2 | `db.delete(dt)` 是永久刪除，不是軟刪除。如果使用者誤刪，沒有還原機會。應改為 `is_active=False`（已有欄位但 DELETE endpoint 未使用）。 |
| T-P8 | 無法批次管理模板 | 效率 | P2 | 如果要清理多個廢棄模板，需要一個一個刪。無全選/批次操作。 |
| T-P9 | 模板 sections 的 instruction 欄位對 prompt injection 無防護 | 信任/安全感 | P1 | 使用者可以在 `instruction` 中寫任意 LLM 指令（如「忽略所有之前的指令」）。需要至少基本的 sanitization 或長度限制。 |
| T-P10 | 編輯器無即時預覽（dry run） | 效率 | P2 | 修改 sections 後無法知道改了之後的摘要長什麼樣。需要一個「用範例會議預覽」功能。 |
| T-P11 | 模板 API 無 pagination | 非功能面 | P2 | `list_templates` 回傳全部。如果自訂模板很多（10+），效能和前端渲染都會受影響。 |

---

## 整合優先級

### P0（安全/核心缺陷 — 必須修復）

| # | 問題 | 建議修法 |
|---|------|---------|
| **T-N1** | Fork 術語非技術者不懂 | 改按鈕文字為「📋 複製為我的版本」|
| **T-P1** | API 無使用者權限 | 加入 `get_current_user` 依賴，所有 CRUD 需驗證登入身分 |
| **T-P2** | 無租戶隔離 | 個人模板限本人可見(owner_upn)；加 `visibility: private/shared/public` 欄位 |

### P1（一週內修復）

| # | 問題 | 建議修法 |
|---|------|---------|
| **T-N2** | 缺乏用途說明 | 在頁面頂部加一段「模板決定 AI 用什麼框架整理您的會議」的引導文字 |
| **T-N4** | 預覽太技術化 | 隱藏 output_key/output_type，只顯示段落標題 + 一句話說明 |
| **T-U1** | Fork 名稱不友善 | Fork 時彈出命名對話框 |
| **T-U2** | 不知道目前使用的模板 | 模板卡片上標注「✓ 目前預設」或「上次使用」|
| **T-U3** | 刪除不檢查使用中 | 刪除前查詢是否有會議使用此模板，顯示警告 |
| **T-U9** | 無「設為預設」| 加「⭐ 設為我的預設」按鈕，存到 user preferences |
| **T-P3** | 無操作日誌 | 記錄 created_by + updated_by + 變更歷史 |
| **T-P4** | created_by 未填 | Create API 從 session 取得 user_upn 填入 |
| **T-P5** | name 碰撞 500 | 加 try/except IntegrityError → 重試 with 隨機後綴 |
| **T-P9** | Prompt injection | 限制 instruction 長度 (max 500 char) + 禁止特定 pattern |

### P2（Backlog）

| # | 建議 |
|---|------|
| T-N3 | 操作按鈕改為 always visible（或至少觸控裝置時） |
| T-N5 | 加「範例輸出預覽」功能 |
| T-N6 | 搜尋 + 分類加視覺區隔 |
| T-N7 | 分類 tab 的「自訂」改為「我的模板」|
| T-U4 | 編輯器取消加確認對話框 |
| T-U5 | 隱藏 output_key（或自動從標題生成）|
| T-U6 | 卡片顯示「已用於 N 場會議」|
| T-U7 | Fork 後不自動進入編輯器，改為 toast + 留在列表 |
| T-U8 | 模板建立後通知上傳選單刷新 |
| T-P6 | 管理員可停用系統模板 |
| T-P7 | 硬刪除改為軟刪除 (is_active=False) |
| T-P8 | 批次管理 UI |
| T-P10 | 編輯器加 dry-run 預覽 |
| T-P11 | API 加 pagination |

---

## MECE 維度覆蓋檢查

| 維度 | 覆蓋問題 |
|------|---------|
| 功能正確性 | T-P4 |
| 流程可用性 | T-N1, T-N2, T-N4, T-N5, T-N6, T-U5, T-U7 |
| 邊界/錯誤處理 | T-U1, T-U3, T-U4, T-P3, T-P5, T-P7 |
| 一致性 | T-N7, T-U2, T-U8 |
| 信任/安全感 | T-P1, T-P2, T-P9 |
| 效率 | T-U6, T-U9, T-P6, T-P8, T-P10 |
| 非功能面 | T-P11 |

---

## 總結

```
模板管理稽核結果：3 P0 + 10 P1 + 14 P2 = 27 issues

核心問題：
  1. 安全性（P0）：API 完全無權限控制、無租戶隔離
  2. 可用性（P0）：Git 術語「Fork」非技術使用者無法理解
  3. 功能缺口：無預設模板設定、無使用統計、無操作追溯

UX 成熟度：α 階段
  - 基本 CRUD 功能完整
  - 權限/隔離/可用性嚴重不足，不適合多人共用環境
  - DB schema 已預留 created_by/is_active 但後端邏輯未接入
```
