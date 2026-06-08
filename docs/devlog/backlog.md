# MeetChi Backlog

> 最後更新：2026-06-08  
> 狀態說明：🟢 done | 🔵 pending | 🔴 blocked | ⏳ in_progress

---

## 待實作項目（Pending）

### g6 — Greeting Card UI（前端）

**優先度**：P0（Greeting Feature 最後一哩路）  
**涉及檔案**：`apps/frontend/src/components/rag/ChatPanel.tsx`  
**說明**：

後端 `/api/v1/rag/greeting` 與前端 `getRagGreeting()` 已就位（g1~g5 已完成），剩下渲染層。

**規格**：
- 位置：訊息串上方、歷史記錄欄下方
- 初次載入時呼叫 `getRagGreeting(userUpn)`，顯示 loading skeleton
- 元件結構：
  ```
  ┌─ GreetingCard (collapsible) ──────────────────────────────┐
  │  {greeting_text}                          [收合 ▲]        │
  │                                                           │
  │  常見主題：[品質管理 ×] [製程優化 ×] [Q3 達成率 ×]       │
  │  待辦行動項目：3 項                                       │
  │                                                           │
  │  建議提問：                                               │
  │  [上次的品質問題後來如何解決？] [有哪些未完成的行動項目？] │
  └───────────────────────────────────────────────────────────┘
  ```
- 建議提問 chip 點擊 → `setInput(question)`（注入輸入欄，不自動送出）
- 收合後只顯示一行摘要文字 + 展開按鈕
- 失敗時靜默隱藏（不顯示錯誤，不影響主功能）

---

### g7 — Greeting 後端測試

**優先度**：P1  
**涉及檔案**：`apps/backend/tests/test_rag_greeting.py`（新建）  
**說明**：

**測試案例清單**：
| # | 案例 | 預期結果 |
|---|------|----------|
| 1 | 正常使用者，有歷史會議 | 回傳完整 payload（display_name, greeting_text, topics...）|
| 2 | 新使用者，無歷史會議 | 回傳 fallback payload（不拋例外，greeting_text 含引導提示）|
| 3 | 存取隔離 | UserB 無法看到 UserA 的會議資料 |
| 4 | summary_json 格式異常 | 跳過該會議，不拋例外 |
| 5 | pending_action_count 計算 | 只計 `status=pending` 的 action items |

---

### g8 — 部署與驗收

**優先度**：P0（依賴 g6 + g7）  
**說明**：

```bash
# 1. 執行後端測試
cd apps/backend && pytest tests/test_rag_greeting.py -v

# 2. 部署後端（含新 MeetingActionItem model）
TAG="20260608-v2"
gcloud builds submit \
  --tag asia-southeast1-docker.pkg.dev/prj-ai-meetchi-du/meetchi/backend:${TAG} \
  --timeout=900 apps/backend

gcloud run services update meetchi-backend \
  --image asia-southeast1-docker.pkg.dev/prj-ai-meetchi-du/meetchi/backend:${TAG} \
  --region asia-southeast1

# 3. 部署前端（含 Greeting Card UI + copy + brand tokens）
gcloud builds submit \
  --config apps/frontend/cloudbuild-frontend.yaml apps/frontend \
  --substitutions=_IMAGE_TAG="${TAG}"

gcloud run services update meetchi-frontend \
  --image asia-southeast1-docker.pkg.dev/prj-ai-meetchi-du/meetchi/meetchi-frontend:${TAG} \
  --region asia-southeast1

# 4. 驗收
curl -s "https://meetchi-backend-315688033208.asia-southeast1.run.app/api/v1/rag/greeting?user_upn=jerry_tai@mail.chimei.com.tw"
# 預期：JSON with display_name, greeting_text, topics, pending_count, suggested_questions
```

---

## 封鎖項目（Blocked）

### batch-gpu-endpoint / batch-backend-tasks / batch-deploy-verify

**封鎖原因**：2026-06-05 用戶決定 revert，待資源就位後重啟。  
**背景**：GPU ASR 服務原計劃從 parallel Semaphore 改為 `POST /asr/batch` 單一呼叫，以解決 GPU VRAM 競爭問題。Revert 後目前維持 Semaphore 並行模式。  
**重啟條件**：用戶確認資源（GPU quota / 預算）已就位。

---

## P1 UX 排期中

以下項目已有規格（`docs/design/brand-ux-optimization-2026-06-08.md`），尚未排入 sprint：

| 項目 | 說明 | 估時 |
|------|------|------|
| UX-2 | Dashboard 空狀態引導 + particle 圖騰 | 0.5d |
| UX-3 | RAG inline error + retry UI | 0.5d |
| UX-4 | 摘要完成「踏實感」toast 動畫 | 0.5d |
| VIS-1 | CHIMEI material particle motif（空狀態）| 1d |
| VIS-2 | MeetingCard chip 飽和度降低 | 0.5d |
| VIS-3 | `MeetingCard` div → button（keyboard nav）| 0.5d |

---

## 技術債備忘

| 項目 | 說明 | 嚴重度 |
|------|------|--------|
| RAG chat history | 目前用 sessionStorage（標籤關閉即清除），正式持久化需後端 DB | 中 |
| Greeting feature Phase 2 | 目前 Approach A（DB+template），Phase 2 規劃 embedding 主題聚類 | 低 |
| MS OAuth 資源 | Azure App 申請中，就位後需接通 `MS_CLIENT_ID` / `MS_TENANT_ID` env var | 待資源 |
| npm ENOSPC | Cloud Shell `/home` 4.8GB，npm cache 易滿 → 執行 `npm cache clean --force` 緩解 | 環境限制 |
