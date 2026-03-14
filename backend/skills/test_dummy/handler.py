"""Test Dummy Skill — Used for testing the skill execution pipeline."""

from core.skills.base import BaseSkill, SkillResult


class TestDummySkill(BaseSkill):
    """A minimal test skill that echoes input and validates the execution pipeline."""

    async def execute(self, args: dict, context=None) -> SkillResult:
        action = args.get("action", "echo")

        if action == "echo":
            message = args.get("message", "Test dummy skill executed successfully")
            return SkillResult(success=True, output=message, data={"action": "echo", "echoed": message})

        if action == "fail":
            return SkillResult(success=False, output="", error="Intentional test failure")

        return SkillResult(success=True, output=f"Unknown action: {action}", data={"action": action})
