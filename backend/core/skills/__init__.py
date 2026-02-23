"""
Sanaa AI — Skill/Plugin System

Dual-layered skill architecture:
  - Skills: YAML-defined tool descriptors for LLM tool calls
  - Plugins: Python classes for deep system integrations

Inspired by OpenClaw's extension model and ClawHub's schema validation.
"""

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.skills.registry import SkillRegistry
from core.skills.loader import SkillLoader
from core.skills.scanner import SkillScanner

__all__ = [
    "BaseSkill",
    "SkillContext",
    "SkillResult",
    "SkillRegistry",
    "SkillLoader",
    "SkillScanner",
]
