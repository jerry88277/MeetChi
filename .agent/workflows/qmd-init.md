---
description: 初始化新專案的 QMD 記憶庫
---

# QMD 記憶庫初始化

本 workflow 用於在新專案中建立 QMD 記憶庫。

// turbo-all

## 步驟

1. 建立 `.agent/qmd/` 目錄：
```powershell
New-Item -ItemType Directory -Force -Path ".agent\qmd"
```

2. 使用 qmd 建立 collection（將 `<project-name>` 替換為專案名稱）：
```powershell
$env:Path = "C:\Users\User\.bun\bin;$env:Path"
qmd.cmd collection add ".agent\qmd" --name <project-name> --mask "**/*.md"
```

3. 設定 context description（描述專案用途）：
```powershell
qmd.cmd context add qmd://<project-name> "<專案描述>"
```

4. 如果有現有知識（KI artifacts），複製到 `.agent/qmd/`：
```powershell
# 範例：從 knowledge 目錄複製
Copy-Item -Path "path\to\knowledge\artifacts\*.md" -Destination ".agent\qmd\" -Force
```

5. 重新索引並驗證：
```powershell
qmd.cmd collection list
```

6. （可選）生成向量嵌入以啟用語義搜尋：
```powershell
qmd.cmd embed
```
注意：首次執行 embed 會自動下載 GGUF 模型（~300MB），需要一些時間。

## 驗證
- `qmd.cmd collection list` — 確認新 collection 有正確的 files 數量
- `qmd.cmd search "test query" --collection <project-name>` — 確認搜尋正常

## 目錄結構
```
<project-root>/
├── .agent/
│   ├── qmd/                  ← 專案記憶庫（本 workflow 建立）
│   │   ├── architecture.md
│   │   ├── decisions.md
│   │   └── patterns.md
│   ├── skills/               ← 專案 skills
│   └── workflows/            ← 專案 workflows
```
