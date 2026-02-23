"""
BaseSkill — abstract base class for all Sanaa skills.

Each skill defines:
  - A name and description (used for LLM tool definitions)
  - Parameter schema (what the LLM can pass)
  - Permissions required (shell, network, filesystem)
  - An execute() method that performs the action

Inspired by OpenClaw's tool interface and ClawHub's schema validation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class SkillContext:
    """Runtime context passed to every skill execution."""

    session_id: str = ""
    channel: str = "web"
    sender_id: str = ""
    sender_name: str = ""
    brain: Any = None          # Reference to Brain instance
    memory: Any = None         # Reference to MemoryManager
    sandbox: Any = None        # Reference to ExecutionSandbox


@dataclass
class SkillResult:
    """Result returned from skill execution."""

    success: bool
    output: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)      # Structured data for programmatic use
    artifacts: list = field(default_factory=list)  # Files/media produced
    needs_approval: bool = False                   # Halt workflow, await human approval
    approval_prompt: str = ""                      # What to ask the human
    execution_time_ms: int = 0


@dataclass
class SkillParameter:
    """Describes a single parameter for a skill."""

    name: str
    type: str = "string"            # string, integer, number, boolean, array, object
    description: str = ""
    required: bool = False
    default: Any = None
    enum: list = field(default_factory=list)

    def to_json_schema(self) -> dict:
        """Convert to JSON Schema format for LLM tool definitions."""
        schema = {"type": self.type, "description": self.description}
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


class BaseSkill(ABC):
    """Abstract base class for all Sanaa skills.

    Subclasses must implement:
      - execute(args, context) -> SkillResult

    Class attributes define the skill metadata:
      - name: unique identifier (e.g. "server_health")
      - description: human-readable description for LLM
      - version: semver string
      - permissions: list of required permissions
      - parameters: list of SkillParameter
      - requires_approval: whether to halt before execution
      - timeout: max execution time in seconds
    """

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    permissions: list[str] = []          # e.g. ["shell", "network", "filesystem"]
    parameters: list[SkillParameter] = []
    requires_approval: bool = False
    timeout: int = 30                    # seconds
    tags: list[str] = []                 # for categorization

    @abstractmethod
    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        """Execute the skill with the given arguments and context.

        Args:
            args: Validated parameters matching the skill's parameter schema.
            context: Runtime context with session, channel, and system references.

        Returns:
            SkillResult with success status, output text, and optional structured data.
        """
        ...

    def to_tool_definition(self) -> dict:
        """Export as an OpenAI-compatible function/tool definition.

        This is what gets injected into the LLM system prompt so it knows
        which tools are available and how to call them.
        """
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def validate_args(self, args: dict) -> tuple[bool, str]:
        """Validate arguments against the parameter schema.

        Returns:
            Tuple of (is_valid, error_message).
        """
        for param in self.parameters:
            if param.required and param.name not in args:
                return False, f"Missing required parameter: {param.name}"

            if param.name in args and param.enum:
                if args[param.name] not in param.enum:
                    return False, (
                        f"Invalid value for {param.name}: {args[param.name]}. "
                        f"Must be one of: {param.enum}"
                    )

        return True, ""

    def apply_defaults(self, args: dict) -> dict:
        """Apply default values for missing optional parameters."""
        result = dict(args)
        for param in self.parameters:
            if param.name not in result and param.default is not None:
                result[param.name] = param.default
        return result

    def __repr__(self) -> str:
        return f"<Skill:{self.name} v{self.version}>"
