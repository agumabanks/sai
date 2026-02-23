import os
import sys
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
        
        try:
            # Note: On Linux, we could use unshare for deeper isolation,
            # but for now, we'll stick to resource limits and preexec_fn.
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=self._set_limits
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout + 5)
                return {
                    "success": process.returncode == 0,
                    "returncode": process.returncode,
                    "stdout": stdout.decode(),
                    "stderr": stderr.decode()
                }
            except asyncio.TimeoutError:
                process.kill()
                return {"success": False, "error": "Execution timed out"}
                
        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return {"success": False, "error": str(e)}

import asyncio
