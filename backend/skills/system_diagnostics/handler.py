import asyncio
import logging
import json
import re
from sqlalchemy import text
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# SQL patterns that indicate injection attempts (case-insensitive)
_DANGEROUS_SQL_PATTERNS = re.compile(
    r"""
    ;                         # statement terminator (multiple statements)
    | --                      # SQL line comment
    | /\*                     # SQL block comment
    | \b(DROP|ALTER|CREATE|TRUNCATE|INSERT|UPDATE|DELETE|EXEC|EXECUTE|
         GRANT|REVOKE|UNION\s+ALL|INTO\s+OUTFILE|INTO\s+DUMPFILE|
         LOAD_FILE|BENCHMARK|SLEEP|WAITFOR)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Allowed tables for diagnostic SELECT queries
_ALLOWED_TABLES = {
    "alerts", "system_knowledge", "commands", "logs", "audit_log",
    "workflow_runs", "skill_runs", "memories", "sessions",
}


def _validate_diagnostic_query(query: str) -> str:
    """Validate and sanitize a diagnostic SQL query.

    Only allows simple SELECT statements without injection patterns.

    Args:
        query: The SQL query to validate.

    Returns:
        Error message if invalid, empty string if valid.
    """
    stripped = query.strip()

    # Must start with SELECT
    if not stripped.lower().startswith("select"):
        return "Only SELECT queries are allowed for safety."

    # Check for dangerous SQL patterns
    if _DANGEROUS_SQL_PATTERNS.search(stripped):
        return (
            "Query contains forbidden SQL patterns. "
            "Semicolons, comments (--), and DML/DDL statements "
            "(DROP, ALTER, INSERT, UPDATE, DELETE, UNION, etc.) are not allowed."
        )

    return ""


class SystemDiagnosticsSkill(BaseSkill):
    name = "system_diagnostics"
    
    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")
        
        if action == "db_query":
            return await self._run_db_query(args.get("query"), args.get("params"))
        elif action == "provider_status":
            return await self._get_provider_status()
        elif action == "alert_history":
            return await self._get_alert_history(args.get("limit", 10))
        elif action == "config_check":
            return await self._get_config_check()
            
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _run_db_query(self, query: str, params: dict = None) -> SkillResult:
        """Execute a diagnostic SELECT query using parameterized queries.

        Security: Validates the query for dangerous patterns, and uses
        SQLAlchemy text() with bind parameters to prevent SQL injection.
        """
        if not query:
            return SkillResult(success=False, error="query is required for db_query")

        # Validate the query structure
        error = _validate_diagnostic_query(query)
        if error:
            logger.warning(f"SQL injection attempt blocked: {query[:200]!r}")
            return SkillResult(success=False, error=error)

        try:
            async with AsyncSessionLocal() as session:
                # Use parameterized query via SQLAlchemy text() with bind params
                stmt = text(query)
                if params and isinstance(params, dict):
                    res = await session.execute(stmt, params)
                else:
                    res = await session.execute(stmt)
                rows = res.mappings().all()
            
            output = json.dumps([dict(r) for r in rows], indent=2, default=str)
            return SkillResult(success=True, output=output[:4000], data={"count": len(rows)})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_provider_status(self) -> SkillResult:
        try:
            from core.brain.engine import Brain
            brain = Brain()
            active = brain.get_current_provider()
            
            # Check failure counts in SystemKnowledge
            sql = text("SELECT key, value FROM system_knowledge WHERE key LIKE 'provider_fail_count.%'")
            async with AsyncSessionLocal() as session:
                res = await session.execute(sql)
                rows = res.mappings().all()
            
            output = f"Active Provider: {active}\n\nFailure Counts:\n"
            for r in rows:
                output += f"- {r['key']}: {r['value']}\n"
            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_alert_history(self, limit: int = 10) -> SkillResult:
        try:
            # Use parameterized query for the limit value
            sql = text("SELECT severity, message, created_at FROM alerts ORDER BY created_at DESC LIMIT :limit")
            async with AsyncSessionLocal() as session:
                res = await session.execute(sql, {"limit": min(int(limit), 100)})
                rows = res.mappings().all()
                
            output = "Recent Alerts:\n"
            for r in rows:
                output += f"[{r['severity'].upper()}] {r['message']} ({r['created_at']})\n"
            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_config_check(self) -> SkillResult:
        try:
            from core.config import get_settings
            settings = get_settings()
            # Mask sensitive values
            output = (
                f"SMTP_HOST: {settings.smtp_host}\n"
                f"SMTP_PORT: {settings.smtp_port}\n"
                f"SMTP_USER: {settings.smtp_user}\n"
                f"SMTP_PASS: ********\n"
                f"BRAIN_PROVIDER: {settings.brain_provider}\n"
                f"OLLAMA_BASE_URL: {settings.ollama_base_url}\n"
            )
            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
