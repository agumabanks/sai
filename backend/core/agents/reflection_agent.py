"""
Reflection Agent — Behavioral Cloning & Memory Consolidation
Runs daily to analyze user commands and interactions, establishing "Jarvis" preferences.
"""

import logging
import json
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from core.database import AsyncSessionLocal
from core.brain import get_shared_brain

logger = logging.getLogger(__name__)

class ReflectionAgent:
    def __init__(self, brain=None):
        self.brain = brain or get_shared_brain()

    async def run_daily_reflection(self):
        """Analyze the last 24 hours of commands and conversations to infer user preferences, profile facts, and active projects."""
        try:
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            
            # Fetch recent terminal commands
            sql_cmds = text("SELECT command_text FROM commands WHERE created_at >= :date AND user_id IS NOT NULL")
            # Fetch recent distinct user requests (conversations)
            sql_conv = text("SELECT content FROM conversations WHERE created_at >= :date AND role = 'user' AND sender_id != 'brain' LIMIT 100")
            
            async with AsyncSessionLocal() as session:
                cmd_res = await session.execute(sql_cmds, {"date": yesterday})
                conv_res = await session.execute(sql_conv, {"date": yesterday})
                
                commands = [r["command_text"] for r in cmd_res.mappings().all()]
                conversations = [r["content"] for r in conv_res.mappings().all()]
                
            if not commands and not conversations:
                logger.info("ReflectionAgent: No new user activity to analyze.")
                return

            # Prepare prompt for Brain
            prompt = f"""You are the Reflection & Memory Consolidation component of Sanaa AI. 
Analyze the user's recent actions and conversations to extract long-term persistent knowledge.

Recent Commands Executed by User:
{json.dumps(commands, indent=2)}

Recent Requests/Conversations from User:
{json.dumps(conversations, indent=2)}

Task: Extract knowledge into exactly three categories:
1. "learned_rules": 1-3 concise operational preferences (e.g., "User prefers reloading Nginx over restarting it").
2. "user_profile": Persistent facts about the user (e.g., "User's working hours are 9-5", "User's name is Banks").
3. "project_context": Active project statuses or deadlines (e.g., "Working on the loan issuance bug", "Migrating Soko to Laravel 11").

Respond ONLY with a valid JSON object matching this schema. If nothing notable can be learned for a category, return an empty list [] for it:
{{
  "learned_rules": ["rule 1"],
  "user_profile": ["fact 1"],
  "project_context": ["project 1"]
}}"""

            # Use a capable model for synthesis
            analysis = await self.brain.think(prompt, complexity="high")
            
            # Extract JSON object
            import re
            match = re.search(r'\{[\s\S]*\}', analysis)
            if match:
                try:
                    extracted = json.loads(match.group())
                    
                    from core.database import SystemKnowledge, AgentMemory
                    from core.memory.manager import MemoryManager
                    from sqlalchemy import update
                    from sqlalchemy.dialects.postgresql import insert
                    
                    memory_manager = MemoryManager()
                    
                    async with AsyncSessionLocal() as session:
                        # 1. Learned Rules -> SystemKnowledge (behavior)
                        for idx, rule in enumerate(extracted.get("learned_rules", [])):
                            key = f"learned_preference.{datetime.now().strftime('%Y%m%d%H%M')}.{idx}"
                            stmt = insert(SystemKnowledge).values(
                                domain="behavior", key=key, value=rule, last_verified=datetime.now(timezone.utc)
                            ).on_conflict_do_nothing()
                            await session.execute(stmt)
                            # Also store as embeddable fact
                            await memory_manager.store(content=rule, category="preference", source="reflection_agent")

                        # 2. User Profile -> SystemKnowledge (user_profile)
                        for idx, fact in enumerate(extracted.get("user_profile", [])):
                            key = f"profile_fact.{datetime.now().strftime('%Y%m%d%H%M')}.{idx}"
                            stmt = insert(SystemKnowledge).values(
                                domain="user_profile", key=key, value=fact, last_verified=datetime.now(timezone.utc)
                            ).on_conflict_do_nothing()
                            await session.execute(stmt)
                            await memory_manager.store(content=fact, category="fact", source="reflection_agent")

                        # 3. Project Context -> SystemKnowledge (project_context)
                        for idx, proj in enumerate(extracted.get("project_context", [])):
                            key = f"project_fact.{datetime.now().strftime('%Y%m%d%H%M')}.{idx}"
                            stmt = insert(SystemKnowledge).values(
                                domain="project_context", key=key, value=proj, last_verified=datetime.now(timezone.utc)
                            ).on_conflict_do_nothing()
                            await session.execute(stmt)
                            await memory_manager.store(content=proj, category="observation", source="reflection_agent")

                        await session.commit()
                        
                    # Request approvals for suggested skills
                    suggested_skills = extracted.get("suggested_skills", [])
                    for skill_def in suggested_skills:
                        name = skill_def.get("name")
                        desc = skill_def.get("description")
                        if name and desc:
                            await approval_manager.request_approval(
                                action="generate_skill",
                                target=name,
                                details={"skill_description": desc},
                                channels=["dashboard"]
                            )
                        
                    logger.info(f"ReflectionAgent: Learned {len(extracted.get('learned_rules', []))} rules, {len(extracted.get('user_profile', []))} profile facts, {len(extracted.get('project_context', []))} project contexts, suggested {len(suggested_skills)} new skills.")
                except json.JSONDecodeError:
                    logger.error("ReflectionAgent: Failed to parse JSON from LLM output.")
                    
        except Exception as e:
            logger.error(f"ReflectionAgent Failed: {e}")

if __name__ == "__main__":
    import asyncio
    agent = ReflectionAgent()
    asyncio.run(agent.run_daily_reflection())
