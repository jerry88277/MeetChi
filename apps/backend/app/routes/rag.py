"""
RAG (Retrieval-Augmented Generation) Routes for Cross-Meeting Q&A

Enables users to ask natural language questions across all meeting transcripts.
Uses pgvector cosine similarity to find relevant segments, then generates
cited answers via Gemini.

Endpoint:
    POST /api/v1/rag/ask - Ask a question across meetings
    POST /api/v1/rag/backfill - One-time backfill embeddings for existing data
"""

import logging
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models import Meeting, TranscriptSegment, MeetingParticipant
from app.llm_utils import get_gemini_client, GEMINI_MODEL
from app.embedding import embed_single_text, backfill_all_embeddings
from app.rag import (
    build_grounded_prompt,
    expand_with_context,
    CONFIDENCE_LEVELS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


# ============================================
# Request / Response Schemas
# ============================================

class ChatMessage(BaseModel):
    role: str = Field(..., description="user or ai")
    text: str = Field(..., description="Message text")

class RAGRequest(BaseModel):
    question:    str            = Field(..., min_length=2, max_length=2000, description="自然語言問題")
    history:     Optional[List[ChatMessage]] = Field([], description="前面的對話歷史紀錄，用於處理跟進追問 (Follow-up) 的上下文切換")
    user_upn:    str            = Field(..., description="當前登入用戶的 AD UPN（user@company.com），強制 MemPlace 隔離存取")
    meeting_ids: Optional[List[str]] = Field(None, description="進一步限定搜索的會議 ID 清單（在 user_upn 範圍內篩選）")
    top_k:       int            = Field(10, ge=1, le=50, description="返回的相關段落數")

    @field_validator('user_upn', mode='before')
    @classmethod
    def validate_user_upn(cls, v: str) -> str:
        """確保 UPN 格式包含 @ 符號，防止空白或非法值繞過存取控制"""
        if not v or not isinstance(v, str):
            raise ValueError("user_upn 不可為空")
        v = v.strip()
        if '@' not in v:
            raise ValueError("user_upn 必須是有效的 AD UPN 格式（user@company.com）")
        return v.lower()  # 統一小寫，避免大小寫造成查詢不到


class Citation(BaseModel):
    meeting_id: str
    meeting_title: str
    speaker: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    content: str
    similarity: float = Field(description="餘弦相似度分數 (0-1)")

class RAGResponse(BaseModel):
    answer: str
    citations: List[Citation]
    segments_searched: int = Field(description="共搜索了多少個 embedding 段落")
    question: str
    confidence: str = Field(
        default="no_answer",
        description="LLM 自我評估的回答信心: high / medium / low / no_answer (見 app.rag.prompt)",
    )


class LastMeetingSummary(BaseModel):
    title: str
    date: str
    key_actions: List[str]


class RagGreetingResponse(BaseModel):
    display_name: str
    meeting_count: int
    top_topics: List[str]
    last_meeting: Optional[LastMeetingSummary] = None
    pending_action_count: int
    greeting_text: str
    suggested_questions: List[str]


# ============================================
# RAG Pipeline Core
# ============================================

def _find_similar_segments(
    db: Session,
    query_embedding: list,
    user_upn: Optional[str] = None,
    meeting_ids: Optional[List[str]] = None,
    top_k: int = 10,
) -> tuple:
    """
    Find top-K most similar transcript segments using pgvector cosine distance.

    存取控制隆離优先級（MemPlace 雔離）：
      1. user_upn  → JOIN meeting_participants ，只搜尋該用戶有權限的會議（首選）
      2. meeting_ids → 在以上範圍內進一步縮小搜索範圍（選遳）
      3. 無兩者  → 展開全域搜索（已登入、管理員模式等）

    Returns:
        (results, total_searched): list of result rows and total segments in search scope
    """
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    if user_upn:
        # ============================================================
        # ★ MemPlace 隔離查詢：JOIN meeting_participants 強制邏存取
        # PostgreSQL Query Planner 會自動：
        #   1. idx_mp_user_upn 定位少數幾場會議 meeting_id
        #   2. 對這少數幾場會議的 segments 做 Exact Search
        #   效能：~1ms（與所有會議的全域搜索相比減封99.95%車算量）
        # ============================================================
        if meeting_ids:
            # user_upn + meeting_ids 雙重邏存取
            placeholders = ",".join(f":mid_{i}" for i in range(len(meeting_ids)))
            sql = text(f"""
                SELECT
                    ts.id,
                    ts.meeting_id,
                    ts.speaker,
                    ts.start_time,
                    ts.end_time,
                    ts.content_polished,
                    ts.content_raw,
                    m.title as meeting_title,
                    (ts.content_embedding <=> CAST(:query_embedding AS vector)) as distance
                FROM transcript_segments ts
                JOIN meetings m ON ts.meeting_id = m.id
                JOIN meeting_participants mp
                    ON m.id = mp.meeting_id AND mp.user_upn = :user_upn
                WHERE ts.content_embedding IS NOT NULL
                  AND ts.meeting_id IN ({placeholders})
                ORDER BY ts.content_embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
            """)
            params = {"query_embedding": embedding_str, "top_k": top_k, "user_upn": user_upn}
            for i, mid in enumerate(meeting_ids):
                params[f"mid_{i}"] = mid
        else:
            # 純 user_upn 隔離（最常見情境）
            sql = text("""
                SELECT
                    ts.id,
                    ts.meeting_id,
                    ts.speaker,
                    ts.start_time,
                    ts.end_time,
                    ts.content_polished,
                    ts.content_raw,
                    m.title as meeting_title,
                    (ts.content_embedding <=> CAST(:query_embedding AS vector)) as distance
                FROM transcript_segments ts
                JOIN meetings m ON ts.meeting_id = m.id
                JOIN meeting_participants mp
                    ON m.id = mp.meeting_id AND mp.user_upn = :user_upn
                WHERE ts.content_embedding IS NOT NULL
                ORDER BY ts.content_embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
            """)
            params = {"query_embedding": embedding_str, "top_k": top_k, "user_upn": user_upn}

        results = db.execute(sql, params).fetchall()

        # 隙間搜索範圍：該用戶實際被搜索的 segments 數
        count_sql = text("""
            SELECT COUNT(*) FROM transcript_segments ts
            JOIN meeting_participants mp ON ts.meeting_id = mp.meeting_id
            WHERE mp.user_upn = :user_upn AND ts.content_embedding IS NOT NULL
        """)
        total_searched = db.execute(count_sql, {"user_upn": user_upn}).scalar()

    elif meeting_ids:
        # 無 user_upn，只有 meeting_ids（公開 API 或管理員專用）
        placeholders = ",".join(f":mid_{i}" for i in range(len(meeting_ids)))
        sql = text(f"""
            SELECT
                ts.id,
                ts.meeting_id,
                ts.speaker,
                ts.start_time,
                ts.end_time,
                ts.content_polished,
                ts.content_raw,
                m.title as meeting_title,
                (ts.content_embedding <=> CAST(:query_embedding AS vector)) as distance
            FROM transcript_segments ts
            JOIN meetings m ON ts.meeting_id = m.id
            WHERE ts.content_embedding IS NOT NULL
              AND ts.meeting_id IN ({placeholders})
            ORDER BY ts.content_embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """)
        params = {"query_embedding": embedding_str, "top_k": top_k}
        for i, mid in enumerate(meeting_ids):
            params[f"mid_{i}"] = mid
        results = db.execute(sql, params).fetchall()
        count_sql = text(
            f"SELECT COUNT(*) FROM transcript_segments "
            f"WHERE meeting_id IN ({placeholders}) AND content_embedding IS NOT NULL"
        )
        total_searched = db.execute(count_sql, {f"mid_{i}": mid for i, mid in enumerate(meeting_ids)}).scalar()

    else:
        # 全域搜索（管理員或未實作 AD 整合時指, 建議硝亮命名 limit 限更小）
        sql = text("""
            SELECT
                ts.id,
                ts.meeting_id,
                ts.speaker,
                ts.start_time,
                ts.end_time,
                ts.content_polished,
                ts.content_raw,
                m.title as meeting_title,
                (ts.content_embedding <=> CAST(:query_embedding AS vector)) as distance
            FROM transcript_segments ts
            JOIN meetings m ON ts.meeting_id = m.id
            WHERE ts.content_embedding IS NOT NULL
            ORDER BY ts.content_embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """)
        params = {"query_embedding": embedding_str, "top_k": top_k}
        results = db.execute(sql, params).fetchall()
        total_searched = db.execute(
            text("SELECT COUNT(*) FROM transcript_segments WHERE content_embedding IS NOT NULL")
        ).scalar()

    return results, total_searched


def _find_similar_summaries(
    db: Session,
    query_embedding: list,
    user_upn: Optional[str] = None,
    meeting_ids: Optional[List[str]] = None,
    top_k: int = 3,
) -> list:
    """
    Search meetings.summary_embedding for high-level meeting-matching.
    
    Returns list of rows with: meeting_id, title, summary_json, distance.
    Summary embeddings contain title + decisions + action_items → excellent for
    "which meeting discussed X?" type questions.
    """
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    if user_upn:
        if meeting_ids:
            placeholders = ",".join(f":mid_{i}" for i in range(len(meeting_ids)))
            sql = text(f"""
                SELECT
                    m.id as meeting_id,
                    m.title as meeting_title,
                    m.summary_json,
                    (m.summary_embedding <=> CAST(:query_embedding AS vector)) as distance
                FROM meetings m
                JOIN meeting_participants mp
                    ON m.id = mp.meeting_id AND mp.user_upn = :user_upn
                WHERE m.summary_embedding IS NOT NULL
                  AND m.deleted_at IS NULL
                  AND m.id IN ({placeholders})
                ORDER BY m.summary_embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
            """)
            params = {"query_embedding": embedding_str, "top_k": top_k, "user_upn": user_upn}
            for i, mid in enumerate(meeting_ids):
                params[f"mid_{i}"] = mid
        else:
            sql = text("""
                SELECT
                    m.id as meeting_id,
                    m.title as meeting_title,
                    m.summary_json,
                    (m.summary_embedding <=> CAST(:query_embedding AS vector)) as distance
                FROM meetings m
                JOIN meeting_participants mp
                    ON m.id = mp.meeting_id AND mp.user_upn = :user_upn
                WHERE m.summary_embedding IS NOT NULL
                  AND m.deleted_at IS NULL
                ORDER BY m.summary_embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
            """)
            params = {"query_embedding": embedding_str, "top_k": top_k, "user_upn": user_upn}
    elif meeting_ids:
        placeholders = ",".join(f":mid_{i}" for i in range(len(meeting_ids)))
        sql = text(f"""
            SELECT
                m.id as meeting_id,
                m.title as meeting_title,
                m.summary_json,
                (m.summary_embedding <=> CAST(:query_embedding AS vector)) as distance
            FROM meetings m
            WHERE m.summary_embedding IS NOT NULL
              AND m.deleted_at IS NULL
              AND m.id IN ({placeholders})
            ORDER BY m.summary_embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """)
        params = {"query_embedding": embedding_str, "top_k": top_k}
        for i, mid in enumerate(meeting_ids):
            params[f"mid_{i}"] = mid
    else:
        sql = text("""
            SELECT
                m.id as meeting_id,
                m.title as meeting_title,
                m.summary_json,
                (m.summary_embedding <=> CAST(:query_embedding AS vector)) as distance
            FROM meetings m
            WHERE m.summary_embedding IS NOT NULL
              AND m.deleted_at IS NULL
            ORDER BY m.summary_embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """)
        params = {"query_embedding": embedding_str, "top_k": top_k}

    try:
        results = db.execute(sql, params).fetchall()
        return results
    except Exception as e:
        logger.warning(f"[RAG] Summary search failed (non-fatal): {e}")
        return []


# ============================================
# Title Fuzzy-Match Pre-Filter (A3 Optimization)
# ============================================

def _find_title_matched_meetings(
    db: Session,
    query: str,
    user_upn: Optional[str] = None,
    meeting_ids: Optional[List[str]] = None,
) -> List[dict]:
    """
    Find meetings whose title is referenced in the user's query.
    
    Strategy:
      1. Fetch all accessible meeting titles
      2. Check if any title (or significant substring) appears in the query
      3. Return matched meetings sorted by title match quality
    
    This handles the common case: "鴻才會議討論什麼" → matches meeting "鴻才討論"
    """
    # Fetch accessible meetings with titles
    if user_upn:
        if meeting_ids:
            placeholders = ",".join(f":mid_{i}" for i in range(len(meeting_ids)))
            sql = text(f"""
                SELECT m.id, m.title, m.summary_json
                FROM meetings m
                JOIN meeting_participants mp ON m.id = mp.meeting_id AND mp.user_upn = :user_upn
                WHERE m.deleted_at IS NULL AND m.title IS NOT NULL AND m.title != ''
                  AND m.id IN ({placeholders})
            """)
            params = {"user_upn": user_upn}
            for i, mid in enumerate(meeting_ids):
                params[f"mid_{i}"] = mid
        else:
            sql = text("""
                SELECT m.id, m.title, m.summary_json
                FROM meetings m
                JOIN meeting_participants mp ON m.id = mp.meeting_id AND mp.user_upn = :user_upn
                WHERE m.deleted_at IS NULL AND m.title IS NOT NULL AND m.title != ''
            """)
            params = {"user_upn": user_upn}
    else:
        sql = text("""
            SELECT m.id, m.title, m.summary_json
            FROM meetings m
            WHERE m.deleted_at IS NULL AND m.title IS NOT NULL AND m.title != ''
        """)
        params = {}

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception as e:
        logger.warning(f"[RAG] Title match query failed: {e}")
        return []

    # Normalize query for matching (remove common filler words)
    query_normalized = query.strip()
    # Remove common question patterns to extract the core topic
    filler_patterns = [
        r'會議[在中裡]?[討論談到提到講了說了]+(什麼|哪些|了什麼)',
        r'[討論談到提到講了說了]+(什麼|哪些|了什麼)',
        r'(的|之)?主要?(內容|議題|討論|重點|結論|決議)(是什麼|有哪些)?',
        r'在(討論|談|講|說)(什麼|哪些)',
    ]
    query_core = query_normalized
    for pat in filler_patterns:
        query_core = re.sub(pat, '', query_core)
    query_core = query_core.strip()
    if not query_core:
        query_core = query_normalized

    matched = []
    for row in rows:
        title = row.title.strip()
        if not title:
            continue
        
        # Strategy 1: Title appears in query (or query_core)
        # Strategy 2: Query core appears in title
        # Strategy 3: Significant overlap (shared characters ratio)
        
        score = 0.0
        
        # Exact title in query
        if title in query_normalized or title in query_core:
            score = 1.0
        # Query core in title
        elif query_core and query_core in title:
            score = 0.9
        else:
            # Character-level fuzzy: compute overlap ratio
            # Split title into meaningful tokens (>= 2 chars)
            title_tokens = [t for t in re.split(r'[\s\-_—–·()（）\[\]【】,，.。]+', title) if len(t) >= 2]
            matched_tokens = [t for t in title_tokens if t in query_normalized or t in query_core]
            if title_tokens and matched_tokens:
                score = len(matched_tokens) / len(title_tokens)
                # Boost if the matched portion is significant
                if len(matched_tokens) >= 1 and any(len(t) >= 2 for t in matched_tokens):
                    score = max(score, 0.5)
        
        if score >= 0.5:
            matched.append({
                "meeting_id": row.id,
                "title": title,
                "summary_json": row.summary_json,
                "match_score": score,
            })

    # Sort by match quality
    matched.sort(key=lambda x: x["match_score"], reverse=True)
    logger.info(f"[RAG/A3] Title match for '{query}' (core='{query_core}'): {[(m['title'], m['match_score']) for m in matched[:5]]}")
    return matched[:3]  # max 3 title-matched meetings


def _fetch_meeting_top_segments(
    db: Session,
    meeting_id: str,
    query_embedding: list,
    top_k: int = 8,
) -> list:
    """
    Fetch top-K segments from a specific meeting, ordered by similarity to query.
    Used when title-match identifies a meeting but vector search missed it.
    """
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    sql = text("""
        SELECT
            ts.id,
            ts.meeting_id,
            ts.speaker,
            ts.start_time,
            ts.end_time,
            ts.content_polished,
            ts.content_raw,
            m.title as meeting_title,
            (ts.content_embedding <=> CAST(:query_embedding AS vector)) as distance
        FROM transcript_segments ts
        JOIN meetings m ON ts.meeting_id = m.id
        WHERE ts.meeting_id = :meeting_id
          AND ts.content_embedding IS NOT NULL
        ORDER BY ts.content_embedding <=> CAST(:query_embedding AS vector)
        LIMIT :top_k
    """)
    try:
        return db.execute(sql, {
            "query_embedding": embedding_str,
            "meeting_id": meeting_id,
            "top_k": top_k,
        }).fetchall()
    except Exception as e:
        logger.warning(f"[RAG/A3] Failed to fetch segments for meeting {meeting_id}: {e}")
        return []


def _build_rag_prompt(question: str, citations: List[Citation], history: Optional[List[ChatMessage]] = None) -> str:
    """
    Build a Gemini prompt with retrieved context, conversation history, and clear citation instructions.
    """
    context_parts = []
    for i, c in enumerate(citations, 1):
        speaker_info = f" ({c.speaker})" if c.speaker else ""
        time_info = f" [{c.start_time:.1f}s]" if c.start_time else ""
        context_parts.append(
            f"[來源{i}] 會議「{c.meeting_title}」{speaker_info}{time_info}:\n{c.content}"
        )
    
    context_block = "\n\n".join(context_parts)
    
    history_block = ""
    if history and len(history) > 0:
        history_parts = []
        for msg in history:
            role_name = "User" if msg.role.lower() == "user" else "AI"
            history_parts.append(f"{role_name}: {msg.text}")
        history_block = "過去的對話紀錄：\n" + "\n".join(history_parts) + "\n---\n"
    
    prompt = f"""你是 MeetChi 跨會議問答智能助手。請作為一名資深分析師，根據以下會議記錄段落與上下文，有邏輯、有條理地綜合分析並解答用戶的問題。

核心原則：
1. 【嚴格 JSON 輸出格式】你必須將回答封裝在一個有效的 JSON 格式中，包含兩個欄位："answer" (字串，你的完整回答內容) 與 "used_citations" (整數陣列，你想在 answer 中引用的來源數字)。
2. 【禁止 Markdown】請拋棄 AI 特有的撰寫風格（明確禁止使用 **、# 粗體或大標題等多餘的 Markdown 語法）。直接提供清晰平鋪直敘、有條理的結構化「純文字」。可適度使用換行符號 `\n` 排版。
3. 【統整思考】不要機械性貼上原文，請消化內容後給出一份清晰易懂的綜合回答。
4. 【事實根據與引用標註】你的回答必須有來源依據。引用特定會議的觀點時，請在句末自然地標註來源，格式嚴格為 [來源N]。
5. 【資訊不足】如果資料無法解答用戶問題，請誠實說明「現有會議記錄未提及相關資訊」。
6. 【對話連貫】如果用戶的最新問題是針對先前的對話追問，請保持連貫性地回答。

請確保你回傳的資料為純 JSON，並遵守以下範例結構：
{{
  "answer": "你清晰平鋪直敘的結構化文字回答，例如：行銷專案的第一階段已經完成[來源1]。後續進度尚未確認[來源2]。",
  "used_citations": [1, 2]
}}

---
提供的會議記錄段落（可用於尋找客觀事實）：

{context_block}

---
{history_block}
用戶最新問題：{question}

請綜合分析並回答："""
    
    return prompt

def _contextualize_query(client, question: str, history: List[ChatMessage]) -> str:
    """
    Query Contextualization: 
    Rewrite the user's question into a standalone query based on conversational history.
    """
    if not history:
        return question
        
    history_str = "\n".join([f"{'User' if m.role.lower() == 'user' else 'AI'}: {m.text}" for m in history])
    
    prompt = f"""你是一個幫助資料庫檢索的「查詢重寫 (Query Rewrite) 助手」。
給定以下對話紀錄以及使用者最新提出的問題，這個問題可能使用了代名詞（例如「那件事的負責人是誰？」或「後來預算怎麼定？」），缺乏具體主詞。
請根據對話紀錄推斷出使用者正在詢問的主題，並將使用者的最新問題重新改寫成一個獨立且沒有代名詞的完整搜尋句（Standalone Query），方便用來搜尋相關會議紀錄。

只要回傳改寫後的完整搜尋句即可，不需要提供任何解釋。如果問題已經完整且不需要歷史脈絡也能理解，請直接原封不動回傳該問題。

>>> 對話紀錄:
{history_str}

>>> 使用者最新問題:
{question}

>>> 改寫後的搜尋句:"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.0,
                "max_output_tokens": 100,
            },
        )
        rewritten = response.text.strip() if response.text else question
        logger.info(f"[Query Contextualizer] Original: {question} -> Rewritten: {rewritten}")
        return rewritten
    except Exception as e:
        logger.warning(f"[Query Contextualizer] Failed to rewrite query: {e}. Falling back to original.")
        return question


# ============================================
# API Endpoints
# ============================================

@router.post("/ask", response_model=RAGResponse)
async def ask_across_meetings(request: RAGRequest, db: Session = Depends(get_db)):
    """
    Ask a question across all (or selected) meeting transcripts.
    
    Pipeline:
    1. Embed the question → 768-dim vector
    2. pgvector cosine similarity search → Top-K segments
    3. Build context prompt → Gemini generates cited answer
    """
    import time
    _t0 = time.time()  # Y5 (2026-05-25)：計時用於 history 紀錄
    client = get_gemini_client()
    if not client:
        raise HTTPException(status_code=503, detail="Gemini client unavailable")

    # Step 1: Query Contextualization (If history exists)
    search_query = request.question
    if request.history:
        search_query = _contextualize_query(client, request.question, request.history)
    
    # Step 1.5: Embed the contextualized query
    query_embedding = embed_single_text(client, search_query)
    if query_embedding is None:
        raise HTTPException(status_code=500, detail="Failed to generate query embedding")
    
    # Step 2: Find similar segments via pgvector (with MemPlace isolation)
    try:
        results, total_searched = _find_similar_segments(
            db, query_embedding,
            user_upn=request.user_upn,
            meeting_ids=request.meeting_ids,
            top_k=request.top_k,
        )
    except Exception as e:
        logger.error(f"[RAG] Vector search failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Vector search failed. Ensure pgvector extension is enabled: {str(e)}"
        )

    # Step 2.1: Also search meeting summaries (A1 optimization)
    # Summary embeddings contain title + decisions + action_items → great for
    # "which meeting discussed X?" or "what were the decisions in meeting Y?"
    summary_citations: List[Citation] = []
    try:
        summary_results = _find_similar_summaries(
            db, query_embedding,
            user_upn=request.user_upn,
            meeting_ids=request.meeting_ids,
            top_k=3,
        )
        for sr in summary_results:
            sim = 1.0 - float(sr.distance)
            if sim < 0.3:
                continue  # skip low-relevance summaries
            # Extract meaningful content from summary_json
            summary_content = ""
            try:
                sdata = json.loads(sr.summary_json) if sr.summary_json else {}
                parts = []
                if sdata.get("summary"):
                    parts.append(sdata["summary"])
                if sdata.get("decisions"):
                    decisions = sdata["decisions"]
                    dec_texts = []
                    for d in decisions:
                        if isinstance(d, str):
                            dec_texts.append(d)
                        elif isinstance(d, dict):
                            dec_texts.append(d.get("decision", ""))
                    if dec_texts:
                        parts.append("決議事項：" + "；".join(filter(None, dec_texts)))
                if sdata.get("action_items"):
                    items = sdata["action_items"]
                    item_texts = []
                    for item in items[:5]:
                        if isinstance(item, str):
                            item_texts.append(item)
                        elif isinstance(item, dict):
                            item_texts.append(item.get("task", ""))
                    if item_texts:
                        parts.append("行動項目：" + "；".join(filter(None, item_texts)))
                summary_content = "\n".join(filter(None, parts))
            except Exception:
                summary_content = sr.summary_json[:500] if sr.summary_json else ""

            if summary_content:
                summary_citations.append(Citation(
                    meeting_id=sr.meeting_id,
                    meeting_title=sr.meeting_title or "未命名會議",
                    speaker=None,
                    start_time=None,
                    end_time=None,
                    content=f"[會議摘要] {summary_content}",
                    similarity=round(sim, 4),
                ))
    except Exception as e:
        logger.warning(f"[RAG] Summary citation build failed (non-fatal): {e}")

    # Step 2.2: Title fuzzy-match pre-filter (A3 optimization)
    # If vector search returned low-quality results AND user's query references
    # a meeting by name, force-include that meeting's segments + summary.
    # This handles: "鴻才會議討論什麼" → matches "鴻才討論" meeting title
    title_match_citations: List[Citation] = []
    title_match_segments = []
    try:
        # Check if top results are low quality (best sim < 0.6)
        best_segment_sim = max((1.0 - float(r.distance) for r in results), default=0.0) if results else 0.0
        best_summary_sim = max((c.similarity for c in summary_citations), default=0.0) if summary_citations else 0.0
        
        # Only activate title-match if vector search quality is poor
        if best_segment_sim < 0.6 or best_summary_sim < 0.5:
            title_matches = _find_title_matched_meetings(
                db, search_query,
                user_upn=request.user_upn,
                meeting_ids=request.meeting_ids,
            )
            
            for tm in title_matches:
                # Fetch this meeting's best segments (by similarity to query)
                tm_segments = _fetch_meeting_top_segments(
                    db, tm["meeting_id"], query_embedding, top_k=8
                )
                if tm_segments:
                    title_match_segments.extend(tm_segments)
                
                # Also add summary as a citation if available
                if tm.get("summary_json"):
                    try:
                        sdata = json.loads(tm["summary_json"])
                        parts = []
                        if sdata.get("summary"):
                            parts.append(sdata["summary"])
                        if sdata.get("decisions"):
                            decisions = sdata["decisions"]
                            dec_texts = []
                            for d in decisions:
                                if isinstance(d, str):
                                    dec_texts.append(d)
                                elif isinstance(d, dict):
                                    dec_texts.append(d.get("decision", ""))
                            if dec_texts:
                                parts.append("決議事項：" + "；".join(filter(None, dec_texts)))
                        if sdata.get("action_items"):
                            items = sdata["action_items"][:5]
                            item_texts = []
                            for item in items:
                                if isinstance(item, str):
                                    item_texts.append(item)
                                elif isinstance(item, dict):
                                    item_texts.append(item.get("task", ""))
                            if item_texts:
                                parts.append("行動項目：" + "；".join(filter(None, item_texts)))
                        summary_content = "\n".join(filter(None, parts))
                        if summary_content:
                            title_match_citations.append(Citation(
                                meeting_id=tm["meeting_id"],
                                meeting_title=tm["title"],
                                speaker=None,
                                start_time=None,
                                end_time=None,
                                content=f"[會議摘要 - 標題匹配] {summary_content}",
                                similarity=round(tm["match_score"], 4),
                            ))
                    except Exception:
                        pass
            
            if title_match_segments:
                logger.info(f"[RAG/A3] Title match injected {len(title_match_segments)} segments from {len(title_matches)} meetings")
                # Merge title-matched segments into results (prepend for priority)
                # Deduplicate by segment id
                existing_ids = {r.id for r in results} if results else set()
                new_segments = [s for s in title_match_segments if s.id not in existing_ids]
                results = list(new_segments) + list(results) if results else new_segments
    except Exception as e:
        logger.warning(f"[RAG/A3] Title match failed (non-fatal): {e}")

    if not results and not summary_citations and not title_match_citations:
        return RAGResponse(
            answer="根據現有會議記錄，未找到與您問題相關的段落。可能尚未有會議記錄被索引。",
            citations=[],
            segments_searched=total_searched,
            question=request.question,
            confidence="no_answer",
        )

    # Step 2.5: Sentence-window expansion (劇本 2 - app.rag.chunker)
    # window=5: 短會議口語 segment 平均 5-8 字，需更大視窗才能涵蓋因果上下文
    expanded_rows = []
    if results:
        try:
            expanded_rows = expand_with_context(db, results, window=5)
        except Exception as e:
            logger.warning(
                f"[RAG] expand_with_context failed: {e}; falling back to raw rows"
            )
            expanded_rows = results  # graceful fallback

    # Build citations from EXPANDED rows for frontend display
    # (expanded content provides 150-250 char paragraphs for better user context)
    # 2026-05-25 (Y2): citation merge — 把同一場會議內間隔 < MERGE_GAP_SEC
    # 的連續 segments 合成單一 citation，避免「10 個來源時間零散」UX 痛點。
    # 同會議內按 start_time 排序，gap < 120s 合併；speakers 用 set 統計，
    # content 用 \n 串接；similarity 取群組內最高分（最具代表性）。
    MERGE_GAP_SEC = 120

    # Use expanded rows for citation content (richer context)
    citation_source = expanded_rows if expanded_rows else results
    sorted_results = sorted(citation_source, key=lambda r: (getattr(r, 'meeting_id', ''), getattr(r, 'start_time', 0) or 0)) if citation_source else []

    citations: List[Citation] = []
    # 群組臨時狀態（避免 pydantic 即時 mutate；最後一次性 build）
    groups: List[dict] = []
    for row in sorted_results:
        # Use expanded content for richer citations (ExpandedRow.content includes window context)
        content = getattr(row, 'content', '') or getattr(row, 'content_polished', '') or getattr(row, 'content_raw', '') or ""
        similarity = 1.0 - float(getattr(row, 'distance', 0.0))
        meeting_id = getattr(row, 'meeting_id', '')
        start_time = getattr(row, 'start_time', None)
        end_time = getattr(row, 'end_time', None)
        meeting_title = getattr(row, 'meeting_title', None) or "未命名會議"
        speaker = getattr(row, 'speaker', None)
        
        if (
            groups
            and groups[-1]["meeting_id"] == meeting_id
            and (start_time or 0) - (groups[-1]["end_time"] or 0) < MERGE_GAP_SEC
        ):
            g = groups[-1]
            g["end_time"] = max(g["end_time"] or 0, end_time or 0)
            g["content"] = (g["content"] + "\n" + content).strip()
            g["similarity"] = max(g["similarity"], similarity)
            if speaker and speaker not in g["speakers"]:
                g["speakers"].append(speaker)
        else:
            groups.append({
                "meeting_id": meeting_id,
                "meeting_title": meeting_title,
                "speakers": [speaker] if speaker else [],
                "start_time": start_time,
                "end_time": end_time,
                "content": content,
                "similarity": similarity,
            })

    # 群組依最高 similarity 排序（讓最強 hit 排前面）
    groups.sort(key=lambda g: g["similarity"], reverse=True)

    for g in groups:
        # speaker 顯示：單一 → 直接給；多人 → 「2 人 (SPEAKER_00, SPEAKER_01)」
        speakers = g["speakers"]
        if len(speakers) == 0:
            speaker_str = None
        elif len(speakers) == 1:
            speaker_str = speakers[0]
        else:
            speaker_str = f"{len(speakers)} 人 ({', '.join(speakers[:3])}{'...' if len(speakers) > 3 else ''})"
        citations.append(Citation(
            meeting_id=g["meeting_id"],
            meeting_title=g["meeting_title"],
            speaker=speaker_str,
            start_time=g["start_time"],
            end_time=g["end_time"],
            content=g["content"],
            similarity=round(g["similarity"], 4),
        ))

    # 用 expanded content 組 prompt（讓 LLM 看到更完整上下文）
    prompt_citations = []
    # A3: Prepend title-match citations (highest priority - user asked about this meeting)
    for tc in title_match_citations:
        prompt_citations.append(tc)
    # A1: Prepend summary citations (highest semantic density)
    for sc in summary_citations:
        prompt_citations.append(sc)
    for er in expanded_rows:
        prompt_citations.append(Citation(
            meeting_id=getattr(er, "meeting_id", ""),
            meeting_title=getattr(er, "meeting_title", None) or "未命名會議",
            speaker=getattr(er, "speaker", None),
            start_time=getattr(er, "start_time", None),
            end_time=getattr(er, "end_time", None),
            content=getattr(er, "content", "") or "",
            similarity=1.0 - float(getattr(er, "distance", 0.0)),
        ))

    # A3 + A1: Merge into frontend citations (prepend for priority)
    citations = title_match_citations + summary_citations + citations

    # Step 3: Generate answer with Gemini using app.rag.prompt.build_grounded_prompt
    # 取代既有 _build_rag_prompt（軟規則） → grounded 5 條硬規則 + 4 級 confidence
    rag_prompt = build_grounded_prompt(request.question, prompt_citations, request.history)

    answer = "無法生成回答。"
    confidence = "no_answer"
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=rag_prompt,
            config={
                "temperature": 0.2,
                "max_output_tokens": 4096,
                "response_mime_type": "application/json",
            },
        )
        try:
            data = json.loads(response.text)
            answer = data.get("answer", "無法生成回答")
            # confidence 必須是 4 級之一，否則 fallback no_answer
            raw_conf = str(data.get("confidence", "no_answer")).lower()
            confidence = raw_conf if raw_conf in CONFIDENCE_LEVELS else "no_answer"
            # used_citations_list 暫不主動過濾，frontend 仍拿到全 citations
        except Exception as parse_err:
            logger.warning(f"[RAG] LLM JSON parse fail: {parse_err}; raw={response.text[:200]!r}")
            answer = response.text or "無法生成回答。"
            confidence = "no_answer"
    except Exception as e:
        logger.error(f"[RAG] Gemini generation failed: {e}")
        answer = f"（回答生成失敗，但以下是最相關的會議段落供參考）\n\n錯誤: {str(e)}"
        confidence = "no_answer"

    # Y5 (2026-05-25)：log to rag_query_logs（寫失敗不影響主回應，只 warn）
    _log_rag_query(
        db,
        user_upn=request.user_upn,
        query=request.question,
        answer=answer,
        citation_count=len(citations),
        confidence=confidence,
        response_time_ms=int((time.time() - _t0) * 1000),
    )

    return RAGResponse(
        answer=answer,
        citations=citations,
        segments_searched=total_searched,
        question=request.question,
        confidence=confidence,
    )


def _log_rag_query(
    db: Session,
    user_upn: str,
    query: str,
    answer: str,
    citation_count: int,
    confidence: str,
    response_time_ms: int,
) -> None:
    """2026-05-25 (Y5)：把每次 RAG ask 寫入 rag_query_logs 表，給歷史 UI 用。
    寫入失敗不影響主回應（log warning 即可）。"""
    import uuid as _uuid
    try:
        db.execute(
            text(
                """
                INSERT INTO rag_query_logs
                    (id, user_upn, query, answer_preview, citation_count, confidence,
                     response_time_ms, created_at)
                VALUES (:id, :upn, :q, :ans, :cc, :conf, :rt, NOW())
                """
            ),
            {
                "id": str(_uuid.uuid4()),
                "upn": user_upn,
                "q": query[:2000],  # safety truncate
                "ans": (answer or "")[:1000],  # preview only
                "cc": citation_count,
                "conf": confidence[:20],
                "rt": response_time_ms,
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"[RAG history] log insert failed (non-fatal): {e}")


class RagHistoryItem(BaseModel):
    id: str
    query: str
    answer_preview: Optional[str]
    citation_count: int
    confidence: Optional[str]
    response_time_ms: Optional[int]
    created_at: str


@router.get("/history", response_model=List[RagHistoryItem])
async def get_rag_history(
    user_upn: str,
    days: int = 90,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """2026-05-25 (Y5)：取得使用者 RAG 查詢歷史。
    Frontend 預設只看 90 天；backend 保留 10 年由 cron 清理。
    """
    if days < 1 or days > 3650:
        days = 90
    if limit < 1 or limit > 500:
        limit = 100
    rows = db.execute(
        text(
            """
            SELECT id, query, answer_preview, citation_count, confidence,
                   response_time_ms, created_at
            FROM rag_query_logs
            WHERE user_upn = :upn
              AND created_at >= NOW() - (:days || ' days')::interval
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"upn": user_upn, "days": days, "limit": limit},
    ).fetchall()
    return [
        RagHistoryItem(
            id=r.id,
            query=r.query,
            answer_preview=r.answer_preview,
            citation_count=r.citation_count or 0,
            confidence=r.confidence,
            response_time_ms=r.response_time_ms,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@router.post("/backfill")
async def trigger_backfill(db: Session = Depends(get_db)):
    """
    One-time endpoint to backfill embeddings for all existing meetings.
    Should be called after enabling pgvector and deploying embedding pipeline.
    """
    try:
        result = backfill_all_embeddings(db)
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"[RAG] Backfill failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reembed")
async def trigger_reembed(db: Session = Depends(get_db)):
    """
    Force re-embed ALL segments with windowed strategy.
    Use after upgrading embedding approach (e.g., window size change).
    WARNING: This clears all existing segment embeddings and regenerates them.
    """
    from app.embedding import force_reembed_all
    try:
        result = force_reembed_all(db)
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"[RAG] Re-embed failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/greeting", response_model=RagGreetingResponse)
async def get_rag_greeting(
    user_upn: str,
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/rag/greeting?user_upn=xxx
    Personalized "five-star hotel check-in" greeting for the RAG workspace.
    Returns user's meeting stats, top topics, pending actions, and suggested questions.
    Always returns 200 with fallback content — never 500 on data issues.
    2026-06-08: Greeting Feature Phase 1 (Approach A: DB + template, no LLM)
    """
    if not user_upn or "@" not in user_upn:
        raise HTTPException(status_code=400, detail="user_upn must be a valid email address")

    user_upn = user_upn.strip().lower()

    from app.services.rag_greeting import build_greeting_payload
    payload = build_greeting_payload(db, user_upn)

    # Normalize last_meeting to Pydantic model
    lm = payload.get("last_meeting")
    last_meeting_obj = LastMeetingSummary(**lm) if lm and lm.get("title") else None

    return RagGreetingResponse(
        display_name=payload["display_name"],
        meeting_count=payload["meeting_count"],
        top_topics=payload["top_topics"],
        last_meeting=last_meeting_obj,
        pending_action_count=payload["pending_action_count"],
        greeting_text=payload["greeting_text"],
        suggested_questions=payload["suggested_questions"],
    )


@router.get("/status")
async def rag_status(db: Session = Depends(get_db)):
    """
    Check RAG system health: how many segments/summaries have embeddings.
    """
    try:
        total_segments = db.execute(
            text("SELECT COUNT(*) FROM transcript_segments")
        ).scalar()
        embedded_segments = db.execute(
            text("SELECT COUNT(*) FROM transcript_segments WHERE content_embedding IS NOT NULL")
        ).scalar()
        total_meetings = db.execute(
            text("SELECT COUNT(*) FROM meetings")
        ).scalar()
        embedded_meetings = db.execute(
            text("SELECT COUNT(*) FROM meetings WHERE summary_embedding IS NOT NULL")
        ).scalar()
        
        return {
            "status": "ok",
            "segments": {
                "total": total_segments,
                "embedded": embedded_segments,
                "coverage": f"{(embedded_segments/total_segments*100):.1f}%" if total_segments > 0 else "N/A",
            },
            "meetings": {
                "total": total_meetings,
                "embedded": embedded_meetings,
                "coverage": f"{(embedded_meetings/total_meetings*100):.1f}%" if total_meetings > 0 else "N/A",
            },
        }
    except Exception as e:
        logger.error(f"[RAG] Status check failed: {e}")
        return {"status": "error", "detail": str(e)}
