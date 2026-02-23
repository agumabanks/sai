"""
Sanaa Clade Bridge — async wrapper around the local `sanaa-clade` CLI.

Allows backend agents/brain to use the switchable Claude/Groq/OpenRouter CLI
as a reasoning engine while preserving Python-side orchestration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass
from typing import Optional

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SanaaCladeResult:
    success: bool
    output: str
    stderr: str
    returncode: int
    latency_ms: int
    source: Optional[str] = None


class SanaaCladeBridge:
    """Runs the `sanaa-clade` CLI as an external reasoning backend."""

    def __init__(self, script_path: Optional[str] = None, timeout: Optional[int] = None):
        self.script_path = script_path or settings.sanaa_clade_path
        self.timeout = int(timeout or settings.sanaa_clade_timeout or 180)

    def is_available(self) -> bool:
        if not self.script_path:
            return False
        if os.path.isabs(self.script_path):
            return os.path.isfile(self.script_path) and os.access(self.script_path, os.X_OK)
        resolved = shutil.which(self.script_path)
        return bool(resolved)

    async def ask(
        self,
        prompt: str,
        source: Optional[str] = None,
        no_admin_sync: Optional[bool] = None,
    ) -> SanaaCladeResult:
        if not self.is_available():
            return SanaaCladeResult(
                success=False,
                output="",
                stderr=f"sanaa-clade not available at {self.script_path}",
                returncode=127,
                latency_ms=0,
                source=source,
            )

        cmd = [self.script_path]
        if source:
            cmd.extend(["--source", source])
        if no_admin_sync if no_admin_sync is not None else settings.sanaa_clade_no_admin_sync:
            cmd.append("--no-admin-sync")
        cmd.append(prompt)

        env = os.environ.copy()
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            latency_ms = int((time.monotonic() - start) * 1000)
            out = (stdout or b"").decode("utf-8", errors="replace").strip()
            err = (stderr or b"").decode("utf-8", errors="replace").strip()
            return SanaaCladeResult(
                success=proc.returncode == 0 and bool(out),
                output=out,
                stderr=err,
                returncode=int(proc.returncode or 0),
                latency_ms=latency_ms,
                source=source,
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("sanaa-clade bridge timed out after %ss", self.timeout)
            return SanaaCladeResult(
                success=False,
                output="",
                stderr=f"sanaa-clade timed out after {self.timeout}s",
                returncode=124,
                latency_ms=latency_ms,
                source=source,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error("sanaa-clade bridge failed: %s", e, exc_info=True)
            return SanaaCladeResult(
                success=False,
                output="",
                stderr=str(e),
                returncode=1,
                latency_ms=latency_ms,
                source=source,
            )
