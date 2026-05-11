"""Audit log helpers.

寫一筆 audit log 是 cheap operation（一次 INSERT），但若 DB 在繁忙狀態
時可能 fail。本檔提供 best-effort 寫入：失敗不擋 caller 主流程。

Usage:
    from app.audit import record_action

    record_action(
        db,
        user_upn=user.ad_upn,
        action_type="meeting.deleted",
        target_id=meeting.id,
        metadata={"title": meeting.title, "status": meeting.status.value},
        request=request,
    )
    # caller 自行決定何時 db.commit() — 通常與主交易一起 commit 才能保 atomic
"""

from __future__ import annotations

import logging
from typing import Optional, Any, Dict

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger(__name__)


def record_action(
    db: Session,
    *,
    user_upn: str,
    action_type: str,
    target_id: Optional[str] = None,
    target_type: str = "meeting",
    metadata: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """寫一筆 audit log row 進 db.session（不 commit，由 caller 統一 commit）。

    失敗時 log warning 但不 raise — audit 不該擋掉使用者主流程。
    """
    try:
        log = AuditLog(
            user_upn=user_upn or "anonymous",
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            log_metadata=metadata or {},
            ip_address=_extract_ip(request),
            user_agent=_extract_user_agent(request),
        )
        db.add(log)
    except Exception as e:
        # 即使 audit 寫入失敗，主流程仍須繼續
        logger.warning(f"[audit] failed to record {action_type} for {target_id}: {e}")


def _extract_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    try:
        # X-Forwarded-For first (Cloud Run / LB)
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
        if request.client and request.client.host:
            return request.client.host[:64]
    except Exception:
        return None
    return None


def _extract_user_agent(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    try:
        ua = request.headers.get("user-agent")
        if ua:
            return ua[:1000]
    except Exception:
        return None
    return None
