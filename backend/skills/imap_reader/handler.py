import logging
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.agents.email_agent import EmailInboxAgent

logger = logging.getLogger(__name__)

class ImapReaderSkill(BaseSkill):
    name = "imap_reader"
    
    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")
        limit = args.get("limit", 5)
        
        agent = EmailInboxAgent()
        
        if action == "check_inbox":
            try:
                result = await agent.get_inbox_summary(limit=limit)

                if "Error" in result.get("summary", ""):
                    return SkillResult(success=False, error=result["summary"])

                output = f"You have {result['count']} unread emails.\n\nSummary:\n{result['summary']}"

                # Log to brain memory
                try:
                    from core.database import AsyncSessionLocal
                    from sqlalchemy import text as sq_text
                    import json
                    async with AsyncSessionLocal() as session:
                        count = result.get("count", 0)
                        urgent = sum(1 for e in result.get("emails", []) if e.get("category") == "Urgent")
                        await session.execute(
                            sq_text("""
                                INSERT INTO agent_memory
                                    (content, category, source, confidence, metadata,
                                     created_at, updated_at, access_count, verified)
                                VALUES
                                    (:content, 'email_check', 'imap_skill', 0.9, :meta,
                                     NOW(), NOW(), 0, false)
                            """),
                            {
                                "content": f"[Email Agent] Checked inbox: {count} unread, {urgent} urgent",
                                "meta": json.dumps({"type": "email_check", "count": count, "urgent": urgent}),
                            },
                        )
                        await session.commit()
                except Exception as e:
                    logger.warning(f"Failed to log email check to memory: {e}")

                return SkillResult(
                    success=True,
                    output=output,
                    data=result
                )
            except Exception as e:
                logger.error(f"IMAP skill error: {e}")
                return SkillResult(success=False, error=str(e))
                
        return SkillResult(success=False, error=f"Unknown action: {action}")
