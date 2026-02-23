"""
Skill Loader — discovers, validates, and dynamically loads skills.

Workflow:
  1. Discover manifest.yaml files in the skills directory
  2. Parse each manifest into a SkillManifest
  3. Run SkillScanner on the handler.py source code
  4. Dynamically import the handler module
  5. Instantiate the BaseSkill subclass or wrap a plain execute() function
"""

import os
import sys
import logging
import importlib.util
from typing import Optional

from core.skills.base import BaseSkill, SkillContext, SkillResult, SkillParameter
from core.skills.manifest import SkillManifest, parse_manifest, discover_manifests
from core.skills.scanner import SkillScanner

logger = logging.getLogger(__name__)


class _ManifestWrappedSkill(BaseSkill):
    """Wraps a plain execute() function as a BaseSkill.

    Used when a skill handler module exports a standalone execute()
    function instead of a BaseSkill subclass.
    """

    def __init__(self, manifest: SkillManifest, execute_fn):
        self.name = manifest.name
        self.description = manifest.description
        self.version = manifest.version
        self.permissions = manifest.permissions
        self.requires_approval = manifest.requires_approval
        self.timeout = manifest.timeout
        self.tags = manifest.tags
        self.parameters = manifest.parameters
        self._execute_fn = execute_fn

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        return await self._execute_fn(args, context)


class SkillLoader:
    """Discovers and loads skills from the filesystem."""

    def __init__(
        self,
        skills_dir: str = "/var/www/ai.sanaa.co/backend/skills",
        scanner: Optional[SkillScanner] = None,
    ):
        self.skills_dir = skills_dir
        self.scanner = scanner or SkillScanner()
        self._loaded: dict[str, BaseSkill] = {}

    async def discover(self) -> list[SkillManifest]:
        """Scan skills directory for manifest.yaml files.

        Returns:
            List of parsed manifests.
        """
        return discover_manifests(self.skills_dir)

    async def load(self, manifest: SkillManifest) -> Optional[BaseSkill]:
        """Load a single skill from its manifest.

        Steps:
          1. Verify handler.py exists
          2. Run security scan on handler source
          3. Dynamically import the module
          4. Extract BaseSkill subclass or execute() function
          5. Return instantiated skill

        Args:
            manifest: Parsed SkillManifest.

        Returns:
            Loaded BaseSkill instance, or None if loading failed.
        """
        handler_path = manifest.handler_path

        # Check handler exists
        if not os.path.exists(handler_path):
            logger.error(f"Handler not found for skill '{manifest.name}': {handler_path}")
            return None

        # Security scan
        scan_result = self.scanner.scan_file(handler_path)
        if not scan_result.passed:
            critical = [f for f in scan_result.findings if f.severity == "critical"]
            logger.error(
                f"Skill '{manifest.name}' REJECTED by security scanner: "
                f"{len(critical)} critical finding(s)"
            )
            for finding in critical:
                logger.error(f"  [{finding.rule_id}] L{finding.line}: {finding.message}")
            return None

        if scan_result.findings:
            logger.warning(
                f"Skill '{manifest.name}' has {len(scan_result.findings)} warning(s)"
            )

        # Dynamic import
        try:
            module_name = f"skills.{manifest.name}.{manifest.handler_module}"
            spec = importlib.util.spec_from_file_location(module_name, handler_path)
            if spec is None or spec.loader is None:
                logger.error(f"Cannot create module spec for: {handler_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        except Exception as e:
            logger.error(f"Failed to import skill '{manifest.name}': {e}")
            return None

        # Extract skill class or function
        skill = self._extract_skill(module, manifest)
        if skill:
            self._loaded[manifest.name] = skill
            logger.info(f"Loaded skill: {manifest.name} v{manifest.version}")

        return skill

    def _extract_skill(self, module, manifest: SkillManifest) -> Optional[BaseSkill]:
        """Extract a BaseSkill from an imported module.

        Supports two patterns:
          1. Module defines a BaseSkill subclass → instantiate it
          2. Module defines an async execute(args, context) function → wrap it
        """
        # Pattern 1: Look for a BaseSkill subclass
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSkill)
                and attr is not BaseSkill
            ):
                try:
                    instance = attr()
                    # Override with manifest values if not set on class
                    if not instance.name:
                        instance.name = manifest.name
                    if not instance.description:
                        instance.description = manifest.description
                    if not instance.parameters:
                        instance.parameters = manifest.parameters
                    return instance
                except Exception as e:
                    logger.error(f"Failed to instantiate {attr_name}: {e}")
                    return None

        # Pattern 2: Look for a standalone execute() function
        execute_fn = getattr(module, "execute", None)
        if execute_fn and callable(execute_fn):
            return _ManifestWrappedSkill(manifest, execute_fn)

        logger.error(
            f"Skill '{manifest.name}' has no BaseSkill subclass "
            f"and no execute() function in {manifest.handler_module}.py"
        )
        return None

    async def load_all(self) -> dict[str, BaseSkill]:
        """Discover and load all valid skills.

        Returns:
            Dict mapping skill names to loaded BaseSkill instances.
        """
        manifests = await self.discover()
        loaded = {}

        for manifest in manifests:
            skill = await self.load(manifest)
            if skill:
                loaded[skill.name] = skill

        logger.info(
            f"Skill loading complete: {len(loaded)}/{len(manifests)} skills loaded"
        )
        return loaded
