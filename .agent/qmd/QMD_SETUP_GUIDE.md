# QMD 記憶庫建置流程（Windows）

> **版本**：v1.0 · **建置日期**：2026-02-12  
> **適用環境**：Windows + Bun + Antigravity IDE  
> **核心工具**：[tobi/qmd](https://github.com/tobi/qmd) — 本地 BM25 + Vector + LLM Re-ranking 搜尋引擎

---

## 架構概覽

```
┌─────────────────────────────────────────────┐
│  Layer 3: Global（全域知識）                  │
│  ~/.gemini/antigravity/qmd-global/           │
│  QMD collection: "global"                    │
│  用途：通用 patterns、技術偏好、跨專案知識      │
├─────────────────────────────────────────────┤
│  Layer 2: Project（專案知識）                 │
│  <project>/.agent/qmd/                      │
│  QMD collection: "<project-name>"            │
│  用途：架構決策、API patterns、troubleshooting │
├─────────────────────────────────────────────┤
│  Layer 1: Ephemeral（會話層）                 │
│  Antigravity brain/ 目錄                     │
│  用途：單次會話，結束後蒸餾至 L2/L3            │
└─────────────────────────────────────────────┘
```

---

## Phase 1: 安裝 QMD

### 1.1 確認 Bun 已安裝

```powershell
bun --version
# 須 >= 1.0.0，本次驗證版本：1.3.6
```

### 1.2 全域安裝 QMD

```powershell
bun install -g https://github.com/tobi/qmd
```

> [!WARNING]
> **已知問題**：  
> - `sqlite-vec-win32-x64` 可能返回 404（alpha 套件），但 `sqlite-vec-windows-x64` 會正常安裝，不影響功能  
> - 安裝時間較長（~2 min），因需下載 `node-llama-cpp` 平台二進位檔  
> - 若出現 `Integrity check failed`，執行 `bun pm cache rm` 後重試

### 1.3 建立 Windows Wrapper

Bun 的 shim 使用 `#!/usr/bin/env bash`，Windows 下無法直接執行。需建立 `.cmd` wrapper：

**檔案**：`C:\Users\User\.bun\bin\qmd.cmd`

```batch
@echo off
bun --cwd "C:\Users\User\.bun\install\global\node_modules\qmd" src/qmd.ts %*
```

### 1.4 手動建立 Cache 目錄

QMD 原始碼使用 `mkdir -p`（Unix 指令），在 Windows 不會自動建立 cache 目錄：

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cache\qmd"
```

> [!IMPORTANT]
> **不執行此步驟會導致所有 QMD 命令失敗**（SQLite 初始化錯誤），錯誤訊息不直觀（顯示 `getDb()` stack trace）。

### 1.5 驗證安裝

```powershell
$env:Path = "C:\Users\User\.bun\bin;$env:Path"
qmd.cmd --help
```

預期輸出包含：
```
Index: C:/Users/User/.cache/qmd/index.sqlite
Models: embeddinggemma-300M-Q8_0, qwen3-reranker-0.6b-q8_0, Qwen3-0.6B-Q8_0
```

---

## Phase 2: 建立記憶庫結構

### 2.1 建立目錄

```powershell
# 全域記憶庫
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.gemini\antigravity\qmd-global"

# 專案記憶庫（以 MeetChi 為例）
New-Item -ItemType Directory -Force -Path "D:\Side_project\MeetChi\.agent\qmd"
```

### 2.2 註冊 QMD Collections

```powershell
$env:Path = "C:\Users\User\.bun\bin;$env:Path"

# 全域 collection
qmd.cmd collection add "$env:USERPROFILE\.gemini\antigravity\qmd-global" --name global --mask "**/*.md"

# 專案 collection
qmd.cmd collection add "D:\Side_project\MeetChi\.agent\qmd" --name meetchi --mask "**/*.md"
```

> [!NOTE]
> **PowerShell 誤報錯誤**：QMD 的 stderr 輸出（如進度條）會被 PowerShell 解讀為 `NativeCommandError`。只要看到 `✓ Collection created successfully` 就是成功。

### 2.3 設定 Context Descriptions

Context 讓搜尋引擎理解各 collection 的內容主題：

```powershell
qmd.cmd context add qmd://global "Global coding patterns, technical preferences, and universal best practices for all projects"

qmd.cmd context add qmd://meetchi "MeetChi project knowledge base: streaming ASR, WebSocket protocol, Cloud Run GPU, Terraform IaC, Gemini API integration"
```

### 2.4 驗證

```powershell
qmd.cmd collection list
```

預期輸出：
```
Collections (2):

global (qmd://global/)
  Pattern:  **/*.md
  Files:    <N>
meetchi (qmd://meetchi/)
  Pattern:  **/*.md
  Files:    <N>
```

---

## Phase 3: 匯入種子知識

### 3.1 從現有 KI 系統匯入

```powershell
# 全域知識（IDE 配置、Skills、Agent 框架）
Copy-Item "$env:USERPROFILE\.gemini\antigravity\knowledge\antigravity_ide_configuration\artifacts\*.md" "$env:USERPROFILE\.gemini\antigravity\qmd-global\" -Force
Copy-Item "$env:USERPROFILE\.gemini\antigravity\knowledge\antigravity_awesome_skills\artifacts\*.md" "$env:USERPROFILE\.gemini\antigravity\qmd-global\" -Force
Copy-Item "$env:USERPROFILE\.gemini\antigravity\knowledge\opencode_sisyphus_agent\artifacts\*.md" "$env:USERPROFILE\.gemini\antigravity\qmd-global\" -Force

# 專案知識（MeetChi）
$src = "$env:USERPROFILE\.gemini\antigravity\knowledge\meetchi_system_kb\artifacts"
$dst = "D:\Side_project\MeetChi\.agent\qmd\"
Copy-Item "$src\*.md" $dst -Force
Copy-Item "$src\implementation\*.md" $dst -Force -ErrorAction SilentlyContinue
Copy-Item "$src\deployment\*.md" $dst -Force -ErrorAction SilentlyContinue
Copy-Item "$src\architecture\*.md" $dst -Force -ErrorAction SilentlyContinue
Copy-Item "$src\testing\*.md" $dst -Force -ErrorAction SilentlyContinue
Copy-Item "$src\setup\*.md" $dst -Force -ErrorAction SilentlyContinue
```

### 3.2 重新索引

新增檔案後，需 remove + re-add collection 以觸發索引：

```powershell
# 全域
qmd.cmd collection remove global
qmd.cmd collection add "$env:USERPROFILE\.gemini\antigravity\qmd-global" --name global --mask "**/*.md"

# 專案
qmd.cmd collection remove meetchi
qmd.cmd collection add "D:\Side_project\MeetChi\.agent\qmd" --name meetchi --mask "**/*.md"
```

> [!WARNING]
> `collection remove` + `re-add` 會清除 context。需在索引後**重新設定 context**（重複 Phase 2.3）。

### 3.3（可選）生成向量嵌入

```powershell
qmd.cmd embed
```

> 首次執行會自動從 HuggingFace 下載 GGUF 模型（~300MB）。  
> 未 embed 時，`qmd search`（BM25）仍可正常使用；`qmd vsearch` 和 `qmd query`（語義搜尋）需 embed 後才能使用。

---

## Phase 4: Antigravity MCP 配置

### 4.1 編輯 MCP 設定

**檔案**：`~/.gemini/antigravity/mcp_config.json`

```json
{
    "mcpServers": {
        "browsermcp": {
            "command": "npx",
            "args": ["@browsermcp/mcp@latest"]
        },
        "notebooklm": {
            "command": "notebooklm-mcp"
        },
        "qmd": {
            "command": "bun",
            "args": [
                "--cwd",
                "C:\\Users\\User\\.bun\\install\\global\\node_modules\\qmd",
                "src/qmd.ts",
                "mcp"
            ]
        }
    }
}
```

> [!NOTE]
> 不使用 `qmd mcp`（依賴 bash shim），而是用 `bun --cwd <qmd_path> src/qmd.ts mcp` 直接執行。

### 4.2 可用的 MCP Tools

配置完成後，Agent 可使用以下工具：

| MCP Tool | 功能 | 用途 |
|----------|------|------|
| `qmd_search` | BM25 關鍵字搜尋 | 精確詞彙匹配 |
| `qmd_vector_search` | 語義向量搜尋 | 同義詞、近義概念 |
| `qmd_deep_search` | 混合搜尋 + query expansion + reranking | 最佳結果品質 |
| `qmd_get` | 取得文件全文 | 閱讀搜尋結果 |
| `qmd_multi_get` | 批量取得多文件 | glob pattern 匹配 |
| `qmd_status` | 索引健康狀態 | 診斷問題 |

---

## Phase 5: 搜尋驗證

### 5.1 專案隔離測試

```powershell
# 專案搜尋 — 應有結果
qmd.cmd search "Cloud Run GPU" --collection meetchi -n 3

# 全域搜尋 — 應無結果（Cloud Run 是 MeetChi 專屬知識）
qmd.cmd search "Cloud Run GPU" --collection global -n 3

# 全域搜尋 — 應有結果
qmd.cmd search "coding style" --collection global -n 3
```

### 5.2 預期結果

| 查詢 | Collection | 預期 |
|------|-----------|------|
| "Cloud Run GPU" | meetchi | ✅ 命中 `deployment-and-infra.md` |
| "Cloud Run GPU" | global | ✅ 無結果（正確隔離） |
| "coding style" | global | ✅ 命中相關文件 |

---

## 新專案快速初始化

使用 `/qmd-init` workflow（已建立於 `.agent/workflows/qmd-init.md`）：

```powershell
$env:Path = "C:\Users\User\.bun\bin;$env:Path"

# 1. 建立目錄
New-Item -ItemType Directory -Force -Path ".agent\qmd"

# 2. 註冊 collection
qmd.cmd collection add ".agent\qmd" --name <project-name> --mask "**/*.md"

# 3. 設定 context
qmd.cmd context add qmd://<project-name> "<專案描述>"

# 4. 驗證
qmd.cmd collection list
```

---

## 常見問題

### Q1: QMD 命令全部失敗，顯示 `getDb()` 錯誤

**原因**：`~/.cache/qmd/` 目錄不存在  
**解法**：

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cache\qmd"
```

### Q2: `qmd` 命令找不到（`not found in %PATH%`）

**原因**：bun 的 shell shim 需要 bash  
**解法**：使用 `qmd.cmd` wrapper 或直接用 bun 執行：

```powershell
bun --cwd "C:\Users\User\.bun\install\global\node_modules\qmd" src/qmd.ts <command>
```

### Q3: 新增的 md 檔案沒被搜尋到

**原因**：QMD 不會自動偵測新檔案  
**解法**：重新索引 collection：

```powershell
qmd.cmd collection remove <name>
qmd.cmd collection add <path> --name <name> --mask "**/*.md"
# 別忘重新設定 context
qmd.cmd context add qmd://<name> "<description>"
```

### Q4: PowerShell 顯示紅色錯誤但命令其實成功

**原因**：QMD 的 stderr 輸出（進度條、警告）被 PowerShell 視為 error  
**判斷**：只要看到 `✓` 符號就是成功，忽略紅色文字

### Q5: `sqlite-vec-win32-x64` 安裝時 404

**影響**：無。正確的 Windows 套件名為 `sqlite-vec-windows-x64`，它會正常安裝並含有 `vec0.dll`。
