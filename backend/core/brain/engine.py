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
        result = await self.skill_registry.execute(name, args, context)
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "data": result.data,
            "execution_time_ms": result.execution_time_ms,
        }

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
            # Simple system prompt if no memory context
            messages = [
                {"role": "system", "content": "You are the central brain of Sanaa AI."},
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
        """Optional one-shot tool loop using JSON tool directives in model output.

        The brain asks the model whether a skill call is needed. If it returns a
        JSON tool request, Sanaa executes the skill and appends the result back into
        the conversation before the final answer is generated.
        """
        if not self._should_offer_skills(original_prompt, channel):
            return messages

        await self.ensure_skills_loaded()
        if not self.skill_registry.count:
            return messages

        visible_skills = []
        visible_tool_defs = []
        visible_names: set[str] = set()
        provider = self.get_effective_tool_provider()
        for skill in self.skill_registry._skills.values():
            access = await evaluate_skill_access(skill=skill, invocation="brain", provider=provider, channel=channel or "web")
            if access.get("allowed"):
                visible_names.add(skill.name)
                visible_skills.append(
                    {
                        "name": skill.name,
                        "description": skill.description,
                        "version": getattr(skill, "version", "1.0.0"),
                        "permissions": getattr(skill, "permissions", []),
                        "requires_approval": bool(getattr(skill, "requires_approval", False)),
                        "tags": getattr(skill, "tags", []),
                        "groups": access.get("groups", []),
                        "safety_tier": access.get("safety_tier", "read_only"),
                    }
                )
                visible_tool_defs.append(skill.to_tool_definition())

        if not visible_names:
            return messages

        tool_prompt = (
            "You can request one Sanaa skill call before answering if it will improve accuracy.\n"
            "If you need a skill, reply ONLY JSON in this format:\n"
            '{"tool":"skill_name","args":{"param":"value"},"reason":"why"}\n'
            "If no skill is needed, reply normally.\n\n"
            "Only choose from the allowed tools below.\n\n"
            "Available skills:\n"
            f"{json.dumps(visible_skills, indent=2)}\n\n"
            "Tool schemas:\n"
            f"{json.dumps(visible_tool_defs, indent=2)}"
        )
        tool_messages = [{"role": "system", "content": tool_prompt}] + messages

        probe = await self._call_with_failover(tool_messages, min(tier, 2))
        skill_call = self._parse_skill_call(probe, allowed_tool_names=visible_names)
        if not skill_call:
            # No tool requested; keep original messages and let final response happen as usual.
            return messages

        skill_name = skill_call.get("tool") or ""
        skill_args = skill_call.get("args") or {}
        if not isinstance(skill_args, dict):
            skill_args = {}

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
            "args": skill_args,
            "success": exec_result.get("success", False),
            "output": (exec_result.get("output") or "")[:4000],
            "error": exec_result.get("error") or "",
            "data": exec_result.get("data") or {},
            "execution_time_ms": exec_result.get("execution_time_ms", 0),
        }

        followup = list(messages)
        followup.append(
            {
                "role": "system",
                "content": (
                    "Sanaa skill execution result (use this to answer precisely; do not invent data):\n"
                    f"{json.dumps(tool_feedback, indent=2, default=str)}"
                ),
            }
        )
        return followup

    async def _call_with_failover(self, messages: list, starting_tier: int) -> str:
        """Try models from starting tier down to tier 1 with failover."""
        if getattr(settings, "sanaa_clade_enabled", False) and self.sanaa_clade:
            try:
                flat_prompt = self._flatten_messages_for_clade(messages)
                result = await self.sanaa_clade.ask(flat_prompt)
                if result.success and result.output:
                    return result.output
                logger.warning(f"sanaa-clade bridge failed, falling back to LiteLLM: {result.stderr}")
            except Exception as e:
                logger.warning(f"sanaa-clade bridge exception, falling back to LiteLLM: {e}")

        for tier in range(starting_tier, 0, -1):
            tier_config = TIERS[tier]
            models = self.registry.get_models_for_tier(tier)
            for model in models:
                try:
                    start = time.monotonic()
                    response = await acompletion(
                        model=model,
                        messages=messages,
                        max_tokens=tier_config["max_tokens"],
                        temperature=0.3,
                        timeout=300,
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
        parts = ["You are the central brain of Sanaa AI. Respond with practical, accurate operational guidance."]
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
        if len(prompt) > 2500:
            return False
        p = prompt.lower()
        indicators = [
            "cpu", "ram", "memory", "disk", "storage", "health", "uptime",
            "service", "process", "logs", "error", "warning", "alerts",
            "check", "scan", "monitor", "status", "website", "web test",
            "latency", "response time", "workflow", "run skill", "self heal",
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
        """Track consecutive failures per provider and trigger failover if threshold met."""
        from core.database import SystemKnowledge, Alert
        
        # Don't failover if we're already local
        if provider in ("local", "ollama"):
            return

        key = f"provider_fail_count.{provider}"
        current = await SystemKnowledge.get_pref(key, default=0)
        new_count = int(current) + 1
        
        # Persist new failure count
        from sqlalchemy import select
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            entry = await session.execute(
                select(SystemKnowledge).where(
                    SystemKnowledge.domain == "preference",
                    SystemKnowledge.key == key
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
                    source="brain_failover"
                )
                session.add(obj)
            await session.commit()

        # Threshold check (e.g. 5 failures)
        if new_count >= 5:
            await self._trigger_provider_failover(provider, error)

    async def _trigger_provider_failover(self, provider: str, last_error: str):
        """Automatically switch system to local Ollama and alert."""
        from core.database import SystemKnowledge, Alert
        
        active_provider = await SystemKnowledge.get_pref("brain.provider", default="auto")
        
        if active_provider == "local":
            return # Already failed over

        # Switch across the whole system
        from sqlalchemy import update
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(SystemKnowledge)
                .where(SystemKnowledge.key == "brain.provider")
                .values(value="local")
            )
            await session.commit()
            
        self.registry.set_active_provider("local")
        
        # Log critical alert
        await Alert.create(
            severity="critical",
            message=f"AI Provider Failover: {provider} is chronically failing. System switched to LOCAL (Ollama) automatically.",
            metric=f"brain.failover.{provider}",
        )
        logger.critical(f"Brain: Triggered automatic failover from {provider} to local due to: {last_error}")

    async def _reset_provider_failure(self, provider: str):
        """Reset failure counter upon successful call."""
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

    def _determine_tier(self, prompt: str, complexity: str) -> int:
        """Determine which tier to use based on complexity hint or heuristics."""
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
            "write code", "fix", "deploy",
        ]
        simple_keywords = [
            "status", "check", "restart", "list", "show", "what is",
            "how many", "uptime", "health",
        ]

        token_estimate = len(prompt.split()) * 1.3

        if any(kw in prompt_lower for kw in complex_keywords) or token_estimate > 500:
            return 3
        elif any(kw in prompt_lower for kw in simple_keywords) and token_estimate < 100:
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
        """Execute an approved plan step by step."""
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

                proc = await asyncio.create_subprocess_shell(
                    actual_cmd,
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
