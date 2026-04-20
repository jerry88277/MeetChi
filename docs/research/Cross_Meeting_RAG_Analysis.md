# 跨會議搜尋 (RAG) 功能架構升級計畫與現況評估

本調查基於第一性原理、MECE 原則與模型思維，對 MeetChi 系統中的「跨會議搜尋」功能進行全面檢驗與開發規劃。

## 1. 第一性原理與現況評估

**核心問題：使用者尋找資訊的行為本質是什麼？**
使用者尋找知識通常不是「一問定生死」，而是「逐步對焦」的對話過程（例如：問「上週行銷會議總結了什麼？」得到回答後，會追問「那預算由誰負責？」）。

**現況 (Is it Complete?)：目前狀態 = 不完善 (Stateless RAG)**
目前的 `/api/v1/rag/ask` 僅接收單一 `question`，轉成 Embedding 後直接對 PgVector 做餘弦相似度比對。雖然前端有精美的 ChatUI，這只是「視覺上的聊天室」——每次送出的 Request 完全不包含上下文。
因此，若使用者追問「由誰負責？」，向量資料庫只會拿「由誰負責」去比對，這在語意空間中找不到任何有用的逐字稿段落。跨會議搜尋不具備「會話記憶」。

## 2. MECE 功能拼圖分析

我們將會話式 RAG 流程拆解為不遺漏、不重疊的四個維度：

1. **輸入與意圖 (User Intent)**：
   前端呼叫 `/api/v1/rag/ask` 時，必須一併傳遞對話歷史 (History)。
2. **檢索重構 (Retrieval Contextualization)**：
   後端必須理解歷史。遇到「它」、「那件事」等無具體主詞的代名詞時，必須啟動小型 LLM 流程進行 **Standalone Query Generation (獨立查詢重寫)**。
3. **推論結合 (Reasoning & Generation)**：
   將「重寫後的 Query」放入 PgVector 檢索得到的 Chunk，並加上完整的對話歷史，一併交給 Gemini 推理出最終連貫的回答。
4. **回饋展示 (Presentation Feedback)**：
   前端在接收回答後，除了引用來源 (Citations) 展示外，必須正確將上下文維持在畫面上。

## 3. 開發計畫 (Implementation Plan)

為了解決這項問題，我們提議以下實作清單：

### [修改] `apps/backend/app/routes/rag.py`
- 新增 `ChatMessage` Pydantic Schema。
- 在 `RAGRequest` 中加入 `history: Optional[List[ChatMessage]] = []`。
- **引入 Query Rewrite 機制**：
  - 如果 API 收到 `history`，呼叫 `get_gemini_client` 重新將 `Question + History` 轉譯成精確的目標語境 `Standalone Query`。
  - 對 `Standalone Query` 做 Vector Embedding 並搜尋。
- 將 `history` 提供給 `_build_rag_prompt`，確保最終生成的內容能接續上下文。

### [修改] `apps/frontend/src/lib/api.ts`
- 擴充 `askRag` 的 Payload，新增可選的 `history` 屬性。

### [修改] `apps/frontend/src/components/rag/ChatPanel.tsx`
- 在送出訊息時，除了目前的 `input`，同時抓取狀態清單中先前的對話 (`role` 與 `text`，可過濾掉一開始的歡迎訊息)，組成 History 陣列一併發送給 Backend API。

## 4. 測試與驗證策略

我們會建立如下的端到端連貫驗證流程，確保這項重大的架構升級穩健生效：
1. **回合 1 (無歷史)**：詢問一個單點問題（如：「設計審查會議有提到介面框架嗎？」），確保能回查到具體文獻。
2. **回合 2 (指代跟進問題)**：緊接著輸入「那負責人是誰？」。
3. **驗證斷言**：後端的日誌應顯示：
   - Query Contextualization 把問題重寫為：「設計審查會議中有關介面框架的負責人是誰？」。
   - 生成結果能基於上述 Query 抓取到正確的逐字稿。

這份計畫已透過 Antigravity 的 Planning Mode 產生了 `implementation_plan.md`，正等待您的授權與同意，一旦通過即可自動進入執行階段。
