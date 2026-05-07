# Phase 9.2: Notification System — Discord Webhook MVP
# Fire-and-forget notifications on task completion/failure.
# Designed with NotificationChannel protocol for future Teams migration (Phase 9.3).

import os
import logging
from typing import Protocol, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

# Taipei timezone (UTC+8)
TPE = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://meetchi-frontend-705495828555.asia-southeast1.run.app")


class NotificationChannel(Protocol):
    """Protocol for notification channels (Discord, Teams, etc.)."""
    def send(self, payload: Dict[str, Any]) -> bool: ...


class DiscordChannel:
    """Discord Webhook notification channel using Embed format."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, payload: Dict[str, Any]) -> bool:
        """Send a Discord Embed message. Returns True on success."""
        if not self.webhook_url:
            logger.warning("[Notify] DISCORD_WEBHOOK_URL not set, skipping notification")
            return False

        try:
            import httpx
            response = httpx.post(
                self.webhook_url,
                json=payload,
                timeout=10.0,
            )
            if response.status_code in (200, 204):
                logger.info("[Notify] Discord notification sent successfully")
                return True
            else:
                logger.warning(f"[Notify] Discord returned {response.status_code}: {response.text[:200]}")
                return False
        except Exception as e:
            # Fire-and-forget: log but don't raise
            logger.error(f"[Notify] Discord notification failed: {e}")
            return False


def _build_discord_embed(meeting: Any, status: str) -> Dict[str, Any]:
    """Build Discord Embed payload from meeting object and status."""
    is_success = status.lower() == "completed"

    # Status indicator
    status_emoji = "✅" if is_success else "❌"
    status_text = "摘要生成完成" if is_success else "摘要生成失敗"
    color = 0x48B070 if is_success else 0xD2343D  # Green / Red

    # Build fields
    fields = []

    # Meeting info
    fields.append({
        "name": "📋 會議標題",
        "value": getattr(meeting, 'title', 'N/A'),
        "inline": True,
    })

    fields.append({
        "name": "🆔 Meeting ID",
        "value": f"`{getattr(meeting, 'id', 'N/A')}`",
        "inline": True,
    })

    # Language + Template
    language = getattr(meeting, 'language', 'zh') or 'zh'
    template = getattr(meeting, 'template_name', 'general') or 'general'
    fields.append({
        "name": "🌐 語言 / 模板",
        "value": f"{language} / {template}",
        "inline": True,
    })

    # Timeline (convert UTC → Taipei time for display)
    created_at = getattr(meeting, 'created_at', None)
    updated_at = getattr(meeting, 'updated_at', None)

    timeline_parts = []
    if created_at:
        if isinstance(created_at, datetime):
            tpe_time = created_at.replace(tzinfo=timezone.utc).astimezone(TPE)
            ts = tpe_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts = str(created_at)
        timeline_parts.append(f"📤 建立時間: {ts}")
    if updated_at:
        if isinstance(updated_at, datetime):
            tpe_time = updated_at.replace(tzinfo=timezone.utc).astimezone(TPE)
            ts = tpe_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts = str(updated_at)
        timeline_parts.append(f"🏁 完成時間: {ts}")

    if timeline_parts:
        fields.append({
            "name": "⏱️ 時間線 (台北時間)",
            "value": "\n".join(timeline_parts),
            "inline": False,
        })

    # Dashboard link
    meeting_id = getattr(meeting, 'id', '')
    if meeting_id:
        fields.append({
            "name": "🔗 連結",
            "value": f"[開啟 Dashboard]({FRONTEND_URL}/dashboard/meetings/{meeting_id})",
            "inline": False,
        })

    embed = {
        "title": f"{status_emoji} MeetChi — {status_text}",
        "color": color,
        "fields": fields,
        "footer": {"text": "MeetChi Notification System"},
        "timestamp": datetime.utcnow().isoformat(),
    }

    return {"embeds": [embed]}


def send_completion_notification(meeting: Any, status: str) -> None:
    """Fire-and-forget notification on task completion/failure.
    
    Args:
        meeting: SQLAlchemy Meeting object (must have id, title, created_at, etc.)
        status: "completed" or "failed"
    """
    if not DISCORD_WEBHOOK_URL:
        logger.debug("[Notify] No DISCORD_WEBHOOK_URL configured, skipping")
        return

    try:
        payload = _build_discord_embed(meeting, status)
        channel = DiscordChannel(DISCORD_WEBHOOK_URL)
        channel.send(payload)
    except Exception as e:
        # Never let notification failures affect the main pipeline
        logger.error(f"[Notify] Unexpected error building notification: {e}")
