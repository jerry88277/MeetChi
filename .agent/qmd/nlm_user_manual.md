# NotebookLM CLI (NLM) 使用手冊

本文件提供 Google NotebookLM 命令列工具（`nlm`）的完整使用指南，旨在幫助使用者與 AI 代理快速掌握各種自動化操作。

## 1. 核心概念：認證與工作階段 (Authentication)

**工作階段（Session）有效期限約為 20 分鐘。** 在執行任何操作前，請確保已完成認證。

### 初次設定與重新認證
```bash
nlm login
```
這會在背景開啟 Chrome 並自動提取 Cookies。如果認證成功，會顯示 `✓ Successfully authenticated!`。

### 檢查是否已認證
```bash
nlm auth status
```
發送真實的 API 請求來驗證當前憑證，並顯示連線狀態與筆記本數量。

### 自動恢復與錯誤處理
- **憑證恢復機​​制**：遇到 401 錯誤時自動重新整理 token、從磁碟重新載入 token，或嘗試直接 headless 認證。
- **伺服器錯誤重試**：遇到 429, 500, 502, 503, 504 錯誤時，最高會使用指數退避方式重試三次。
- **認證過期**：若指令出現「Cookies have expired」或「authentication may have expired」，請隨時執行 `nlm login`。

---

## 2. 指令風格：資源優先 vs 動作優先

CLI 支援兩種指令風格，功能完全相同，可依習慣混用：

1. **資源（名詞）優先風格**：
   ```bash
   nlm notebook create "專案名稱"
   nlm source add <notebook> --url <url>
   ```
2. **動作（動詞）優先風格**：
   ```bash
   nlm create notebook "專案名稱"
   nlm add url <notebook> <url>
   ```

---

## 3. 別名系統 (Alias System)

使用好記的名稱來取代長 UUID 識別碼，簡化指令輸入：
```bash
# 設定別名 (會自動偵測對應的是 Notebook 還是 Source)
nlm alias set myproject abc123-def456-...

# 於指令中使用別名
nlm notebook get myproject
nlm source list myproject  

# 其他別名管理
nlm alias list                    # 列出所有別名
nlm alias get myproject           # 取得別名對應的 UUID
nlm alias delete myproject        # 刪除別名
```

---

## 4. 核心操作指令參考

### 4.1 筆記本管理 (Notebooks)
- **列出與檢視**：
  ```bash
  nlm notebook list               # 列出所有筆記本
  nlm notebook create "標題"      # 建立新筆記本
  nlm notebook get <id>           # 取德筆記本資訊
  nlm notebook describe <id>      # 取得 AI 生成的摘要與主題
  ```
- **修改與刪除**：
  ```bash
  nlm notebook rename <id> "新標題"
  nlm notebook delete <id> --confirm
  ```

### 4.2 資料來源管理 (Sources)
- **新增來源**：
  ```bash
  nlm source add <notebook-id> --url "https://..."           # 網頁或 YouTube
  nlm source add <notebook-id> --text "內文" --title "標題"  # 純文字
  nlm source add <notebook-id> --file /path/to/doc.pdf       # 本地檔案
  nlm source add <notebook-id> --drive <doc-id>              # Google 雲端硬碟檔案
  ```
  *(💡 在最後加上 `--wait` 參數可等待處理完成)*
- **管理與檢視來源**：
  ```bash
  nlm source list <notebook-id>          # 列出該筆記本所有來源
  nlm source describe <source-id>        # AI 產生摘要與關鍵字
  nlm source content <source-id>         # 取得無處理的原始純文字內容
  nlm source delete <source-id> --confirm
  ```
- **同步雲端硬碟來源**：
  ```bash
  nlm source stale <notebook-id>         # 列出需要更新的 Drive 來源
  nlm source sync <notebook-id> --confirm  # 同步更新
  ```

### 4.3 聊天與問答 (Chat & Query)
> **⚠️ 機器人請勿使用 REPL（`chat start`）功能，應使用單次 `query` 系列指令。**
```bash
nlm notebook query <id> "請問這份文件重點為何？"
nlm notebook query <id> "後續問題" --conversation-id <cid>
nlm chat configure <id> --response-length longer # 配置回答長度 (longer, default, shorter)
```

### 4.4 AI 深度研究 (Research)
NotebookLM 可上網幫你搜尋資料（此功能需要 `--notebook-id` 參數）。
- **啟動研究**：
  ```bash
  nlm research start "搜尋關鍵字" --notebook-id <id>            # 快速搜尋 (Fast web)
  nlm research start "搜尋關鍵字" --notebook-id <id> --mode deep # 深度搜尋 (~5分鐘)
  nlm research start "搜尋關鍵字" --notebook-id <id> --source drive # 搜尋 Drive
  ```
- **追蹤與匯入**：
  ```bash
  nlm research status <notebook-id> --max-wait 300   # 輪詢一直到完成為止
  nlm research import <notebook-id> <task-id>        # 完成後將來源匯入到筆記本
  ```

### 4.5 內容生成 (Studio Artifacts)
產生各式音訊播客、報告、視覺檔案，以下皆以傳入 `--confirm` 為例。
- **音訊/Podcast**：`nlm audio create <notebook-id> --format deep_dive --confirm`
- **報告/文件**：`nlm report create <notebook-id> --format "Study Guide" --confirm`
- **測驗題**：`nlm quiz create <notebook-id> --count 5 --difficulty 3 --confirm`
- **投影片**：`nlm slides create <notebook-id> --confirm`
- **心智圖**：`nlm mindmap create <notebook-id> --confirm`
- **資訊圖表**：`nlm infographic create <notebook-id> --orientation portrait --confirm`
- **影片**：`nlm video create <notebook-id> --style whiteboard --confirm`

**後續管理**：
```bash
nlm studio status <notebook-id>                  # 查看檔案生成進度
nlm studio delete <notebook-id> <artifact-id>    # 刪除檔案
```

### 4.6 下載與匯出 (Download & Export)
在狀態顯示 "completed" 後即可下載生成物：
- **下載檔案到本地**：
  ```bash
  nlm download audio <notebook> --id <artifact-id> --output podcast.mp3
  nlm download slide-deck <notebook> --id <slides-id> --format pptx
  nlm download report <notebook> --output report.md
  ```
- **互動問答格式 (Quiz/Flashcards)**：
  支援格式有 json (預設), markdown, html 等。
  ```bash
  nlm download quiz <notebook-id> <artifact-id> --format html
  ```
- **匯出至 Google Docs / Sheets**：
  ```bash
  nlm export to-docs <notebook-id> <artifact-id>     # 報告匯出到 Google Docs
  nlm export to-sheets <notebook-id> <artifact-id>   # 資料表匯出到 Google Sheets
  ```

### 4.7 分享與協作 (Share)
```bash
nlm share status <notebook-id>              # 檢視分享設定
nlm share public <notebook-id>              # 開放公開連結
nlm share invite <notebook-id> <email> --role editor  # 邀請共同編輯者
```

### 4.8 Skills 安裝與 MCP 屬性設定
可透過指令幫主流 AI 開發環境（如 Claude Code, Cursor, OpenCode, Antigravity 等）安裝 NotebookLM MCP Server 與 Skill：
```bash
nlm skill list                              # 檢視安裝狀態
nlm skill install claude-code               # 安裝給 Claude Code (預設安裝到 User 設定區)
nlm skill install cursor --level project    # 安裝給 Cursor (當前專案)
nlm setup add claude-desktop                # 新增 MCP server 到 Claude Desktop
```

---

## 5. 常見使用情境範例

### 情境一：研究特定主題並轉成 Podcast 發布
```bash
# 1. 登入並建立名為 "Tech Report" 的筆記本
nlm login
nlm notebook create "Tech Report"
# 2. 為方便操作，設定別名為 tech
nlm alias set tech abc123-def456-...
# 3. 進行深度的網路研究
nlm research start "AI Agents 2026" --notebook-id tech --mode deep
# 4. 等待搜尋完成 (5分鐘以內)
nlm research status tech --max-wait 300
# 5. 將找到的文獻都載入筆記本內
nlm research import tech task456...
# 6. 生成一個深入探討的雙人播客 (Deep Dive Audio)
nlm audio create tech --format deep_dive --confirm
# 7. 輪詢查看進度，直到 audio 產出顯示 finished/completed
nlm studio status tech
# 8. 下載到本地
nlm download audio tech audio789... --output tech_podcast.mp3
```

---

## 6. AI Agent 最佳實踐提示 (Tips for AI Assistants)

遇到開發自動化操作任務時，請留意：
1. **認證失效**：遇到錯誤就請先使用 `nlm login` 嘗試復原，認證效期約20分鐘。
2. **免除了確認提示**：需要自動執行操作時（生成、刪除），務必加上 `--confirm` 參數。但執行「刪除指令」前**一定要先取得使用者的同意**。
3. **單向輸出控制**：大部分狀態與列出的情況都可以加上 `--json` 方便進行物件處理；如果只要取 id 傳給另一個指令，可利用 `--quiet`。
4. **生成需等待時間**：Studio 內容多半須花費 1-5 分鐘生成。不要馬上要求下載，請使用 `nlm studio status <id>` **輪詢直到狀態變成 Completed**。
5. **對話限制**：切勿使用互動式介面 `chat start`，請使用 `query` 加減一問一答。
6. **支援檔案串流下載**：所有資源的下載預設都支援串流儲存大檔，指令中的 `--output <檔名>` 建議明確補上以免檔名衝突。
