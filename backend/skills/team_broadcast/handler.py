"""Team Broadcast — send messages via WhatsApp, email, or Telegram to individuals or groups."""
import logging
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.config import get_settings

logger = logging.getLogger(__name__)


class TeamBroadcastSkill(BaseSkill):
    name = "team_broadcast"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        channel = args.get("channel")
        message = args.get("message", "")
        recipient = args.get("recipient", "")
        recipients = args.get("recipients", [])  # multi-recipient list

        if not message:
            return SkillResult(success=False, error="'message' is required.")

        # Normalise recipients: single or list
        if recipient and not recipients:
            recipients = [recipient]
        if not recipients:
            return SkillResult(success=False, error="'recipient' or 'recipients' is required.")

        results = []
        errors = []
        for r in recipients:
            if channel == "whatsapp":
                res = await self._send_whatsapp(r, message)
            elif channel == "email":
                subject = args.get("subject", "[Sanaa AI] Team Broadcast")
                res = await self._send_email(r, message, subject)
            elif channel == "telegram":
                res = await self._send_telegram(r, message)
            else:
                return SkillResult(success=False, error=f"Unknown channel: {channel}. Use: whatsapp, email, telegram")
            if res.success:
                results.append(r)
            else:
                errors.append(f"{r}: {res.error}")

        if errors:
            return SkillResult(
                success=len(results) > 0,
                output=f"Sent to {len(results)}/{len(recipients)}. Errors: {'; '.join(errors)}",
                data={"sent": results, "failed": errors},
            )
        return SkillResult(
            success=True,
            output=f"Message sent via {channel} to {len(results)} recipient(s): {', '.join(results)}",
            data={"sent": results},
        )

    # ── WhatsApp via WhatsJet ─────────────────────────────────────────────────
    async def _send_whatsapp(self, phone: str, message: str) -> SkillResult:
        try:
            from core.integrations.whatsjet import WhatsAppSaaSManager
            wa = WhatsAppSaaSManager()
            result = await wa.send_text(phone, message)
            if result:
                return SkillResult(success=True, output=f"WhatsApp sent to {phone}.")
            return SkillResult(success=False, error="WhatsJet send returned False.")
        except ImportError:
            return SkillResult(success=False, error="WhatsJet integration not available.")
        except Exception as e:
            return SkillResult(success=False, error=f"WhatsApp failed: {e}")

    # ── Email via SMTP ────────────────────────────────────────────────────────
    async def _send_email(self, to_email: str, message: str, subject: str) -> SkillResult:
        settings = get_settings()
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.smtp_user
            msg["To"] = to_email
            msg.attach(MIMEText(message, "plain"))

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._smtp_send, settings, msg, to_email)
            return SkillResult(success=True, output=f"Email sent to {to_email}.")
        except Exception as e:
            return SkillResult(success=False, error=f"Email failed: {e}")

    def _smtp_send(self, settings, msg, to_email: str):
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)

    # ── Telegram via Bot API ──────────────────────────────────────────────────
    async def _send_telegram(self, chat_id: str, message: str) -> SkillResult:
        try:
            from core.config import get_settings
            settings = get_settings()
            bot_token = getattr(settings, "telegram_bot_token", "")
            if not bot_token:
                return SkillResult(success=False,
                                   error="TELEGRAM_BOT_TOKEN not configured in .env")

            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                )
                resp.raise_for_status()
                return SkillResult(success=True, output=f"Telegram message sent to chat {chat_id}.")
        except Exception as e:
            return SkillResult(success=False, error=f"Telegram failed: {e}")
