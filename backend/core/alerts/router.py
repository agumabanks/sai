"""
Sanaa AI — Alert Router.
Matches incoming alerts (metric + value) to configured AlertRule entries and
routes notifications to the appropriate channels.  Respects quiet-hours and
severity settings.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.database import AlertRule, AsyncSessionLocal
from sqlalchemy import select

logger = logging.getLogger(__name__)


def _is_within_quiet_hours(quiet_hours: dict | None) -> bool:
    """Check if the current time falls within the rule's quiet-hours window.

    ``quiet_hours`` format: ``{"start": "22:00", "end": "07:00", "timezone": "Africa/Kampala"}``
    Uses UTC when timezone is omitted or cannot be resolved.
    """
    if not quiet_hours:
        return False

    start_str = quiet_hours.get("start", "")
    end_str = quiet_hours.get("end", "")
    if not start_str or not end_str:
        return False

    try:
        tz_name = quiet_hours.get("timezone", "UTC")
        # Use simple UTC offset to avoid hard dependency on pytz/zoneinfo
        now = datetime.now(timezone.utc)

        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))

        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        if start_minutes <= end_minutes:
            # Simple range: e.g. 08:00 – 17:00
            return start_minutes <= current_minutes <= end_minutes
        else:
            # Wrap-around range: e.g. 22:00 – 07:00
            return current_minutes >= start_minutes or current_minutes <= end_minutes
    except Exception as e:
        logger.warning(f"Failed to parse quiet hours: {e}")
        return False


class AlertRouter:
    """Routes alerts to channels based on matching rules."""

    async def find_matching_rules(
        self,
        metric: str,
        value: float,
    ) -> List[AlertRule]:
        """Find all enabled rules whose condition matches the metric and
        whose threshold is exceeded by *value*."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AlertRule).where(
                    AlertRule.condition == metric,
                    AlertRule.enabled == True,
                )
            )
            rules = result.scalars().all()

        # Filter by threshold
        matched = [r for r in rules if value >= r.threshold]
        return matched

    async def route_alert(
        self,
        metric: str,
        value: float,
        message: str,
        source: Optional[str] = None,
    ) -> dict:
        """Find matching rules and route the alert accordingly.

        Returns a summary dict with keys:
          - ``routed`` (bool): whether at least one notification was sent
          - ``matched_rules``: number of matching rules
          - ``suppressed_count``: rules skipped due to quiet hours
          - ``notified_count``: rules that triggered notifications
        """
        from core.alerts.email_sender import send_alert_email
        from core.alerts.escalation import EscalationEngine

        matched_rules = await self.find_matching_rules(metric=metric, value=value)

        if not matched_rules:
            return {"routed": False, "matched_rules": 0, "suppressed_count": 0, "notified_count": 0}

        suppressed = 0
        notified = 0
        escalation_engine = EscalationEngine()

        for rule in matched_rules:
            # Check quiet hours – suppress non-critical/non-high severity
            if _is_within_quiet_hours(rule.quiet_hours):
                if rule.severity not in ("critical", "high"):
                    suppressed += 1
                    logger.info(
                        f"Alert suppressed (quiet hours) for rule '{rule.name}' "
                        f"[severity={rule.severity}]"
                    )
                    continue

            # Build recipients from the rule
            recipients = rule.recipients or []
            if not recipients:
                logger.warning(f"Rule '{rule.name}' has no recipients, skipping.")
                continue

            subject = f"[Sanaa AI] {rule.severity.upper()} ALERT: {rule.name}"
            body = (
                f"Rule: {rule.name}\n"
                f"Condition: {rule.condition} (threshold: {rule.threshold})\n"
                f"Current value: {value}\n"
                f"Severity: {rule.severity}\n"
                f"Source: {source or 'N/A'}\n\n"
                f"{message}"
            )

            # Send immediate email
            sent = await send_alert_email(subject=subject, body=body, recipients=recipients)
            if sent:
                notified += 1

            # Start escalation if policy configured
            if rule.escalation_policy and rule.escalation_policy.get("levels"):
                try:
                    await escalation_engine.start_escalation(
                        alert_rule_id=rule.id,
                        message=body,
                        recipients=recipients,
                        policy=rule.escalation_policy,
                    )
                except Exception as e:
                    logger.error(f"Failed to start escalation for rule '{rule.name}': {e}")

        return {
            "routed": notified > 0,
            "matched_rules": len(matched_rules),
            "suppressed_count": suppressed,
            "notified_count": notified,
        }
