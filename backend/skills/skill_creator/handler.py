"""Skill Creator — Sanaa AI writes its own new skills dynamically, then hot-reloads them."""
import os
import logging
import json
import re
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.brain import Brain

logger = logging.getLogger(__name__)
SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..")


class SkillCreatorSkill(BaseSkill):
    name = "skill_creator"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "create")

        if action == "create":
            return await self._create(args, context)
        elif action == "list_skills":
            return self._list_skills(context)
        elif action == "hot_reload":
            return await self._hot_reload(args, context)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ── create ──────────────────────────────────────────────────────────────
    async def _create(self, args: dict, context: SkillContext) -> SkillResult:
        skill_name = args.get("skill_name", "").strip().replace("-", "_").replace(" ", "_").lower()
        description = args.get("skill_description", "")

        if not skill_name or not description:
            return SkillResult(success=False, error="skill_name and skill_description are required.")

        skill_path = os.path.join(SKILLS_DIR, skill_name)
        if os.path.exists(skill_path):
            return SkillResult(success=False, error=f"Skill '{skill_name}' already exists at {skill_path}")

        brain = Brain()
        class_name = "".join(w.capitalize() for w in skill_name.split("_")) + "Skill"

        prompt = f"""You are a Python skill generator for the Sanaa AI framework.
Generate a complete, working skill. The framework uses BaseSkill with an async execute method.

Skill Name: {skill_name}
Description: {description}

Respond ONLY with a JSON object (no markdown, no extra text):
{{
  "manifest_yaml": "name: {skill_name}\\ndescription: ...\\nversion: 1.0.0\\ncategory: ...\\ntags: [...]\\nparameters:\\n  action:\\n    type: string\\n    required: true",
  "handler_py": "import logging\\nfrom core.skills.base import BaseSkill, SkillContext, SkillResult\\n\\nlogger = logging.getLogger(__name__)\\n\\nclass {class_name}(BaseSkill):\\n    name = \\"{skill_name}\\"\\n\\n    async def execute(self, args: dict, context: SkillContext) -> SkillResult:\\n        ..."
}}"""

        try:
            response = await brain.think(prompt, complexity="high")
            response = re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()
            match = re.search(r'\{[\s\S]*\}', response)
            if not match:
                return SkillResult(success=False, error="Brain did not return valid JSON for skill generation.")

            data = json.loads(match.group())
            manifest = data.get("manifest_yaml", "")
            handler = data.get("handler_py", "")

            if not manifest or not handler:
                return SkillResult(success=False, error="Generated skill is incomplete.")

            os.makedirs(skill_path, exist_ok=True)
            with open(os.path.join(skill_path, "manifest.yaml"), "w") as f:
                f.write(manifest)
            with open(os.path.join(skill_path, "handler.py"), "w") as f:
                f.write(handler)

            # Auto hot-reload the new skill into the running registry
            reload_result = await self._hot_reload({"skill_name": skill_name}, context)
            reload_note = (
                f"\nHot-reloaded successfully — skill is live immediately."
                if reload_result.success
                else "\nRestart service to activate (hot-reload unavailable)."
            )

            return SkillResult(
                success=True,
                output=f"Skill '{skill_name}' created at {skill_path}.{reload_note}",
                data={"path": skill_path, "reloaded": reload_result.success},
            )
        except Exception as e:
            logger.error(f"Skill creation failed: {e}")
            return SkillResult(success=False, error=str(e))

    # ── list_skills ──────────────────────────────────────────────────────────
    def _list_skills(self, context: SkillContext) -> SkillResult:
        brain = context.brain
        if brain and brain._skill_registry:
            skills = brain.skill_registry.list_skills()
            if not skills:
                return SkillResult(success=True, output="No skills registered.")
            lines = [f"{'NAME':<25} {'VER':<8} TAGS"]
            lines.append("-" * 60)
            for s in sorted(skills, key=lambda x: x["name"]):
                tags = ", ".join(s.get("tags", []))[:30]
                lines.append(f"{s['name']:<25} {s['version']:<8} {tags}")
            return SkillResult(success=True, output="\n".join(lines), data={"count": len(skills)})

        # Fallback: filesystem scan
        skill_dirs = [
            d for d in os.listdir(SKILLS_DIR)
            if os.path.isdir(os.path.join(SKILLS_DIR, d)) and not d.startswith("_")
        ]
        return SkillResult(
            success=True,
            output=f"Skills on disk ({len(skill_dirs)}):\n" + "\n".join(sorted(skill_dirs)),
            data={"count": len(skill_dirs)},
        )

    # ── hot_reload ───────────────────────────────────────────────────────────
    async def _hot_reload(self, args: dict, context: SkillContext) -> SkillResult:
        """Dynamically import and register a skill without restarting the service."""
        skill_name = args.get("skill_name", "").strip()
        if not skill_name:
            return SkillResult(success=False, error="'skill_name' is required for hot_reload.")

        skill_path = os.path.join(SKILLS_DIR, skill_name)
        manifest_path = os.path.join(skill_path, "manifest.yaml")
        handler_path = os.path.join(skill_path, "handler.py")

        if not os.path.exists(manifest_path) or not os.path.exists(handler_path):
            return SkillResult(success=False,
                               error=f"Skill '{skill_name}' not found at {skill_path}")

        try:
            from core.skills.loader import SkillLoader
            from core.skills.manifest import parse_manifest

            manifest = parse_manifest(manifest_path)
            if not manifest:
                return SkillResult(success=False, error=f"Cannot parse manifest for '{skill_name}'.")

            loader = SkillLoader()
            skill = await loader.load(manifest)
            if not skill:
                return SkillResult(success=False,
                                   error=f"Loader rejected '{skill_name}' — check security scanner logs.")

            brain = context.brain
            if brain and brain._skill_registry:
                brain.skill_registry.register(skill)
                return SkillResult(
                    success=True,
                    output=f"'{skill_name}' v{skill.version} hot-reloaded into live registry.",
                    data={"name": skill_name, "version": skill.version},
                )

            return SkillResult(
                success=True,
                output=f"'{skill_name}' loaded but Brain registry unavailable. Restart to activate.",
            )
        except Exception as e:
            logger.error(f"Hot reload failed for '{skill_name}': {e}")
            return SkillResult(success=False, error=str(e))
