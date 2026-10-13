import os
import sys
import asyncio
import resource
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ExecutionSandbox:
    """
    Lightweight sandbox for executing agent-generated scripts.
    Provides resource limits and basic isolation.
    """
    def __init__(self, timeout: int = 30, memory_limit_mb: int = 128):
        self.timeout = timeout
        self.memory_limit = memory_limit_mb * 1024 * 1024

    def _set_limits(self):
        """Set CPU and Memory limits for the child process."""
        # Limit address space (memory)
        resource.setrlimit(resource.RLIMIT_AS, (self.memory_limit, self.memory_limit))
        # Limit CPU time
        resource.setrlimit(resource.RLIMIT_CPU, (self.timeout, self.timeout))
        # Prevent core dumps
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    async def run_script(self, script_path: str, args: Optional[list] = None) -> Dict[str, Any]:
        """Runs a script in a subprocess with resource limits."""
        if not os.path.exists(script_path):
            return {"success": False, "error": "Script not found"}

        cmd = [sys.executable, script_path] + (args or [])
        return await self.execute_command(cmd)

    async def execute_command(
        self,
        argv: list[str],
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run an explicit argument list with shell=False and resource limits.

        Args:
            argv: Command argument list (first item is the executable).
            cwd: Optional working directory for the subprocess.
            env: Optional environment dictionary.
            timeout: Optional per-command timeout (defaults to self.timeout).

        Returns:
            Dict with success, returncode, stdout, stderr and/or error.
        """
        if not argv:
            return {"success": False, "error": "Empty command"}

        for arg in argv:
            if not isinstance(arg, str):
                return {"success": False, "error": "Invalid argument type"}

        executable = argv[0]
        if executable.startswith("/") and not os.path.exists(executable):
            return {"success": False, "error": f"Executable not found: {executable}"}

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
                preexec_fn=self._set_limits,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=(timeout or self.timeout) + 5
                )
                return {
                    "success": process.returncode == 0,
                    "returncode": process.returncode,
                    "stdout": stdout.decode(errors="replace"),
                    "stderr": stderr.decode(errors="replace"),
                }
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except Exception:
                    pass
                return {"success": False, "error": "Execution timed out"}

        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return {"success": False, "error": str(e)}
