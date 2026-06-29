"""
Email notification module for MeetChi.

Sends notifications to users when meeting processing stages complete:
- TRANSCRIBED: 逐字稿已完成，可先行查看
- COMPLETED: 摘要已生成完畢
- FAILED: 處理失敗通知

Configuration via environment variables:
- SMTP_HOST: SMTP server hostname (default: mail.chimei.com.tw)
- SMTP_PORT: SMTP server port (default: 25 for internal relay)
- SMTP_USER: SMTP authentication username (optional for internal relay)
- SMTP_PASSWORD: SMTP authentication password (optional for internal relay)
- SMTP_USE_TLS: Whether to use STARTTLS (default: false for internal relay)
- SMTP_FROM_EMAIL: Sender email address (default: MeetChi_notify@mail.chimei.com.tw)
- SMTP_FROM_NAME: Sender display name (default: MeetChi 會議助理)
- SMTP_TIMEOUT: Connection timeout in seconds (default: 60)
- NOTIFICATION_ENABLED: Enable/disable email notifications (default: false)
"""

import logging
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formatdate, make_msgid
from typing import Optional, List

logger = logging.getLogger(__name__)

# Configuration — 預設值對齊奇美內部 SMTP relay（inbound1.mail.chimei.com.tw:25, no auth）
# 注意：mail.chimei.com.tw 從外部 (GCP) 不可達，需用 inbound1 MX 入口
SMTP_HOST = os.getenv("SMTP_HOST", "inbound1.mail.chimei.com.tw")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() in ("true", "1", "yes")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "MeetChi_notify@mail.chimei.com.tw")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MeetChi 會議助理")
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "60"))
NOTIFICATION_ENABLED = os.getenv("NOTIFICATION_ENABLED", "false").lower() in ("true", "1", "yes")


def _build_transcript_ready_email(meeting_title: str, meeting_url: str) -> tuple[str, str]:
    """Build email content for transcript ready notification."""
    subject = f"[MeetChi] 逐字稿已完成：{meeting_title}"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #4F46E5; color: white; padding: 20px 24px; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0; font-size: 18px;">📝 逐字稿已準備好</h2>
        </div>
        <div style="background: #F9FAFB; padding: 24px; border: 1px solid #E5E7EB; border-top: none; border-radius: 0 0 8px 8px;">
            <p style="color: #374151; font-size: 15px; line-height: 1.6;">
                您的會議 <strong>{meeting_title}</strong> 的逐字稿已經轉錄完成。
            </p>
            <p style="color: #6B7280; font-size: 14px;">
                💡 智慧摘要正在生成中（約 2~3 分鐘），您可以先查看逐字稿內容。
            </p>
            <a href="{meeting_url}" 
               style="display: inline-block; background: #4F46E5; color: white; padding: 12px 24px; 
                      border-radius: 6px; text-decoration: none; font-weight: 500; margin-top: 12px;">
                查看逐字稿 →
            </a>
        </div>
        <p style="color: #9CA3AF; font-size: 12px; text-align: center; margin-top: 16px;">
            此信件由 MeetChi 會議助理自動發送，請勿直接回覆。
        </p>
    </div>
    """
    return subject, html


def _build_summary_ready_email(meeting_title: str, meeting_url: str) -> tuple[str, str]:
    """Build email content for summary ready notification."""
    subject = f"[MeetChi] 會議摘要已完成：{meeting_title}"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #059669; color: white; padding: 20px 24px; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0; font-size: 18px;">✅ 會議摘要已生成完畢</h2>
        </div>
        <div style="background: #F9FAFB; padding: 24px; border: 1px solid #E5E7EB; border-top: none; border-radius: 0 0 8px 8px;">
            <p style="color: #374151; font-size: 15px; line-height: 1.6;">
                您的會議 <strong>{meeting_title}</strong> 已全部處理完成。
            </p>
            <p style="color: #6B7280; font-size: 14px;">
                包含：逐字稿、智慧摘要、行動項目、重點整理
            </p>
            <a href="{meeting_url}" 
               style="display: inline-block; background: #059669; color: white; padding: 12px 24px; 
                      border-radius: 6px; text-decoration: none; font-weight: 500; margin-top: 12px;">
                查看完整會議紀錄 →
            </a>
        </div>
        <p style="color: #9CA3AF; font-size: 12px; text-align: center; margin-top: 16px;">
            此信件由 MeetChi 會議助理自動發送，請勿直接回覆。
        </p>
    </div>
    """
    return subject, html


def _build_failed_email(meeting_title: str, meeting_url: str) -> tuple[str, str]:
    """Build email content for processing failure notification."""
    subject = f"[MeetChi] 處理需要注意：{meeting_title}"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #DC2626; color: white; padding: 20px 24px; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0; font-size: 18px;">⚠️ 會議處理遇到問題</h2>
        </div>
        <div style="background: #F9FAFB; padding: 24px; border: 1px solid #E5E7EB; border-top: none; border-radius: 0 0 8px 8px;">
            <p style="color: #374151; font-size: 15px; line-height: 1.6;">
                您的會議 <strong>{meeting_title}</strong> 在處理過程中遇到問題。
            </p>
            <p style="color: #6B7280; font-size: 14px;">
                系統將自動重試。如果問題持續，請聯繫管理員。
            </p>
            <a href="{meeting_url}" 
               style="display: inline-block; background: #6B7280; color: white; padding: 12px 24px; 
                      border-radius: 6px; text-decoration: none; font-weight: 500; margin-top: 12px;">
                查看詳情 →
            </a>
        </div>
        <p style="color: #9CA3AF; font-size: 12px; text-align: center; margin-top: 16px;">
            此信件由 MeetChi 會議助理自動發送，請勿直接回覆。
        </p>
    </div>
    """
    return subject, html


def _parse_recipients(recipients) -> List[str]:
    """穩健解析收件者：分號/逗號/頓號/空白皆可混用，去重去空白。"""
    if isinstance(recipients, str):
        raw = re.split(r'[;,、\s]+', recipients)
    elif isinstance(recipients, (list, tuple, set)):
        raw = []
        for item in recipients:
            raw.extend(re.split(r'[;,、\s]+', str(item)))
    else:
        raw = re.split(r'[;,、\s]+', str(recipients))

    seen = set()
    cleaned = []
    for addr in raw:
        addr = addr.strip()
        if addr and addr not in seen:
            seen.add(addr)
            cleaned.append(addr)
    return cleaned


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an HTML email via internal SMTP relay.

    採用奇美內部 mail.chimei.com.tw relay 模式：
    - 預設 port 25、無需認證
    - 支援多收件者（分號/逗號分隔）
    - 加上 Date + Message-ID 防止被當重複信去重
    - 含 timeout 防止卡死

    Returns True on success, False on failure (never raises).
    """
    if not NOTIFICATION_ENABLED:
        logger.debug(f"[Email] Notification disabled, skipping: {subject}")
        return False

    try:
        # 解析收件者（支援多人）
        receiver = _parse_recipients(to_email)
        if not receiver:
            logger.error(f"[Email] No valid recipients from: {to_email}")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg["To"] = ", ".join(receiver)
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()

        # Plain text fallback
        plain_text = f"{subject}\n\n請使用支援 HTML 的郵件客戶端查看此信件。"
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # 連線 SMTP（內部 relay 通常 port 25 無驗證）
        smtp = smtplib.SMTP(timeout=SMTP_TIMEOUT)
        try:
            smtp.connect(SMTP_HOST, SMTP_PORT)
            if SMTP_USE_TLS:
                smtp.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(SMTP_FROM_EMAIL, receiver, msg.as_string())
        finally:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass

        logger.info(f"[Email] Sent successfully to {receiver}: {subject}")
        return True

    except Exception as e:
        logger.error(f"[Email] Failed to send to {to_email}: {e}", exc_info=True)
        return False


def notify_transcript_ready(
    to_email: str, meeting_title: str, meeting_id: str, base_url: Optional[str] = None
) -> bool:
    """Notify user that transcript is ready (can view before summary completes)."""
    base = base_url or os.getenv("FRONTEND_URL", "https://meetchi.chimei.com.tw")
    meeting_url = f"{base}/meetings/{meeting_id}"
    subject, html = _build_transcript_ready_email(meeting_title, meeting_url)
    return send_email(to_email, subject, html)


def notify_summary_ready(
    to_email: str, meeting_title: str, meeting_id: str, base_url: Optional[str] = None
) -> bool:
    """Notify user that full processing (transcript + summary) is complete."""
    base = base_url or os.getenv("FRONTEND_URL", "https://meetchi.chimei.com.tw")
    meeting_url = f"{base}/meetings/{meeting_id}"
    subject, html = _build_summary_ready_email(meeting_title, meeting_url)
    return send_email(to_email, subject, html)


def notify_processing_failed(
    to_email: str, meeting_title: str, meeting_id: str, base_url: Optional[str] = None
) -> bool:
    """Notify user that processing has failed."""
    base = base_url or os.getenv("FRONTEND_URL", "https://meetchi.chimei.com.tw")
    meeting_url = f"{base}/meetings/{meeting_id}"
    subject, html = _build_failed_email(meeting_title, meeting_url)
    return send_email(to_email, subject, html)


def send_test_email(to_email: str) -> bool:
    """Send a test email to verify SMTP configuration."""
    subject = "[MeetChi] SMTP 測試信件"
    html = """
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #4F46E5; color: white; padding: 20px 24px; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0; font-size: 18px;">🧪 SMTP 測試成功</h2>
        </div>
        <div style="background: #F9FAFB; padding: 24px; border: 1px solid #E5E7EB; border-top: none; border-radius: 0 0 8px 8px;">
            <p style="color: #374151; font-size: 15px; line-height: 1.6;">
                如果您收到這封信，表示 MeetChi 的 Email 通知功能已正確設定。
            </p>
            <p style="color: #6B7280; font-size: 14px;">
                SMTP Host: {host}:{port}<br>
                TLS: {tls}<br>
                From: {from_email}
            </p>
        </div>
    </div>
    """.format(
        host=SMTP_HOST or "(未設定)",
        port=SMTP_PORT,
        tls="是" if SMTP_USE_TLS else "否",
        from_email=SMTP_FROM_EMAIL,
    )
    return send_email(to_email, subject, html)
