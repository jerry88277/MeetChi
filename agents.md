# MeetChi AI Agent Harness & Cognitive Rules

歡迎來到 MeetChi 專案。這是一套結合會議音訊識別 (ASR)、大型語言模型語意整理 (LLM) 與 RAG 架構的全棧端到端系統。
作為本專案的 AI Engineer，你必須嚴格遵守以下由「Harness Engineering」推行而來的工作原則：

## 1. 認知邊界：完成定義 (Definition of Done, DoD)
當你接到「修復 Bug」、「優化模組」或「新增功能」的任務時，你必須認知到：修改完程式碼並不是終點。只有完成以下 **所有** 階段，才允許宣稱任務結束：
1. **Research (謀定後動)**：修改 codebase 前，優先使用 `mcp_qmd_search` (查詢 `meetchi` collection)，確認是否有踩過的雷或既定架構模式。
2. **Implementation (實作)**：完成程式碼與設定的修改。
3. **Local Verification (本地驗證)**：主動執行 Diagnostic、`npm run lint` 或 `pytest`。不能全憑「肉眼除錯」。
4. **Deployment (強制上線)**：若功能涉及後端或前端交付，必須自動依循 `.agent/workflows/gcp-deploy.md` 執行部署上雲。不准停下來單純詢問「需要幫您部署嗎？」，應將其直接視為任務的必要收斂環節。
5. **Production Verification (真實物理反饋)**：部署完成後，必須發送 cURL 請求到實際的 API endpoint (例如 `/health`) 或觸發 `/e2e-test`，確保服務不回傳 503 且能正常回應。
6. **Documentation (記憶沉澱)**：若發生架構層變更，觸發 `/update-docs.md` 更新系統文件，避免知識風化。

## 2. 流程控制：嚴禁幻想與越俎代庖
- **No Hallucinations**：在宣告「我已修復此問題」或「服務已啟動」之前，你必須擁有系統層面的 stdout/stderr Output 作為物理證據 (Actual Gradient)。
- **活用 Workflows**：當面臨特定的標準情境時，應直接載入對應的工作流程 (Workflow) 來控管你的行為步調，拒絕重造輪子：
  - 遇到 GCP 連線問題 -> 利用 `/gcp-deploy` 內的排誤指南。
  - 遇到 ASR Diarization Bug -> 觸發 `/bug-fix-asr-diarization`。
  - 找不到 Bug 根因 -> 退回 `/debug-pipeline` 建立 11 個觀測點。

## 3. 安全邊界與權限控制
- **自動化賦權**：當你處於 `/ultrawork` 模式，或正在依照白名單的工作流程執行 `gcloud` 或 `terraform` 指令時，為了保持自動化鏈條不中斷，你擁有最高判斷權將 `SafeToAutoRun` 參數強制設定為 `true`。
- **變數與配置**：任何涉及 GCP 環境變數、Secret 的全域性變更， Source of Truth 必須是 `terraform/**/*.tf` 檔案。切勿使用 `gcloud --set-*` 指令直接暴力覆蓋現行所有佈署設定。

請將以上 Harness 控制規則深刻內化於每次生成的 `task.md` 之中。沒有經過 Evaluator (驗證層) 的程式碼，不叫完成。
