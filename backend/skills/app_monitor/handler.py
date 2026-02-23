"""
App Monitor Skill — wraps the existing AppMonitorAgent.

Scans Laravel and application logs for errors and warnings
across the Sanaa ecosystem.
"""

import logging

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class AppMonitorSkill(BaseSkill):
    name = "app_monitor"
    description = "Scan application logs for errors, warnings, and anomalies"
    version = "1.0.0"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        try:
            from core.agents.app_monitor import AppMonitorAgent

            agent = AppMonitorAgent()
            errors = await agent.scan_for_new_errors()

            if not errors:
                return SkillResult(
                    success=True,
                    output="✅ No new errors detected across monitored applications.",
                    data={"errors": [], "count": 0},
                )

            lines = [f"🔍 **{len(errors)} Error(s) Detected**\n"]
            for err in errors[:10]:
                app = err.get("app", "unknown")
                raw = err.get("raw", "No details")[:200]
                lines.append(f"- **[{app}]** {raw}")

            if len(errors) > 10:
                lines.append(f"\n... and {len(errors) - 10} more errors")

            return SkillResult(
                success=True,
                output="\n".join(lines),
                data={"errors": errors, "count": len(errors)},
            )

        except Exception as e:
            logger.error(f"app_monitor skill failed: {e}")
            return SkillResult(success=False, error=str(e))
