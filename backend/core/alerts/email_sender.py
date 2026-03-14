"""
Sanaa AI — Alert email sender.
Sends alert emails via SMTP to specified recipients, integrating with existing
SMTP configuration (ReportAgent pattern).
"""

import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_alert_email(
    subject: str,
    body: str,
    recipients: List[str],
) -> bool:
    """Send an alert email via SMTP to the given recipients.

    Respects the global ``alert.enabled`` preference stored in
    ``SystemKnowledge``.  Returns ``True`` on success, ``False`` if sending
    was skipped or failed.
    """
    from core.database import SystemKnowledge

    # Check global alert enabled preference
    is_enabled = await SystemKnowledge.get_pref("alert.enabled", True)
    if isinstance(is_enabled, str):
        enabled = is_enabled.strip().lower() not in ("false", "0", "no", "off", "")
    else:
        enabled = bool(is_enabled)

    if not enabled:
        logger.info("Alert email skipped: disabled in system preferences.")
        return False

    smtp_host = settings.smtp_host
    smtp_port = settings.smtp_port
    smtp_user = settings.smtp_user
    smtp_pass = settings.smtp_pass
    from_addr = settings.smtp_from

    if not smtp_host:
        logger.warning("Alert email skipped: SMTP_HOST is not configured.")
        return False

    if not recipients:
        logger.warning("Alert email skipped: no recipients specified.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(recipients)

        html_body = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; background: #0a0a0a; color: #e0e0e0;">
            <div style="max-width: 600px; margin: 0 auto; background: #1a1a2e; border-radius: 12px; padding: 24px; border: 1px solid #2a2a4a;">
                <div style="display: flex; align-items: center; margin-bottom: 16px;">
                    <span style="font-size: 24px; margin-right: 8px;">🛸</span>
                    <h2 style="margin: 0; color: #00d4ff;">Sanaa AI Alert</h2>
                </div>
                <div style="background: #0d0d1a; border-radius: 8px; padding: 16px; margin: 16px 0;">
                    <pre style="white-space: pre-wrap; color: #b0b0b0; margin: 0;">{body}</pre>
                </div>
                <p style="color: #666; font-size: 12px; margin-top: 16px;">
                    Sent by Sanaa AI at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} EAT
                    <br>Manage at <a href="https://ai.sanaa.co" style="color: #00d4ff;">ai.sanaa.co</a>
                </p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, recipients, msg.as_string())

        logger.info(f"Alert email sent to {recipients}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Alert email send failed: {e}")
        return False
