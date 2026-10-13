import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, text

from core.database import AsyncSessionLocal, Log, Alert, IntelligenceBriefing
from core.brain import Brain

logger = logging.getLogger(__name__)

class WelcomeBackBriefing:
    """Generates a summary of what happened while the user was away."""

    def __init__(self, brain: Optional[Brain] = None):
        self.brain = brain or Brain()

    async def generate_briefing(self, since_hours: int = 12) -> str:
        """Fetch system events, alerts, and news, and summarize them."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        async with AsyncSessionLocal() as session:
            # 1. Fetch Errors/Warnings from Logs
            log_result = await session.execute(
                select(Log)
                .where(Log.created_at >= cutoff_time)
                .where(Log.level.in_(["error", "warning"]))
                .limit(20)
            )
            logs = [f"[{l.level.upper()}] {l.source}: {l.message}" for l in log_result.scalars().all()]

            # 2. Fetch Unacknowledged Alerts
            alert_result = await session.execute(
                select(Alert)
                .where(Alert.acknowledged == False)
            )
            alerts = [f"🚨 {a.severity.upper()} ({a.source}): {a.message}" for a in alert_result.scalars().all()]

            # 3. Fetch Recent Intelligence Briefings
            news_result = await session.execute(
                select(IntelligenceBriefing)
                .where(IntelligenceBriefing.created_at >= cutoff_time)
                .limit(3)
            )
            news = [f"📰 {n.title}" for n in news_result.scalars().all()]

            if not logs and not alerts and not news:
                return "Welcome back! The system has been quiet. No new errors, alerts, or briefings."

        prompt = f"""You are Sanaa AI returning a "Welcome Back" briefing to the user.
The user has been away for up to {since_hours} hours.
Here is what happened while they were away:

System Logs (Errors/Warnings):
{chr(10).join(logs) if logs else "None"}

Active Alerts:
{chr(10).join(alerts) if alerts else "None"}

New Briefings:
{chr(10).join(news) if news else "None"}

Draft a concise, professional message summarizing the system state. Highlight any blockers or active alerts first. If there are mostly normal news/briefings, mention them briefly."""

        return await self.brain.think(prompt, complexity="medium")
