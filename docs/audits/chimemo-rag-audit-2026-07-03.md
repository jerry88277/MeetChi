# ChiMemo RAG 對抗式稽核 (2026-07-03, UTC+8)
查詢樣本: meeting b4d5503e-0a24-4984-a94e-4c1d87de6c08
方法: 第一性原理 + MECE + 多角色對抗式

## 核心 BUG (程式碼實證)
1. [HIGH] 引用索引錯位: LLM prompt 用 prompt_citations(title+summary+expanded_rows, rag.py:881-897)，
   但前端 citations = title+summary+**grouped/merged**(rag.py:900, 依相似度重排+120s合併)。
   兩者長度/順序不同 → [來源N] 指到錯的 citation。點錯來源、%顯示錯來源。
2. 三通道(segment/summary/title-match)無會議級去重 → 同會議重複(錄製(2)×6)。
3. segment citations 無相似度下限(summary 有 <0.3 skip, rag.py:670; segment 無) → 57% 也顯示。
4. used_citation_indices 後端算了(rag.py:926,966)但前端渲染全部 citations(ChatPanel:541) → 顯示未使用雜訊。
5. 單一會議提問卻跨會議: greeting 建議問句不帶 meeting_ids → 全域 user-scope 搜尋。
6. no_answer fallback 反而捏造答案(rag.py:938-945) 違反自己的誠實拒答規則。
7. 講者名未解析: RAG 取原始 ts.speaker(SPEAKER_A), 從不 JOIN meetings.speaker_mappings。
8. meeting_ids-only 分支(rag.py:197)無 user_upn 隔離 → 潛在越權。
9. 百分比對使用者無意義且因#1常是錯來源的分數。

## Q3 講者串接方案
speaker_mappings(meetings.speaker_mappings JSON: {SPEAKER_A:{display_name,role,color}}) 已由
逐字稿/摘要頁套用(SpeakerName.tsx)，但 RAG 完全沒用。修法:
- _find_similar_segments / _fetch_meeting_top_segments SELECT 增 m.speaker_mappings
- 組 citation.speaker 與 prompt context 時用 display_name(role) 取代 SPEAKER_A
- 無對應時 fallback 「講者N」(對齊前端規則), 不外露 SPEAKER_xx

## Q4 百分比
移除/弱化 cosine %，改為可點擊「跳到原文時間點」的來源連結；重點是精準連回問題，非分數。

## Q5 根因(MECE): (a)metadata (b)system prompt (c)intent→SQL 前置縮域
主因 = (a)+(c)，(b)次要。
- (a) segment 缺乏乾淨豐富 metadata: 無解析後講者名、會議日期、章節/主題標籤、敏感度標記；
  embedding 是原始 ASR 文字(含 Paltform/兩院 錯字)。→ 語意搜尋噪音大。
- (c) 現況已用 title-match+summary 兩個啟發式補丁，正因純向量過度召回。應加「意圖分類器」
  判斷 {單場查詢/跨場彙整/人物中心/待辦} 並產出 SQL WHERE(meeting_id/date/speaker) 先縮域再語意搜尋。
  b4d5503e 案例證明: 單場問題擴散成 13 條跨場引用。
- (b) system prompt(strict grounding, prompt.py) 其實不錯，但被 #6 fallback 與 #1 索引錯位破壞，
  任何 prompt 都救不了 → 非主因。

建議優先序: #1索引對齊 > #7講者名(Q3) > #2去重/#3門檻/#4used_citations > #9移除%(Q4) > 意圖路由器(Q5,較大)
