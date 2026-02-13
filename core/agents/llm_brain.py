"""
Sanaa AI LLM Brain
Tiered intelligence: local model for routine, cloud for complex
"""

import os
import json
import subprocess
from litellm import acompletion
import asyncio

SYSTEM_PROMPT = """You are Sanaa AI, an AI operations agent managing the Sanaa fintech platform ecosystem.

Your operator is Banks, the founder of Sanaa — a comprehensive fintech platform based in Uganda serving East Africa.

SANAA ECOSYSTEM:
- cards.sanaa.ug — Card/Identity platform
- fx.sanaa.co — FX Trading platform
- soko.sanaa.ug — Soko 24 Marketplace
- sanaa.co — Main website
- Sanaa Finance — SACCO/ERP services
- Tech stack: Laravel 11, PostgreSQL, Redis, Filament Admin, Flutter mobile apps
- VPS: Ubuntu Linux (sanaa-vps)

YOUR CAPABILITIES:
1. Monitor server health (CPU, RAM, Disk, Network, Services)
2. Monitor all Sanaa web applications for errors and downtime
3. Read and triage Banks' email inbox
4. Fix minor server/application issues when approved
5. Run database queries and maintenance
6. Restart services (nginx, php-fpm, redis, queues)
7. Test web applications (load pages, check forms, verify APIs)
8. Search the web for relevant news and information
9. Generate daily/weekly activity reports
10. Monitor connected devices (Mac, phones)
11. Execute bash commands on the server
12. Analyze Laravel logs for errors

YOUR RULES:
- ALWAYS explain what you're about to do before doing it
- For destructive operations (delete, drop, modify), ALWAYS require approval
- Read-only operations (check status, read logs, test pages) can auto-execute
- When something is wrong, assess severity and notify Banks appropriately
- Be concise but thorough in reports
- Think like a senior DevOps engineer + executive assistant
- When in doubt, ask rather than act
- Log everything you do
"""

class LLMBrain:
    def __init__(self):
        self.strategy = os.getenv("LLM_STRATEGY", "auto")
        self.local_model = f"ollama/{os.getenv('OLLAMA_MODEL', 'qwen2.5:7b')}"
        # Fallback to local if cloud keys missing
        if os.getenv("ANTHROPIC_API_KEY"):
            self.cloud_model = "anthropic/claude-3-5-sonnet-20240620"
        elif os.getenv("OPENAI_API_KEY"):
            self.cloud_model = "openai/gpt-4o"
        else:
            self.cloud_model = self.local_model # Fallback

    async def think(self, prompt: str, complexity: str = "auto") -> str:
        """
        Route to appropriate model based on task complexity.
        complexity: low | high | auto
        """
        model = self.local_model

        if complexity == "high" or (complexity == "auto" and self._is_complex(prompt)):
            model = self.cloud_model

        try:
            response = await acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"LLM Error ({model}): {e}")
            # Fallback: if cloud fails, try local; if local fails, try cloud
            fallback = self.cloud_model if model == self.local_model else self.local_model
            if fallback == model:
                return f"Error: {str(e)}"
                
            try:
                response = await acompletion(
                    model=fallback,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4096,
                )
                return response.choices[0].message.content
            except Exception as e2:
                return f"Error in fallback: {str(e2)}"

    def _is_complex(self, prompt: str) -> bool:
        """Heuristic: is this task complex enough to need cloud model?"""
        complex_keywords = [
            "fix", "debug", "refactor", "analyze code", "write code",
            "migration", "deploy", "security", "research", "summarize article",
            "strategy", "plan", "architecture"
        ]
        return any(kw in prompt.lower() for kw in complex_keywords)

    async def analyze_command(self, command: str, server_context: dict, recent_logs: list) -> dict:
        """Analyze a user command and create an execution plan"""
        prompt = f"""You are Sanaa AI, Banks' AI operations agent for the Sanaa fintech platform.

Analyze this command and create an execution plan.

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

        result = await self.think(prompt, complexity="high")
        try:
            # Try to parse JSON clean
            return json.loads(result)
        except json.JSONDecodeError:
            # Extract JSON from markdown code blocks if needed
            import re
            match = re.search(r'\{[\s\S]*\}', result)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            
            # Fallback
            return {
                "summary": result[:100] + "...",
                "plan": ["Manual review needed (JSON parse failed)"],
                "auto_execute": False,
                "severity": "medium"
            }

    async def execute_plan(self, cmd_id: str, plan: list[str]):
        """Execute an approved plan step by step"""
        from database import Command, Log
        results = []

        for i, step in enumerate(plan):
            try:
                # Use LLM to translate step into actual bash/python command
                cmd_prompt = (
                    f"Translate this plan step into a safe bash command. "
                    f"Only output the command, nothing else. "
                    f"If it's not safe to automate, output 'SKIP: reason'.\n\n"
                    f"Step: {step}"
                )
                actual_cmd = await self.think(cmd_prompt, complexity="low")
                actual_cmd = actual_cmd.strip().replace('`', '')

                if actual_cmd.startswith("SKIP:"):
                    results.append({"step": step, "status": "skipped", "reason": actual_cmd})
                    continue

                # Execute with timeout and capture output
                proc = await asyncio.create_subprocess_shell(
                    actual_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                
                results.append({
                    "step": step,
                    "command": actual_cmd,
                    "status": "success" if proc.returncode == 0 else "failed",
                    "output": stdout.decode()[-500:] if stdout else "",
                    "error": stderr.decode()[-500:] if stderr else "",
                })
            except asyncio.TimeoutError:
                results.append({"step": step, "status": "timeout"})
            except Exception as e:
                results.append({"step": step, "status": "error", "error": str(e)})

        # Update command record
        await Command.update_by_id(cmd_id, status="completed", results=results)

        # Log execution
        await Log.create(
            source="brain",
            level="info",
            message=f"Executed plan for command {cmd_id}: {len(results)} steps completed"
        )
