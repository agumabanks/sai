"""
Workflow Runtime — executes workflows step-by-step.

Features:
  - Step-by-step execution with condition evaluation
  - Approval gates (pause and resume)
  - Template resolution for step references ({{ steps.health_check.output }})
  - State persistence to workflow_runs DB table
  - Timeout management per step
  - Error handling with configurable failure policies (abort, skip, retry)
  - Resume from pause point via resume tokens

Inspired by Lobster's runWorkflowFile() with approval gates + resume tokens.
"""

import re
import time
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from core.workflows.models import (
    WorkflowDefinition,
    WorkflowStep,
    StepResult,
    WorkflowState,
)
from core.database import WorkflowRun, AuditLog

logger = logging.getLogger(__name__)


class WorkflowRuntime:
    """Execute Sanaa workflows step-by-step with full lifecycle management."""

    def __init__(self, skill_registry=None, brain=None, sandbox=None):
        """
        Args:
            skill_registry: SkillRegistry instance for executing skill steps.
            brain: Brain instance for LLM steps.
            sandbox: ExecutionSandbox for shell steps.
        """
        self.skill_registry = skill_registry
        self.brain = brain
        self.sandbox = sandbox
        self._active_runs: dict[int, WorkflowState] = {}

    async def start(
        self,
        workflow: WorkflowDefinition,
        args: dict = None,
        started_by: str = "system",
        channel: str = "web",
    ) -> int:
        """Start a new workflow execution.

        Args:
            workflow: Parsed workflow definition.
            args: Arguments to pass to the workflow.
            started_by: Who initiated the run.
            channel: Source channel.

        Returns:
            Run ID (integer from the database).
        """
        args = args or {}

        # Apply arg defaults from workflow definition
        resolved_args = {}
        for name, schema in workflow.args.items():
            if isinstance(schema, dict):
                resolved_args[name] = args.get(name, schema.get("default"))
            else:
                resolved_args[name] = args.get(name, schema)
        resolved_args.update(args)

        # Create DB record
        run = await WorkflowRun.create(
            workflow_name=workflow.name,
            started_by=started_by,
            channel=channel,
            status="running",
            current_step=0,
            state={},
            input_args=resolved_args,
        )

        state = WorkflowState(
            run_id=run.id,
            workflow_name=workflow.name,
            status="running",
            current_step=0,
            input_args=resolved_args,
            started_at=datetime.now(timezone.utc),
            started_by=started_by,
            channel=channel,
        )
        self._active_runs[run.id] = state

        logger.info(
            f"Starting workflow '{workflow.name}' (run_id={run.id}) "
            f"with {len(workflow.steps)} steps"
        )
        try:
            await AuditLog.log(
                actor=started_by,
                action="workflow.start",
                resource=workflow.name,
                details={"run_id": run.id, "channel": channel},
                success=True,
            )
        except Exception:
            pass

        # Execute steps sequentially
        try:
            await self._execute_steps(workflow, state)
        except Exception as e:
            logger.error(f"Workflow '{workflow.name}' failed: {e}", exc_info=True)
            state.status = "failed"
            await self._persist_state(state)

        return run.id

    async def _execute_steps(
        self,
        workflow: WorkflowDefinition,
        state: WorkflowState,
    ):
        """Execute workflow steps starting from current_step."""
        for i in range(state.current_step, len(workflow.steps)):
            step = workflow.steps[i]
            state.current_step = i

            # Check condition
            if step.condition and not self._evaluate_condition(step.condition, state):
                result = StepResult(
                    step_id=step.id,
                    success=True,
                    skipped=True,
                    output="Condition not met — skipped",
                )
                state.step_results[step.id] = result
                continue

            # Check dependencies
            if step.depends_on:
                deps_met = all(
                    dep_id in state.step_results and state.step_results[dep_id].success
                    for dep_id in step.depends_on
                )
                if not deps_met:
                    result = StepResult(
                        step_id=step.id,
                        success=False,
                        skipped=True,
                        output="Dependencies not met — skipped",
                    )
                    state.step_results[step.id] = result
                    continue

            # Check approval gate
            if step.approval:
                state.status = "paused"
                state.resume_token = str(uuid.uuid4())
                resolved_params = self._resolve_templates(step.params, state)
                approval_prompt = (
                    resolved_params.get("message")
                    or step.description
                    or f"Approval required for workflow step '{step.id}'"
                )
                state.output.append(
                    {
                        "type": "approval_request",
                        "step_id": step.id,
                        "workflow": state.workflow_name,
                        "prompt": approval_prompt,
                        "channel": resolved_params.get("channel", state.channel),
                        "resume_token": state.resume_token,
                    }
                )
                await self._persist_state(state)
                logger.info(
                    f"Workflow paused at step '{step.id}' — "
                    f"approval required (token={state.resume_token})"
                )
                try:
                    await AuditLog.log(
                        actor=state.started_by,
                        action="workflow.pause",
                        resource=state.workflow_name,
                        details={"run_id": state.run_id, "step_id": step.id},
                        success=True,
                    )
                except Exception:
                    pass
                return  # Halt execution — will resume via resume()

            # Execute this step
            result = await self._execute_single_step(step, state)
            state.step_results[step.id] = result

            if not result.success and step.on_failure == "abort":
                state.status = "failed"
                await self._persist_state(state)
                logger.error(
                    f"Workflow '{state.workflow_name}' aborted at step '{step.id}': "
                    f"{result.error}"
                )
                return

            # Persist progress every few steps
            if i % 3 == 0:
                await self._persist_state(state)

        # All steps complete
        state.status = "completed"
        state.completed_at = datetime.now(timezone.utc)
        await self._persist_state(state)
        logger.info(
            f"Workflow '{state.workflow_name}' completed (run_id={state.run_id})"
        )

    async def _execute_single_step(
        self,
        step: WorkflowStep,
        state: WorkflowState,
    ) -> StepResult:
        """Execute a single workflow step based on its action type."""
        start = time.monotonic()
        started_at = datetime.now(timezone.utc)
        resolved_params = self._resolve_templates(step.params, state)

        try:
            result = await asyncio.wait_for(
                self._dispatch_step(step.action, resolved_params, state),
                timeout=step.timeout,
            )
            result.step_id = step.id
            result.duration_ms = int((time.monotonic() - start) * 1000)
            result.started_at = started_at
            result.completed_at = datetime.now(timezone.utc)
            return result

        except asyncio.TimeoutError:
            return StepResult(
                step_id=step.id,
                success=False,
                error=f"Step '{step.id}' timed out after {step.timeout}s",
                duration_ms=int((time.monotonic() - start) * 1000),
                started_at=started_at,
            )
        except Exception as e:
            return StepResult(
                step_id=step.id,
                success=False,
                error=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
                started_at=started_at,
            )

    async def _dispatch_step(
        self,
        action: str,
        params: dict,
        state: WorkflowState,
    ) -> StepResult:
        """Dispatch a step to the appropriate executor."""
        if action == "skill":
            return await self._run_skill_step(params, state)
        elif action == "shell":
            return await self._run_shell_step(params)
        elif action == "llm":
            return await self._run_llm_step(params, state)
        elif action == "notify":
            return await self._run_notify_step(params, state)
        elif action == "wait":
            return await self._run_wait_step(params)
        elif action == "http":
            return await self._run_http_step(params)
        else:
            return StepResult(
                step_id="",
                success=False,
                error=f"Unknown action type: {action}",
            )

    # ─── Step executors ─────────────────────────────────────

    async def _run_skill_step(self, params: dict, state: WorkflowState) -> StepResult:
        """Execute a registered skill."""
        if not self.skill_registry:
            return StepResult(step_id="", success=False, error="No skill registry")

        skill_name = params.get("skill", "")
        skill_args = params.get("args", {})

        from core.skills.base import SkillContext
        context = SkillContext(
            session_id=str(state.run_id),
            channel=state.channel,
            sender_id=state.started_by,
            brain=self.brain,
        )

        if self.brain:
            exec_result = await self.brain.execute_skill(
                name=skill_name,
                args=skill_args,
                session_id=str(state.run_id),
                channel=state.channel,
                sender_id=state.started_by,
                execution_mode="workflow",
            )
            return StepResult(
                step_id="",
                success=exec_result.get("success", False),
                output=exec_result.get("output", ""),
                error=exec_result.get("error", ""),
                data=exec_result.get("data", {}),
            )

        result = await self.skill_registry.execute(skill_name, skill_args, context)
        return StepResult(
            step_id="",
            success=result.success,
            output=result.output,
            error=result.error,
            data=result.data,
        )

    async def _run_shell_step(self, params: dict) -> StepResult:
        """Execute a shell command (sandboxed)."""
        command = params.get("command", "")
        if not command:
            return StepResult(step_id="", success=False, error="No command specified")

        if self.sandbox:
            output = await self.sandbox.execute(command)
            return StepResult(
                step_id="",
                success=True,
                output=str(output)[:2000],
            )

        # Fallback: direct execution (limited safety)
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        return StepResult(
            step_id="",
            success=proc.returncode == 0,
            output=stdout.decode()[-2000:] if stdout else "",
            error=stderr.decode()[-1000:] if stderr else "",
        )

    async def _run_llm_step(self, params: dict, state: WorkflowState) -> StepResult:
        """Send a prompt to the Brain for LLM processing."""
        if not self.brain:
            return StepResult(step_id="", success=False, error="No brain instance")

        prompt = params.get("prompt", "")
        complexity = params.get("complexity", "auto")

        response = await self.brain.think(
            prompt, complexity=complexity, session_id=str(state.run_id)
        )
        return StepResult(step_id="", success=True, output=response)

    async def _run_notify_step(self, params: dict, state: WorkflowState) -> StepResult:
        """Send a notification — logs it for now."""
        message = params.get("message", "")
        channel = params.get("channel", state.channel)

        logger.info(f"[WORKFLOW NOTIFY] [{channel}] {message}")
        state.output.append({"type": "notification", "channel": channel, "message": message})

        return StepResult(step_id="", success=True, output=f"Notified on {channel}")

    async def _run_wait_step(self, params: dict) -> StepResult:
        """Pause execution for a specified duration."""
        duration = params.get("seconds", 5)
        await asyncio.sleep(min(duration, 300))  # Cap at 5 minutes
        return StepResult(step_id="", success=True, output=f"Waited {duration}s")

    async def _run_http_step(self, params: dict) -> StepResult:
        """Make an HTTP request."""
        try:
            import httpx

            url = params.get("url", "")
            method = params.get("method", "GET").upper()
            headers = params.get("headers", {})
            body = params.get("body")

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(method, url, headers=headers, json=body)

            return StepResult(
                step_id="",
                success=response.is_success,
                output=response.text[:2000],
                data={"status_code": response.status_code},
            )
        except ImportError:
            return StepResult(step_id="", success=False, error="httpx not installed")
        except Exception as e:
            return StepResult(step_id="", success=False, error=str(e))

    # ─── Resume + State ─────────────────────────────────────

    async def resume(
        self,
        run_id: int,
        workflow: WorkflowDefinition,
        approved: bool = True,
    ) -> bool:
        """Resume a paused workflow after approval.

        Args:
            run_id: The workflow run ID.
            workflow: The workflow definition (needed for step list).
            approved: Whether the approval was granted.

        Returns:
            True if resumed successfully.
        """
        state = self._active_runs.get(run_id)
        if not state:
            # Try to restore from DB
            state = await self._load_state(run_id)
            if not state:
                logger.error(f"Cannot resume: run {run_id} not found")
                return False

        if state.status != "paused":
            logger.warning(f"Cannot resume run {run_id}: status is {state.status}")
            return False

        if not approved:
            state.status = "cancelled"
            await self._persist_state(state)
            try:
                await AuditLog.log(
                    actor=state.started_by,
                    action="workflow.resume_denied",
                    resource=state.workflow_name,
                    details={"run_id": run_id},
                    success=True,
                )
            except Exception:
                pass
            return True

        # Move past the approval step
        state.status = "running"
        state.resume_token = None
        approval_step_idx = state.current_step
        approval_step = workflow.steps[approval_step_idx]

        state.step_results[approval_step.id] = StepResult(
            step_id=approval_step.id,
            success=True,
            approved=True,
            output="Approved by human",
        )
        state.current_step = approval_step_idx + 1

        # Continue execution
        try:
            await AuditLog.log(
                actor=state.started_by,
                action="workflow.resume",
                resource=state.workflow_name,
                details={"run_id": run_id, "approved": approved},
                success=True,
            )
        except Exception:
            pass
        await self._execute_steps(workflow, state)
        return True

    async def get_status(self, run_id: int) -> Optional[WorkflowState]:
        """Get the current state of a workflow run."""
        state = self._active_runs.get(run_id)
        if state:
            return state
        return await self._load_state(run_id)

    async def cancel(self, run_id: int) -> bool:
        """Cancel a running or paused workflow."""
        state = self._active_runs.get(run_id) or await self._load_state(run_id)
        if not state:
            return False

        state.status = "cancelled"
        state.completed_at = datetime.now(timezone.utc)
        await self._persist_state(state)
        try:
            await AuditLog.log(
                actor=state.started_by or "system",
                action="workflow.cancel",
                resource=state.workflow_name,
                details={"run_id": run_id},
                success=True,
            )
        except Exception:
            pass
        return True

    # ─── Persistence ────────────────────────────────────────

    async def _persist_state(self, state: WorkflowState):
        """Persist workflow state to the database."""
        try:
            update_data = {
                "status": state.status,
                "current_step": state.current_step,
                "state": state.to_db_dict(),
                "resume_token": state.resume_token,
            }
            if state.completed_at:
                update_data["completed_at"] = state.completed_at
            if state.status == "paused":
                update_data["paused_at"] = datetime.now(timezone.utc)
            if state.output:
                update_data["output"] = state.output

            await WorkflowRun.update_by_id(state.run_id, **update_data)
        except Exception as e:
            logger.error(f"Failed to persist workflow state: {e}")

    async def _load_state(self, run_id: int) -> Optional[WorkflowState]:
        """Load workflow state from the database."""
        try:
            run = await WorkflowRun.get_by_id(run_id)
            if not run:
                return None

            state = WorkflowState(
                run_id=run.id,
                workflow_name=run.workflow_name,
                status=run.status,
                current_step=run.current_step,
                resume_token=run.resume_token,
                input_args=run.input_args or {},
                started_at=run.started_at,
                completed_at=run.completed_at,
                started_by=run.started_by,
                channel=run.channel or "web",
                output=run.output or [],
            )

            # Restore step results from state JSON
            saved = run.state or {}
            for step_id, res_data in saved.get("step_results", {}).items():
                state.step_results[step_id] = StepResult(
                    step_id=step_id,
                    success=res_data.get("success", False),
                    output=res_data.get("output", ""),
                    error=res_data.get("error", ""),
                    skipped=res_data.get("skipped", False),
                )

            self._active_runs[run_id] = state
            return state

        except Exception as e:
            logger.error(f"Failed to load workflow state for run {run_id}: {e}")
            return None

    # ─── Template Resolution ────────────────────────────────

    def _resolve_templates(self, params: dict, state: WorkflowState) -> dict:
        """Resolve {{ steps.X.output }} and {{ args.Y }} references in params."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = self._resolve_string(value, state)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_templates(value, state)
            else:
                resolved[key] = value
        return resolved

    def _resolve_string(self, template: str, state: WorkflowState) -> str:
        """Resolve template variables in a string."""
        def replacer(match):
            expr = match.group(1).strip()

            # steps.step_id.output / steps.step_id.data.key
            if expr.startswith("steps."):
                parts = expr.split(".", 2)
                if len(parts) >= 3:
                    step_id = parts[1]
                    field = parts[2]
                    result = state.step_results.get(step_id)
                    if result:
                        return str(getattr(result, field, result.data.get(field, "")))
                return ""

            # args.key
            if expr.startswith("args."):
                key = expr[5:]
                return str(state.input_args.get(key, ""))

            # env.key
            if expr.startswith("env."):
                import os
                key = expr[4:]
                return os.environ.get(key, "")

            return match.group(0)

        return re.sub(r"\{\{\s*(.+?)\s*\}\}", replacer, template)

    def _evaluate_condition(self, condition: str, state: WorkflowState) -> bool:
        """Evaluate a step condition expression.

        Supported expressions:
          - "steps.check.success" — true if step succeeded
          - "steps.check.output contains 'error'" — substring match
          - "args.severity == 'critical'" — equality check
        """
        condition = condition.strip()

        # "steps.X.success"
        if condition.startswith("steps.") and condition.endswith(".success"):
            parts = condition.split(".")
            step_id = parts[1]
            result = state.step_results.get(step_id)
            return bool(result and result.success)

        # "steps.X.output contains 'Y'"
        contains_match = re.match(
            r"steps\.(\w+)\.output\s+contains\s+['\"](.+?)['\"]", condition
        )
        if contains_match:
            step_id = contains_match.group(1)
            search = contains_match.group(2)
            result = state.step_results.get(step_id)
            return bool(result and search in result.output)

        # "args.X == 'Y'"
        eq_match = re.match(r"args\.(\w+)\s*==\s*['\"](.+?)['\"]", condition)
        if eq_match:
            key = eq_match.group(1)
            value = eq_match.group(2)
            return str(state.input_args.get(key, "")) == value

        logger.warning(f"Unknown condition expression: {condition}")
        return True  # Default to true for unknown conditions
