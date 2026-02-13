---
description: Ultrawork 模式 - Sisyphus 式全自動任務執行（含 Todo 強制完成、Ralph Loop、Wisdom 累積）
---

# /ultrawork — 全自動執行模式

當用戶提及 `ultrawork` 或 `ulw` 時，啟動全自動執行。**持續工作直到 100% 完成，不中途停止詢問用戶。**

> **參考 Skill**: `opencode-sisyphus`（主 Agent 工作流程）、`opencode-atlas`（並行委派）

// turbo-all

## 步驟 1：Intent Gate（意圖閘門）

分析用戶請求，30 秒內完成判斷：

1. **分類請求類型**: 直接任務 / 問題 / 探索 / 模糊
2. **檢查模糊度**: 如果不確定，從 context 推斷（不要問用戶）
3. **驗證理解**: 確認你理解的是實際需求，不只是字面意思

> **如果用戶方向有問題**：簡短說明你的顧慮 + 替代方案，然後直接用更好的方案執行。

## 步驟 2：並行探索

**同時啟動多路搜索**（不要一個一個來）：

```
# 並行執行，不要等待
grep_search → 搜索相關程式碼內容
find_by_name → 定位文件位置
view_file_outline → 了解結構

# 停止搜索的條件：
# - 已經有足夠 context 繼續
# - 相同資訊重複出現
# - 2 輪搜索沒有新發現
```

## 步驟 3：建立 Todo 清單（MANDATORY）

在 brain 目錄建立 `task.md`，**超級詳細**：

```markdown
# [任務名稱]

## Tasks
- [ ] 步驟 1：[描述] — 預期結果：[具體結果]
- [ ] 步驟 2：[描述] — 預期結果：[具體結果]
...
```

**規則：**
- 任何非平凡任務（2+ 步驟）→ 必須建立 todo
- 開始前標記 `[/]`
- 完成後**立即**標記 `[x]`（不要批次處理）

## 步驟 4：逐步實作

按優先順序執行每個步驟：

1. 標記 `[/]` in progress
2. 執行步驟（code changes、commands 等）
3. 驗證結果（diagnostics、build、test）
4. 標記 `[x]` completed
5. **立即進入下一步**

### 委派結構（Delegation Prompt）

需要委派時，prompt 必須包含 6 個部分：
```
1. TASK: 原子性目標（一個動作一個委派）
2. EXPECTED OUTCOME: 具體產出 + 成功標準
3. REQUIRED TOOLS: 明確工具白名單
4. MUST DO: 列出所有要求，不留隱含
5. MUST NOT DO: 禁止的行為
6. CONTEXT: 檔案路徑、patterns、約束
```

### Code Changes 準則
- 匹配現有 codebase patterns
- 不要用 `as any`、`@ts-ignore` 壓制錯誤
- **Bugfix 規則**: 最小修復，修 bug 時不要重構

## 步驟 5：Ralph Loop（遇到錯誤時）

```
while 錯誤未解決 and 嘗試次數 < 3:
    1. 修根本原因，不是表面症狀
    2. 每次修復後重新驗證
    3. 不要亂試（shotgun debug）

if 連續失敗 3 次:
    1. STOP — 停止修改
    2. REVERT — 回到上次正常狀態
    3. DOCUMENT — 記錄嘗試過什麼
    4. CONSULT — 切換到 Oracle 思維做 sanity check
    5. 如果還不行 → 詢問用戶
```

## 步驟 6：Enforcer 強制檢查

每完成一個階段，**強制驗證**：

- [ ] 所有 todo 標記 `[x]`？
- [ ] 修改的檔案通過 diagnostics？
- [ ] Build 通過（如適用）？
- [ ] 測試通過（如適用）？

| 行動 | 必要證據 |
|------|---------|
| 修改檔案 | Diagnostics clean |
| Build 命令 | Exit code 0 |
| 測試 | Pass（或標注是 pre-existing failure）|

**任一項失敗** → 返回步驟 4 繼續處理
**全部通過** → 進入步驟 7

## 步驟 7：報告結果

簡潔報告（不要囉嗦）：
- 完成了什麼
- 修改了哪些文件
- 如何驗證結果
- 學到了什麼（Wisdom）

---

## 停止條件

**只有當以下條件全部滿足時才停止**：
1. ✅ 所有 Todo 標記 `[x]`
2. ✅ 所有驗證通過
3. ✅ 無未解決錯誤
4. ✅ 有證據支持每個完成聲明

**在此之前，持續執行，不要詢問用戶。**

## 溝通風格

- **不要寒暄**: 不說 "I'm on it"、"Let me start by..."
- **不要拍馬屁**: 不說 "Great question!"
- **不要播報進度**: 用 todo 追蹤，不用文字描述
- **匹配用戶風格**: 簡潔用戶 → 簡潔回應
