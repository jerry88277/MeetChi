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

## 4. ML 模型供應鏈安全 (Model Supply Chain Security)

### 4.1 強制規則：模型不得未經掃描進入生產環境
任何從外部來源（HuggingFace Hub、GitHub Releases、第三方）下載的 ML 模型檔案，**必須**經過安全掃描後才能部署至 GCS 或 bake 進 Docker Image。

### 4.2 掃描工具與版本要求
| 工具 | 最低版本 | 用途 | 來源驗證 |
|------|---------|------|---------|
| ModelScan | ≥ 0.8.8 | 全格式掃描（safetensors, pickle, h5, SavedModel） | Protect AI → Palo Alto Networks 旗下 |
| Fickling | ≥ 0.1.11 | Pickle 格式專精靜態分析 + runtime hook | Trail of Bits（頂尖資安顧問） |

**版本鎖定理由**：Fickling < 0.1.7 存在 CVE-2026-22608/22609/22612 繞過漏洞。

### 4.3 Pipeline 架構（Scan-Then-Deploy）
```
Download (parallel) → Security Gate → Upload to GCS
                         │
                    scan fails? → exit 1, 不上傳
```

- 實作檔案：`cloudbuild-models.yaml`
- 共用卷掛載：`/mnt/models`（Cloud Build volumes）
- 下載與上傳分離：模型先存 volume，掃描通過後才 gsutil 上傳

### 4.4 觸發時機
以下情境必須執行模型安全掃描：
1. 新增或更換 ASR / Diarization / Embedding 模型
2. 升級模型版本（例如 pyannote 3.1 → 4.0）
3. 將模型從 runtime-download 改為 bake-into-image
4. 定期排程（建議每月一次重新掃描既有模型）

### 4.5 失敗處置
- ModelScan 回報 `CRITICAL` 或 `HIGH` → **立即停止**，不得繼續部署
- Fickling 回報 `UNSAFE` 或 `OVERTLY_MALICIOUS` → **立即停止**
- 需人工調查後，在 Issue Tracker 記錄調查結果才可放行

## 5. Agent 可攜性 (LLM-Agnostic Compliance)

本文件為 **LLM-Agnostic** 設計。無論由 Claude、GPT、Gemini、或其他 LLM 驅動的 AI Agent 執行任務，均須遵守以上所有規則。

### 5.1 跨 LLM 相容性設計原則
- **聲明式規則**：所有規則以「條件 → 動作」的確定性語句撰寫，不依賴特定 LLM 的 system prompt 語法
- **工具無關**：規則引用通用 CLI 工具（gcloud, gsutil, pip, curl），不綁定特定 IDE 或 Agent 框架
- **可驗證**：每條規則的遵守與否，可透過 stdout/stderr 輸出客觀判斷

### 5.2 各 LLM 平台的載入方式
| 平台 | 載入方式 |
|------|---------|
| Claude (Anthropic) | 專案根目錄 `agents.md` 自動載入，或透過 CLAUDE.md |
| GitHub Copilot | 專案根目錄 `agents.md` 或 `.github/copilot-instructions.md` |
| Cursor | `.cursorrules` 內引用本檔 |
| Windsurf | `.windsurfrules` 內引用本檔 |
| GPT (OpenAI) | System prompt 中引用本檔內容 |
| Gemini (Google) | Context window 中載入本檔 |

### 5.3 規則更新協議
- 修改本文件時，必須在 commit message 中標注 `[agent-rules]` tag
- 新增規則必須包含：觸發條件、執行動作、驗證方式 三要素
- 刪除規則必須附上理由與替代方案

## 6. 時區與時間顯示規則 (Timezone Convention)

### 6.1 強制規則：所有時間一律使用 UTC+8（Asia/Taipei）
- **觸發條件**：任何需要向使用者呈現時間戳的場景（log 分析、部署時間、測試報告、進度回報等）
- **執行動作**：將 UTC 時間轉換為 `UTC+8`（台北時間）後再呈現，格式為 `YYYY-MM-DD HH:MM:SS (UTC+8)` 或 `HH:MM:SS (台北)`
- **驗證方式**：輸出中不得出現未標注時區的裸 UTC 時間；若原始資料為 UTC，必須加 8 小時後顯示

### 6.2 例外
- 原始 log 引用（作為證據保留原始 UTC 時間時），需額外標注對應的台北時間
- 程式碼內部仍應使用 UTC 儲存，僅在「面向使用者的輸出」層做轉換

## 7. GPU ASR Image 建置規則 (Diarization 模型不得遺漏)

> **背景事故（2026-07-08）**：以 `cloudbuild-gpu-asr.yaml`（`Dockerfile.gpu-service`）
> 重建 GPU image 修 zh-nan bug，該 build **未 bake pyannote 模型、未設 `PYANNOTE_MODEL_PATH`**
> → 退回 runtime 從 HF 下載 → 撞上無效 `HF_TOKEN`（14 字元佔位值）→ diarization 全失敗 →
> 整場會議 0 說話者標籤（`speaker_mappings=null`）。逐字稿正常但講者資訊全失。

### 7.1 強制規則：GPU image 的唯一正確建置來源
- **觸發條件**：任何需要重建 / 部署 `meetchi-gpu-asr` 服務的情境（修 ASR bug、改語言邏輯、
  升級 provider 等）。
- **執行動作**：**一律使用 `apps/backend/cloudbuild-community1.yaml`**
  （對應 `Dockerfile.gpu-service-community1`）建置。此 config 會：
  1. 從 GCS `gs://prj-ai-meetchi-du-meetchi-audio/models/pyannote/speaker-diarization-community-1`
     `gsutil cp` 下載 baked pyannote 模型；
  2. `COPY models/pyannote/... ` 進 image、設 `ENV PYANNOTE_MODEL_PATH=/app/models/...`；
  3. 使 diarization 走**本地模型**，不依賴 runtime HF 下載。
  ```bash
  gcloud builds submit --config apps/backend/cloudbuild-community1.yaml apps/backend \
    --substitutions=_IMAGE_TAG="<meaningful-tag>" --project prj-ai-meetchi-du
  ```
- **禁止**：以 `cloudbuild-gpu-asr.yaml` / `Dockerfile.gpu-service` 建置生產 GPU image
  （該版本缺 baked 模型，僅供無 diarization 的實驗，已於檔頭標註 DEPRECATED）。

### 7.2 驗證方式（部署後必做，物理證據）
- 上傳一場多人音檔（或重跑既有會議），確認 GPU log 出現
  `Done for ...: N segments, K speakers`，且 **K > 0**（非 `0 speakers`）。
- DB 檢查：`transcript_segments.speaker` 非空、`meetings.speaker_mappings` 非 null。
- 若見 `Pipeline.from_pretrained returned None` / `Invalid user token` → 即為用錯 build，
  退回 §7.1 以 community1 config 重建。

### 7.3 模型異動時的合規串接
- 若需**更新** pyannote 版本或重新下載模型：先依 §4（ModelScan + Fickling 掃描）通過後，
  才 `gsutil` 上傳至上述 GCS 路徑，再以 §7.1 重建 image。

---

請將以上 Harness 控制規則深刻內化於每次生成的 `task.md` 之中。沒有經過 Evaluator (驗證層) 的程式碼，不叫完成。
