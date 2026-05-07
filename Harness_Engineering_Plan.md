# MeetChi 專案 Harness Engineering 架構規劃

基於李宏毅教授《Harness Engineering》課程精神，結合**第一性原理**、**MECE 原則**與**模型思維 (Model-Thinking)**，我們針對 MeetChi 系統所規劃的「AI 駕馭框架 (Harness)」。

這套框架旨在解決 AI Agent 在開發過程中常見的「幻想完成」、「管殺不管埋（只寫扣不部署）」、「未經物理驗證的假正確」等問題，將任務流程封裝為結構化的檢查鏈條。

---

## 1. 原理分析 (First Principles & MECE)

為了讓 Agent 能穩健地驅動 MeetChi 從開發、測試到上線，我們將 Harness MECE（不遺漏、不重疊）地切割為四大面向：

| 面向 | 定義 | MeetChi 目前遇到的問題 | 解決方案 (Harness) |
| --- | --- | --- | --- |
| **認知邊界**<br/>(Context/Rules) | AI 對任務範圍與「完成 (Done)」的理解 | 認為修改完程式碼、沒報錯就是「任務完成」，忽略部署與線上環境。 | 透過根目錄的 `agents.md` 定義 **DoD (Definition of Done)**，重塑對於任務終點的世界觀。 |
| **流程控制**<br/>(Workflows) | AI 採取的逐步工作途徑 | 發散思維，開發完後未銜接 GCP 部署與測試 Workflow。 | 升級 `.agent/workflows/` (如 `planning.md`, `ultrawork.md`)，用 Checklist 強制串聯 `gcp-deploy`。 |
| **驗證反饋**<br/>(Feedback) | 確認任務結果的真實性 | 只依賴本地 Diagnostics，未取得雲端部署後的實體運作證據 (Actual Gradient)。 | 部署後強制執行 `e2e-test.md` 或 cURL health check，確保拿到真實的 HTTP 200 回饋才算數。 |
| **記憶沉澱**<br/>(Memory) | 系統長期運作的知識累積 | 隨著開發推進，舊的錯誤與架構演進不斷遺失，需重複踩坑。 | 利用 `update-docs.md` 搭配 QMD (MeetChi collection)，讓 Agent 的智慧沉澱到文件並注入回記憶。 |

---

## 2. 專屬 Harness 指令集

這裡定義了將要在 IDE 中推行的 Harness 指令，可以嵌入 `task.md` 模板或作為全局行為指引：

1. **強制先觀測 (Observe First)**
   - **指令**：在撰寫或修改任何 MeetChi 核心邏輯（如 RAG、ASR）之前，強制執行 `mcp_qmd_search` 查詢 `meetchi` collection，確認是否有已被踩過的雷或既定架構。
2. **零信任驗證 (Zero-Trust Feedback)**
   - **指令**：本地修改完必須跑 `npm run lint` 或 `pytest`；GCP 部署後必須拿到 `{"status":"healthy"}` 的 JSON 響應。不可光憑「代碼看起來沒錯」就宣布完成。
3. **強制收斂 (Forced Convergence)**
   - **指令**：所有功能變更任務，清單(`task.md`) 尾端強制掛上兩個節點：`[ ] 執行 /gcp-deploy` 與 `[ ] 執行 /update-docs`。

---

## 3. 面向 MeetChi 的 `agents.md` 提案

請將以下內容存為 `d:\Side_project\MeetChi\agents.md`，這將成為 AI 每次啟動任務前強制閱讀的「大憲章」：

```markdown
# MeetChi AI Agent Harness & Cognitive Rules

歡迎來到 MeetChi 專案。這是一套結合會議音訊識別 (ASR)、大型語言模型整理 (LLM)、與 RAG 架構的全棧端到端系統。
作為本專案的 AI Engineer，你必須嚴格遵守以下 Harness Engineering 原則：

## 1. 認知邊界：完成定義 (Definition of Done, DoD)
當你接到「修復 Bug」、「優化模組」或「新增功能」的任務時，只有完成以下 **所有** 階段，才允許宣稱任務結束：
- [ ] **Research**: 修改前，使用 QMD 或 grep 確認有沒有類似的實作或災情紀錄。
- [ ] **Implementation**: 完成程式碼撰寫與修改。
- [ ] **Local Verification**: 執行無錯誤 (Diagnostics clean) 與本地測試。
- [ ] **Deployment**: 自動載入並執行 `.agent/workflows/gcp-deploy.md` 上雲。不准問「需要幫您部署嗎？」，需主動完成。
- [ ] **Production Verification**: 部署成功後，必須 cURL 訪問 Cloud Run Health Check Endpoint 或啟動 `/e2e-test.md`，確保服務不為 503 且正常運作。
- [ ] **Documentation**: 如果有架構等級的變更，啟動 `/update-docs.md` 進行記憶沉澱。

## 2. 流程控制：嚴禁越俎代庖的猜測
- **不可幻想完成**：在給出「我已經修好這個問題」的結論前，必須給出執行的命令與驗證測試的 Output 證據。
- **依賴 Workflows**：專案下有一系列標準的 `.agent/workflows`，遇到部署、測試或 Debug 情境時，優先呼叫 workflow 來執行，不要重造輪子進行 bash 組合。
  - 遇到 GCP 連線問題 -> 使用 `/gcp-deploy` 指南
  - 遇到 ASR Diarization Bug -> 觸發 `/bug-fix-asr-diarization`
  - 找不到 Bug 根因 -> 退回 `/debug-pipeline`

## 3. 安全與權限控制
- **自動化執行**：當你處於 ultrawork 模式或依照 workflow 執行 `gcloud` 或 `terraform` 步驟時，你有權限將 `SafeToAutoRun` 設為 `true`，以防中斷自動化驗收鏈條。
- **變數管理**：所有環境變數與 Secret 異動，以 Terraform (.tf 檔) 為 Source of Truth，請勿隨意用 `gcloud --set-*` 覆蓋全部變數。

如果你理解了以上規則，請在今後的會話中，將其貫徹於你的 task.md 規劃與最終結案報告中。
```
