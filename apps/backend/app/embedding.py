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
    Only processes segments that don't have embeddings yet.
    
    Called automatically after transcription completes (tasks.py integration).
    
    Args:
        db: SQLAlchemy session
        meeting_id: Meeting UUID
        
    Returns:
        Number of segments successfully embedded
    """
    client = get_gemini_client()
    if not client:
        logger.error(f"[Embedding] Cannot embed segments for {meeting_id}: Gemini client unavailable")
        return 0
    
    # Query segments without embeddings
    segments = db.query(TranscriptSegment).filter(
        TranscriptSegment.meeting_id == meeting_id,
        TranscriptSegment.content_embedding == None  # noqa: E711
    ).order_by(TranscriptSegment.order).all()
    
    if not segments:
        logger.info(f"[Embedding] No un-embedded segments for {meeting_id}")
        return 0
    
    # Prepare texts (prefer polished, fallback to raw)
    texts = []
    for seg in segments:
        content = seg.content_polished or seg.content_raw or ""
        # Prepend speaker label for better context in embeddings
        if seg.speaker:
            content = f"[{seg.speaker}] {content}"
        texts.append(content)
    
    logger.info(f"[Embedding] Generating embeddings for {len(texts)} segments of meeting {meeting_id}")
    
    embeddings = embed_texts(client, texts)
    
    # Write embeddings back to DB
    embedded_count = 0
    for seg, embedding in zip(segments, embeddings):
        if embedding is not None:
            seg.content_embedding = embedding
            embedded_count += 1
    
    try:
        db.commit()
        logger.info(f"[Embedding] Successfully embedded {embedded_count}/{len(segments)} segments for {meeting_id}")
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


def backfill_all_embeddings(db: Session) -> dict:
    """
    One-time backfill: generate embeddings for all existing meetings
    that have NULL embeddings.
    
    Returns:
        Summary dict with counts of processed items
    """
    client = get_gemini_client()
    if not client:
        logger.error("[Embedding] Cannot backfill: Gemini client unavailable")
        return {"error": "Gemini client unavailable"}
    
    # Find meetings with NULL summary_embedding
    meetings = db.query(Meeting).filter(
        Meeting.summary_embedding == None,  # noqa: E711
        Meeting.summary_json != None  # noqa: E711
    ).all()
    
    summary_count = 0
    segment_count = 0
    
    for meeting in meetings:
        # Embed summary
        if embed_meeting_summary(db, meeting.id):
            summary_count += 1
        
        # Embed segments
        seg_embedded = embed_transcript_segments(db, meeting.id)
        segment_count += seg_embedded
    
    result = {
        "meetings_processed": len(meetings),
        "summaries_embedded": summary_count,
        "segments_embedded": segment_count,
    }
    logger.info(f"[Embedding] Backfill complete: {result}")
    return result
