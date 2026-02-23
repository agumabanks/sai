"""
Skill Manifest Parser — reads YAML skill definitions.

Each skill lives in its own directory with:
  - manifest.yaml: metadata, parameters, permissions
  - handler.py: Python module with execute() function or BaseSkill subclass
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

from core.skills.base import BaseSkill, SkillParameter

logger = logging.getLogger(__name__)


@dataclass
class SkillManifest:
    """Parsed representation of a skill's manifest.yaml."""

    name: str
    description: str
    version: str = "1.0.0"
    permissions: list[str] = field(default_factory=list)
    requires_approval: bool = False
    timeout: int = 30
    tags: list[str] = field(default_factory=list)
    parameters: list[SkillParameter] = field(default_factory=list)
    handler_module: str = "handler"  # Python module name within the skill directory
    path: str = ""                   # Absolute path to the skill directory

    @property
    def handler_path(self) -> str:
        """Full path to the handler Python file."""
        return os.path.join(self.path, f"{self.handler_module}.py")


def parse_manifest(manifest_path: str) -> SkillManifest:
    """Parse a skill manifest YAML file.

    Expected format:
        name: server_health
        version: "1.0.0"
        description: Check server health metrics
        permissions: [shell]
        requires_approval: false
        timeout: 30
        tags: [monitoring, infrastructure]
        handler: handler  # Python module name (default: handler)
        parameters:
          - name: metric
            type: string
            description: Specific metric to check
            required: false
            default: all
            enum: [cpu, ram, disk, services, all]

    Args:
        manifest_path: Path to the manifest.yaml file.

    Returns:
        Parsed SkillManifest.

    Raises:
        ValueError: If manifest is missing required fields.
        FileNotFoundError: If manifest file doesn't exist.
    """
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, "r") as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        raise ValueError(f"Invalid manifest format: {manifest_path}")

    # Required fields
    name = raw.get("name")
    description = raw.get("description")
    if not name:
        raise ValueError(f"Manifest missing 'name': {manifest_path}")
    if not description:
        raise ValueError(f"Manifest missing 'description': {manifest_path}")

    # Parse parameters
    params = []
    for p in raw.get("parameters", []):
        if isinstance(p, dict):
            params.append(
                SkillParameter(
                    name=p["name"],
                    type=p.get("type", "string"),
                    description=p.get("description", ""),
                    required=p.get("required", False),
                    default=p.get("default"),
                    enum=p.get("enum", []),
                )
            )

    skill_dir = os.path.dirname(os.path.abspath(manifest_path))

    return SkillManifest(
        name=name,
        description=description,
        version=raw.get("version", "1.0.0"),
        permissions=raw.get("permissions", []),
        requires_approval=raw.get("requires_approval", False),
        timeout=raw.get("timeout", 30),
        tags=raw.get("tags", []),
        parameters=params,
        handler_module=raw.get("handler", "handler"),
        path=skill_dir,
    )


def discover_manifests(skills_dir: str) -> list[SkillManifest]:
    """Discover all skill manifests in a directory.

    Scans for subdirectories containing a manifest.yaml file.

    Args:
        skills_dir: Root directory containing skill subdirectories.

    Returns:
        List of parsed SkillManifest objects.
    """
    manifests = []

    if not os.path.isdir(skills_dir):
        logger.warning(f"Skills directory not found: {skills_dir}")
        return manifests

    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry)
        manifest_path = os.path.join(skill_path, "manifest.yaml")

        if os.path.isdir(skill_path) and os.path.exists(manifest_path):
            try:
                manifest = parse_manifest(manifest_path)
                manifests.append(manifest)
                logger.info(f"Discovered skill: {manifest.name} v{manifest.version}")
            except Exception as e:
                logger.error(f"Failed to parse manifest {manifest_path}: {e}")

    return manifests
