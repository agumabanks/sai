import os
import random
import string
import logging
import smtplib
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

from core.database import PendingApproval, AsyncSessionLocal
from core.config import get_settings
from core.integrations.whatsapp_saas_manager import WhatsAppSaaSManager

logger = logging.getLogger(__name__)
settings = get_settings()

def generate_token(length=6):
    """Generate a random alphanumeric token."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

class ApprovalManager:
    """Manages the lifecycle of pending approvals for destructive operations."""

    def __init__(self):
        self.whatsapp_saas = WhatsAppSaaSManager(
            source_path=settings.whatsapp_saas_source_path,
            base_url=settings.whatsapp_saas_base_url,
            vendor_uid=settings.whatsapp_saas_vendor_uid,
            api_token=settings.whatsapp_saas_api_token,
        )

    async def request_approval(self, action: str, target: str, details: dict = None, channels: list = None) -> PendingApproval:
        """
        Create a new PendingApproval request and dispatch notifications.
        Returns the created PendingApproval record.
        """
        if channels is None:
            channels = ["whatsapp", "email"]
            
        token = generate_token()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        approval = await PendingApproval.create(
            action=action,
            target=target,
            details=details,
            token=token,
            expires_at=expires_at,
        )
        
        message = f"🚨 SECURITY APPROVAL REQUIRED 🚨\n\nApprove {action} of {target}?\nReply YES-{token} to approve.\n\nExpires in 15 minutes."
        
        if "whatsapp" in channels and settings.whatsapp_saas_enabled:
            await self._send_whatsapp(message)
            
        if "email" in channels and settings.smtp_host:
            await self._send_email(
                subject=f"Approval Required: {action} of {target}",
                body=message,
                to=settings.alert_recipients
            )
            
        return approval

    async def process_approval(self, token: str, via: str) -> bool:
        """
        Verify an approval token.
        If valid and not expired, marks it approved and returns True.
        """
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(PendingApproval).where(PendingApproval.token == token.upper())
            )
            approval = result.scalars().first()
            
            if not approval:
                logger.warning(f"Invalid approval token received: {token}")
                return False
                
            if approval.approved_at:
                logger.info(f"Token {token} already approved.")
                return True
                
            if datetime.now(timezone.utc) > approval.expires_at.replace(tzinfo=timezone.utc):
                logger.warning(f"Expired approval token received: {token}")
                return False
                
            approval.approved_at = datetime.now(timezone.utc)
            approval.approved_via = via
            await session.commit()
            
            # Here we would normally trigger the execution of whatever was blocked.
            # To decouple, the caller logic (e.g. Brain or WhatsApp adapter) handles execution.
            return True

    async def _send_whatsapp(self, message: str):
        """Send approval notification via WhatsApp SaaS."""
        try:
            admin_phone = await self._get_admin_phone()
            if not admin_phone:
                logger.warning("No admin phone configured for WhatsApp approval notifications")
                return
            result = await self.whatsapp_saas.send_message(admin_phone, message)
            if result.get("success"):
                logger.info(f"WhatsApp approval notification sent to {admin_phone}")
            else:
                logger.error(f"WhatsApp approval notification failed: {result.get('error', 'unknown')}")
        except Exception as e:
            logger.error(f"WhatsApp dispatch failed: {e}")

    async def _get_admin_phone(self) -> str:
        """Get admin phone number from system preferences."""
        from core.database import SystemKnowledge
        phone = await SystemKnowledge.get_pref("alert.emergency_phone", default=None)
        if not phone:
            phone = settings.alert_recipients.split(",")[0].strip() if settings.alert_recipients else None
        return phone

    async def _send_email(self, subject: str, body: str, to: str):
        """Send message via SMTP."""
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = settings.smtp_from
            msg["To"] = to
            
            # Synchronous SMTP for now as per report_agent.py
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                if settings.smtp_user and settings.smtp_pass:
                    server.login(settings.smtp_user, settings.smtp_pass)
                server.send_message(msg)
            logger.info(f"Email sent to {to} for approval request.")
        except Exception as e:
            logger.error(f"Email dispatch failed: {e}")

manager = ApprovalManager()
