"""
Workflow Models — dataclasses for workflow definitions, steps, results, and state.

Based on Lobster's WorkflowFile/WorkflowStep/WorkflowStepResult pattern,
adapted for Python + Celery runtime.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
from enum import Enum


class StepAction(str, Enum):
    """Types of actions a workflow step can perform."""
    SKILL = "skill"       # Execute a registered skill
    SHELL = "shell"       # Run a shell command (sandboxed)
    LLM = "llm"           # Send a prompt to the Brain
    NOTIFY = "notify"     # Send a notification to a channel
    WAIT = "wait"         # Pause for a duration or human input
    HTTP = "http"         # Make an HTTP request


class StepFailurePolicy(str, Enum):
    """What to do when a step fails."""
    ABORT = "abort"       # Stop the workflow
    SKIP = "skip"         # Mark as skipped, continue
    RETRY = "retry"       # Retry the step (up to max_retries)


class WorkflowStatus(str, Enum):
    """Status of a workflow run."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """A single step in a workflow definition.

    Attributes:
        id: Unique step identifier within the workflow.
        action: Type of action (skill, shell, llm, notify, wait, http).
        params: Action-specific parameters.
        approval: Whether this step requires human approval before execution.
        condition: Expression to evaluate — step is skipped if false.
        timeout: Max execution time in seconds.
        on_failure: What to do if the step fails.
        max_retries: Number of retries if on_failure is "retry".
        depends_on: List of step IDs that must complete before this step.
        description: Human-readable description of what this step does.
    """
    id: str
    action: str = "skill"
    params: dict = field(default_factory=dict)
    approval: bool = False
    condition: Optional[str] = None
    timeout: int = 60
    on_failure: str = "abort"
    max_retries: int = 1
    depends_on: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class StepResult:
    """Result from executing a single workflow step."""
    step_id: str
    success: bool
    output: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)
    skipped: bool = False
    approved: Optional[bool] = None
    duration_ms: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class WorkflowDefinition:
    """A complete workflow definition parsed from YAML.

    Attributes:
        name: Unique workflow name (e.g. "daily_triage").
        description: Human-readable description.
        steps: Ordered list of workflow steps.
        args: Schema definition for workflow arguments.
        env: Environment variables to set for all steps.
        triggers: When this workflow should auto-run (cron, event, etc.).
        version: Workflow version string.
    """
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    args: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    triggers: list[dict] = field(default_factory=list)
    version: str = "1.0.0"
    path: str = ""  # Path to source YAML file


@dataclass
class WorkflowState:
    """Runtime state of a workflow execution.

    Persisted to the workflow_runs DB table for pause/resume support.
    """
    run_id: int = 0
    workflow_name: str = ""
    status: str = "pending"
    current_step: int = 0
    step_results: dict[str, StepResult] = field(default_factory=dict)
    resume_token: Optional[str] = None
    input_args: dict = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    started_by: str = ""
    channel: str = "web"
    output: list = field(default_factory=list)

    def to_db_dict(self) -> dict:
        """Serialize for database storage (JSON-compatible)."""
        results_data = {}
        for step_id, result in self.step_results.items():
            results_data[step_id] = {
                "success": result.success,
                "output": result.output[:1000],
                "error": result.error[:500] if result.error else "",
                "skipped": result.skipped,
                "duration_ms": result.duration_ms,
            }
        return {
            "step_results": results_data,
            "current_step": self.current_step,
        }
