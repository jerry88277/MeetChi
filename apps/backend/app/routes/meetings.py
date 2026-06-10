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
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session, selectinload

from app.audit import record_action
from app.database import get_db
from app.models import (
    Meeting,
    MeetingStatus,
    TranscriptSegment,
    TaskStatus,
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

def _ensure_user_exists(db: Session, upn: str) -> None:
    """Upsert a user record by ad_upn. Ensures FK constraints on meetings.owner_upn,
    meetings.deleted_by etc. are always satisfiable for real login identities."""
    if not upn or upn == "anonymous":
        return
    user = db.query(User).filter(User.ad_upn == upn).first()
    if not user:
        db.add(User(
            id=str(uuid.uuid4()),
            ad_upn=upn,
            display_name=upn.split("@")[0],
            is_admin=False,
        ))
        db.flush()


# ============================================
# Meeting CRUD
# ============================================
@router.post("/api/v1/meetings", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def create_meeting(meeting_data: MeetingCreate, db: Session = Depends(get_db)):
    """Create a new meeting entry (and ensure user / participant binding)."""
    upn = meeting_data.user_upn or 'test@company.com'

    _ensure_user_exists(db, upn)

    db_meeting = Meeting(
        title=meeting_data.title,
        language=meeting_data.language,
        template_name=meeting_data.template_name,
        duration=meeting_data.duration,
        custom_prompt=meeting_data.custom_context,
        owner_upn=upn,
        is_confidential=meeting_data.is_confidential,
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
async def list_meetings(
    skip: int = 0,
    limit: int = 100,
    user_upn: Optional[str] = Query(None, description="當前登入用戶 UPN，啟用 MemPlace 隔離"),
    keyword: Optional[str] = Query(None, description="依會議標題搜尋"),
    date_from: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    include_meta: bool = Query(False, description="Include pagination metadata in response"),
    db: Session = Depends(get_db),
):
    """List active (non-deleted) meetings filtered by user access.

    When user_upn is provided, only returns meetings where the user is a participant
    (MemPlace isolation). Without user_upn, returns all meetings (admin/legacy mode).

    Supports keyword search (title) and date range filtering.
    When include_meta=true, returns {items, total, skip, limit, has_more}.
    """
    query = db.query(Meeting).filter(Meeting.deleted_at.is_(None))

    if user_upn:
        # MemPlace 隔離：只回傳使用者有權限的會議
        query = (
            query
            .join(MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id)
            .filter(MeetingParticipant.user_upn == user_upn)
        )

    if keyword:
        query = query.filter(Meeting.title.ilike(f"%{keyword}%"))

    if date_from:
        try:
            from datetime import datetime as _dt
            df = _dt.fromisoformat(date_from)
            query = query.filter(Meeting.created_at >= df)
        except ValueError:
            pass

    if date_to:
        try:
            from datetime import datetime as _dt, timedelta as _td
            dt = _dt.fromisoformat(date_to) + _td(days=1)
            query = query.filter(Meeting.created_at < dt)
        except ValueError:
            pass

    total = query.count() if include_meta else None

    meetings = (
        query
        .order_by(desc(Meeting.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [MeetingListItem.from_orm(m) for m in meetings]

    if include_meta:
        return JSONResponse(content={
            "items": [m.dict() for m in items],
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": (skip + limit) < total,
        })

    return items


@router.get("/api/v1/meetings/{meeting_id}", response_model=MeetingRead)
async def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """Get meeting details including transcript and summary.

    Soft-deleted meeting 仍可由 ID 直接讀取（給 IT debug + 還原 flow 用），
    但 list 端不顯示。Frontend 主要 UI 預設不會路由到 deleted meeting。
    """
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


class BulkDeleteRequest(BaseModel):
    meeting_ids: List[str]
    requester_upn: Optional[str] = None


@router.post("/api/v1/meetings/bulk-delete")
async def bulk_delete_meetings(
    payload: BulkDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Bulk soft-delete N meetings in one transaction.

    2026-05-24 (user request #1)：給拖曳多選後批次刪除用。
    每筆走與單一 delete_meeting 相同的 soft-delete + audit log 邏輯，
    但 commit 集中一次，省 N-1 次 round trip。

    Idempotent：已刪除的 meeting 跳過不重複寫 deleted_at；不存在的 ID
    記在 not_found 回傳給前端提示但不 raise。
    """
    if not payload.meeting_ids:
        return {"deleted": 0, "skipped_already_deleted": 0, "not_found": []}

    if len(payload.meeting_ids) > 100:
        raise HTTPException(
            status_code=400,
            detail="一次最多刪除 100 筆會議（請分批操作）",
        )

    deleted_count = 0
    skipped_already = 0
    not_found: List[str] = []
    now = datetime.utcnow()

    # Ensure the requester exists in users table before FK assignment
    if payload.requester_upn:
        _ensure_user_exists(db, payload.requester_upn)

    for mid in payload.meeting_ids:
        meeting = db.query(Meeting).filter(Meeting.id == mid).first()
        if not meeting:
            not_found.append(mid)
            continue
        if meeting.deleted_at is not None:
            skipped_already += 1
            continue

        meeting.deleted_at = now
        meeting.deleted_by = payload.requester_upn

        record_action(
            db,
            user_upn=payload.requester_upn or "anonymous",
            action_type="meeting.deleted",
            target_id=mid,
            metadata={
                "title": meeting.title,
                "status": meeting.status.value if meeting.status else None,
                "duration": meeting.duration,
                "owner_upn": meeting.owner_upn,
                "audio_url": meeting.audio_url,
                "template_name": meeting.template_name,
                "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
                "bulk_operation": True,
            },
            request=request,
        )
        deleted_count += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk delete commit failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"批次刪除失敗：{type(e).__name__}: {str(e)[:200]}",
        )

    logger.info(
        f"Bulk soft-deleted {deleted_count} meetings by "
        f"{payload.requester_upn or 'anonymous'} "
        f"(skipped {skipped_already} already-deleted, {len(not_found)} not-found)"
    )
    return {
        "deleted": deleted_count,
        "skipped_already_deleted": skipped_already,
        "not_found": not_found,
    }


@router.delete("/api/v1/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: str,
    request: Request,
    requester_upn: Optional[str] = Query(None, description="觸發刪除的使用者 UPN（給 audit）"),
    db: Session = Depends(get_db),
):
    """Soft-delete a meeting.

    2026-05-11 改為 soft delete：
      - 標記 deleted_at = NOW(), deleted_by = requester_upn
      - 不刪 audio_url 也不刪 transcript_segments（保留 30 天）
      - 寫 audit_logs 一筆 meeting.deleted (含 title/status/duration/owner_upn)
      - list endpoint 自動 filter 掉這筆，使用者看不到，但 ID 還在 DB
      - 30 天後由 cron job hard-delete (另設 — 不在此 PR 內)

    給 IT 的能力：可由 meeting_id 查 audit_logs 找出誰、何時刪、ip/UA。
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.deleted_at is not None:
        # 已刪除：idempotent，仍記 audit 但不重覆寫 deleted_at
        logger.info(f"Meeting {meeting_id} already deleted at {meeting.deleted_at}; idempotent return 204")
        return None

    try:
        # 1. Mark soft-deleted
        meeting.deleted_at = datetime.utcnow()
        meeting.deleted_by = requester_upn

        # 2. Audit log: title/status/duration/owner_upn 保留給 IT debug
        record_action(
            db,
            user_upn=requester_upn or "anonymous",
            action_type="meeting.deleted",
            target_id=meeting_id,
            metadata={
                "title": meeting.title,
                "status": meeting.status.value if meeting.status else None,
                "duration": meeting.duration,
                "owner_upn": meeting.owner_upn,
                "audio_url": meeting.audio_url,
                "template_name": meeting.template_name,
                "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
            },
            request=request,
        )

        db.commit()
        logger.info(
            f"Soft-deleted meeting {meeting_id} by {requester_upn or 'anonymous'} "
            f"(title='{meeting.title}', status={meeting.status})"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete meeting {meeting_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"刪除失敗：{type(e).__name__}: {str(e)[:200]}",
        )

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
        True,   # skip_asr=True — segments already exist; re-run summary only
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
# Rename Meeting
# ============================================
class RenameMeetingRequest(BaseModel):
    title: str

@router.patch("/api/v1/meetings/{meeting_id}/title")
async def rename_meeting(
    meeting_id: str,
    body: RenameMeetingRequest,
    db: Session = Depends(get_db),
):
    """Rename a meeting's title."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    old_title = meeting.title
    meeting.title = body.title.strip()
    meeting.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Meeting renamed", "meeting_id": meeting_id, "old_title": old_title, "new_title": meeting.title}


# ============================================
# Meeting Progress (UX Audit V2 - P0)
# ============================================
@router.get("/api/v1/meetings/{meeting_id}/progress")
async def get_meeting_progress(
    meeting_id: str,
    db: Session = Depends(get_db),
):
    """Get real-time progress of a meeting's processing pipeline."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Determine stage from TaskStatus entries
    tasks = db.query(TaskStatus).filter(
        TaskStatus.meeting_id == meeting_id
    ).order_by(TaskStatus.created_at.desc()).all()

    # Count transcript segments for chunk progress
    segment_count = db.query(TranscriptSegment).filter(
        TranscriptSegment.meeting_id == meeting_id
    ).count()

    # Determine current stage
    stage = "pending"
    stage_label = "等待處理"
    progress_pct = 0
    elapsed_seconds = 0
    estimated_remaining = None

    if meeting.status == MeetingStatus.COMPLETED:
        stage = "completed"
        stage_label = "已完成"
        progress_pct = 100
    elif meeting.status == MeetingStatus.FAILED:
        stage = "failed"
        stage_label = "處理失敗"
        progress_pct = 0
    elif meeting.status == MeetingStatus.PROCESSING:
        # Check task statuses to determine sub-stage
        task_map = {t.task_name: t for t in tasks}

        if "embedding" in task_map and task_map["embedding"].status == "IN_PROGRESS":
            stage = "embedding"
            stage_label = "正在建立知識索引"
            progress_pct = 85
        elif "summary" in task_map and task_map["summary"].status == "IN_PROGRESS":
            stage = "summarizing"
            stage_label = "正在生成摘要"
            progress_pct = 70
        elif "asr" in task_map:
            asr_task = task_map["asr"]
            if asr_task.status == "IN_PROGRESS":
                stage = "transcribing"
                stage_label = "正在轉錄語音"
                # Estimate progress from segments if available
                if asr_task.message:
                    try:
                        import json as _json
                        msg_data = _json.loads(asr_task.message)
                        chunks_done = msg_data.get("chunks_done", 0)
                        chunks_total = msg_data.get("chunks_total", 1)
                        progress_pct = int((chunks_done / max(chunks_total, 1)) * 60) + 10
                    except Exception:
                        progress_pct = 30
                else:
                    progress_pct = 30 if segment_count > 0 else 15
            elif asr_task.status == "COMPLETED":
                stage = "summarizing"
                stage_label = "正在生成摘要"
                progress_pct = 65
        else:
            stage = "uploading"
            stage_label = "正在處理音檔"
            progress_pct = 10

        # Calculate elapsed time
        if meeting.created_at:
            elapsed_seconds = int((datetime.utcnow() - meeting.created_at).total_seconds())
            # Rough estimate: 1 min per 10 min audio (based on historical data)
            if progress_pct > 0 and progress_pct < 100:
                estimated_remaining = int(elapsed_seconds * (100 - progress_pct) / max(progress_pct, 1))

    return {
        "meeting_id": meeting_id,
        "status": meeting.status.value if hasattr(meeting.status, 'value') else str(meeting.status),
        "stage": stage,
        "stage_label": stage_label,
        "progress_pct": progress_pct,
        "segments_count": segment_count,
        "elapsed_seconds": elapsed_seconds,
        "estimated_remaining_seconds": estimated_remaining,
        "failure_reason": meeting.failure_reason if meeting.status == MeetingStatus.FAILED else None,
    }


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
# Dashboard Aggregate API (UX Audit V2)
# ============================================
@router.get("/api/v1/dashboard")
async def get_dashboard_aggregate(
    user_upn: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Aggregate dashboard data in a single API call."""
    from sqlalchemy import func

    base_query = db.query(Meeting).filter(Meeting.deleted_at.is_(None))
    if user_upn:
        base_query = base_query.join(
            MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id
        ).filter(MeetingParticipant.user_upn == user_upn)

    total_meetings = base_query.count()
    processing_count = base_query.filter(Meeting.status == MeetingStatus.PROCESSING).count()
    failed_count = base_query.filter(Meeting.status == MeetingStatus.FAILED).count()
    completed_count = base_query.filter(Meeting.status == MeetingStatus.COMPLETED).count()

    # Recent meetings (top 5)
    recent = base_query.order_by(desc(Meeting.created_at)).limit(5).all()

    # Segment count for RAG
    segment_count = db.query(func.count(TranscriptSegment.id)).scalar() or 0

    # Last upload time
    last_meeting = base_query.order_by(desc(Meeting.created_at)).first()
    last_upload_at = last_meeting.created_at.isoformat() if last_meeting and last_meeting.created_at else None

    # Suggested actions
    suggested_actions = []
    if failed_count > 0:
        suggested_actions.append(f"有 {failed_count} 場會議轉錄失敗，點擊查看")
    if processing_count > 0:
        suggested_actions.append(f"有 {processing_count} 場會議正在處理中")

    return {
        "total_meetings": total_meetings,
        "completed_count": completed_count,
        "processing_count": processing_count,
        "failed_count": failed_count,
        "rag_segments_total": segment_count,
        "last_upload_at": last_upload_at,
        "suggested_actions": suggested_actions,
        "recent_meetings": [
            {
                "id": m.id,
                "title": m.title,
                "status": m.status.value if hasattr(m.status, 'value') else str(m.status),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in recent
        ],
    }


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
