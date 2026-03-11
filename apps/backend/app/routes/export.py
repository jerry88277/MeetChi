"""
Transcript Export API Routes
Provides SRT, VTT and TXT download endpoints for meeting transcripts.

Inspired by TranscriptHub's multi-format output design.
"""

import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models import TranscriptSegment, Meeting
from app.database import get_db

router = APIRouter(prefix="/api/v1/meetings", tags=["Export"])


# ============================================
# Time Formatting Helpers
# ============================================

def _fmt_time_srt(seconds: float) -> str:
    """Format seconds → SRT timestamp (00:01:23,456)"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_time_vtt(seconds: float) -> str:
    """Format seconds → VTT timestamp (00:01:23.456)"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# ============================================
# Format Converters
# ============================================

def _to_srt(segments: list) -> str:
    """Convert TranscriptSegments → SRT subtitle format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _fmt_time_srt(seg.start_time or 0)
        end = _fmt_time_srt(seg.end_time or 0)
        text = seg.content_polished or seg.content_raw or ""
        speaker_prefix = f"[{seg.speaker}] " if seg.speaker else ""
        lines.append(f"{i}\n{start} --> {end}\n{speaker_prefix}{text}\n")
    return "\n".join(lines)


def _to_vtt(segments: list) -> str:
    """Convert TranscriptSegments → WebVTT subtitle format."""
    lines = ["WEBVTT\n"]
    for i, seg in enumerate(segments, 1):
        start = _fmt_time_vtt(seg.start_time or 0)
        end = _fmt_time_vtt(seg.end_time or 0)
        text = seg.content_polished or seg.content_raw or ""
        speaker_prefix = f"<v {seg.speaker}>" if seg.speaker else ""
        lines.append(f"{i}\n{start} --> {end}\n{speaker_prefix}{text}\n")
    return "\n".join(lines)


def _to_txt(segments: list) -> str:
    """Convert TranscriptSegments → plain text with speaker labels."""
    lines = []
    for seg in segments:
        text = seg.content_polished or seg.content_raw or ""
        if seg.speaker:
            lines.append(f"{seg.speaker}: {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


# ============================================
# Export Endpoint
# ============================================

@router.get("/{meeting_id}/export/{fmt}")
async def export_transcript(
    meeting_id: str,
    fmt: Literal["srt", "vtt", "txt"],
    db: Session = Depends(get_db),
):
    """
    Export meeting transcript in SRT, VTT, or TXT format.

    - **srt**: SubRip subtitle format (compatible with most video players)
    - **vtt**: WebVTT format (web-native, supports speaker tags)
    - **txt**: Plain text with speaker labels
    """
    # Verify meeting exists
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Get segments ordered by time
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.order)
        .all()
    )

    if not segments:
        raise HTTPException(status_code=404, detail="No transcript segments found for this meeting")

    # Convert to requested format
    format_handlers = {
        "srt": (_to_srt, "application/x-subrip"),
        "vtt": (_to_vtt, "text/vtt"),
        "txt": (_to_txt, "text/plain"),
    }

    converter, media_type = format_handlers[fmt]
    content = converter(segments)

    # Build filename from meeting title
    safe_title = (meeting.title or "transcript").replace(" ", "_")[:50]
    filename = f"{safe_title}.{fmt}"

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type=f"{media_type}; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
