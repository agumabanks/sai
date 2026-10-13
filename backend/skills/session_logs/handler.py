"""Session Logs — search conversations, audit trails, LLM costs, tool calls, and error analysis."""
import logging
from sqlalchemy import text
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class SessionLogsSkill(BaseSkill):
    name = "session_logs"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")
        limit = int(args.get("limit", 10))

        if action == "recent":
            return await self._recent(limit)
        elif action == "search":
            return await self._search(args, limit)
        elif action == "cost_summary":
            return await self._cost_summary()
        elif action == "tool_calls":
            return await self._tool_calls(limit)
        elif action == "error_analysis":
            return await self._error_analysis(args, context, limit)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ── recent conversations ──────────────────────────────────────────────────
    async def _recent(self, limit: int) -> SkillResult:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT role, content, created_at FROM conversations
                    ORDER BY created_at DESC LIMIT :limit
                """), {"limit": limit})
                rows = result.mappings().all()
            if not rows:
                return SkillResult(success=True, output="No conversation history found.")
            lines = []
            for r in rows:
                snippet = (r["content"] or "")[:120].replace("\n", " ")
                lines.append(f"[{r['created_at']}] {r['role']}: {snippet}")
            return SkillResult(success=True, output="\n".join(reversed(lines)))
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── search conversations ──────────────────────────────────────────────────
    async def _search(self, args: dict, limit: int) -> SkillResult:
        query = args.get("query", "")
        if not query:
            return SkillResult(success=False, error="'query' is required for search.")
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT role, content, created_at FROM conversations
                    WHERE content ILIKE :q ORDER BY created_at DESC LIMIT :limit
                """), {"q": f"%{query}%", "limit": limit})
                rows = result.mappings().all()
            if not rows:
                return SkillResult(success=True, output=f"No results for '{query}'.")
            lines = [f"Found {len(rows)} results for '{query}':"]
            for r in rows:
                snippet = (r["content"] or "")[:150].replace("\n", " ")
                lines.append(f"[{r['created_at']}] {r['role']}: {snippet}")
            return SkillResult(success=True, output="\n".join(lines))
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── LLM cost summary ─────────────────────────────────────────────────────
    async def _cost_summary(self) -> SkillResult:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT provider, COUNT(*) as calls, SUM(total_tokens) as tokens, SUM(cost_usd) as cost
                    FROM llm_usage WHERE created_at >= NOW() - INTERVAL '24 hours'
                    GROUP BY provider
                """))
                rows = result.mappings().all()
            if not rows:
                return SkillResult(success=True, output="No LLM usage in the last 24 hours.")
            lines = ["LLM Cost Summary (Last 24h):"]
            total_cost = 0
            for r in rows:
                cost = float(r["cost"] or 0)
                total_cost += cost
                lines.append(f"  {r['provider']}: {r['calls']} calls, {r['tokens'] or 0} tokens, ${cost:.4f}")
            lines.append(f"\n  TOTAL: ${total_cost:.4f}")
            return SkillResult(success=True, output="\n".join(lines))
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── tool/skill call audit ─────────────────────────────────────────────────
    async def _tool_calls(self, limit: int) -> SkillResult:
        """Show recent skill invocations from the skill_runs table."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT skill_name, status, duration_ms, triggered_by, error_message, created_at
                    FROM skill_runs
                    ORDER BY created_at DESC LIMIT :limit
                """), {"limit": limit})
                rows = result.mappings().all()
            if not rows:
                return SkillResult(success=True, output="No skill runs recorded yet.")
            lines = [f"{'SKILL':<25} {'STATUS':<8} {'MS':>6} {'BY':<20} CREATED"]
            lines.append("-" * 80)
            for r in rows:
                err = f" ⚠ {r['error_message'][:40]}" if r.get("error_message") else ""
                lines.append(
                    f"{r['skill_name']:<25} {r['status']:<8} {r['duration_ms']:>6} "
                    f"{str(r['triggered_by']):<20} {str(r['created_at'])[:16]}{err}"
                )
            return SkillResult(success=True, output="\n".join(lines))
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── error analysis ────────────────────────────────────────────────────────
    async def _error_analysis(self, args: dict, context: SkillContext, limit: int) -> SkillResult:
        """Analyze recent skill failures and suggest fixes using the Brain."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT skill_name, error_message, input_data, created_at
                    FROM skill_runs
                    WHERE status = 'failed' AND error_message IS NOT NULL
                    ORDER BY created_at DESC LIMIT :limit
                """), {"limit": limit})
                rows = result.mappings().all()

            if not rows:
                return SkillResult(success=True, output="No recent skill failures found. All good!")

            error_summary = "\n".join([
                f"  [{r['created_at']}] {r['skill_name']}: {r['error_message'][:100]}"
                for r in rows
            ])

            brain = context.brain
            if brain:
                analysis = await brain.think(
                    f"Analyze these Sanaa AI skill failures and suggest specific fixes:\n\n{error_summary}\n\n"
                    "Be concise. Group similar errors. Suggest concrete remediation steps.",
                    complexity="medium",
                )
                return SkillResult(
                    success=True,
                    output=f"Recent Failures ({len(rows)}):\n{error_summary}\n\nAI Analysis:\n{analysis}",
                    data={"failure_count": len(rows)},
                )

            return SkillResult(
                success=True,
                output=f"Recent Failures ({len(rows)}):\n{error_summary}",
                data={"failure_count": len(rows)},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))
