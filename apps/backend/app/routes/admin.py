"""Admin endpoints — 一次性 / 維護操作。

僅限 IT 或主帳號使用，不放 prod 公開流量；目前**不**強制 auth 是因為
單一企業內部部署，但有 X-Admin-Token header 軟性閘門（env var 提供）。
未來上多租戶要補 SSO admin role check。
"""

import logging
import os
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AccessSource,
    Meeting,
    MeetingParticipant,
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
