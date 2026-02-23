"""
Workflow YAML Loader — parses workflow definition files.

Workflow YAML format:
    name: daily_triage
    version: "1.0.0"
    description: Daily system health triage
    args:
      severity:
        type: string
        default: error
    steps:
      - id: health_check
        action: skill
        params:
          skill: server_health
          args:
            metric: all
      - id: notify
        action: notify
        params:
          channel: web
          message: "Health check results: {{ steps.health_check.output }}"
        depends_on: [health_check]
"""

import os
import logging
from typing import Optional

import yaml

from core.workflows.models import WorkflowDefinition, WorkflowStep

logger = logging.getLogger(__name__)


class WorkflowLoader:
    """Discovers and parses YAML workflow definitions."""

    def __init__(self, workflows_dir: str = "/var/www/ai.sanaa.co/backend/workflows"):
        self.workflows_dir = workflows_dir

    def load(self, path: str) -> WorkflowDefinition:
        """Parse a single YAML workflow file.

        Args:
            path: Absolute or relative path to the YAML file.

        Returns:
            Parsed WorkflowDefinition.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If YAML is invalid.
        """
        # Resolve relative paths against workflows_dir
        if not os.path.isabs(path):
            path = os.path.join(self.workflows_dir, path)

        if not os.path.exists(path):
            raise FileNotFoundError(f"Workflow file not found: {path}")

        with open(path, "r") as f:
            raw = yaml.safe_load(f)

        if not raw or not isinstance(raw, dict):
            raise ValueError(f"Invalid workflow YAML: {path}")

        return self._parse_definition(raw, path)

    def discover(self, workflows_dir: str = None) -> list[WorkflowDefinition]:
        """Discover all YAML workflow files in a directory.

        Args:
            workflows_dir: Override directory to scan (defaults to self.workflows_dir).

        Returns:
            List of parsed WorkflowDefinition objects.
        """
        search_dir = workflows_dir or self.workflows_dir
        definitions = []

        if not os.path.isdir(search_dir):
            logger.warning(f"Workflows directory not found: {search_dir}")
            return definitions

        for filename in sorted(os.listdir(search_dir)):
            if filename.endswith((".yaml", ".yml")):
                filepath = os.path.join(search_dir, filename)
                try:
                    definition = self.load(filepath)
                    definitions.append(definition)
                    logger.info(
                        f"Discovered workflow: {definition.name} "
                        f"({len(definition.steps)} steps)"
                    )
                except Exception as e:
                    logger.error(f"Failed to parse workflow {filepath}: {e}")

        return definitions

    def _parse_definition(self, raw: dict, path: str) -> WorkflowDefinition:
        """Parse a raw YAML dict into a WorkflowDefinition."""
        name = raw.get("name")
        if not name:
            raise ValueError(f"Workflow missing 'name': {path}")

        steps = []
        for raw_step in raw.get("steps", []):
            step = self._parse_step(raw_step)
            steps.append(step)

        return WorkflowDefinition(
            name=name,
            description=raw.get("description", ""),
            steps=steps,
            args=raw.get("args", {}),
            env=raw.get("env", {}),
            triggers=raw.get("triggers", []),
            version=raw.get("version", "1.0.0"),
            path=path,
        )

    def _parse_step(self, raw: dict) -> WorkflowStep:
        """Parse a raw YAML step dict into a WorkflowStep."""
        if not raw.get("id"):
            raise ValueError(f"Workflow step missing 'id': {raw}")

        return WorkflowStep(
            id=raw["id"],
            action=raw.get("action", "skill"),
            params=raw.get("params", {}),
            approval=raw.get("approval", False),
            condition=raw.get("condition"),
            timeout=raw.get("timeout", 60),
            on_failure=raw.get("on_failure", "abort"),
            max_retries=raw.get("max_retries", 1),
            depends_on=raw.get("depends_on", []),
            description=raw.get("description", ""),
        )
