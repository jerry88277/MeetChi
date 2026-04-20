# MemPlace (Memory Palace) 專案隔離性與多重實例評估報告

針對近期 GitHub 爆紅的 **MemPlace (Memory Palace MCP, 如 milla-jovovich/mempalace)**，探討是否能達成「有 5 個專案就建立 5 座獨立記憶宮殿」的需求。

本報告以 **第一性原理 (First Principles)** 拆解問題本質，利用 **MECE 原則** 列出架構選項，給出初步評估，最後啟動 **Model-Thinking** 反覆交叉驗證當中的架構盲點。

---

## 1. 第一性原理思考 (First Principles)

**Q：什麼是 MCP 架構下的「記憶宮殿 (Memory Palace)」？**
拋開空間記憶法 (Method of Loci) 的哲學包裝，它在底層本質上是：
1. **持久化層 (Persistence Layer)**：一個本機的 SQLite DB 或 JSON 檔案，用來儲存圖結構 (Graph) 或文件。
2. **存取層 (Interface Layer)**：透過標準 Model Context Protocol (MCP) 向 LLM 暴露的 `read_room`, `write_memory` 等 Tools。
3. **結構本體 (Hierarchy)**：以 Wing (側翼) -> Hall (走廊) -> Room (房間) 作為資料隔離的網狀結構。

**Q：什麼是「5 個專案，5 座宮殿」？**
在物理與邏輯上，這代表我們要求 **Context Boundary (上下文邊界)** 絕對隔離，LLM 在思考專案 A 時，沒有機會意外 Query 到專案 B 的空間，避免幻覺與記憶交疊。

**第一性結論**：
要達成「5 個專案，5 座宮殿」，本質上只需要在「持久化層」或「介面層」其中一刀切開即可。這在軟體工程上是 **絕對可以實現** 的。

---

## 2. MECE 原則架構解析

我們透過 MECE (Mutually Exclusive, Collectively Exhaustive，互斥且周延) 原則，列出所有實作多宮殿的潛在路徑。

### A. 物理隔離 (Infrastructure-level / Physical Split)
*方法：啟動 5 個獨立的 MCP Server 程序*
*   **A1. 透過啟動參數分配持久化檔案**：配置 5 個 MCP Server，分別指向 `db=proj1.db` ~ `proj5.db`。LLM 面對的是 5 組截然不同的 Tool API。
*   **A2. 透過工作目錄 (CWD) 隔離**：如果 MemPlace 寫死讀取當前目錄的 `.mempalace.db`，我們就在配置層強迫 5 個 Server 分別在 5 個專案資料夾啟動。

### B. 邏輯隔離 (Architecture-level / Logical Split)
*方法：只啟動 1 個 MCP Server，在語意空間上切出 5 個專案*
*   **B1. 最高層的降維打擊 (以 Wing 代替 Palace)**：MemPlace 的標準架構最高層級是 Wing (側翼)。我們強制約定：Wing 1 叫做「專案A大樓」、Wing 2 叫做「專案B大樓」。
*   **B2. Namespace 前綴法**：在所有的 Hall 與 Room 的命名強制冠上專案代號，例如 `[ProjA]_Marketing_Hall`。

---

## 3. 初步評估報告 (Preliminary Conclusion)

**初步結論：強烈建議採用「B1. 邏輯隔離（以 Wing 取代 Palace）」做為實質上的 5 座記憶宮殿。**

| 評估維度 | 物理隔離法 (5 個 MCP Server) | 邏輯隔離法 (1 個 Server, 5 個 Wing) |
| :--- | :--- | :--- |
| **可實現性** | 取決於底層 codebase 是否支援 CLI 改 DB 路徑 | **極高** (開箱即用支援新增無限多 Wing) |
| **隔離徹底度** | 100% 絕對隔離 | 90% 依賴 LLM 的系統 prompt 約束力 |
| **系統效能耗損** | 差 (同時跑 5 個 Node.js/Python 背景端點) | **極佳** (只有 1 個程序) |

**初步規劃建議**：
與其真的從程式碼層級拆開成 5 個「宮殿實體資料庫」，不如將一個巨大的宮殿定義為您的「公司總部」，而這 5 個專案對應到總部的「5 個大型 Wing (側翼/裙樓)」。這樣可以開箱即用，無須魔改原始碼。

---

## 4. Model-Thinking 反覆審查與盲點突破 (Blind-Spot Analysis)

我們將上述的「初步報告」放到不同維度的模型 (Model) 面對進行壓力測試：

### 🛑 盲點一：上下文長度通膨模型 (Token Budget Model)
- **如果採用物理隔離 (5 個 MCP Server)**：LLM 每次發送對話時，系統需要將 5 組一模一樣的 Tools (共計數十個函數，包含各自的 prompt 描述) 注入到 System Prompt 裡。
- **致命傷**：這會造成極為嚴重的 Token 浪費，而且 LLM 極度容易因為 Tool 介面都叫 `create_room_in_palace_1`, `create_room_in_palace_2` 而產生幻覺或呼叫錯誤！
- **修正思維**：絕對不能採用 5 個 MCP Server 的做法，這違反了 LLM Tool Calling 的極簡收斂原則。

### 🛑 盲點二：資源跨域共享模型 (Cross-Pollination Dependency)
- **如果採用 5 座絕對隔離的宮殿**：當你在專案 A 解決了一個 Terraform 的深層 Bug，這個記憶被鎖在宮殿 A。日後專案 C 遇到一樣的問題，LLM 沒辦法走到宮殿 A 的房間調取知識。
- **致命傷**：過度強調「專案隔離」反而切斷了 Memory Palace 最大的價值——**跨界啟發與全域檢索**。如果你把大腦分成 5 個，就等於你同時失去跨專案連接的能力。
- **修正思維**：統一使用 **單一持久化資料庫 (共用一個大宮殿)**，但賦予明確的資料隔離標籤。

### 🛑 盲點三：架構層級天花板限制 (Structural Ceiling Model)
- **如果採用「B1 把 Wing 拿來當作 Project」**：
- **致命傷**：GitHub 上開源的 MemPlace 結構通常限縮為三維：`Wing -> Hall -> Room`。如果你把最大的 Wing 拿來當 Project，你的專案底下只剩下 `Hall -> Room` 兩個維度可以使用。對於大型專案而言，只有 2 個層級用來收納複雜的軟體架構，會立刻顯得不敷使用，導致同一間房間被塞滿大雜燴，最終 LLM 短期記憶崩潰 (Context Confusion)。
- **修正思維**：如果真的要「5 個專案」，我們必須對開源的 MemPlace 原始碼進行「降維擴充」。亦即：在資料庫架構 (SQL/Graph) 最上層，強行寫入一層 `Palace` 節點。結構變為 `Palace (Project) -> Wing -> Hall -> Room`。

---

## 🎯 最終綜合結論與執行建議

1. **可以做到，但不要用 5 個 Server**：絕對避免啟動 5 個獨立的 MCP Server 或資料庫，因為這會摧毀 LLM 的上下文 Token 預算並引發選擇困難症。
2. **真正的解法是「單庫擴充」**：
   - 保持 1 個 MCP Server 運行 1 個強大的底層 Database。
   - Fork 該專案，向頂層抽象出 `[Project]` 或 `[Palace]` 階層。
   - 只暴露 **共用的一組 Tool API**，但在 API 參數中皆加入 `project_id=xxx` 作為過濾器 (Filter)。如 `search_memory(query, project="ProjA")`。
3. **第一性勝利**：「將記憶依專案分流以提升專注度」，用單一入口 + 參數路由 (Parameter Routing)，是系統資源、LLM 相容性與人類管理三方兼顧的最完美架構。
