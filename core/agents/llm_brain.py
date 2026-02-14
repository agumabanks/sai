"""
Sanaa AI LLM Brain — Tiered Intelligence with Memory Integration
Tier 1: Local (Ollama) — free, fast, simple tasks
Tier 2: Cloud cheap (Haiku/GPT-mini) — moderate reasoning
Tier 3: Cloud premium (Sonnet/GPT-4o) — complex analysis
"""

import json
import re
import logging
import asyncio
import time
from litellm import acompletion

from config import get_settings
from database import LLMUsage, Command, Log, AuditLog, AsyncSessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()

TIERS = {
    1: {
        "name": "local",
        "max_tokens": 2048,
        "use_for": ["status_check", "simple_query", "format_response"],
        "cost_per_1k": 0.0,
    },
    2: {
        "name": "cloud_cheap",
        "max_tokens": 4096,
        "use_for": ["log_analysis", "email_summary", "moderate_reasoning"],
        "cost_per_1k": 0.001,
    },
    3: {
        "name": "cloud_premium",
        "max_tokens": 8192,
        "use_for": ["complex_analysis", "code_review", "planning", "security_audit"],
        "cost_per_1k": 0.015,
    },
}


class LLMBrain:
    def __init__(self):
        self.strategy = settings.llm_strategy
        self.local_model = f"ollama/{settings.ollama_model}"

        # Build model chain for each tier
        self.models = {1: [self.local_model]}

        tier2 = []
        if settings.anthropic_api_key:
            tier2.append("anthropic/claude-haiku-4-5-20251001")
        if settings.openai_api_key:
            tier2.append("openai/gpt-4o-mini")
        self.models[2] = tier2 if tier2 else [self.local_model]

        tier3 = []
        if settings.anthropic_api_key:
            tier3.append("anthropic/claude-sonnet-4-5-20250929")
        if settings.openai_api_key:
            tier3.append("openai/gpt-4o")
        self.models[3] = tier3 if tier3 else self.models[2]

        # Memory integration (lazy init)
        self._memory = None
        self._context = None

    @property
    def memory(self):
        if self._memory is None:
            from memory.manager import MemoryManager
            self._memory = MemoryManager()
        return self._memory

    @property
    def context_assembler(self):
        if self._context is None:
            from memory.context import ContextAssembler
            self._context = ContextAssembler(self.memory)
        return self._context

    # ==================== CORE THINKING ====================

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
            from memory.context import SYSTEM_PROMPT
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

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

    async def _call_with_failover(self, messages: list, starting_tier: int) -> str:
        """Try models from starting tier down to tier 1 with failover."""
        for tier in range(starting_tier, 0, -1):
            tier_config = TIERS[tier]
            for model in self.models[tier]:
                try:
                    start = time.monotonic()
                    response = await acompletion(
                        model=model,
                        messages=messages,
                        max_tokens=tier_config["max_tokens"],
                        temperature=0.3,
                        timeout=30,
                    )
                    latency = int((time.monotonic() - start) * 1000)
                    content = response.choices[0].message.content

                    # Track usage
                    await self._track_usage(
                        model=model,
                        tier=tier,
                        usage=response.usage,
                        latency_ms=latency,
                    )

                    return content

                except Exception as e:
                    logger.warning(f"Tier {tier} model {model} failed: {e}")
                    continue

        return "All models unavailable. Please try again later."

    def _determine_tier(self, prompt: str, complexity: str) -> int:
        """Determine which tier to use based on complexity hint or heuristics."""
        if complexity == "low":
            return 1
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

    async def _track_usage(self, model: str, tier: int, usage, latency_ms: int):
        """Record token usage and estimated cost."""
        try:
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            cost_per_1k = TIERS[tier]["cost_per_1k"]
            cost = (input_tokens + output_tokens) / 1000 * cost_per_1k

            provider = model.split("/")[0] if "/" in model else "unknown"

            async with AsyncSessionLocal() as session:
                entry = LLMUsage(
                    model=model,
                    provider=provider,
                    tier=tier,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                )
                session.add(entry)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to track LLM usage: {e}")

    # ==================== COMMAND ANALYSIS ====================

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

    # ==================== PLAN EXECUTION ====================

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

    # ==================== MEMORY HELPERS ====================

    async def remember(self, content: str, category: str = "fact", source: str = "brain"):
        """Store a fact in long-term memory."""
        return await self.memory.store(content, category=category, source=source)

    async def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Search long-term memory."""
        return await self.memory.search(query, limit=limit)
