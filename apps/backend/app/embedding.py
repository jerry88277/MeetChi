"""
Embedding Pipeline for MeetChi Cross-Meeting RAG

Generates 768-dimensional embeddings using Gemini text-embedding-004
for both TranscriptSegment content and Meeting summaries.

Integrates with the existing task pipeline (tasks.py) to auto-embed
after transcription and summarization complete.
"""

import logging
import os
from typing import List, Optional

from sqlalchemy.orm import Session
from google import genai

from app.models import Meeting, TranscriptSegment
from app.llm_utils import get_gemini_client

logger = logging.getLogger(__name__)

# Embedding model configuration
# text-embedding-004: Best multilingual performance (zh + en), 768 dimensions
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
EMBEDDING_DIMENSION = 768
# Batch size for Gemini embed_content API (max 100 per request)
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))


def embed_texts(client: genai.Client, texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a batch of texts using Gemini Embedding API.
    
    Args:
        client: Initialized Gemini client
        texts: List of text strings to embed
        
    Returns:
        List of 768-dimensional embedding vectors
    """
    if not texts:
        return []
    
    embeddings = []
    # Process in batches to respect API limits
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + EMBEDDING_BATCH_SIZE]
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
            )
            for embedding_obj in response.embeddings:
                embeddings.append(embedding_obj.values)
        except Exception as e:
            logger.error(f"Embedding batch {i//EMBEDDING_BATCH_SIZE} failed: {e}")
            # Fill with None for failed batch items so indices stay aligned
            embeddings.extend([None] * len(batch))
    
    return embeddings


def embed_single_text(client: genai.Client, text: str) -> Optional[List[float]]:
    """
    Generate embedding for a single text string.
    
    Args:
        client: Initialized Gemini client
        text: Text to embed
        
    Returns:
        768-dimensional embedding vector, or None on failure
    """
    if not text or not text.strip():
        return None
    
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[text.strip()],
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error(f"Single text embedding failed: {e}")
        return None


def embed_transcript_segments(db: Session, meeting_id: str) -> int:
    """
    Generate and store embeddings for all TranscriptSegments of a meeting.
    
    Strategy (2026-06-09 改良):
      每個 segment 的 embedding 不再只用自身 5-8 字的短文做向量，
      而是用「滑動視窗合併文字」(sliding window paragraph) 產生 embedding，
      讓每個 segment 的向量同時包含前後文語意上下文。
      
      視窗大小: EMBED_WINDOW (env, default=5) — 前後各取 5 個 segment 合併成
      ~100-300 字的段落後做 embedding。
      
      效果: retrieval 時 cosine similarity 更能匹配語意完整的段落，
      而非只匹配零散短句。
    
    Called automatically after transcription completes (tasks.py integration).
    
    Args:
        db: SQLAlchemy session
        meeting_id: Meeting UUID
        
    Returns:
        Number of segments successfully embedded
    """
    EMBED_WINDOW = int(os.getenv("EMBED_WINDOW", "5"))
    
    client = get_gemini_client()
    if not client:
        logger.error(f"[Embedding] Cannot embed segments for {meeting_id}: Gemini client unavailable")
        return 0
    
    # Query ALL segments (ordered) to build context windows
    all_segments = db.query(TranscriptSegment).filter(
        TranscriptSegment.meeting_id == meeting_id,
    ).order_by(TranscriptSegment.order).all()
    
    if not all_segments:
        logger.info(f"[Embedding] No segments for {meeting_id}")
        return 0
    
    # Filter to only un-embedded segments for actual embedding
    segments_to_embed = [s for s in all_segments if s.content_embedding is None]
    if not segments_to_embed:
        logger.info(f"[Embedding] No un-embedded segments for {meeting_id}")
        return 0

    # A2 Optimization REMOVED: Title prefix causes embedding pollution
    # (all segments from same meeting get near-identical embeddings dominated by prefix)
    # Title-based queries are now handled by A3 title-match pre-filter in rag.py
    
    # Build order→index map for fast window lookup
    order_to_idx = {seg.order: i for i, seg in enumerate(all_segments)}
    
    def _get_segment_text(seg) -> str:
        content = seg.content_polished or seg.content_raw or ""
        if seg.speaker:
            return f"[{seg.speaker}] {content}"
        return content
    
    # Build windowed text for each segment to embed
    texts = []
    for seg in segments_to_embed:
        idx = order_to_idx.get(seg.order)
        if idx is None:
            texts.append(_get_segment_text(seg))
            continue
        
        # Collect window: [idx - EMBED_WINDOW, ..., idx, ..., idx + EMBED_WINDOW]
        start_idx = max(0, idx - EMBED_WINDOW)
        end_idx = min(len(all_segments) - 1, idx + EMBED_WINDOW)
        
        window_parts = []
        for wi in range(start_idx, end_idx + 1):
            window_parts.append(_get_segment_text(all_segments[wi]))
        
        # Join with space (Chinese doesn't need word separators but newline preserves flow)
        texts.append(" ".join(window_parts))
    
    logger.info(
        f"[Embedding] Generating embeddings for {len(texts)} segments of meeting {meeting_id} "
        f"(window={EMBED_WINDOW}, avg_len={sum(len(t) for t in texts)//max(len(texts),1)} chars)"
    )
    
    embeddings = embed_texts(client, texts)
    
    # Write embeddings back to DB
    embedded_count = 0
    for seg, embedding in zip(segments_to_embed, embeddings):
        if embedding is not None:
            seg.content_embedding = embedding
            embedded_count += 1
    
    try:
        db.commit()
        logger.info(f"[Embedding] Successfully embedded {embedded_count}/{len(segments_to_embed)} segments for {meeting_id}")
    except Exception as e:
        logger.error(f"[Embedding] Failed to commit segment embeddings for {meeting_id}: {e}")
        db.rollback()
        return 0
    
    return embedded_count


def embed_meeting_summary(db: Session, meeting_id: str) -> bool:
    """
    Generate and store embedding for a meeting's summary.
    Uses summary_json text content for embedding.
    
    Called automatically after summarization completes (tasks.py integration).
    
    Args:
        db: SQLAlchemy session
        meeting_id: Meeting UUID
        
    Returns:
        True if embedding was generated successfully
    """
    client = get_gemini_client()
    if not client:
        logger.error(f"[Embedding] Cannot embed summary for {meeting_id}: Gemini client unavailable")
        return False
    
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        logger.error(f"[Embedding] Meeting {meeting_id} not found")
        return False
    
    if not meeting.summary_json:
        logger.warning(f"[Embedding] No summary_json for {meeting_id}, skipping summary embedding")
        return False
    
    # Extract meaningful text from summary JSON for embedding
    import json
    try:
        summary_data = json.loads(meeting.summary_json)
    except (json.JSONDecodeError, TypeError):
        logger.error(f"[Embedding] Invalid summary_json for {meeting_id}")
        return False
    
    # Build embedding text from key summary fields
    parts = []
    if meeting.title:
        parts.append(f"會議標題: {meeting.title}")
    if summary_data.get("summary"):
        parts.append(summary_data["summary"])
    for item in summary_data.get("action_items", []):
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(item.get("task", ""))
    for decision in summary_data.get("decisions", []):
        if isinstance(decision, str):
            parts.append(decision)
        elif isinstance(decision, dict):
            parts.append(decision.get("decision", ""))
    
    embedding_text = "\n".join(filter(None, parts))
    if not embedding_text.strip():
        logger.warning(f"[Embedding] Empty summary text for {meeting_id}")
        return False
    
    logger.info(f"[Embedding] Generating summary embedding for {meeting_id} ({len(embedding_text)} chars)")
    
    embedding = embed_single_text(client, embedding_text)
    if embedding is None:
        return False
    
    meeting.summary_embedding = embedding
    
    try:
        db.commit()
        logger.info(f"[Embedding] Successfully embedded summary for {meeting_id}")
        return True
    except Exception as e:
        logger.error(f"[Embedding] Failed to commit summary embedding for {meeting_id}: {e}")
        db.rollback()
        return False


def find_cross_meeting_refs(
    db: Session,
    meeting_id: str,
    *,
    top_k: int = 5,
    min_similarity: float = 0.7,
    same_owner_only: bool = True,
) -> List[dict]:
    """Q7 (SUMMARY_FINAL_SPEC) — 找出與此會議相似的歷史會議。

    依 pgvector cosine similarity 排序，過濾：
      - 相同 owner_upn（避免跨使用者洩漏資訊）
      - similarity >= min_similarity (預設 0.7)
      - 不包含自己
      - 不包含已軟刪除的 meeting (deleted_at IS NOT NULL)
    回傳 dict list，可直接寫進 summary_json["cross_meeting_refs"]。

    Args:
        db: SQLAlchemy session
        meeting_id: 當前會議 ID（拿它的 summary_embedding 作 query vector）
        top_k: 最多回傳幾筆
        min_similarity: 0.0-1.0；低於此分數不列
        same_owner_only: True = 只查同 owner，False = 跨 owner（後者目前未授權）

    Returns:
        List of dict, each: {topic, related_meeting_id, related_meeting_title, url, similarity}
    """
    from sqlalchemy import text

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting or meeting.summary_embedding is None:
        logger.info(f"[CrossRef] No embedding for {meeting_id}, skip cross-ref lookup")
        return []

    # pgvector cosine distance: smaller = more similar
    # similarity = 1 - distance (cosine_distance is in [0, 2], for normalized vectors [0, 1])
    # 1 - cos_dist = cos_similarity
    sql = """
        SELECT
            m.id,
            m.title,
            1 - (m.summary_embedding <=> :query_vec) AS similarity
        FROM meetings m
        WHERE m.id != :self_id
          AND m.summary_embedding IS NOT NULL
          AND m.deleted_at IS NULL
          {owner_filter}
        ORDER BY m.summary_embedding <=> :query_vec ASC
        LIMIT :limit
    """.format(
        owner_filter="AND m.owner_upn = :owner" if same_owner_only and meeting.owner_upn else ""
    )

    # 2026-05-22 fix: numpy 2.x 把 np.float32(x) 加進 repr 字串，pgvector 不認得
    # ('[np.float32(0.044), ...]' → InvalidTextRepresentation)。
    # 改用純 float 重組成 '[0.044,0.034,...]' 字串。
    vec_str = "[" + ",".join(str(float(v)) for v in meeting.summary_embedding) + "]"
    params = {
        "query_vec": vec_str,
        "self_id": meeting_id,
        "limit": top_k * 2,  # over-fetch then filter by similarity
    }
    if same_owner_only and meeting.owner_upn:
        params["owner"] = meeting.owner_upn

    try:
        rows = db.execute(text(sql), params).fetchall()
    except Exception as e:
        logger.error(f"[CrossRef] Query failed for {meeting_id}: {e}", exc_info=True)
        return []

    refs = []
    for row in rows:
        if row.similarity < min_similarity:
            continue
        refs.append({
            "topic": row.title,  # 主題 = 對應會議的 title；LLM 可後續細化
            "related_meeting_id": row.id,
            "related_meeting_title": row.title,
            "url": f"/dashboard/meetings/{row.id}",
            "similarity": round(float(row.similarity), 3),
        })
        if len(refs) >= top_k:
            break

    logger.info(
        f"[CrossRef] {meeting_id}: found {len(refs)} cross-meeting refs "
        f"(min_similarity={min_similarity})"
    )
    return refs


def backfill_all_embeddings(db: Session) -> dict:
    """
    Backfill: generate embeddings for meetings/segments with NULL embeddings.

    Two-pass strategy:
      Pass 1 — meetings with summary_json but no summary_embedding
      Pass 2 — ALL COMPLETED meetings that still have un-embedded segments
               (covers cases where summary_embedding was set but segment
               embedding never ran, e.g. after pipeline was added later)

    Returns:
        Summary dict with counts of processed items
    """
    client = get_gemini_client()
    if not client:
        logger.error("[Embedding] Cannot backfill: Gemini client unavailable")
        return {"error": "Gemini client unavailable"}

    from sqlalchemy import text as sa_text
    from app.models import MeetingStatus

    summary_count = 0
    segment_count = 0
    meetings_touched: set = set()

    # Pass 1: meetings with summary_json but no summary_embedding
    meetings_need_summary = db.query(Meeting).filter(
        Meeting.summary_embedding == None,  # noqa: E711
        Meeting.summary_json != None,       # noqa: E711
    ).all()
    for meeting in meetings_need_summary:
        meetings_touched.add(meeting.id)
        if embed_meeting_summary(db, meeting.id):
            summary_count += 1

    # Pass 2: COMPLETED meetings that have un-embedded segments
    # Subquery: meeting_ids with at least one segment lacking content_embedding
    rows = db.execute(sa_text(
        "SELECT DISTINCT meeting_id FROM transcript_segments "
        "WHERE content_embedding IS NULL"
    )).fetchall()
    meeting_ids_with_unembedded = {r[0] for r in rows}

    for mid in meeting_ids_with_unembedded:
        seg_embedded = embed_transcript_segments(db, mid)
        if seg_embedded:
            segment_count += seg_embedded
            meetings_touched.add(mid)

    result = {
        "meetings_processed": len(meetings_touched),
        "summaries_embedded": summary_count,
        "segments_embedded": segment_count,
    }
    logger.info(f"[Embedding] Backfill complete: {result}")
    return result


def force_reembed_all(db: Session) -> dict:
    """
    Force re-embed ALL segments with the new windowed strategy.
    Clears existing embeddings first, then triggers full backfill.
    
    Use after changing EMBED_WINDOW or embedding strategy.
    """
    from sqlalchemy import text as sa_text
    
    # Clear all segment embeddings
    cleared = db.execute(sa_text(
        "UPDATE transcript_segments SET content_embedding = NULL WHERE content_embedding IS NOT NULL"
    ))
    db.commit()
    cleared_count = cleared.rowcount
    logger.info(f"[Embedding] Cleared {cleared_count} segment embeddings for force re-embed")
    
    # Run backfill (will now re-embed all with windowed strategy)
    result = backfill_all_embeddings(db)
    result["cleared_embeddings"] = cleared_count
    return result
