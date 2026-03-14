"""
Sanaa AI System Brain - Core Engine
"""

import json
import re
import logging
import asyncio
import time
from typing import Optional
from litellm import acompletion

from core.config import get_settings
from core.database import Command, Log, AuditLog
from core.brain.providers import ModelRegistry, TIERS
from core.brain.usage import track_usage
from core.policies import evaluate_skill_access, effective_brain_provider_name

logger = logging.getLogger(__name__)
settings = get_settings()

class Brain:
    def __init__(self):
        self.registry = ModelRegistry()
        
        # Memory integration (lazy init)
        self._memory = None
        self._context = None
        self._skill_registry = None
        self._sanaa_clade = None
        self._skills_loaded = False
        self._skill_loader_task = None

    @property
    def skill_registry(self):
        """Lazy-loaded skill registry — discovers and loads skills on first access."""
        if self._skill_registry is None:
            from core.skills.registry import SkillRegistry

            self._skill_registry = SkillRegistry()
        return self._skill_registry

    async def ensure_skills_loaded(self):
        """Load skills once and wait for completion when tool execution is needed."""
        _ = self.skill_registry  # ensure registry exists
        if self._skills_loaded:
            return

        if self._skill_loader_task:
            await self._skill_loader_task
            return

        from core.skills.loader import SkillLoader
        loader = SkillLoader()
        self._skill_loader_task = asyncio.create_task(self._load_skills(loader))
        try:
            await self._skill_loader_task
        finally:
            self._skill_loader_task = None

    async def _load_skills(self, loader):
        """Load all skills into the registry."""
        skills = await loader.load_all()
        for skill in skills.values():
            self._skill_registry.register(skill)
        self._skills_loaded = True
        logger.info(f"Brain loaded {len(skills)} skills")

    async def execute_skill(
        self,
        name: str,
        args: dict,
        session_id: str = "",
        channel: str = "web",
        sender_id: str = "",
        execution_mode: str = "manual",
    ) -> dict:
        """Execute a skill by name through the registry.

        Returns dict with success, output, error, and data.
        """
        await self.ensure_skills_loaded()
        skill = self.skill_registry.get(name)
        if not skill:
            return {
                "success": False,
                "output": "",
                "error": f"Skill not found: {name}",
                "data": {},
                "execution_time_ms": 0,
            }

        access = await evaluate_skill_access(
            skill=skill,
            invocation=execution_mode,
            provider=self.get_effective_tool_provider(),
            channel=channel or "web",
        )
        if not access.get("allowed"):
            reason = access.get("reason") or "Skill blocked by policy"
            try:
                await AuditLog.log(
                    actor=f"{channel}:{sender_id or 'unknown'}",
                    action="skill.policy_denied",
                    resource=name,
                    details={
                        "execution_mode": execution_mode,
                        "reason": reason,
                        "session_id": session_id,
                    },
                    success=False,
                )
            except Exception:
                pass
            return {
                "success": False,
                "output": "",
                "error": reason,
                "data": {"policy_denied": True, "access": access},
                "execution_time_ms": 0,
            }

        from core.skills.base import SkillContext
        context = SkillContext(
            session_id=session_id,
            channel=channel,
            sender_id=sender_id,
            brain=self,
            memory=self.memory,
        )

        _start = time.time()
        result = await self.skill_registry.execute(name, args, context)
        _elapsed_ms = int((time.time() - _start) * 1000)

        # Track for learned shortcuts
        if result.success and execution_mode == "brain":
            await self._record_skill_invocation_for_shortcuts(name, args, session_id)

        # Record execution in skill_runs for ML analysis
        await self._record_skill_run(
            skill_name=name,
            args=args,
            result=result,
            elapsed_ms=_elapsed_ms,
            session_id=session_id,
            execution_mode=execution_mode,
        )

        # Log skill errors to learning system for self-improvement
        if not result.success and result.error:
            try:
                from core.intelligence.learning_logs import learning_log_manager
                await learning_log_manager.log_skill_error(
                    skill_name=name,
                    action=args.get("action", ""),
                    error=result.error,
                    args=args,
                    session_id=session_id,
                )
            except Exception:
                pass

        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "data": result.data,
            "execution_time_ms": _elapsed_ms or result.execution_time_ms,
        }

    async def _record_skill_invocation_for_shortcuts(self, name: str, args: dict, session_id: str):
        """Record skill usage to optionally auto-suggest shortcuts for repetitive tasks."""
        try:
            from core.database import SystemKnowledge
            from sqlalchemy.dialects.postgresql import insert
            
            # Use the skill name and sorted argument keys as a signature
            arg_signature = ",".join(sorted(args.keys()))
            signature = f"{name}({arg_signature})"
            
            key = f"shortcut_tracker.{signature}"
            current_count_str = await SystemKnowledge.get_pref(key, default="0", domain="behavior")
            count = int(current_count_str) + 1
            
            # Simple heuristic: If we do the exact same shape 5 times, it might be a shortcut
            if count == 5:
                suggestion = (
                    f"💡 I noticed you frequently use the `{name}` skill with arguments {list(args.keys())}. "
                    f"Would you like me to create a shortcut or alias for this?"
                )
                # Store the suggestion in the context buffer so the brain can mention it
                # For now, just log it. A fuller implementation would inject this into ContextAssembler.
                logger.info(f"Learned Shortcut Suggestion: {suggestion}")
            
            await SystemKnowledge.set_pref(key, str(count), source="brain", domain="behavior")
        except Exception as e:
            logger.warning(f"Failed to record shortcut logic: {e}")

    async def _record_skill_run(
        self,
        skill_name: str,
        args: dict,
        result,
        elapsed_ms: int,
        session_id: str,
        execution_mode: str,
    ):
        """Record skill execution to skill_runs table for ML analysis."""
        try:
            from core.database import SkillRun, utcnow
            status = "success" if result.success else "failed"
            if result.error and "timeout" in result.error.lower():
                status = "timeout"

            await SkillRun.create(
                skill_name=skill_name,
                action=args.get("action", ""),
                triggered_by=execution_mode,
                input_data=args,
                output_data={"output": result.output[:500] if result.output else "", "data": result.data},
                status=status,
                error_message=result.error if not result.success else None,
                duration_ms=elapsed_ms,
                completed_at=utcnow(),
            )
        except Exception as e:
            logger.warning(f"Failed to record skill run for ML: {e}")

    def get_effective_tool_provider(self) -> str:
        return effective_brain_provider_name(
            self.get_current_provider(),
            getattr(settings, "brain_claude_source", "anthropic"),
        )

    @property
    def memory(self):
        if self._memory is None:
            from core.memory.manager import MemoryManager
            self._memory = MemoryManager()
        return self._memory

    @property
    def context_assembler(self):
        if self._context is None:
            from core.memory.context import ContextAssembler
            self._context = ContextAssembler(self.memory)
        return self._context

    @property
    def sanaa_clade(self):
        if self._sanaa_clade is None:
            try:
                from core.brain.sanaa_clade_bridge import SanaaCladeBridge
                self._sanaa_clade = SanaaCladeBridge()
            except Exception as e:
                logger.warning(f"Failed to initialize sanaa-clade bridge: {e}")
                self._sanaa_clade = False
        return self._sanaa_clade if self._sanaa_clade is not False else None

    def switch_provider(self, provider: str):
        """Switch the active LLM provider (auto, local, groq, claude, openrouter)."""
        self.registry.set_active_provider(provider)
        logger.info(f"Brain switched to provider: {provider}")

    def get_current_provider(self) -> str:
        return self.registry.active_provider

    async def think(
        self,
        prompt: str,
        complexity: str = "auto",
        session_id: str = None,
        channel: str = "web",
    ) -> str:
        """
        Route to appropriate model tier based on task complexity.
        Now uses memory-enriched context when session_id is provided.
        """
        tier = self._determine_tier(prompt, complexity)

        # Build context with memories if session available
        if session_id:
            messages = await self.context_assembler.assemble(
                prompt, session_id=session_id, channel=channel
            )
        else:
            messages = [
                {"role": "system", "content": "You are Sanaa AI, an autonomous intelligence assistant. Be concise, helpful, and conversational."},
                {"role": "user", "content": prompt},
            ]

        # Allow a lightweight skill-tool loop for operational prompts.
        messages = await self._maybe_invoke_skills(messages, prompt, tier, session_id, channel)

        # Try models with failover: tier N → N-1 → ... → 1
        response_text = await self._call_with_failover(messages, tier)

        # Save conversation turn if session exists
        if session_id:
            await self.context_assembler.save_turn(
                session_id=session_id,
                channel=channel,
                sender_id="assistant",
                role="assistant",
                content=response_text,
            )

        return response_text

    async def _maybe_invoke_skills(
        self,
        messages: list[dict],
        original_prompt: str,
        tier: int,
        session_id: Optional[str],
        channel: str,
    ) -> list[dict]:
        """One-shot or multi-shot tool loop using JSON tool directives in model output."""
        if not self._should_offer_skills(original_prompt, channel):
            return messages

        await self.ensure_skills_loaded()
        if not self.skill_registry.count:
            return messages

        provider = self.get_effective_tool_provider()
        
        # Allow up to 3 tool calls to chain diagnostics
        for loop_idx in range(3):
            visible_skills = []
            visible_tool_defs = []
            visible_names: set[str] = set()
            
            for skill in self.skill_registry._skills.values():
                access = await evaluate_skill_access(skill=skill, invocation="brain", provider=provider, channel=channel or "web")
                if access.get("allowed"):
                    visible_names.add(skill.name)
                    visible_skills.append({
                        "name": skill.name,
                        "description": skill.description,
                        "tags": getattr(skill, "tags", []),
                    })
                    visible_tool_defs.append(skill.to_tool_definition())

            if not visible_names:
                break

            tool_prompt = (
                f"Iteration {loop_idx + 1}/3. You can request ONE skill call if needed for accuracy.\n"
                "If you need a skill, reply ONLY JSON:\n"
                '{"tool":"name","args":{"param":"value"},"reason":"why"}\n'
                "If no (more) skills are needed, reply 'READY'.\n\n"
                "Allowed tools:\n" + json.dumps(visible_skills, indent=2)
            )
            
            # Use a slightly complex model for the tool loop itself
            loop_messages = [{"role": "system", "content": tool_prompt}] + messages
            probe = await self._call_with_failover(loop_messages, max(tier, 2))
            
            if "READY" in probe.upper() and "{" not in probe:
                break
                
            skill_call = self._parse_skill_call(probe, allowed_tool_names=visible_names)
            if not skill_call:
                break

            skill_name = skill_call.get("tool")
            skill_args = skill_call.get("args") or {}

            exec_result = await self.execute_skill(
                name=skill_name,
                args=skill_args,
                session_id=session_id or "",
                channel=channel or "web",
                sender_id="brain",
                execution_mode="brain",
            )

            tool_feedback = {
                "skill": skill_name,
                "success": exec_result.get("success", False),
                "output": (exec_result.get("output") or "")[:5000],
                "error": exec_result.get("error") or "",
            }

            messages.append({"role": "assistant", "content": probe})
            messages.append({
                "role": "system",
                "content": f"Skill result:\n{json.dumps(tool_feedback, indent=2, default=str)}"
            })

        return messages

    async def _call_with_failover(self, messages: list, starting_tier: int) -> str:
        """Try models from starting tier down to tier 1 with failover."""
        if getattr(settings, "sanaa_clade_enabled", False) and self.sanaa_clade:
            try:
                flat_prompt = self._flatten_messages_for_clade(messages)
                result = await self.sanaa_clade.ask(flat_prompt)
                if result.success and result.output:
                    output = result.output
                    # Strip provider error JSON that leaks from the CLI
                    import re as _re
                    output = _re.sub(r'\{\s*"type"\s*:\s*"error".*?"request_id"\s*:\s*"[^"]*"\s*\}\s*', '', output, flags=_re.DOTALL).strip()
                    if output:
                        return output
                logger.warning(f"sanaa-clade bridge failed, falling back to LiteLLM: {result.stderr}")
            except Exception as e:
                logger.warning(f"sanaa-clade bridge exception, falling back to LiteLLM: {e}")

        for tier in range(starting_tier, 0, -1):
            tier_config = TIERS[tier]
            models = self.registry.get_models_for_tier(tier)
            for model in models:
                try:
                    # Ollama on CPU needs more time; cloud APIs are fast
                    model_timeout = 90 if model.startswith("ollama/") else 30
                    start = time.monotonic()
                    response = await acompletion(
                        model=model,
                        messages=messages,
                        max_tokens=tier_config["max_tokens"],
                        temperature=0.3,
                        timeout=model_timeout,
                    )
                    latency = int((time.monotonic() - start) * 1000)
                    content = response.choices[0].message.content

                    # Track usage
                    await track_usage(
                        model=model,
                        tier=tier,
                        usage=response.usage,
                        latency_ms=latency,
                    )

                    # Successful call: Reset failures for this provider's domain
                    provider = model.split("/")[0] if "/" in model else model
                    await self._reset_provider_failure(provider)

                    return content

                except Exception as e:
                    logger.warning(f"Tier {tier} model {model} failed: {e}")
                    provider = model.split("/")[0] if "/" in model else model
                    await self._track_provider_failure(provider, str(e))
                    continue

        return "All models unavailable. Please try again later."

    def _flatten_messages_for_clade(self, messages: list[dict]) -> str:
        """Flatten chat messages into a single prompt for the CLI wrapper."""
        parts = ["You are Sanaa AI, an autonomous intelligence assistant. Be concise, helpful, and conversational."]
        for msg in messages:
            role = (msg.get("role") or "user").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                # Defensive: flatten any multimodal-style arrays to text fragments.
                content = " ".join(
                    c.get("text", str(c)) if isinstance(c, dict) else str(c)
                    for c in content
                )
            parts.append(f"{role}: {content}")
        return "\n\n".join(parts)

    def _should_offer_skills(self, prompt: str, channel: str) -> bool:
        if not prompt:
            return False
        if len(prompt) > 3000:
            return False
        p = prompt.lower()
        indicators = [
            # System & infra
            "cpu", "ram", "memory", "disk", "storage", "health", "uptime",
            "service", "process", "logs", "error", "warning", "alerts",
            "check", "scan", "monitor", "status", "website", "web test",
            "latency", "response time", "workflow", "run skill", "self heal",
            "celery", "beat", "worker", "schedule", "task",
            "database", "postgres", "sql", "query", "config", "settings",
            # Communication
            "email", "news", "briefing", "newsletter", "send", "smtp",
            "whatsapp", "broadcast", "message", "notify", "telegram",
            "voice", "audio", "transcribe", "whisper", "voice note",
            # Development & coding
            "code", "file", "read file", "write file", "patch", "diff",
            "search code", "git", "commit", "deploy", "fix bug",
            # Productivity & tasks
            "create task", "ticket", "project", "add task", "list tasks", "mark done",
            # Research & web
            "fetch", "summarize url", "browse", "web fetch", "scrape",
            "watch site", "site changed", "competitor",
            # Skills & meta
            "skill", "create skill", "new skill", "reload skill",
            "tmux", "background task", "long running",
            # External monitoring
            "endpoint", "api status", "telecom", "payment",
        ]
        return any(k in p for k in indicators)

    def _parse_skill_call(self, response: str, allowed_tool_names: Optional[set[str]] = None) -> Optional[dict]:
        """Parse a model-issued JSON skill call from free-form text."""
        if not response:
            return None
        response = response.strip()
        candidates = [response]
        obj_match = re.search(r"\{[\s\S]*\}", response)
        if obj_match and obj_match.group() not in candidates:
            candidates.append(obj_match.group())

        for raw in candidates:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            tool = str(data.get("tool") or "").strip()
            if allowed_tool_names is not None and tool not in allowed_tool_names:
                continue
            if tool and self.skill_registry.get(tool):
                return {"tool": tool, "args": data.get("args") or {}, "reason": data.get("reason")}
        return None

    async def _track_provider_failure(self, provider: str, error: str):
        """Track consecutive failures for a cloud provider and alert when degraded.

        Ollama/local failures are intentionally not tracked here — local is the
        last-resort fallback and has no upstream to switch to.

        IMPORTANT: We do NOT permanently switch the active provider to "local" on
        failure. The model chain in auto mode already lists Groq first and Ollama
        last — so every request tries Groq, falls back to Ollama if Groq is down,
        and automatically recovers when Groq comes back. Locking the registry into
        "local" mode would prevent Groq from being tried even after it recovers.
        """
        from core.database import SystemKnowledge, Alert

        # Ollama is the last-resort fallback — no action when it fails
        if provider in ("local", "ollama"):
            return

        key = f"provider_fail_count.{provider}"
        current = await SystemKnowledge.get_pref(key, default=0)
        new_count = int(current) + 1

        from sqlalchemy import select
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            entry = await session.execute(
                select(SystemKnowledge).where(
                    SystemKnowledge.domain == "preference",
                    SystemKnowledge.key == key,
                )
            )
            obj = entry.scalars().first()
            if obj:
                obj.value = str(new_count)
            else:
                obj = SystemKnowledge(
                    domain="preference",
                    key=key,
                    value=str(new_count),
                    value_type="int",
                    source="brain_failover",
                )
                session.add(obj)
            await session.commit()

        # Alert at threshold — but do NOT change the active provider.
        # The per-request chain already falls back to Ollama automatically.
        if new_count >= 5:
            await Alert.create(
                severity="high",
                message=(
                    f"Brain: {provider} has failed {new_count} consecutive times. "
                    f"Requests are falling back to Ollama. Last error: {error[:200]}"
                ),
                metric=f"brain.provider.degraded.{provider}",
            )
            logger.warning(
                f"Brain: {provider} is degraded ({new_count} failures). "
                f"Auto-fallback to Ollama active. Groq will be retried on every request."
            )

    async def _reset_provider_failure(self, provider: str):
        """Reset failure counter after a successful call to this provider."""
        from core.database import SystemKnowledge
        key = f"provider_fail_count.{provider}"
        current = await SystemKnowledge.get_pref(key, default=0)
        if int(current) > 0:
            from sqlalchemy import update
            from core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(SystemKnowledge)
                    .where(SystemKnowledge.key == key)
                    .values(value="0")
                )
                await session.commit()
            logger.info(f"Brain: {provider} recovered — failure counter reset")

    def _determine_tier(self, prompt: str, complexity: str) -> int:
        """Determine which tier to use based on complexity hint or heuristics.
        Tier 1 (Local): Status checks, emails, backups, formatting.
        Tier 3 (Groq/Claude): Complex reasoning, coding, deep analysis.
        """
        if complexity == "low":
            return 1
        if complexity == "medium":
            return 2
        if complexity == "high":
            return 3

        # Auto-detect
        prompt_lower = prompt.lower()

        complex_keywords = [
            "analyze", "plan", "review", "audit", "debug", "explain why",
            "architecture", "strategy", "migration", "refactor", "security",
            "write code", "fix", "deploy", "investigate anomaly"
        ]
        
        # Expanded simple keywords for personal assistant tasks (Jarvis mode)
        simple_keywords = [
            "status", "check", "restart", "list", "show", "what is",
            "how many", "uptime", "health", "read email", "inbox",
            "backup", "summary", "translate", "format", "brief"
        ]

        token_estimate = len(prompt.split()) * 1.3

        if any(kw in prompt_lower for kw in complex_keywords) or token_estimate > 500:
            return 3
        elif any(kw in prompt_lower for kw in simple_keywords) and token_estimate < 150:
            return 1
        else:
            return 2

    async def analyze_command(
        self,
        command: str,
        server_context: dict,
        recent_logs: list,
        session_id: str = None,
    ) -> dict:
        """Analyze a user command and create an execution plan."""
        prompt = f"""Analyze this command and create an execution plan.

COMMAND: {command}

CURRENT SERVER STATE:
{json.dumps(server_context, indent=2, default=str)}

RECENT ERROR LOGS:
{json.dumps(recent_logs[-10:], indent=2, default=str)}

Respond ONLY in JSON with:
{{
    "summary": "Brief analysis of what's needed",
    "severity": "low|medium|high|critical",
    "plan": ["step 1", "step 2", ...],
    "auto_execute": true/false (true only for safe, read-only operations),
    "estimated_time": "Xm",
    "risks": ["any risks"]
}}"""

        result = await self.think(prompt, complexity="high", session_id=session_id)
        return self._parse_json_response(result)

    def _parse_json_response(self, result: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", result)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {
                "summary": result[:200],
                "plan": ["Manual review needed (JSON parse failed)"],
                "auto_execute": False,
                "severity": "medium",
            }

    async def execute_plan(self, cmd_id: str, plan: list[str]):
        """Execute an approved plan step by step.

        Security: Uses subprocess with shell=False and argument lists to
        prevent shell injection. Commands are parsed via shlex.split() and
        validated for dangerous metacharacters before execution.
        """
        from core.utils.sanitize import sanitize_command_string

        results = []

        for step in plan:
            try:
                cmd_prompt = (
                    "Translate this plan step into a safe bash command. "
                    "Only output the command, nothing else. "
                    "If it's not safe to automate, output 'SKIP: reason'.\n\n"
                    f"Step: {step}"
                )
                actual_cmd = await self.think(cmd_prompt, complexity="low")
                actual_cmd = actual_cmd.strip().strip("`").strip()

                if actual_cmd.startswith("SKIP:"):
                    results.append({"step": step, "status": "skipped", "reason": actual_cmd})
                    continue

                # Sanitize and split command into argument list (shell=False)
                try:
                    cmd_args = sanitize_command_string(actual_cmd)
                except ValueError as e:
                    results.append({
                        "step": step,
                        "command": actual_cmd,
                        "status": "blocked",
                        "error": f"Command blocked by sanitizer: {e}",
                    })
                    logger.warning(f"Brain: blocked unsafe command: {actual_cmd!r}")
                    continue

                proc = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

                results.append({
                    "step": step,
                    "command": actual_cmd,
                    "status": "success" if proc.returncode == 0 else "failed",
                    "output": stdout.decode()[-500:] if stdout else "",
                    "error": stderr.decode()[-500:] if stderr else "",
                })

                # Audit log
                await AuditLog.log(
                    actor="brain",
                    action="command.execute_step",
                    resource=actual_cmd[:200],
                    success=proc.returncode == 0,
                )

            except asyncio.TimeoutError:
                results.append({"step": step, "status": "timeout"})
            except Exception as e:
                results.append({"step": step, "status": "error", "error": str(e)})

        await Command.update_by_id(cmd_id, status="completed", results=results)
        await Log.create(
            source="brain",
            level="info",
            message=f"Executed plan for command {cmd_id}: {len(results)} steps",
        )

    async def remember(self, content: str, category: str = "fact", source: str = "brain"):
        """Store a fact in long-term memory."""
        return await self.memory.store(content, category=category, source=source)

    async def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Search long-term memory."""
        return await self.memory.search(query, limit=limit)
