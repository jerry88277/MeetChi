"""System Operations Admin API — 系統維運管理 endpoints.

提供：
  - 會議處理時間明細（上傳→轉錄→完成）
  - 使用者使用統計
  - 資源成本估算
  - 管理者/超級管理者角色分層

角色分層：
  - admin: 可查看所有會議的 metadata（ID、時間、狀態、擁有者）但看不到內容
  - super_admin: 可查看所有會議的完整內容（含逐字稿、摘要）

使用 User.role 欄位: 'user' (預設) | 'admin' | 'super_admin'
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, case, and_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.timeutil import UTCDateTime, to_utc_iso
from app.models import (
    Meeting,
    MeetingParticipant,
    MeetingStatus,
    TaskStatus as TaskStatusModel,
    TranscriptSegment,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ops", tags=["ops-admin"])

# ============================================
# Role Constants
# ============================================
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"
ADMIN_ROLES = {ROLE_ADMIN, ROLE_SUPER_ADMIN}

# Fallback: env-based admin emails (backward compat with existing ADMIN_EMAILS)
_ADMIN_EMAILS = set(
    e.strip() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
)
_SUPER_ADMIN_EMAILS = set(
    e.strip() for e in os.getenv("SUPER_ADMIN_EMAILS", "").split(",") if e.strip()
)


# ============================================
# Dependencies
# ============================================
def _get_user_role(user_email: str, db: Session) -> str:
    """Resolve user role from DB, with env fallback."""
    # Check env-based override first
    if user_email in _SUPER_ADMIN_EMAILS:
        return ROLE_SUPER_ADMIN
    if user_email in _ADMIN_EMAILS:
        return ROLE_ADMIN

    # Check DB
    user_record = db.query(User).filter(User.ad_upn == user_email).first()
    if user_record:
        role = getattr(user_record, "role", None)
        if role in ADMIN_ROLES:
            return role
        if user_record.is_admin:
            return ROLE_ADMIN
    return "user"


async def require_admin(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Dependency: require admin or super_admin role.
    
    In dev mode (AUTH_REQUIRED=false), also checks X-User-UPN header for role lookup.
    """
    email = user.get("email", "")
    # In dev mode, the email is 'dev@example.com' — try DB lookup for real user
    if email == "dev@example.com":
        # Prefer super_admin over admin
        admin_user = (
            db.query(User)
            .filter(User.role.in_(list(ADMIN_ROLES)))
            .order_by(User.role.desc())  # super_admin > admin alphabetically
            .first()
        )
        if admin_user:
            email = admin_user.ad_upn
            user["email"] = email
    role = _get_user_role(email, db)
    if role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理員權限不足",
        )
    user["_role"] = role
    return user


async def require_super_admin(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Dependency: require super_admin role."""
    email = user.get("email", "")
    if email == "dev@example.com":
        admin_user = db.query(User).filter(User.role == ROLE_SUPER_ADMIN).first()
        if admin_user:
            email = admin_user.ad_upn
            user["email"] = email
    role = _get_user_role(email, db)
    if role != ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="超級管理員權限不足",
        )
    user["_role"] = role
    return user


# ============================================
# Response Models
# ============================================
class MeetingOpsItem(BaseModel):
    id: str
    title: str
    status: str
    owner_upn: Optional[str]
    created_at: Optional[UTCDateTime]
    updated_at: Optional[UTCDateTime]
    duration: Optional[float]
    segment_count: int = 0
    # Timing breakdown
    upload_completed_at: Optional[UTCDateTime] = None
    transcription_started_at: Optional[UTCDateTime] = None
    transcription_completed_at: Optional[UTCDateTime] = None
    embedding_completed_at: Optional[UTCDateTime] = None
    total_processing_seconds: Optional[float] = None
    failure_reason: Optional[str] = None

    class Config:
        from_attributes = True


class UserUsageStats(BaseModel):
    user_upn: str
    display_name: Optional[str]
    meeting_count: int
    total_audio_seconds: float
    last_upload_at: Optional[UTCDateTime]
    estimated_cost_usd: float


class SystemOverview(BaseModel):
    total_users: int
    total_meetings: int
    meetings_completed: int
    meetings_processing: int
    meetings_failed: int
    total_audio_hours: float
    total_segments: int
    estimated_monthly_cost_usd: float


class RoleUpdateRequest(BaseModel):
    user_upn: str
    role: str  # 'user' | 'admin' | 'super_admin'


# ============================================
# Endpoints
# ============================================

@router.get("/overview", response_model=SystemOverview)
async def get_system_overview(
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """系統總覽：使用者數、會議數、資源消耗。"""
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_meetings = db.query(func.count(Meeting.id)).filter(
        Meeting.deleted_at.is_(None)
    ).scalar() or 0

    status_counts = (
        db.query(Meeting.status, func.count(Meeting.id))
        .filter(Meeting.deleted_at.is_(None))
        .group_by(Meeting.status)
        .all()
    )
    status_map = {s.value if hasattr(s, 'value') else s: c for s, c in status_counts}

    total_audio_seconds = (
        db.query(func.coalesce(func.sum(Meeting.duration), 0))
        .filter(Meeting.deleted_at.is_(None))
        .scalar()
    ) or 0

    total_segments = db.query(func.count(TranscriptSegment.id)).scalar() or 0

    # Cost estimation: L4 GPU ~$0.24/hr (minScale=1 = 24/7)
    # + embedding API: ~$0.0001 per 1000 tokens
    gpu_monthly = 0.24 * 24 * 30  # ~$172.8 for always-on
    # Gemini costs: ~$0.075 per 1M input tokens for summary
    gemini_per_meeting = 0.005  # rough estimate per meeting
    estimated_monthly = gpu_monthly + (total_meetings * gemini_per_meeting / 30)

    return SystemOverview(
        total_users=total_users,
        total_meetings=total_meetings,
        meetings_completed=status_map.get("COMPLETED", 0),
        meetings_processing=status_map.get("PROCESSING", 0) + status_map.get("PENDING", 0),
        meetings_failed=status_map.get("FAILED", 0),
        total_audio_hours=total_audio_seconds / 3600,
        total_segments=total_segments,
        estimated_monthly_cost_usd=round(estimated_monthly, 2),
    )


@router.get("/meetings", response_model=List[MeetingOpsItem])
async def list_meetings_ops(
    user_upn: Optional[str] = Query(None, description="Filter by owner UPN"),
    status_filter: Optional[str] = Query(None, description="Filter by status: COMPLETED, PROCESSING, FAILED"),
    date_from: Optional[str] = Query(None, description="ISO date from (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="ISO date to (YYYY-MM-DD)"),
    keyword: Optional[str] = Query(None, description="Search in meeting title"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """維運管理：列出所有會議的處理狀態與時間明細。管理員只看 metadata，不看內容。"""
    query = db.query(Meeting).filter(Meeting.deleted_at.is_(None))

    if user_upn:
        query = query.filter(Meeting.owner_upn == user_upn)
    if status_filter:
        try:
            ms = MeetingStatus(status_filter)
            query = query.filter(Meeting.status == ms)
        except ValueError:
            pass
    if date_from:
        try:
            df = datetime.fromisoformat(date_from)
            query = query.filter(Meeting.created_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to) + timedelta(days=1)
            query = query.filter(Meeting.created_at < dt)
        except ValueError:
            pass
    if keyword:
        query = query.filter(Meeting.title.ilike(f"%{keyword}%"))

    meetings = (
        query.order_by(Meeting.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Batch fetch task_status for timing breakdown
    meeting_ids = [m.id for m in meetings]
    task_statuses = (
        db.query(TaskStatusModel)
        .filter(TaskStatusModel.meeting_id.in_(meeting_ids))
        .all()
    ) if meeting_ids else []

    # Group task statuses by meeting_id
    task_map: dict = {}
    for ts in task_statuses:
        task_map.setdefault(ts.meeting_id, []).append(ts)

    # Batch fetch segment counts
    seg_counts = {}
    if meeting_ids:
        rows = (
            db.query(
                TranscriptSegment.meeting_id,
                func.count(TranscriptSegment.id),
            )
            .filter(TranscriptSegment.meeting_id.in_(meeting_ids))
            .group_by(TranscriptSegment.meeting_id)
            .all()
        )
        seg_counts = {mid: cnt for mid, cnt in rows}

    results = []
    for m in meetings:
        tasks = task_map.get(m.id, [])
        timing = _extract_timing(tasks, m)
        results.append(MeetingOpsItem(
            id=m.id,
            title=m.title or "Untitled",
            status=m.status.value if m.status else "UNKNOWN",
            owner_upn=m.owner_upn,
            created_at=m.created_at,
            updated_at=m.updated_at,
            duration=m.duration,
            segment_count=seg_counts.get(m.id, 0),
            failure_reason=m.failure_reason,
            **timing,
        ))

    return results


@router.get("/users", response_model=List[UserUsageStats])
async def list_user_usage(
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """使用者使用統計：每人會議數、音源總時長、預估成本。"""
    rows = (
        db.query(
            User.ad_upn,
            User.display_name,
            func.count(Meeting.id).label("meeting_count"),
            func.coalesce(func.sum(Meeting.duration), 0).label("total_seconds"),
            func.max(Meeting.created_at).label("last_upload"),
        )
        .outerjoin(Meeting, and_(
            Meeting.owner_upn == User.ad_upn,
            Meeting.deleted_at.is_(None),
        ))
        .group_by(User.ad_upn, User.display_name)
        .order_by(func.count(Meeting.id).desc())
        .all()
    )

    # Cost per audio hour: GPU ~$0.24/hr amortized + Gemini ~$0.01/meeting
    cost_per_hour = 0.25

    return [
        UserUsageStats(
            user_upn=r.ad_upn,
            display_name=r.display_name,
            meeting_count=r.meeting_count,
            total_audio_seconds=float(r.total_seconds),
            last_upload_at=r.last_upload,
            estimated_cost_usd=round(float(r.total_seconds) / 3600 * cost_per_hour, 2),
        )
        for r in rows
    ]


@router.get("/meetings/{meeting_id}/full")
async def get_meeting_full_content(
    meeting_id: str,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """超級管理者：查看會議完整內容（含逐字稿、摘要）。"""
    from sqlalchemy.orm import selectinload

    meeting = (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id)
        .options(selectinload(Meeting.transcript_segments))
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    segments = [
        {
            "order": s.order,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "speaker": s.speaker,
            "content": s.content_raw,
        }
        for s in (meeting.transcript_segments or [])
    ]

    return {
        "id": meeting.id,
        "title": meeting.title,
        "status": meeting.status.value if meeting.status else None,
        "owner_upn": meeting.owner_upn,
        "created_at": to_utc_iso(meeting.created_at),
        "duration": meeting.duration,
        "summary_json": meeting.summary_json,
        "transcript_segments": segments,
        "segment_count": len(segments),
    }


@router.post("/roles")
async def update_user_role(
    req: RoleUpdateRequest,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """超級管理者：更新使用者角色。"""
    valid_roles = {"user", "admin", "super_admin"}
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    target_user = db.query(User).filter(User.ad_upn == req.user_upn).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.role = req.role
    target_user.is_admin = req.role in ADMIN_ROLES
    db.commit()

    logger.info(f"[Ops] Role updated: {req.user_upn} → {req.role} (by {user.get('email')})")
    return {"user_upn": req.user_upn, "role": req.role, "message": "Role updated"}


@router.get("/my-role")
async def get_my_role(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取得當前使用者的角色。"""
    email = user.get("email", "")
    # In dev mode, resolve to actual admin user
    if email == "dev@example.com":
        admin_user = db.query(User).filter(User.role.in_(list(ADMIN_ROLES))).first()
        if admin_user:
            email = admin_user.ad_upn
    role = _get_user_role(email, db)
    return {"email": email, "role": role}


# ============================================
# Internal Helpers
# ============================================
def _extract_timing(tasks: list, meeting) -> dict:
    """Extract timing breakdown from task_status records."""
    timing = {
        "upload_completed_at": None,
        "transcription_started_at": None,
        "transcription_completed_at": None,
        "embedding_completed_at": None,
        "total_processing_seconds": None,
    }

    for t in tasks:
        name = t.task_name or ""
        ts_status = t.status or ""
        if "upload" in name.lower() and ts_status.upper() in ("COMPLETED", "IN_PROGRESS"):
            timing["upload_completed_at"] = t.updated_at
        elif "transcri" in name.lower() or "asr" in name.lower():
            if ts_status.upper() == "COMPLETED":
                timing["transcription_completed_at"] = t.updated_at
            elif ts_status.upper() == "IN_PROGRESS":
                timing["transcription_started_at"] = t.updated_at or t.created_at
        elif "embed" in name.lower() and ts_status.upper() == "COMPLETED":
            timing["embedding_completed_at"] = t.updated_at

    # Calculate total processing time
    start = meeting.created_at
    end = timing.get("embedding_completed_at") or timing.get("transcription_completed_at")
    if start and end:
        timing["total_processing_seconds"] = (end - start).total_seconds()

    return timing
