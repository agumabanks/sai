"""
Web Test Skill — wraps the existing WebTestAgent.

Tests webapp uptime and response times across Sanaa ecosystem sites.
"""

import logging

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class WebTestSkill(BaseSkill):
    name = "web_test"
    description = "Test webapp uptime and response times across all Sanaa ecosystem sites"
    version = "1.0.0"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        try:
            from core.agents.web_test_agent import WebTestAgent

            agent = WebTestAgent()
            results = await agent.test_all()

            up = [r for r in results if r.get("status") == "up"]
            down = [r for r in results if r.get("status") != "up"]

            lines = [f"🌐 **Webapp Uptime Report** — {len(up)}/{len(results)} UP\n"]

            if down:
                lines.append("**❌ DOWN:**")
                for r in down:
                    lines.append(f"  - {r.get('url', '?')} — {r.get('error', 'Unknown')}")

            if up:
                lines.append("\n**✅ UP:**")
                for r in up:
                    ms = r.get("response_time_ms", "?")
                    lines.append(f"  - {r.get('url', '?')} — {ms}ms")

            return SkillResult(
                success=True,
                output="\n".join(lines),
                data={"results": results, "up": len(up), "down": len(down)},
            )

        except Exception as e:
            logger.error(f"web_test skill failed: {e}")
            return SkillResult(success=False, error=str(e))
