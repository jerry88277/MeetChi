"""
Email notification module for MeetChi.

Sends notifications to users when meeting processing stages complete:
- TRANSCRIBED: 逐字稿已完成，可先行查看
- COMPLETED: 摘要已生成完畢
- FAILED: 處理失敗通知

Configuration via environment variables:
- SMTP_HOST: SMTP server hostname
- SMTP_PORT: SMTP server port (default: 587)
- SMTP_USER: SMTP authentication username (optional for relay)
- SMTP_PASSWORD: SMTP authentication password (optional for relay)
- SMTP_USE_TLS: Whether to use STARTTLS (default: true)
- SMTP_FROM_EMAIL: Sender email address
- SMTP_FROM_NAME: Sender display name (default: MeetChi 會議助理)
- NOTIFICATION_ENABLED: Enable/disable email notifications (default: false)
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "meetchi-noreply@meetchi.ai")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MeetChi 會議助理")
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


def _resolve_mx(domain: str) -> Optional[str]:
    """Resolve MX record for a domain. Returns highest priority MX host."""
    import socket
    import struct

    # Method 1: try dnspython if available
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        mx_hosts = [(r.preference, str(r.exchange).rstrip(".")) for r in answers]
        if mx_hosts:
            mx_hosts.sort()
            return mx_hosts[0][1]
    except ImportError:
        pass
    except Exception:
        pass

    # Method 2: use subprocess nslookup
    import subprocess
    try:
        result = subprocess.run(
            ["nslookup", "-type=mx", domain],
            capture_output=True, text=True, timeout=10
        )
        mx_hosts = []
        for line in result.stdout.split("\n"):
            if "mail exchanger" in line:
                parts = line.strip().split()
                priority = int(parts[-2])
                host = parts[-1].rstrip(".")
                mx_hosts.append((priority, host))
        if mx_hosts:
            mx_hosts.sort()
            return mx_hosts[0][1]
    except Exception:
        pass

    # Method 3: hardcoded fallback for known domains
    known_mx = {
        "mail.chimei.com.tw": "inbound1.mail.chimei.com.tw",
        "gmail.com": "gmail-smtp-in.l.google.com",
    }
    return known_mx.get(domain)


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an HTML email via SMTP.
    
    Supports two modes:
    1. SMTP relay (SMTP_HOST configured): standard authenticated SMTP
    2. Direct MX delivery (SMTP_HOST="auto"): resolve recipient's MX and deliver directly
    
    Returns True on success, False on failure (never raises).
    """
    if not NOTIFICATION_ENABLED:
        logger.debug(f"[Email] Notification disabled, skipping: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg["To"] = to_email

        # Plain text fallback
        plain_text = f"{subject}\n\n請使用支援 HTML 的郵件客戶端查看此信件。"
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if SMTP_HOST == "auto" or not SMTP_HOST:
            # Direct MX delivery — resolve recipient domain's MX record
            domain = to_email.split("@")[1]
            mx_host = _resolve_mx(domain)
            if not mx_host:
                logger.error(f"[Email] Cannot resolve MX for {domain}")
                return False
            logger.info(f"[Email] Direct MX delivery to {mx_host}:25")
            import socket
            with smtplib.SMTP(mx_host, 25, timeout=30) as server:
                server.ehlo(socket.getfqdn())
                try:
                    server.starttls()
                    server.ehlo(socket.getfqdn())
                except (smtplib.SMTPNotSupportedError, smtplib.SMTPException):
                    pass
                server.sendmail(SMTP_FROM_EMAIL, to_email, msg.as_string())
        elif SMTP_USE_TLS and SMTP_PORT == 465:
            # SSL mode
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM_EMAIL, to_email, msg.as_string())
        else:
            # STARTTLS or plain mode
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM_EMAIL, to_email, msg.as_string())

        logger.info(f"[Email] Sent successfully to {to_email}: {subject}")
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
