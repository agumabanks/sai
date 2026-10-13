import json
from typing import Dict, Any
from core.skills.base import BaseSkill, SkillResult

class MediaAgent(BaseSkill):
    async def execute(self, params: Dict[str, Any], context: Any) -> SkillResult:
        action = params.get("action", "generate_schedule")
        topic = params.get("topic", "general fintech")

        if action == "analyze_market":
            return await self._analyze_market(topic, context)
        elif action == "generate_schedule":
            return await self._generate_schedule(topic, context)
            
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _analyze_market(self, topic: str, context: Any) -> SkillResult:
        # Fetch latest internet intelligence on the topic using news_pipeline and site_watcher
        # For simplicity in this agent script, we'll ask the brain to synthesize recent news
        prompt = (
            f"You are the Sanaa Media Agent. Briefly analyze the market landscape "
            f"for '{topic}' based on recent tech/finance trends. "
            "Suggest 3 strategic content pillars we should focus on today."
        )
        synthesis = await context.brain.think(prompt, complexity="medium", channel="media_agent")
        
        output = f"📈 Market Analysis for '{topic}':\n\n{synthesis}"
        return SkillResult(success=True, output=output)

    async def _generate_schedule(self, topic: str, context: Any) -> SkillResult:
        # Draft a weekly social media schedule
        prompt = (
            f"You are the Sanaa Media Agent. Act as a social media manager for a leading "
            f"East African software and finance company. Create a brief 2-post content schedule "
            f"for this week specifically around the topic: '{topic}'. "
            "Provide the copy, suggested image/graphic, and best time to post."
        )
        schedule = await context.brain.think(prompt, complexity="medium", channel="media_agent")
        
        output = f"🗓️ Weekly Content Schedule ('{topic}'):\n\n{schedule}"
        return SkillResult(success=True, output=output)

# Register the entry point
handler = MediaAgent
