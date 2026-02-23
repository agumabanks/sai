"""
Server Health Skill — wraps the existing ServerHealthAgent.

Provides CPU, RAM, disk, services, and Docker status checks
through the skill interface for LLM tool calling.
"""

import json
import logging

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class ServerHealthSkill(BaseSkill):
    name = "server_health"
    description = "Check server health metrics including CPU, RAM, disk usage, and service status"
    version = "1.0.0"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        try:
            from core.agents.server_health import ServerHealthAgent

            agent = ServerHealthAgent()
            metric = args.get("metric", "all")
            output_format = args.get("format", "text")

            if metric == "all":
                snapshot = await agent.get_snapshot()
                alerts = await agent.get_alerts()
            else:
                snapshot = await agent.get_metric(metric)
                alerts = []

            if output_format == "json":
                output = json.dumps(snapshot, indent=2, default=str)
            else:
                output = self._format_text(snapshot, alerts)

            return SkillResult(
                success=True,
                output=output,
                data={"snapshot": snapshot, "alerts": alerts},
            )

        except Exception as e:
            logger.error(f"server_health skill failed: {e}")
            return SkillResult(success=False, error=str(e))

    def _format_text(self, snapshot: dict, alerts: list) -> str:
        lines = ["📊 **Server Health Report**\n"]

        if isinstance(snapshot, dict):
            for key, value in snapshot.items():
                lines.append(f"- **{key}**: {value}")

        if alerts:
            lines.append(f"\n⚠️ **Alerts** ({len(alerts)}):")
            for alert in alerts:
                severity = alert.get("severity", "unknown")
                msg = alert.get("message", "No details")
                lines.append(f"  - [{severity.upper()}] {msg}")

        return "\n".join(lines)
