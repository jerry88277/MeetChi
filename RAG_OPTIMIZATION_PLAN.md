# MeetChi RAG 優化計畫

> 文件建立：2026-06-09  
> 目的：解決跨會議知識庫搜尋品質問題，使用者詢問特定會議內容時能得到正確答案

---

## 一、現況盤點

### 1.1 會議資料庫現況

| 會議名稱 | 時長(min) | Segments | Avg 字數/segment | 已嵌入 |
|---------|-----------|----------|-----------------|--------|
| AI Agent Paltform (ff5c) | 80.7 | 1207 | 17 | 100% |
| AI Agent Paltform (a843) | 80.7 | 1186 | 17 | 100% |
| 錄製 (2) | 59.9 | 391 | 10 | 100% |
| 勤威國際-奇美廠內自駕和導航雲端維護案合併議題討論 | 21.0 | 381 | 13 | 100% |
| 鴻才討論 | 18.8 | 368 | 14 | 100% |

**總計：3,533 segments，全部已嵌入 (100%)**

### 1.2 問題重現

- **問**：「勤崴國際會議的決議是什麼？」
- **答**：「根據現有會議記錄，無法明確回答此問題」
- **根因分析**：

### 1.3 核心問題（第一性原理拆解）

| 層次 | 問題 | 影響 |
|------|------|------|
| **ASR 層** | Whisper 將「勤崴」轉錄為「晴威」「勤威」「勤美」 | 關鍵詞向量不匹配 |
| **Embedding 層** | 每個 segment 平均僅 13-17 字，即使 sliding window 合併 11 段也僅 ~150 字 | 語意密度不足 |
| **搜尋層** | 純向量搜尋（cosine similarity），無 BM25 關鍵字匹配 | 同音異字/專有名詞完全搜不到 |
| **知識層** | 會議標題和摘要（summary_json）不參與 RAG 搜尋 | 「哪個會議」的問題無法定位 |
| **回答層** | LLM 僅看到低相關度的 citations，無法合成有用答案 | 回答品質差 |

---

## 二、逐字稿品質分析（勤威國際會議）

### 2.1 ASR 轉錄品質問題

```
逐字稿中出現的稱呼：
- "晴威" (正確：勤崴)
- "勤威" (正確：勤崴)  
- "勤美" (正確：奇美，但此處指勤崴)
- "浩瑤" / "浩耀" (同一人)
```

### 2.2 逐字稿內容樣本

```
[0] 晴威的這部分
[1] 自駕車的部分
[2] 那這邊應該還是可以啦
[3] 對晴威來講
[4] 他們只是一個類似 software
[5] 對不對
...
```

**觀察**：
1. 口語化極高，大量語氣詞（「對不對」「好」「那」）
2. 每段極短（5-15 字），缺乏完整句意
3. 專有名詞被 ASR 錯誤轉錄

### 2.3 會議摘要品質（LLM 生成）

```json
{
  "tldr": "本次會議主要討論導航系統與自駕車系統整合的雲端維護費用問題，
           目標是將雙方合計的雲端維護費從約 100 萬降至 33 萬...",
  "decisions": ["由「說話者 A」統籌導航..."],
  "action_items": [...]
}
```

**觀察**：摘要品質很好，包含正確的決議資訊。但摘要**不參與 RAG 搜尋**。

---

## 三、優化方案（MECE 分層）

### 方案 A：搜尋架構優化（效果最大、實作中等）

#### A1. 會議摘要納入 RAG 搜尋

**原理**：會議摘要已由 LLM 整理過，語意密度高、包含決議/行動項目。
將 `summary_json` 作為獨立的「超級 segment」參與向量搜尋。

```
實作方式：
1. 新增 summary_embedding 欄位到 meetings 表（已存在）
2. RAG 搜尋時，除了搜 transcript_segments，也搜 meetings.summary_embedding
3. 匹配到摘要時，直接將 summary_json 的相關欄位作為 citation 返回
```

**預期效果**：「勤崴國際會議的決議」→ 匹配到摘要中的 "decisions" 欄位 → 正確回答

#### A2. 會議標題 + 關鍵字注入 Embedding

**原理**：在每個 segment 的 embedding 文本前面加入會議標題作為 prefix，
讓向量搜尋能透過標題關聯到正確會議。

```
Before: "[說話者A] 晴威的這部分 自駕車的部分 那這邊應該還是可以啦..."
After:  "[會議：勤威國際-奇美廠內自駕和導航雲端維護案] 晴威的這部分 自駕車的部分..."
```

**預期效果**：向量搜尋「勤崴國際」時，「勤威國際」的 prefix 提供足夠語意接近度

#### A3. Hybrid Search（向量 + BM25 關鍵字）

**原理**：純向量搜尋無法處理同音異字（勤崴 vs 晴威），
BM25 可以匹配部分字元重疊（勤崴 → 勤威，至少「勤」字一樣）。

```
實作方式：
1. 對 content_raw 建立 pg_trgm GIN 索引
2. RAG 查詢時：
   - Vector search: top_k=10 (語意相關)
   - BM25/trigram search: top_k=10 (關鍵字匹配)
   - 合併去重 + RRF (Reciprocal Rank Fusion) 排序
```

**預期效果**：「勤崴」搜尋能透過 trigram 匹配到含「勤威」的 segments

---

### 方案 B：Embedding 品質優化（效果中等、實作簡單）

#### B1. 加大 Sliding Window

```
現狀：EMBED_WINDOW=5（前後各 5 段，共 11 段 ≈ 150 字）
建議：EMBED_WINDOW=10（前後各 10 段，共 21 段 ≈ 300 字）
```

**取捨**：更大窗口 → 語意更完整，但相鄰 segments 的 embedding 更相似 → 區分度降低

#### B2. 段落合併 (Paragraph Chunking)

**原理**：不再以 ASR 原始 segment 為 embedding 單位，
改為將連續 segments 合併成語意段落（基於停頓 > 2 秒 or 說話者切換）。

```
合併策略：
- 同一說話者連續發言 → 合成一個段落（直到停頓 > 3 秒 or 字數 > 200）
- 合併後段落作為新的 embedding 單位
- 保留原始 segment 對照關係（用於 citation 精確定位）
```

**預期效果**：Embedding 單位從 13 字提升到 100-200 字，語意密度大幅提升

---

### 方案 C：ASR 品質提升（效果大、實作需時）

#### C1. 專有名詞表 (Hotwords/Prompt)

**原理**：Whisper API 支持 `initial_prompt` 參數，可注入預期出現的詞彙，
提高這些詞彙的辨識準確率。

**架構設計：Global + Local 聯集策略**

```
┌─────────────────────────────────────────────────────┐
│              專有名詞對照表 (Glossary)                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Global 對照表 (By User)                             │
│  ┌───────────────┬──────────────────────┐           │
│  │ 錯誤轉錄       │ 正確名稱              │           │
│  ├───────────────┼──────────────────────┤           │
│  │ 晴威 / 勤威    │ 勤崴國際              │           │
│  │ 勤美          │ 奇美實業              │           │
│  │ 鴻材          │ 鴻才                  │           │
│  └───────────────┴──────────────────────┘           │
│                                                     │
│  Local 對照表 (By Meeting)                           │
│  ┌───────────────┬──────────────────────┐           │
│  │ 錯誤轉錄       │ 正確名稱              │           │
│  ├───────────────┼──────────────────────┤           │
│  │ 浩瑤          │ 浩耀                  │           │
│  │ 勤威雲        │ 勤崴雲                │           │
│  └───────────────┴──────────────────────┘           │
│                                                     │
│  合併規則：                                          │
│  final_glossary = Global ∪ Local                    │
│  若 key 重複 → Local 優先覆蓋 Global                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**DB Schema 設計：**

```sql
-- 使用者級全域對照表
CREATE TABLE user_glossary (
    id          VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    user_upn    VARCHAR NOT NULL,         -- 擁有者
    wrong_text  VARCHAR NOT NULL,         -- ASR 可能的錯誤轉錄
    correct_text VARCHAR NOT NULL,        -- 正確名稱
    category    VARCHAR DEFAULT 'company', -- company/person/product/other
    usage_count INT DEFAULT 0,            -- 使用次數（排序用）
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_upn, wrong_text)          -- 同使用者不重複
);

-- 單一會議對照表
CREATE TABLE meeting_glossary (
    id          VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id  VARCHAR NOT NULL REFERENCES meetings(id),
    wrong_text  VARCHAR NOT NULL,
    correct_text VARCHAR NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE(meeting_id, wrong_text)
);

CREATE INDEX idx_user_glossary_upn ON user_glossary(user_upn);
CREATE INDEX idx_meeting_glossary_mid ON meeting_glossary(meeting_id);
```

**使用流程（UX）：**

```
1. 上傳錄音檔 → 建立 Meeting
2. (Optional) 彈出「專有名詞提示」：
   - 自動帶入 Global 詞彙表（使用者已建立的）
   - 使用者可新增 Local 詞彙（本次會議特有）
   - 可跳過 (Skip)
3. 開始轉錄 → Whisper initial_prompt 注入聯集後的詞彙
4. 轉錄完成後 → Post-processing 用對照表做文字替換
5. 替換完成後 → Re-embed（embedding 用修正後的文字）
```

**ASR Pipeline 整合：**

```python
# 在 tasks.py 的轉錄流程中
def get_whisper_prompt(user_upn: str, meeting_id: str, db: Session) -> str:
    """合併 Global + Local 詞彙表，生成 Whisper initial_prompt"""
    # 1. 取得 Global
    global_terms = db.query(UserGlossary).filter(
        UserGlossary.user_upn == user_upn
    ).all()
    
    # 2. 取得 Local
    local_terms = db.query(MeetingGlossary).filter(
        MeetingGlossary.meeting_id == meeting_id
    ).all()
    
    # 3. 聯集（Local 優先）
    merged = {t.correct_text for t in global_terms}
    merged.update({t.correct_text for t in local_terms})
    
    # 4. 組成 prompt（Whisper 格式：用逗號分隔的詞彙列表）
    return "以下是本次會議可能出現的專有名詞：" + "、".join(merged)

def post_correct_transcript(segments, glossary_map: dict) -> list:
    """轉錄後用對照表修正錯字"""
    for seg in segments:
        for wrong, correct in glossary_map.items():
            seg.content_raw = seg.content_raw.replace(wrong, correct)
    return segments
```

**前端 UI 規劃：**

```
系統設定 → 專有名詞管理（Global）
├── 新增對照：[錯誤轉錄] → [正確名稱] [分類▼] [新增]
├── 已建立清單（可編輯/刪除）
└── 常用清單（usage_count 排序，快速勾選）

上傳流程 → Step 2: 專有名詞提示（Local）
├── 自動帶入 Global 詞彙（灰色 tag，可取消）
├── 新增本次會議詞彙：[輸入框] [新增]
├── [跳過] [確認並開始轉錄]
└── 提示文字：「新增會議中可能出現的人名、公司名，可提高轉錄準確率」
```

#### C2. 後處理修正 (Post-processing)

**原理**：ASR 完成後，用 LLM 對逐字稿做一次修正，
將明顯錯誤的專有名詞替換為正確版本。

```
pipeline: ASR → LLM post-correct (based on global glossary) → embedding
```

---

### 方案 D：查詢理解優化（效果中等、實作簡單）

#### D1. Query Expansion

**原理**：使用者查詢「勤崴國際」，系統先用 LLM 擴展為多個同義查詢：

```
原始查詢：「勤崴國際會議的決議是什麼」
擴展查詢：
- 「勤崴國際 會議決議」
- 「勤威 自駕車 雲端維護 決議」（利用已知的 ASR 錯字）
- 「導航系統整合 費用 決定」（語意擴展）
```

#### D2. 先定位會議，再搜尋內容（Two-stage Retrieval）

**原理**：先搜尋 meeting title / summary 確定是哪個會議，
再限定 meeting_id 做細部 segment 搜尋。

```
Stage 1: Query vs summary_embedding → 確認 meeting_id
Stage 2: Query vs segments (filtered by meeting_id) → 取得具體段落
```

---

## 四、優先順序建議

| 優先 | 方案 | 預期效果 | 實作時間 | 理由 |
|------|------|----------|----------|------|
| P0 | A1 (摘要納入搜尋) | ⭐⭐⭐⭐⭐ | 2h | 摘要已有正確答案，只差「被搜到」|
| P0 | A2 (標題注入 Embedding) | ⭐⭐⭐⭐ | 1h | 解決「哪個會議」的定位問題 |
| P1 | D2 (Two-stage Retrieval) | ⭐⭐⭐⭐ | 3h | 先定位會議再搜內容，精準度高 |
| P1 | B2 (段落合併) | ⭐⭐⭐ | 4h | 提升 embedding 品質根本方案 |
| P2 | A3 (Hybrid Search) | ⭐⭐⭐ | 4h | 解決同音異字，但需新 index |
| P2 | C1 (專有名詞表) | ⭐⭐⭐ | 6h | 解決 ASR 根源問題，需新 UI |
| P3 | D1 (Query Expansion) | ⭐⭐ | 2h | 效果有限但簡單 |
| P3 | B1 (加大 Window) | ⭐⭐ | 0.5h | 邊際效益遞減 |
| P4 | C2 (Post-processing) | ⭐⭐⭐ | 3h | 需重新轉錄已有資料 |

---

## 五、建議實施順序

### Phase 1（即刻可做，1-2 小時）
1. **A1**: 讓 RAG 搜尋也查 `meetings.summary_embedding`
2. **A2**: Re-embed 所有 segments，prefix 加入會議標題

### Phase 2（短期，3-4 小時）
3. **D2**: Two-stage retrieval（先找會議 → 再搜段落）
4. **B2**: Paragraph chunking（合併短 segments 為語意段落）

### Phase 3（中期，功能開發）
5. **C1**: 專有名詞 UI + Whisper hotwords
6. **A3**: Hybrid search (BM25 + Vector)

---

## 六、驗證基準

修復後需通過以下測試查詢：

| 查詢 | 預期回答關鍵字 | 目標會議 |
|------|--------------|----------|
| 勤崴國際會議的決議是什麼 | 雲端維護費 / 100萬降至33萬 / 統籌 | 勤威國際 |
| AI Agent 平台怎麼部署 | 部署階段 / 啟用 / 後台測試 | AI Agent Paltform |
| 鴻才討論了什麼 | (需確認該會議摘要內容) | 鴻才討論 |
| 自駕車的雲端維護費多少 | 100萬 / 33萬 / 省20萬 | 勤威國際 |

---

## 七、技術備註

- **Embedding Model**: Gemini `text-embedding-004` (768 維)
- **Vector DB**: PostgreSQL + pgvector (cosine distance)
- **Current Window**: `EMBED_WINDOW=5` (前後各5段)
- **MemPlace 隔離**: JOIN `meeting_participants` by `user_upn`
- **Summary 已生成**: 所有會議都有 `summary_json`（tldr + summary + decisions + action_items）
- **summary_embedding 欄位**: meetings 表已有此欄位，部分會議已嵌入
