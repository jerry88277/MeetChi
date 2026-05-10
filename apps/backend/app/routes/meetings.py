"""
Meeting CRUD + summary versioning + speaker mapping + corrections + summarize endpoints.

Extracted from main.py. Existing routes/meeting_ops.py (merge/split/upload-url)
remains untouched — that module owns the /api/v1/meetings/{merge,split,upload-url}
sub-tree, while this one owns the rest of the meeting REST surface plus
two unrelated small surfaces (settings/corrections, summarize/full-transcript).

We use empty prefix and write full paths per endpoint to keep this concern in
one place without cross-module path coupling.
"""

import os
import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    Meeting,
    MeetingStatus,
    TranscriptSegment,
    User,
    MeetingParticipant,
    SummaryVersion,
)
from app.schemas import (
    MeetingRead,
    MeetingListItem,
    MeetingCreate,
    TranscriptSegmentCreate,
    RegenerateSummaryRequest,
    SpeakerMappingUpdate,
    SummarizeRequestModel,
    SummarizeResponseModel,
)
from app.llm_utils import get_gemini_client, generate_summary

logger = logging.getLogger(__name__)
router = APIRouter()

CORRECTIONS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "..", "config", "corrections.json"
)


# ============================================
# Meeting CRUD
# ============================================
@router.post("/api/v1/meetings", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def create_meeting(meeting_data: MeetingCreate, db: Session = Depends(get_db)):
    """Create a new meeting entry (and ensure user / participant binding)."""
    upn = meeting_data.user_upn or 'test@company.com'

    user_obj = db.query(User).filter(User.ad_upn == upn).first()
    if not user_obj:
        user_obj = User(
            id=str(uuid.uuid4()),
            ad_upn=upn,
            display_name=upn.split('@')[0],
            is_admin=True if upn == 'test@company.com' else False,
        )
        db.add(user_obj)
        db.flush()

    db_meeting = Meeting(
        title=meeting_data.title,
        language=meeting_data.language,
        template_name=meeting_data.template_name,
        duration=meeting_data.duration,
        custom_prompt=meeting_data.custom_context,
        owner_upn=upn,
    )
    db.add(db_meeting)
    db.flush()

    db_participant = MeetingParticipant(
        id=str(uuid.uuid4()),
        meeting_id=db_meeting.id,
        user_upn=upn,
        role='owner',
        access_source='upload',
    )
    db.add(db_participant)

    db.commit()
    db.refresh(db_meeting)
    return MeetingRead.from_orm(db_meeting)


@router.get("/api/v1/meetings", response_model=List[MeetingListItem])
async def list_meetings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List historical meetings (lightweight — no transcript_segments).

    Detail view 仍會用 GET /api/v1/meetings/{id} 拿完整 segments；
    list 端不回 segments 是為了避免 N+1 lazy-load 把 worker pool 拖垮
    （見 prod 503 incident 2026-05-09：limit=100 的 list 要 74s 並 503）。
    """
    meetings = (
        db.query(Meeting)
        .order_by(desc(Meeting.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [MeetingListItem.from_orm(m) for m in meetings]


@router.get("/api/v1/meetings/{meeting_id}", response_model=MeetingRead)
async def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """Get meeting details including transcript and summary."""
    meeting = (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id)
        .options(selectinload(Meeting.transcript_segments))
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingRead.from_orm(meeting)


@router.post("/api/v1/meetings/{meeting_id}/add_segments")
async def add_transcript_segments(
    meeting_id: str,
    segments: List[TranscriptSegmentCreate],
    db: Session = Depends(get_db),
):
    """Bulk-add transcript segments (typically called when recording finishes)."""
    db_meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not db_meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    new_segments = []
    for segment_data in segments:
        data = segment_data.dict(exclude_unset=True)
        if "id" not in data or data["id"] is None:
            data["id"] = str(uuid.uuid4())
        new_segment = TranscriptSegment(**data, meeting_id=meeting_id)
        db.add(new_segment)
        new_segments.append(new_segment)

    db.commit()
    db.refresh(db_meeting)
    return {"message": f"Added {len(new_segments)} segments to meeting {meeting_id}"}


@router.delete("/api/v1/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """Delete a meeting and its associated resources (audio file, transcripts)."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # 1. Delete Audio File (best-effort — Cloud SQL may have GCS path; skip if missing)
    if meeting.audio_url and os.path.exists(meeting.audio_url):
        try:
            os.remove(meeting.audio_url)
            logger.info(f"Deleted audio file: {meeting.audio_url}")
        except Exception as e:
            logger.error(f"Failed to delete audio file {meeting.audio_url}: {e}")

    # 2. Delete Transcripts
    db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).delete()

    # 3. Delete Meeting Record
    db.delete(meeting)
    db.commit()

    return None


# ============================================
# Summary Generation / Regeneration
# ============================================
@router.post("/api/v1/meetings/{meeting_id}/generate-summary")
def trigger_summary_generation(
    meeting_id: str,
    template_type: str = "general",
    context: str = "",
    length: str = "medium",
    style: str = "formal",
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Trigger background summary generation. Bypasses Celery (no Redis dep)."""
    logger.info(f"Triggering local background summary for {meeting_id}")

    from app.tasks import generate_summary_core
    background_tasks.add_task(
        generate_summary_core, meeting_id, template_type, context, length, style
    )

    return JSONResponse(
        content={"message": "Summary generation started (Local Force)", "task_id": "local-force"},
        status_code=status.HTTP_200_OK,
    )


@router.post("/api/v1/meetings/{meeting_id}/regenerate-summary")
async def regenerate_summary(
    meeting_id: str,
    request: RegenerateSummaryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Regenerate summary; saves the existing one as a version (Phase D)."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.transcript_raw and not meeting.transcript_polished:
        segment_count = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.meeting_id == meeting_id)
            .count()
        )
        if segment_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Meeting has no transcript content to summarize",
            )

    if meeting.summary_json:
        version = SummaryVersion(
            id=str(uuid.uuid4()),
            meeting_id=meeting_id,
            template_name=meeting.template_name or "general",
            summary_json=meeting.summary_json,
        )
        db.add(version)
        logger.info(
            f"Saved summary version for meeting {meeting_id} "
            f"(template: {meeting.template_name})"
        )

    meeting.summary_json = None
    meeting.status = MeetingStatus.PROCESSING
    meeting.updated_at = datetime.utcnow()
    db.commit()

    logger.info(
        f"Regenerating summary for meeting {meeting_id} with template {request.template_name}"
    )

    from app.tasks import generate_summary_core
    background_tasks.add_task(
        generate_summary_core,
        meeting_id,
        request.template_name,
        request.context,
        "medium",
        "formal",
    )

    return JSONResponse(
        content={
            "message": "Summary regeneration started",
            "meeting_id": meeting_id,
            "status": "processing",
        },
        status_code=status.HTTP_200_OK,
    )


@router.get("/api/v1/meetings/{meeting_id}/summary-versions")
async def list_summary_versions(meeting_id: str, db: Session = Depends(get_db)):
    """List all saved summary versions for a meeting (Phase D)."""
    versions = (
        db.query(SummaryVersion)
        .filter(SummaryVersion.meeting_id == meeting_id)
        .order_by(SummaryVersion.created_at.desc())
        .all()
    )

    return [
        {
            "id": v.id,
            "template_name": v.template_name,
            "summary_json": v.summary_json,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router.post("/api/v1/meetings/{meeting_id}/restore-summary-version/{version_id}")
async def restore_summary_version(
    meeting_id: str, version_id: str, db: Session = Depends(get_db)
):
    """Restore a specific summary version as the current summary (Phase D)."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    version = (
        db.query(SummaryVersion)
        .filter(
            SummaryVersion.id == version_id,
            SummaryVersion.meeting_id == meeting_id,
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Save current as a version first
    if meeting.summary_json:
        current_version = SummaryVersion(
            id=str(uuid.uuid4()),
            meeting_id=meeting_id,
            template_name=meeting.template_name or "general",
            summary_json=meeting.summary_json,
        )
        db.add(current_version)

    meeting.summary_json = version.summary_json
    meeting.template_name = version.template_name
    meeting.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Summary restored", "template_name": version.template_name}


# ============================================
# Speaker Mappings (Phase 8.1.3)
# ============================================
@router.patch("/api/v1/meetings/{meeting_id}/speakers")
async def update_speaker_mappings(
    meeting_id: str,
    update: SpeakerMappingUpdate,
    db: Session = Depends(get_db),
):
    """Update speaker label mappings for a meeting."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting.speaker_mappings = json.dumps(
        {k: v.dict() for k, v in update.mappings.items()},
        ensure_ascii=False,
    )
    meeting.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Speaker mappings updated", "meeting_id": meeting_id}


# ============================================
# Settings — keyword corrections
# ============================================
@router.get("/api/v1/settings/corrections")
async def get_corrections():
    """Get current keyword correction rules."""
    if os.path.exists(CORRECTIONS_CONFIG_PATH):
        with open(CORRECTIONS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


@router.post("/api/v1/settings/corrections")
async def update_corrections(corrections: dict):
    """Update keyword correction rules."""
    try:
        with open(CORRECTIONS_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(corrections, f, ensure_ascii=False, indent=4)
        return {"message": "Corrections updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save corrections: {e}")


# ============================================
# Full-Transcript Summarize (legacy /api/v1/summarize)
# ============================================
@router.post("/api/v1/summarize", response_model=SummarizeResponseModel)
async def summarize_full_transcript(request_data: SummarizeRequestModel):
    """Synchronous full-transcript summarization via Gemini."""
    logger.info(
        f"Received summarization request for transcript "
        f"(len: {len(request_data.transcript)}) with template: {request_data.template_name}"
    )
    try:
        client = get_gemini_client()
        if not client:
            raise HTTPException(status_code=500, detail="Gemini client unavailable")

        def _run_summary():
            return generate_summary(
                client=client,
                text=request_data.transcript,
                template_name=request_data.template_name,
            )

        summary_data = await asyncio.to_thread(_run_summary)

        if "error" in summary_data:
            raise Exception(summary_data["error"])

        return SummarizeResponseModel(
            summary=summary_data.get("summary", "無法生成摘要。"),
            action_items=summary_data.get("action_items", []),
            decisions=summary_data.get("decisions", []),
            risks=summary_data.get("risks", []),
        )
    except Exception as e:
        logger.error(f"Error calling Gemini for summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {e}")
