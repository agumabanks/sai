"""
Sanaa AI — Escalation Engine.
Manages multi-tier alert escalation: email → WhatsApp → full recipient list.
Tracks escalation state in the ``alert_escalations`` table and advances
through policy levels after configured timeouts.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import AlertEscalation, AsyncSessionLocal, utcnow
from sqlalchemy import select

logger = logging.getLogger(__name__)


class EscalationEngine:
    """Manages alert escalation lifecycle."""

    async def start_escalation(
        self,
        alert_rule_id: int,
        message: str,
        recipients: list[str],
        policy: dict,
    ) -> dict:
        """Create a new escalation entry and execute the first level immediately.

        Returns a dict describing the created escalation state.
        """
        levels = policy.get("levels", [])
        if not levels:
            logger.warning("Escalation policy has no levels, skipping.")
            return {"id": None, "current_level": 0, "channel": None}

        first_level = levels[0]

        # Persist escalation tracking record
        entry = await AlertEscalation.create(
            alert_rule_id=alert_rule_id,
            message=message,
            recipients=recipients,
            policy=policy,
            current_level=0,
        )

        # Execute the first level immediately
        await self._execute_level(
            channel=first_level.get("channel", "email"),
            message=message,
            recipients=recipients,
        )

        return {
            "id": entry.id,
            "current_level": 0,
            "channel": first_level.get("channel", "email"),
        }

    async def check_and_escalate(
        self,
        escalation_id: int,
        force: bool = False,
    ) -> Optional[dict]:
        """Check if an escalation needs to advance to the next level.

        If ``force`` is True, advance immediately (used for testing).
        Returns the updated state dict, or ``None`` if already at max level.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AlertEscalation).where(AlertEscalation.id == escalation_id)
            )
            entry = result.scalars().first()

        if not entry:
            logger.warning(f"Escalation {escalation_id} not found.")
            return None

        if entry.acknowledged:
            logger.info(f"Escalation {escalation_id} already acknowledged.")
            return None

        levels = entry.policy.get("levels", [])
        current = entry.current_level
        next_level = current + 1

        if next_level >= len(levels):
            logger.info(f"Escalation {escalation_id} at max level ({current}).")
            return None

        # Check timeout (skip if force)
        if not force:
            timeout_minutes = levels[current].get("timeout_minutes", 15)
            elapsed = (datetime.now(timezone.utc) - entry.last_escalated_at).total_seconds() / 60
            if elapsed < timeout_minutes:
                return None  # Not yet time to escalate

        # Advance to next level
        level_config = levels[next_level]
        channel = level_config.get("channel", "email")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AlertEscalation).where(AlertEscalation.id == escalation_id)
            )
            db_entry = result.scalars().first()
            if db_entry:
                db_entry.current_level = next_level
                db_entry.last_escalated_at = utcnow()
                await session.commit()

        await self._execute_level(
            channel=channel,
            message=entry.message,
            recipients=entry.recipients,
        )

        logger.info(
            f"Escalation {escalation_id} advanced to level {next_level} "
            f"(channel={channel})"
        )

        return {
            "id": escalation_id,
            "current_level": next_level,
            "channel": channel,
        }

    async def acknowledge(self, escalation_id: int) -> bool:
        """Mark an escalation as acknowledged, stopping further advancement."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AlertEscalation).where(AlertEscalation.id == escalation_id)
            )
            entry = result.scalars().first()
            if not entry:
                return False
            entry.acknowledged = True
            await session.commit()
            return True

    async def _execute_level(
        self,
        channel: str,
        message: str,
        recipients: list[str],
    ) -> None:
        """Execute notification for a given channel."""
        if channel == "email":
            from core.alerts.email_sender import send_alert_email
            await send_alert_email(
                subject="[Sanaa AI] Alert Escalation",
                body=message,
                recipients=recipients,
            )
        elif channel == "whatsapp":
            # WhatsApp integration — attempt via existing adapter
            try:
                from core.routes.deps import whatsapp_adapter
                if whatsapp_adapter:
                    for recipient in recipients:
                        await whatsapp_adapter.send_message(recipient, message)
                else:
                    logger.warning("WhatsApp adapter not available for escalation.")
            except Exception as e:
                logger.error(f"WhatsApp escalation failed: {e}")
        elif channel == "all":
            # Send to all channels
            from core.alerts.email_sender import send_alert_email
            await send_alert_email(
                subject="[Sanaa AI] URGENT Alert Escalation (all channels)",
                body=message,
                recipients=recipients,
            )
            try:
                from core.routes.deps import whatsapp_adapter
                if whatsapp_adapter:
                    for recipient in recipients:
                        await whatsapp_adapter.send_message(recipient, message)
            except Exception as e:
                logger.error(f"WhatsApp (all-channel) escalation failed: {e}")
        else:
            logger.warning(f"Unknown escalation channel: {channel}")
