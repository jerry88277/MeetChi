"""Admin endpoints — 一次性 / 維護操作。

僅限 IT 或主帳號使用，不放 prod 公開流量；目前**不**強制 auth 是因為
單一企業內部部署，但有 X-Admin-Token header 軟性閘門（env var 提供）。
未來上多租戶要補 SSO admin role check。
"""

import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AccessSource,
    Meeting,
    MeetingParticipant,
    MeetingStatus,
    ParticipantRole,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# 簡易閘門：env var ADMIN_TOKEN 設了就要 match header
# 若沒設則 endpoint 無 auth（內部部署便利）
_ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def _check_admin(x_admin_token: str = Header(default="")) -> None:
    if _ADMIN_TOKEN and x_admin_token != _ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )


@router.get("/gpu-queue-stats")
async def gpu_queue_stats(_: None = Depends(_check_admin)):
    """GPU 全局排隊機制即時統計。"""
    from app.gpu_semaphore import get_stats
    return get_stats()


@router.post("/gpu-queue-reset-stats")
async def gpu_queue_reset_stats(_: None = Depends(_check_admin)):
    """重置 GPU queue 統計（壓測前清零用）。"""
    from app.gpu_semaphore import reset_stats
    reset_stats()
    return {"message": "GPU queue stats reset"}


@router.post("/send-test-email")
async def send_test_email_endpoint(
    to_email: str,
    _: None = Depends(_check_admin),
):
    """發送測試信件，驗證 SMTP 通知功能。"""
    from app.notifications import send_test_email
    success = send_test_email(to_email)
    if success:
        return {"message": f"Test email sent to {to_email}", "success": True}
    return {"message": "Failed to send test email (check logs)", "success": False}


@router.post("/fix-stale-failure-reasons")
async def fix_stale_failure_reasons(
    db: Session = Depends(get_db),
    _: None = Depends(_check_admin),
):
    """清除已 COMPLETED 會議的殘留 failure_reason（一次性資料修復）。"""
    stale = db.query(Meeting).filter(
        Meeting.status == MeetingStatus.COMPLETED,
        Meeting.failure_reason.isnot(None),
    ).all()
    count = 0
    for m in stale:
        m.failure_reason = None
        count += 1
    db.commit()
    return {"fixed": count, "message": f"Cleared failure_reason from {count} COMPLETED meetings"}


@router.post("/backfill-participants")
async def backfill_participants(
    user_upn: str,
    db: Session = Depends(get_db),
    _: None = Depends(_check_admin),
):
    """把所有未軟刪除的 meeting 都加入指定 user 為 participant (owner role)。

    解 2026-05-22 痛點：歷史 meeting 都以 test@company.com 為 owner，
    使用者改用真實 session email 後 RAG 查不到。本 endpoint 一鍵把
    所有歷史 meeting 加進該 email 的可見範圍。

    Idempotent：已存在的 (meeting_id, user_upn) 不會重複 INSERT
    （ON CONFLICT 由 schema 的 UNIQUE constraint 自動處理，
    這裡用 WHERE NOT EXISTS 顯式 skip 已存在的）。

    Args:
        user_upn: 要綁定的使用者 email（必須已存在於 users 表）

    Returns:
        {inserted: int, total_meetings: int, user_upn: str}
    """
    if not user_upn or "@" not in user_upn:
        raise HTTPException(status_code=400, detail="user_upn must be a valid email")

    # 2026-05-24 rewrite：原 raw SQL 對 PG ENUM 沒做 explicit cast，
    # 試 'admin_backfill' / 'granted' 都被 DB 拒絕。改用 SQLAlchemy ORM 讓
    # Enum(AccessSource) 自動處理序列化（DB 可能存 uppercase member name），
    # 避免猜 ENUM 內部 representation。

    # 確保 users 表有此記錄（否則 FK 違反）
    existing_user = db.query(User).filter(User.ad_upn == user_upn).first()
    if not existing_user:
        db.add(User(
            id=str(uuid.uuid4()),
            ad_upn=user_upn,
            display_name=user_upn.split("@")[0],
            is_admin=False,
        ))
        db.flush()  # 讓後續 FK 看得到

    # 取得所有未刪除 meeting
    meetings = db.query(Meeting).filter(Meeting.deleted_at.is_(None)).all()
    total = len(meetings)

    # 取得該 user 已經是 participant 的 meeting_ids set
    existing_mids = {
        row[0]
        for row in db.query(MeetingParticipant.meeting_id)
            .filter(MeetingParticipant.user_upn == user_upn).all()
    }

    inserted = 0
    for m in meetings:
        if m.id in existing_mids:
            continue
        db.add(MeetingParticipant(
            id=str(uuid.uuid4()),
            meeting_id=m.id,
            user_upn=user_upn,
            role=ParticipantRole.OWNER,
            access_source=AccessSource.GRANTED,
        ))
        inserted += 1

    db.commit()

    logger.info(
        f"[Admin] backfill_participants: user_upn={user_upn} "
        f"inserted={inserted}/{total} meetings"
    )

    return {
        "user_upn": user_upn,
        "inserted": inserted,
        "total_meetings": total,
        "message": (
            f"Granted access to {inserted} meeting(s). "
            f"({total - inserted} already had access)"
        ),
    }


# 卡住會議自助復原：worker 在 claim 後死掉/逾時會讓 status 永久鎖在
# PROCESSING/REFINING/TRANSCRIBED，重試只認 PENDING/FAILED 故無法自動復原。
# 此端點把卡住列安全重置回 PENDING 並（可選）重新 enqueue 轉錄。
_STUCK_STATUSES = ("PROCESSING", "REFINING", "TRANSCRIBED")


@router.get("/stuck-meetings")
def list_stuck_meetings(
    min_stuck_minutes: int = Query(15, ge=0, description="只列出停滯超過 N 分鐘的會議"),
    db: Session = Depends(get_db),
    _: None = Depends(_check_admin),
):
    """列出疑似卡住（PROCESSING/REFINING/TRANSCRIBED 且久無更新）的會議。"""
    now = datetime.utcnow()
    rows = (
        db.query(Meeting)
        .filter(Meeting.status.in_([MeetingStatus[s] for s in _STUCK_STATUSES]))
        .filter(Meeting.deleted_at.is_(None))
        .all()
    )
    out = []
    for m in rows:
        updated = m.updated_at or m.created_at
        age_min = int((now - updated).total_seconds() // 60) if updated else None
        if age_min is None or age_min < min_stuck_minutes:
            continue
        out.append({
            "id": m.id,
            "title": m.title,
            "status": m.status.value if hasattr(m.status, "value") else str(m.status),
            "processing_stage": m.processing_stage,
            "updated_at": updated.isoformat() + "Z" if updated else None,
            "stuck_minutes": age_min,
        })
    out.sort(key=lambda x: x["stuck_minutes"], reverse=True)
    return {"count": len(out), "min_stuck_minutes": min_stuck_minutes, "meetings": out}


@router.post("/reset-stuck-meeting")
def reset_stuck_meeting(
    meeting_id: str = Query(..., description="要復原的會議 ID"),
    min_stuck_minutes: int = Query(10, ge=0, description="安全閘門：只重置停滯超過 N 分鐘者"),
    reenqueue: bool = Query(True, description="重置後是否自動重新 enqueue 轉錄"),
    force: bool = Query(False, description="略過停滯時間安全檢查"),
    db: Session = Depends(get_db),
    _: None = Depends(_check_admin),
):
    """把卡住的會議從 PROCESSING/REFINING/TRANSCRIBED 安全重置回 PENDING 並重新 enqueue。

    安全設計：
    - 只允許重置 _STUCK_STATUSES；COMPLETED 一律拒絕（避免誤刪成果）。
    - 預設要求停滯 >= min_stuck_minutes，避免打斷正在處理中的會議；可用 force 略過。
    - 清空 processing_stage / failure_reason，讓 worker 的 atomic claim（僅認 PENDING/FAILED）能成功。
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")

    cur_status = meeting.status.value if hasattr(meeting.status, "value") else str(meeting.status)

    if cur_status == "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail="Meeting is COMPLETED; refusing to reset (would risk existing results)",
        )
    if cur_status not in _STUCK_STATUSES and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Meeting status is {cur_status}, not a stuck state {_STUCK_STATUSES}; use force=true to override",
        )

    updated = meeting.updated_at or meeting.created_at
    age_min = int((datetime.utcnow() - updated).total_seconds() // 60) if updated else None
    if not force and (age_min is None or age_min < min_stuck_minutes):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Meeting last updated {age_min} min ago (< {min_stuck_minutes}); "
                f"may still be actively processing. Use force=true to override."
            ),
        )

    prev_stage = meeting.processing_stage
    db.execute(
        text("""
            UPDATE meetings
            SET status = 'PENDING', processing_stage = NULL,
                failure_reason = NULL, updated_at = NOW()
            WHERE id = :mid
        """),
        {"mid": meeting_id},
    )
    db.commit()
    logger.warning(
        f"[Admin] reset-stuck-meeting {meeting_id}: {cur_status}/{prev_stage} "
        f"(stuck {age_min} min) -> PENDING, reenqueue={reenqueue}"
    )

    result = {
        "meeting_id": meeting_id,
        "previous_status": cur_status,
        "previous_stage": prev_stage,
        "stuck_minutes": age_min,
        "new_status": "PENDING",
        "reenqueued": False,
    }

    if reenqueue:
        from app.routes.cloud_tasks import (
            EnqueueTranscriptionRequest,
            enqueue_transcription,
        )
        enq = enqueue_transcription(
            EnqueueTranscriptionRequest(meeting_id=meeting_id, template_type="general", context="")
        )
        result["reenqueued"] = getattr(enq, "status", None) == "enqueued"
        result["enqueue_status"] = getattr(enq, "status", None)
        result["enqueue_message"] = getattr(enq, "message", None)

    result["message"] = (
        f"Reset {cur_status} -> PENDING"
        + (" and re-enqueued transcription" if result["reenqueued"] else "")
    )
    return result
