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

    # 確保 users 表有此記錄（否則 FK 違反）— 不存在就先補
    db.execute(
        text(
            """
            INSERT INTO users (id, ad_upn, display_name, is_admin)
            VALUES (:id, :upn, :name, false)
            ON CONFLICT (ad_upn) DO NOTHING
            """
        ),
        {"id": str(uuid.uuid4()), "upn": user_upn, "name": user_upn.split("@")[0]},
    )

    # 取得目前 meeting 總數（含已 deleted）做為 total reference
    total = db.execute(
        text("SELECT COUNT(*) FROM meetings WHERE deleted_at IS NULL")
    ).scalar()

    # 用 INSERT ... SELECT 一次 bulk add；用 NOT EXISTS 跳過已綁定的
    result = db.execute(
        text(
            """
            INSERT INTO meeting_participants
                (id, meeting_id, user_upn, role, access_source, granted_at)
            SELECT
                gen_random_uuid()::varchar(36),
                m.id,
                :upn,
                'owner',
                'admin_backfill',
                NOW()
            FROM meetings m
            WHERE m.deleted_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM meeting_participants mp
                  WHERE mp.meeting_id = m.id AND mp.user_upn = :upn
              )
            RETURNING id
            """
        ),
        {"upn": user_upn},
    )
    inserted_rows = result.fetchall()
    inserted = len(inserted_rows)

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
