"""
Proactive Messenger Agent — OpenClaw-inspired conversational outreach.

Unlike alert-only notifications, the ProactiveMessenger initiates helpful
conversational messages based on context, time, and system state.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from core.config import get_settings
from core.database import SystemKnowledge, Alert, AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)
settings = get_settings()


class ProactiveMessenger:
    """Generates and sends proactive conversational messages."""

    async def morning_greeting(self, brain=None) -> str:
        """Generate a morning briefing message."""
        now = datetime.now(timezone.utc)
        hour = (now.hour + 3) % 24  # EAT = UTC+3

        parts = [f"Good morning! It's {now.strftime('%A, %B %d')} ({hour}:{now.strftime('%M')} EAT)."]

        # Overnight alerts
        alerts = await self._get_recent_alerts(hours=12)
        if alerts:
            critical = [a for a in alerts if a.get("severity") == "critical"]
            high = [a for a in alerts if a.get("severity") == "high"]
            if critical:
                parts.append(f"\n{len(critical)} critical alert(s) overnight:")
                for a in critical[:3]:
                    parts.append(f"  - {a.get('message', 'Unknown')[:100]}")
            if high:
                parts.append(f"{len(high)} high-priority alert(s).")
        else:
            parts.append("No critical alerts overnight — all systems stable.")

        # Pending approvals
        pending = await self._get_pending_approvals()
        if pending:
            parts.append(f"\n{len(pending)} pending approval(s) awaiting your response.")

        # Learning stats
        try:
            from core.intelligence.learning_logs import learning_log_manager
            stats = await learning_log_manager.get_stats()
            total = stats.get("total_learnings", 0)
            if total > 0:
                parts.append(f"\nI've logged {total} learning(s) so far — {stats.get('corrections', 0)} corrections, {stats.get('feature_requests', 0)} feature requests.")
        except Exception:
            pass

        parts.append("\nHow can I help you today?")
        return "\n".join(parts)

    async def context_aware_suggestion(self, channel: str = "web") -> Optional[str]:
        """Generate a contextual suggestion based on recent activity."""
        now = datetime.now(timezone.utc)
        hour = (now.hour + 3) % 24  # EAT

        # Monday morning special
        if now.weekday() == 0 and 7 <= hour <= 9:
            return (
                "It's Monday morning — would you like me to run a full system health check "
                "and prepare your weekly overview? Just say 'yes' or '/new weekly review'."
            )

        # End of day
        if 17 <= hour <= 18:
            return (
                "End of day approaching. Want me to summarize today's activities, "
                "pending items, and overnight monitoring priorities?"
            )

        return None

    async def ssl_expiry_warning(self) -> Optional[str]:
        """Check for upcoming SSL expirations and warn proactively."""
        sql = text("""
            SELECT key, value FROM system_knowledge
            WHERE domain = 'infrastructure' AND key LIKE 'ssl.%'
            ORDER BY last_verified DESC
            LIMIT 20
        """)
        async with AsyncSessionLocal() as session:
            result = await session.execute(sql)
            rows = result.mappings().all()

        warnings = []
        for row in rows:
            try:
                days = int(row["value"])
                domain = row["key"].replace("ssl.", "")
                if days <= 14:
                    warnings.append(f"  - {domain}: expires in {days} days")
            except (ValueError, TypeError):
                pass

        if warnings:
            return (
                "SSL Certificate Warning:\n"
                + "\n".join(warnings)
                + "\n\nWould you like me to initiate auto-renewal?"
            )
        return None

    async def _get_recent_alerts(self, hours: int = 12) -> list[dict]:
        """Get recent alerts from the database."""
        sql = text("""
            SELECT severity, message, source, created_at
            FROM alerts
            WHERE created_at > NOW() - INTERVAL ':hours hours'
            ORDER BY created_at DESC
            LIMIT 20
        """.replace(":hours", str(hours)))
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(sql)
                return [dict(r) for r in result.mappings().all()]
        except Exception:
            return []

    async def _get_pending_approvals(self) -> list:
        """Get pending approvals."""
        from core.database import PendingApproval
        sql = text("""
            SELECT id, action, target, created_at
            FROM pending_approvals
            WHERE approved_at IS NULL AND expires_at > NOW()
            ORDER BY created_at DESC
        """)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(sql)
                return [dict(r) for r in result.mappings().all()]
        except Exception:
            return []


proactive_messenger = ProactiveMessenger()
