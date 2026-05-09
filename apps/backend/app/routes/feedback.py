"""
Feedback report routes (Sprint 2d / PR22).

  POST   /api/v1/feedback          — 使用者送 feedback (any user_upn)
  GET    /api/v1/feedback           — 使用者看自己的 feedback 歷史 (filter by user_upn)
  GET    /api/v1/feedback/admin     — admin 看 backlog (含 status filter)
  GET    /api/v1/feedback/{id}      — 看單筆 feedback 詳情
  PATCH  /api/v1/feedback/{id}      — admin 改 status / assignee / notes

設計重點：
  - 不擋使用者體驗：建立時快速回 201 不阻塞
  - is_admin 旗標未實作前 admin endpoint 暫設為 user_upn 為 'test@company.com' 的特權
    (對齊 main.py 內 backfill 邏輯; 將來補 RBAC 後改 dependency 注入)
  - 列出時依 created_at desc 排序，最新優先
  - 不做 hard delete (可改 status='wontfix' 或 'duplicate')
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FeedbackReport, User
from app.schemas import FeedbackCreate, FeedbackPatch, FeedbackRead

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_admin(db: Session, user_upn: str) -> bool:
    """簡化版 admin check — 暫用 User.is_admin。RBAC 升級後改 dependency。"""
    user = db.query(User).filter(User.ad_upn == user_upn).first()
    return bool(user and user.is_admin)


# ============================================
# Create
# ============================================
@router.post(
    "/api/v1/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Feedback"],
)
async def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
):
    """建立 feedback 紀錄。所有 user 皆可送。"""
    # Idempotency 不在本版做 — feedback 重送無大害；session_id+summary 重複可後續視需求加 dedup

    fb = FeedbackReport(
        user_upn=payload.user_upn,
        issue_type=payload.issue_type,
        summary=payload.summary,
        severity=payload.severity,
        expected=payload.expected,
        actual=payload.actual,
        repro_steps=payload.repro_steps,
        frequency=payload.frequency,
        attachment_url=payload.attachment_url,
        meeting_id=payload.meeting_id,
        page_url=payload.page_url,
        browser_info=payload.browser_info,
        session_id=payload.session_id,
        frontend_version=payload.frontend_version,
        backend_version=payload.backend_version,
        console_errors=payload.console_errors,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    logger.info(
        f"[Feedback] new {fb.id} from {fb.user_upn} "
        f"type={fb.issue_type} severity={fb.severity}"
    )
    return fb


# ============================================
# Read (user 看自己 / admin 看全部)
# ============================================
@router.get(
    "/api/v1/feedback",
    response_model=List[FeedbackRead],
    tags=["Feedback"],
)
async def list_my_feedback(
    user_upn: str = Query(..., min_length=1, description="本 user 的 UPN"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """列出某 user 自己的 feedback 歷史，依時間倒序。"""
    rows = (
        db.query(FeedbackReport)
        .filter(FeedbackReport.user_upn == user_upn)
        .order_by(desc(FeedbackReport.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows


@router.get(
    "/api/v1/feedback/admin",
    response_model=List[FeedbackRead],
    tags=["Feedback"],
)
async def list_all_feedback(
    requester_upn: str = Query(..., description="呼叫者 UPN，須為 admin"),
    status_filter: Optional[str] = Query(None, alias="status", description="篩選狀態"),
    issue_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """admin 看 feedback backlog，可依 status / issue_type 篩選。"""
    if not _ensure_admin(db, requester_upn):
        raise HTTPException(status_code=403, detail="Admin only")

    q = db.query(FeedbackReport)
    if status_filter:
        q = q.filter(FeedbackReport.status == status_filter)
    if issue_type:
        q = q.filter(FeedbackReport.issue_type == issue_type)
    rows = q.order_by(desc(FeedbackReport.created_at)).offset(skip).limit(limit).all()
    return rows


@router.get(
    "/api/v1/feedback/{feedback_id}",
    response_model=FeedbackRead,
    tags=["Feedback"],
)
async def get_feedback(
    feedback_id: str,
    requester_upn: str = Query(..., description="呼叫者 UPN，須為作者本人或 admin"),
    db: Session = Depends(get_db),
):
    fb = db.query(FeedbackReport).filter(FeedbackReport.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if fb.user_upn != requester_upn and not _ensure_admin(db, requester_upn):
        raise HTTPException(status_code=403, detail="Not authorized to view this feedback")
    return fb


# ============================================
# Update (admin only)
# ============================================
@router.patch(
    "/api/v1/feedback/{feedback_id}",
    response_model=FeedbackRead,
    tags=["Feedback"],
)
async def update_feedback(
    feedback_id: str,
    payload: FeedbackPatch,
    requester_upn: str = Query(..., description="呼叫者 UPN，須為 admin"),
    db: Session = Depends(get_db),
):
    """admin 改 status / 指派人 / admin notes。"""
    if not _ensure_admin(db, requester_upn):
        raise HTTPException(status_code=403, detail="Admin only")

    fb = db.query(FeedbackReport).filter(FeedbackReport.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if payload.status is not None:
        fb.status = payload.status
        if payload.status in ("fixed", "wontfix", "duplicate") and fb.resolved_at is None:
            fb.resolved_at = datetime.utcnow()
    if payload.assigned_to is not None:
        fb.assigned_to = payload.assigned_to
    if payload.admin_notes is not None:
        fb.admin_notes = payload.admin_notes
    if payload.notify_user is not None:
        fb.notify_user = payload.notify_user

    db.commit()
    db.refresh(fb)

    logger.info(
        f"[Feedback] updated {fb.id} status={fb.status} assigned_to={fb.assigned_to}"
    )
    return fb
