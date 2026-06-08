# MeetChi Personalized Greeting / User Memory 實作計畫

## 0. 現況摘要

本功能要落在既有跨會議 RAG 架構上，而不是另開一套記憶系統。

### 已確認的現有能力
- 前端 RAG 入口：`apps/frontend/src/components/rag/ChatPanel.tsx`
  - 目前以硬編 `WELCOME_MESSAGE` 當作第一則 AI 訊息。
  - 查詢歷史已存在：`GET /api/v1/rag/history`。
  - `messages.slice(1)` 會略過第一則 welcome message，不把它送回 RAG history。
- 工作區容器：`apps/frontend/src/components/rag/RagWorkspace.tsx`
  - 目前 header 很精簡，適合放標題，不適合承載長篇個人化內容。
- 前端 API：`apps/frontend/src/lib/api.ts`
  - 已有 `askRag()`、`getRagHistory()` 型別與呼叫模式，可延伸新增 `getRagGreeting()`。
- 後端 RAG 路由：`apps/backend/app/routes/rag.py`
  - 已有 `/api/v1/rag/ask`、`/api/v1/rag/history`、`/api/v1/rag/status`。
  - 已建立 MemPlace 存取隔離：以 `meeting_participants.user_upn` 控制可見會議。
- 資料模型：`apps/backend/app/models.py`
  - `users.display_name` 可當 display name 來源。
  - `meetings.summary_json`、`meetings.summary_embedding`、`transcript_segments.content_embedding` 已存在。
  - 目前 **沒有** 正規化的 action item 狀態表。
- 會議資料來源：`apps/backend/app/routes/meetings.py`
  - `MeetingRead/MeetingListItem` 都含 `summary_json`。
  - 會議採 soft delete，查詢時應排除 `deleted_at IS NOT NULL`。
- Embedding：`apps/backend/app/embedding.py`
  - 既有 `summary_embedding` 與 `content_embedding` pipeline。
- RAG prompt 組裝
  - 專案中不是單一 `app/rag.py`，而是 `apps/backend/app/rag/` package。
  - `app/rag/prompt.py` 提供 grounded prompt builder。

### 重要限制
- `summary_json.action_items` 多數是字串陣列；`next_steps` 雖可帶 assignee/due，但 **沒有 resolved / pending 狀態**。
- 因此 `pending_action_count` 若要可靠，建議新增正規化資料表，而不是從 JSON 猜測。

---

## 1. Feature Specification

### 1.1 User Story
作為回到跨會議知識庫的使用者，
我希望系統在開啟 RAG workspace 時，先用我的真實會議脈絡向我打招呼，
讓我立刻知道最近常討論什麼、上次停在哪裡、有哪些後續可追，
而不是看到一段對所有人都一樣的通用歡迎詞。

### 1.2 目標體驗
範例：

> 歡迎回來，Jerry。根據您過去 8 場會議，您最常討論的主題是 AI 導入策略、供應商議價與 Q3 預算。上次在「供應商季度評估」會議中，仍有 2 個待追蹤事項。需要我幫您繼續整理嗎？

### 1.3 Acceptance Criteria
1. 使用者進入跨會議知識庫時，前端會呼叫 `GET /api/v1/rag/greeting?user_upn=...`。
2. API 僅使用該 `user_upn` 有權限的會議資料（`meeting_participants`），且排除 soft-deleted meetings。
3. 若使用者至少有 1 場可用會議，回傳：
   - `display_name`
   - `meeting_count`
   - `top_topics`（最多 3 個）
   - `last_meeting` 摘要
   - `pending_action_count`
   - `greeting_text`
   - `suggested_questions`（3 題）
4. 若無足夠歷史資料，API 回傳通用 fallback greeting，而不是 500。
5. Greeting 載入失敗時，前端仍可正常使用 RAG chat，不阻塞輸入框。
6. Greeting 不得暴露使用者無權限的會議內容。
7. Greeting UI 可收合，不應永久占滿 header 或污染真正的聊天歷史。

---

## 2. Hotel Analogy → Meeting Memory Mapping

| Hotel memory | Meeting equivalent | 現有資料來源 | MVP 可行性 |
|---|---|---|---|
| Guest name | 使用者顯示名稱 | `users.display_name`；前端 session `session.user.name` 可 fallback | 高 |
| Preferred room type | 最常見會議主題 / 類型 | `meetings.title`、`summary_json.summary`、`summary_json.chapters`、未來 `summary_embedding`/`content_embedding` | 中 |
| Last stay details | 最近一次會議重點 | 最新 `meetings.created_at` + `summary_json` | 高 |
| Outstanding requests | 尚未完成的待辦 | **需新增** `meeting_action_items.status`；目前 JSON 無狀態 | 低（現況）/高（加表後） |
| Frequent destinations | recurring discussion topics | 近期 summaries / embeddings | 中 |
| Special dietary needs | 個人工作風格偏好 | 可由 `speaker_contributions` / 問句歷史推估，但現階段不建議上線 | 低 |
| Loyalty tier | 累積會議數 | `COUNT(DISTINCT meeting_id)` | 高 |

### MVP 建議納入
- name
- meeting_count
- top_topics
- last_meeting
- pending_action_count
- suggested_questions

### Phase 2 才納入
- working style patterns（例如偏好 budget / vendor / execution 類問題）
- 更進階 topic clustering / memory ranking

---

## 3. Recommended Implementation Approach

### 3.1 Evaluate 3 approaches

#### Approach A: Pure DB query + template greeting
**做法**
- 查 `users`、`meeting_participants`、`meetings.summary_json`
- 從結構化欄位組出 top topics / last meeting / pending counts
- 以 template 產生 `greeting_text` 與 `suggested_questions`

**優點**
- 最符合現有系統形狀
- 延遲低、穩定、可測試
- 不會讓 RAG workspace 首屏依賴即時 LLM
- 容易做 fallback

**缺點**
- 文案自然度較機械
- `top_topics` 智慧程度有限

#### Approach B: Embedding-based topic clustering
**做法**
- 利用 `TranscriptSegment.content_embedding` 或 `Meeting.summary_embedding`
- 對使用者可見會議做 topic clustering
- 再用 LLM 幫 cluster 命名

**優點**
- 主題辨識更接近真正的「記得你常聊什麼」
- 比單看標題更準

**缺點**
- 線上 clustering 成本高
- 仍需 LLM 做 topic labeling
- 首屏延遲與 cache 複雜度上升
- 現階段沒有現成 topic snapshot/caching 層

#### Approach C: Lightweight LLM summarization
**做法**
- 撈最近 5 場 meeting summaries
- 送 Gemini 產生 greeting + suggestions

**優點**
- 文案最自然
- 可以直接模仿 concierge 語氣

**缺點**
- 每次 page load 都有成本與延遲
- 對 LLM availability 敏感
- 測試與除錯較難
- 若 prompt 漏控，容易產生過度推論

### 3.2 Recommendation
**推薦：Approach A 作為 v1 正式方案**，並把 Approach B 當作 v2 離線增強層。

### 3.3 Rationale
1. `ChatPanel` 是 workspace 首屏；不適合把 greeting 綁死在即時 Gemini 呼叫上。
2. 目前系統已經有夠多結構化資料可支持 deterministic greeting：`display_name`、`meeting_count`、`last_meeting.summary_json`、`next_steps/action_items`。
3. `pending_action_count` 若要可信，本來就應該用 DB state，不應交給 LLM 幻覺判斷。
4. 若未來要提升 top topic 品質，可以新增 nightly/offline topic snapshot，不必重寫 API contract。

### 3.4 實務落地建議
- **v1 online path**：Approach A
- **v1.5 data quality**：加入 `meeting_action_items` 正規化表
- **v2 intelligence upgrade**：離線 clustering + topic snapshot/cache

---

## 4. Data Model Changes

### 4.1 必要變更：新增 `meeting_action_items`
目前 `summary_json` 只能提供「提到過的待辦」，不能提供「目前仍 pending 的待辦」。
若要支援 `pending_action_count` 與「有哪些跨多場會議未解決」，需要正規化。

### 4.2 Proposed table
**File(s)**
- `apps/backend/app/models.py`
- `apps/backend/alembic/versions/<new_revision>_add_meeting_action_items.py`

**Suggested schema**
- `id: String(36)`
- `meeting_id: ForeignKey(meetings.id)`
- `user_upn: String(255)` — 主要責任人；未知可 null
- `source_type: String(20)` — `action_item` / `next_step`
- `text: Text`
- `normalized_text: Text` — 後續去重/聚合用
- `assignee: String(255) | null`
- `due_date: Date | null`
- `status: String(20)` — `pending` / `done` / `cancelled`
- `source_summary_version_id: String(36) | null`
- `created_at`, `updated_at`, `resolved_at`

**Indexes**
- `(meeting_id)`
- `(status)`
- `(user_upn, status)`

### 4.3 寫入時機
在 `apps/backend/app/tasks.py -> generate_summary_core()` 成功寫入 `meeting.summary_json` 後：
1. 解析 `summary_json.action_items`
2. 解析 `summary_json.next_steps` / `next_steps_v2`
3. upsert 到 `meeting_action_items`
4. 預設 `status='pending'`

### 4.4 可選變更：不新增 greeting cache table
v1 不需要額外 `user_memory_snapshot` 表。
先採 request-time 計算即可；若未來 B/C 導入後延遲變高，再補 snapshot/cache layer。

---

## 5. Backend API Spec

### 5.1 Endpoint
`GET /api/v1/rag/greeting?user_upn=xxx`

### 5.2 Request
**Query params**
- `user_upn: string` (required)

**Validation**
- 必填
- 必須含 `@`
- 後端統一轉小寫

### 5.3 Response
```json
{
  "display_name": "Jerry",
  "meeting_count": 8,
  "top_topics": ["AI導入策略", "供應商議價", "Q3預算"],
  "last_meeting": {
    "title": "供應商季度評估",
    "date": "2026-06-05",
    "key_actions": ["確認Q3預算", "評估3家供應商報價"]
  },
  "pending_action_count": 3,
  "greeting_text": "歡迎回來，Jerry...",
  "suggested_questions": [
    "上次提到的 Q3 預算定案了嗎？",
    "彙整所有供應商議價的結論",
    "有哪些待辦事項跨多場會議都還沒解決？"
  ]
}
```

### 5.4 Additional response behavior
- 若使用者無歷史資料：
```json
{
  "display_name": "Jerry",
  "meeting_count": 0,
  "top_topics": [],
  "last_meeting": null,
  "pending_action_count": 0,
  "greeting_text": "歡迎使用跨會議知識庫，我可以協助您彙整不同會議中的共同主題。",
  "suggested_questions": [
    "最近有哪些會議提到 AI 導入？",
    "幫我整理所有會議中的待辦事項",
    "比較不同會議對同一主題的看法"
  ]
}
```

### 5.5 Access control
Greeting API 必須沿用 RAG 的 MemPlace 邏輯：
- `meeting_participants.user_upn = :user_upn`
- `meetings.deleted_at IS NULL`
- 建議只納入 `meetings.status = COMPLETED`
- 若 `summary_json IS NULL`，可納入 meeting_count，但不納入 top_topics / last_meeting summary extraction

### 5.6 Query design
建議拆成 4 個 helper query：
1. `get_user_profile(user_upn)`
2. `get_accessible_meeting_stats(user_upn)`
3. `get_recent_meetings_for_greeting(user_upn, limit=5)`
4. `get_pending_action_count(user_upn)`

### 5.7 Topic extraction design for v1
不做線上 embedding clustering；改採 deterministic topic candidates：
- `summary_json.chapters[].title`
- `summary_json.speaker_contributions[].main_topics[]`
- `summary_json.cross_meeting_refs[].topic`
- `meetings.title`

處理方式：
1. 蒐集最近 10 場會議的 candidate topics
2. 正規化（trim、lower、去除空字串、去除過短字）
3. 計數排序
4. 取前 3 個

### 5.8 Greeting text generation
v1 用 template，不呼叫 LLM：

```text
歡迎回來，{display_name}。根據您過去 {meeting_count} 場會議，您最常討論的主題是 {topic_list}。{last_meeting_sentence}{pending_sentence}
```

其中：
- `last_meeting_sentence`：來自最近一場會議 title + date + key actions
- `pending_sentence`：若 `pending_action_count > 0` 才出現

### 5.9 Suggested question generation
v1 用規則生成 3 題：
1. 根據最近會議 key action 產生 follow-up 問句
2. 根據 top topic 產生彙整問句
3. 根據 pending count 產生跨會議待辦問句

### 5.10 Suggested backend structure
**推薦新增檔案**
- `apps/backend/app/services/rag_greeting.py`

**保留 route 檔案輕量**
- `apps/backend/app/routes/rag.py`
  - 定義 `RagGreetingResponse` Pydantic model
  - 新增 `@router.get("/greeting")`
  - 呼叫 service layer

### 5.11 Error handling
- 無 user：400
- user 無資料：200 + fallback payload
- DB 失敗：500
- 不應因某場 `summary_json` 壞掉而整體失敗；單場 parse fail 應 skip + warning log

---

## 6. Frontend Integration Plan

### 6.1 UX options evaluation

#### Option 1: Replace `WELCOME_MESSAGE`
**不推薦作為主方案**。

原因：
- 目前 `WELCOME_MESSAGE` 是 `messages[0]`，而 `handleSend()` 依賴 `slice(1)` 排除它。
- 若改成動態 greeting，會把 UI loading / cache / sessionStorage / history restore 複雜化。
- Greeting 本質上是 dashboard-style memory，不是真正的聊天內容。

#### Option 2: Add greeting card in `ChatPanel`
**推薦。**

原因：
- 不污染聊天歷史
- 能獨立 loading / error / collapse
- 可以放 suggested question chips，點擊後直接填入 input
- 與現有 `WELCOME_MESSAGE` 可並存：Greeting 負責「記得你」，welcome text 負責「教你怎麼問」

#### Option 3: Put greeting in `RagWorkspace` header
**不推薦。**

原因：
- Header 空間太小，不適合承載 last meeting + pending actions + suggested questions
- 可讀性與掃讀體驗較差

### 6.2 Recommended UX pattern
**採 Option 2：在 `ChatPanel.tsx` 中加入可收合 greeting card。**

### 6.3 UI behavior
- 位置：建議放在 `歷史查詢` bar 下方、messages 區塊上方
- 初次載入時顯示 skeleton/loading
- 成功時顯示：
  - 標題：`歡迎回來，Jerry`
  - 內文：`greeting_text`
  - metadata pills：meeting count / pending actions / top topics
  - suggested question chips（點擊即填入 input 或直接送出）
- 失敗時：直接隱藏 card 或顯示極簡 fallback 文案，不影響輸入
- 可收合：避免使用者反覆進入時佔空間

### 6.4 Frontend file changes
- `apps/frontend/src/lib/api.ts`
  - 新增 `RagGreetingResponse` type
  - 新增 `getRagGreeting(userUpn: string)`
- `apps/frontend/src/components/rag/ChatPanel.tsx`
  - 新增 greeting state / loading / error
  - `useEffect` 在 `userUpn` ready 後 fetch greeting
  - render greeting card + suggested questions
  - 保留 `WELCOME_MESSAGE` 作為 generic usage hint
- `apps/frontend/src/components/rag/RagWorkspace.tsx`
  - 可不改；若要全域控制，可傳入 feature flag，但非必要

---

## 7. Ordered Implementation Steps

| # | Step | File paths | Complexity |
|---|---|---|---|
| 1 | 新增 action item 正規化資料表與 model | `apps/backend/app/models.py`, `apps/backend/alembic/versions/*` | M |
| 2 | 在 summary pipeline 寫入/更新 `meeting_action_items` | `apps/backend/app/tasks.py` | M |
| 3 | 新增 greeting service，封裝 user profile / stats / topics / suggestions | `apps/backend/app/services/rag_greeting.py` | L |
| 4 | 在 RAG route 暴露 `GET /api/v1/rag/greeting` 與 response model | `apps/backend/app/routes/rag.py` | M |
| 5 | 前端 API client 與 TS 型別擴充 | `apps/frontend/src/lib/api.ts` | S |
| 6 | `ChatPanel` 加入 greeting card、loading、collapse、suggested chips | `apps/frontend/src/components/rag/ChatPanel.tsx` | M |
| 7 | 補 backend tests（正常/無資料/權限隔離/壞 JSON） | `apps/backend/tests/test_rag_greeting.py` | M |
| 8 | 前端 lint + backend pytest + 手動 smoke test greeting API 與 UI | 既有腳本/測試 | S |

### 7.1 Detailed step notes

#### Step 1 — DB schema
- 新增 `MeetingActionItem` model
- Alembic migration 建表與 index
- 不需要改 `MeetingRead` API contract

#### Step 2 — Summary ingestion
- `generate_summary_core()` 成功後同步 refresh action items
- 若重新產生 summary，先刪除該 meeting 舊 action items 再重建，避免殘留髒資料

#### Step 3 — Greeting service
建議拆 helper：
- `resolve_display_name()`
- `list_recent_meetings()`
- `extract_top_topics()`
- `build_greeting_text()`
- `build_suggested_questions()`

#### Step 4 — Greeting endpoint
- 回傳固定 JSON contract
- 內部若 action item table 尚未有資料，也能 fallback `pending_action_count=0`

#### Step 5 — Frontend API
- 補 TS type，避免 `any`
- 與 `askRag()` 同風格

#### Step 6 — ChatPanel UX
- 加 greeting card，不動既有 RAG answer message format
- 點 suggestion chip：優先 `setInput(question)`；是否 auto-send 可後續 AB test

#### Step 7 — Tests
至少覆蓋：
- 有 3 場 completed meetings 的正常回傳
- 無歷史資料 fallback
- `meeting_participants` 隔離正確
- 某 meeting `summary_json` parse fail 不拖垮整體
- pending count 正確反映 `meeting_action_items.status='pending'`

#### Step 8 — Verification
- backend: `pytest apps/backend/tests/test_rag_greeting.py`
- backend existing: `pytest apps/backend/tests/test_rag_prompt.py apps/backend/tests/test_rag_chunker.py`
- frontend: `npm run lint`
- smoke: `curl /api/v1/rag/greeting?user_upn=...`

---

## 8. Risk Assessment

| Risk | Why it matters | Mitigation |
|---|---|---|
| `pending_action_count` 不可信 | 現況沒有待辦狀態欄位 | 新增 `meeting_action_items`，不要從 JSON 瞎猜 |
| top topics 品質普通 | 單靠 title/summary 關鍵字可能不穩 | v1 先 deterministic；v2 再上 embedding clustering |
| workspace 首屏變慢 | greeting 在 page load 觸發 | 採 DB/template path，不走即時 LLM |
| 壞 `summary_json` 造成 API 失敗 | 舊資料可能格式不一致 | per-meeting try/except + skip bad rows |
| 權限外洩 | greeting 是跨會議聚合，更容易越權 | 全程沿用 `meeting_participants` JOIN |
| UI 過度打擾 | greeting 若太大會壓縮聊天區 | 可收合 card + 僅在上方顯示一次 |

---

## 9. Complexity Summary

| Area | Complexity | Reason |
|---|---|---|
| Backend endpoint 本身 | M | 主要是 aggregation + fallback |
| Pending action 正規化 | M | 需要 migration + pipeline 寫入 |
| Topic extraction v1 | M | JSON 欄位來源多、要做 defensive parsing |
| Frontend greeting card | M | 需兼顧 session、loading、collapse、suggestions |
| Embedding clustering v2 | L | 需要 clustering、labeling、cache |
| LLM greeting v2 | M | prompt 不難，但成本與穩定性要額外治理 |

---

## 10. Final Recommendation

### 建議採用的版本切法

#### Phase 1（建議先做）
- `GET /api/v1/rag/greeting`
- `ChatPanel` greeting card
- deterministic greeting text
- `meeting_action_items` table
- pending action count

#### Phase 2（優化）
- 離線 topic clustering（使用 `summary_embedding` / `content_embedding`）
- per-user topic snapshot/cache
- 更自然的文案模板或小型 LLM rewrite（非 blocking）

### 一句話結論
**以「DB + template + 正規化 pending action state」做 v1，是最符合現況、最安全、也最像真正 enterprise concierge 的方案。**
