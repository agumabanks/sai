import asyncio
import logging
import json
from sqlalchemy import text
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class NewsPipelineSkill(BaseSkill):
    name = "news_pipeline"
    
    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")
        
        if action == "briefing_status":
            return await self._get_briefing_status()
        elif action == "feed_check":
            return await self._check_feeds()
        elif action == "newsletter_status":
            return await self._get_newsletter_status()
        elif action == "send_now":
            return await self._trigger_send()
            
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_briefing_status(self) -> SkillResult:
        try:
            sql = text("SELECT id, title, created_at FROM intelligence_briefings ORDER BY created_at DESC LIMIT 5")
            async with AsyncSessionLocal() as session:
                res = await session.execute(sql)
                rows = res.mappings().all()
            
            if not rows:
                return SkillResult(success=True, output="No briefings found in database.")
                
            output = "Latest Briefings:\n"
            for r in rows:
                output += f"- {r['title']} (ID: {r['id']}, Created: {r['created_at']})\n"
            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _check_feeds(self) -> SkillResult:
        try:
            from core.agents.news_agent import NewsAgent
            agent = NewsAgent()
            feeds = agent.feeds
            output = f"Configured Sectors: {list(feeds.keys())}\nTotal Feeds: {sum(len(u) for u in feeds.values())}"
            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_newsletter_status(self) -> SkillResult:
        try:
            from core.config import get_settings
            settings = get_settings()
            output = (
                f"SMTP Host: {settings.smtp_host}\n"
                f"SMTP Port: {settings.smtp_port}\n"
                f"SMTP From: {settings.smtp_from}\n"
                f"Alert Recipients: {settings.alert_recipients}\n"
            )
            # Check for recent PDFs
            import os
            pdf_dir = "/var/www/ai.sanaa.co/data/news"
            if os.path.exists(pdf_dir):
                files = sorted(os.listdir(pdf_dir), reverse=True)[:5]
                output += f"\nRecent PDFs in {pdf_dir}:\n" + "\n".join(f"- {f}" for f in files)
            else:
                output += f"\nPDF directory not found: {pdf_dir}"
                
            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _trigger_send(self) -> SkillResult:
        try:
            from core.tasks import send_news_newsletter
            # Triggering via Celery task directly for async handling but calling it synchronously in this subprocess context might be tricky
            # Better to just call the agent method directly if we want immediate feedback
            from core.agents.news_agent import NewsAgent
            agent = NewsAgent()
            summary = await agent.get_daily_summary()
            success = await agent.send_newsletter(summary)
            return SkillResult(success=success, output="Newsletter triggered successfully" if success else "Newsletter send failed")
        except Exception as e:
            return SkillResult(success=False, error=str(e))
