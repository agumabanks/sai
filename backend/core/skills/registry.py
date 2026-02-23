"""
Skill Registry — runtime registry used by the Brain to look up and invoke skills.

The registry:
  - Holds all loaded skills in memory
  - Exports tool definitions for the LLM system prompt
  - Handles skill execution with audit logging, timeouts, and error handling
  - Records skill runs to the database
"""

import time
import asyncio
import logging
from typing import Optional

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import SkillRun, AuditLog

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Runtime registry of loaded skills."""

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill in the registry."""
        if skill.name in self._skills:
            logger.warning(f"Overwriting existing skill: {skill.name}")
        self._skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")

    def unregister(self, name: str) -> None:
        """Remove a skill from the registry."""
        self._skills.pop(name, None)

    def get(self, name: str) -> Optional[BaseSkill]:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        """List all registered skills with metadata."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "permissions": s.permissions,
                "requires_approval": s.requires_approval,
                "tags": s.tags,
                "parameter_count": len(s.parameters),
            }
            for s in self._skills.values()
        ]

    def list_tools(self) -> list[dict]:
        """Export all skills as LLM tool definitions (OpenAI function calling format)."""
        return [s.to_tool_definition() for s in self._skills.values()]

    async def execute(
        self,
        name: str,
        args: dict,
        context: SkillContext,
    ) -> SkillResult:
        """Execute a skill by name with full lifecycle management.

        Steps:
          1. Validate skill exists
          2. Validate arguments
          3. Apply default values
          4. Check approval requirements
          5. Execute with timeout
          6. Record to database
          7. Audit log

        Args:
            name: Skill name to execute.
            args: Arguments to pass to the skill.
            context: Runtime context.

        Returns:
            SkillResult with execution outcome.
        """
        skill = self.get(name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"Skill not found: {name}",
            )

        # Validate arguments
        is_valid, error_msg = skill.validate_args(args)
        if not is_valid:
            return SkillResult(success=False, error=error_msg)

        # Apply defaults
        args = skill.apply_defaults(args)

        # Check approval
        if skill.requires_approval:
            return SkillResult(
                success=True,
                needs_approval=True,
                approval_prompt=(
                    f"Skill '{name}' requires approval before execution.\n"
                    f"Arguments: {args}"
                ),
            )

        # Execute with timeout
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                skill.execute(args, context),
                timeout=skill.timeout,
            )
            result.execution_time_ms = int((time.monotonic() - start) * 1000)

        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - start) * 1000)
            result = SkillResult(
                success=False,
                error=f"Skill '{name}' timed out after {skill.timeout}s",
                execution_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error(f"Skill '{name}' execution failed: {e}", exc_info=True)
            result = SkillResult(
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )

        # Record to database
        try:
            await SkillRun.create(
                skill_name=name,
                input_data=args,
                output_data={
                    "output": result.output[:2000] if result.output else "",
                    "data": result.data,
                },
                status="success" if result.success else "failed",
                error_message=result.error if result.error else None,
                duration_ms=result.execution_time_ms,
                triggered_by=f"{context.channel}:{context.sender_id}",
            )
        except Exception as e:
            logger.error(f"Failed to record skill run: {e}")

        # Audit log
        try:
            await AuditLog.log(
                actor=f"{context.channel}:{context.sender_id}",
                action=f"skill.execute.{name}",
                resource=str(args)[:200],
                details={
                    "success": result.success,
                    "execution_time_ms": result.execution_time_ms,
                },
                success=result.success,
            )
        except Exception as e:
            logger.error(f"Failed to audit skill execution: {e}")

        return result

    @property
    def count(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __repr__(self) -> str:
        return f"<SkillRegistry: {self.count} skills>"
