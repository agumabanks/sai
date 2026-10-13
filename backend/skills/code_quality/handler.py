"""Code Quality Sweep — automated linting, formatting, dead code removal."""
import os
import asyncio
import logging
import json
import re
import shlex
from datetime import datetime
from pathlib import Path
from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

PROJECT_ROOTS = {
    "backend": {
        "path": "/var/www/ai.sanaa.co/backend",
        "lang": "python",
        "linter": "ruff check --fix",
        "formatter": "ruff format",
        "unused_imports": "ruff check --select F401 --fix",
        "test_cmd": "python -m pytest --tb=short -q",
    },
    "frontend": {
        "path": "/var/www/ai.sanaa.co/frontend",
        "lang": "php",
        "linter": "vendor/bin/pint --test",
        "formatter": "vendor/bin/pint",
        "unused_imports": None,
        "test_cmd": "php artisan test --no-interaction",
    },
}

NOTES_FILE = "/var/www/ai.sanaa.co/quality-sweep-notes.md"


async def _run(args: list[str], cwd: str, timeout: int = 120) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "exit": proc.returncode,
            "stdout": (stdout or b"").decode("utf-8", errors="replace").strip()[-2000:],
            "stderr": (stderr or b"").decode("utf-8", errors="replace").strip()[-1000:],
        }
    except asyncio.TimeoutError:
        return {"exit": -1, "stdout": "", "stderr": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"exit": -1, "stdout": "", "stderr": str(e)}


async def _run_shell(cmd: str, cwd: str, timeout: int = 120) -> dict:
    """Execute a hardcoded shell pipeline via an explicit ["bash", "-c", cmd] list.

    Only used for internal commands that require pipes or redirections.
    Any user-influenced values must be sanitized before interpolation.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "exit": proc.returncode,
            "stdout": (stdout or b"").decode("utf-8", errors="replace").strip()[-2000:],
            "stderr": (stderr or b"").decode("utf-8", errors="replace").strip()[-1000:],
        }
    except asyncio.TimeoutError:
        return {"exit": -1, "stdout": "", "stderr": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"exit": -1, "stdout": "", "stderr": str(e)}


def _has_tool(cmd: str, cwd: str) -> bool:
    tool = cmd.split()[0]
    full = os.path.join(cwd, tool)
    if os.path.isfile(full) and os.access(full, os.X_OK):
        return True
    from shutil import which
    return which(tool) is not None


def _safe_glob(value: str) -> str:
    """Restrict file glob to alphanumerics and *?_.- to avoid shell injection."""
    if re.match(r"^[A-Za-z0-9_*?.\-]+$", value):
        return value
    raise ValueError(f"Invalid glob pattern: {value}")


class CodeQualitySkill(BaseSkill):
    name = "code_quality"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "report")
        target_dir = args.get("directory")
        auto_commit = args.get("auto_commit", False)
        dry_run = args.get("dry_run", False)

        if action == "report":
            return await self._report()
        elif action == "sweep":
            return await self._full_sweep(target_dir, auto_commit, dry_run)
        elif action == "lint":
            return await self._run_lint(target_dir, auto_commit, dry_run)
        elif action == "format":
            return await self._run_format(target_dir, auto_commit, dry_run)
        elif action == "dead_code":
            return await self._find_dead_code(target_dir)
        elif action == "unused_imports":
            return await self._fix_unused_imports(target_dir, auto_commit, dry_run)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _report(self) -> SkillResult:
        lines = ["## Code Quality Report\n"]
        for name, cfg in PROJECT_ROOTS.items():
            cwd = cfg["path"]
            if not os.path.isdir(cwd):
                lines.append(f"### {name}\n- Directory not found: {cwd}\n")
                continue

            lines.append(f"### {name} ({cfg['lang']})")

            # Check lint issues
            if cfg.get("linter"):
                check_cmd = cfg["linter"].replace("--fix", "").strip()
                r = await _run(shlex.split(check_cmd), cwd, timeout=60)
                issue_count = r["stdout"].count("\n") if r["exit"] != 0 else 0
                lines.append(f"- Lint issues: {issue_count if r['exit'] != 0 else 'clean'}")

            # Count files
            ext = "*.py" if cfg["lang"] == "python" else "*.php"
            r = await _run_shell(
                f"find . -name '{_safe_glob(ext)}' -not -path '*/vendor/*' -not -path '*/__pycache__/*' | wc -l",
                cwd,
                timeout=15,
            )
            lines.append(f"- Source files: {r['stdout'].strip()}")

            # Check for commented-out code blocks
            r = await _run_shell(
                f"grep -rn '# TODO\\|# FIXME\\|# HACK\\|# XXX' --include='{_safe_glob(ext)}' . 2>/dev/null | wc -l",
                cwd,
                timeout=15,
            )
            lines.append(f"- TODO/FIXME markers: {r['stdout'].strip()}")
            lines.append("")

        return SkillResult(success=True, output="\n".join(lines))

    async def _full_sweep(self, target_dir: str = None, auto_commit: bool = False, dry_run: bool = False) -> SkillResult:
        results = {"lint": [], "format": [], "unused_imports": [], "dead_code": [], "tests": []}
        notes = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        projects = self._get_projects(target_dir)

        for name, cfg in projects.items():
            cwd = cfg["path"]
            if not os.path.isdir(cwd):
                continue

            # 1. Lint with auto-fix
            if cfg.get("linter"):
                if dry_run:
                    check_cmd = cfg["linter"].replace("--fix", "").strip()
                    r = await _run(shlex.split(check_cmd), cwd, timeout=60)
                    results["lint"].append(f"{name}: {r['stdout'][:200] if r['exit'] != 0 else 'clean'}")
                else:
                    r = await _run(shlex.split(cfg["linter"]), cwd, timeout=60)
                    results["lint"].append(f"{name}: fixed (exit {r['exit']})")
                    if auto_commit and r["exit"] == 0:
                        await self._auto_commit(cwd, "style: auto-fix lint violations")

            # 2. Format
            if cfg.get("formatter"):
                if dry_run:
                    results["format"].append(f"{name}: dry-run (would format)")
                else:
                    r = await _run(shlex.split(cfg["formatter"]), cwd, timeout=60)
                    results["format"].append(f"{name}: formatted (exit {r['exit']})")
                    if auto_commit and r["exit"] == 0:
                        await self._auto_commit(cwd, "style: format code")

            # 3. Unused imports
            if cfg.get("unused_imports"):
                if dry_run:
                    results["unused_imports"].append(f"{name}: dry-run")
                else:
                    r = await _run(shlex.split(cfg["unused_imports"]), cwd, timeout=60)
                    results["unused_imports"].append(f"{name}: cleaned (exit {r['exit']})")
                    if auto_commit and r["exit"] == 0:
                        await self._auto_commit(cwd, "refactor: remove unused imports")

            # 4. Dead code scan
            if cfg["lang"] == "python":
                r = await _run_shell("grep -rn 'def \\|class ' --include='*.py' . | head -50", cwd, timeout=30)
                results["dead_code"].append(f"{name}: scanned")

            # 5. Run tests
            if cfg.get("test_cmd"):
                r = await _run(cfg["test_cmd"], cwd, timeout=120)
                passed = r["exit"] == 0
                results["tests"].append(f"{name}: {'PASS' if passed else 'FAIL'}")
                if not passed:
                    note = f"[{timestamp}] {name}: Test failure after sweep. stdout: {r['stdout'][:300]}"
                    notes.append(note)

        # Write notes
        if notes:
            with open(NOTES_FILE, "a") as f:
                f.write(f"\n## Sweep {timestamp}\n")
                for n in notes:
                    f.write(f"- {n}\n")

        # Build output
        out = f"## Code Quality Sweep {'(dry run)' if dry_run else ''}\n\n"
        for cat, items in results.items():
            if items:
                out += f"**{cat.replace('_', ' ').title()}:**\n"
                for item in items:
                    out += f"- {item}\n"
                out += "\n"

        if notes:
            out += f"**Notes:** {len(notes)} issue(s) logged to quality-sweep-notes.md\n"

        return SkillResult(success=True, output=out, data=results)

    async def _run_lint(self, target_dir: str = None, auto_commit: bool = False, dry_run: bool = False) -> SkillResult:
        projects = self._get_projects(target_dir)
        lines = []
        for name, cfg in projects.items():
            if not cfg.get("linter") or not os.path.isdir(cfg["path"]):
                continue
            cmd = cfg["linter"] if not dry_run else cfg["linter"].replace("--fix", "").strip()
            r = await _run(shlex.split(cmd), cfg["path"], timeout=60)
            lines.append(f"**{name}** (exit {r['exit']}):\n```\n{r['stdout'][:1000]}\n```")
        return SkillResult(success=True, output="\n\n".join(lines) or "No lintable projects found.")

    async def _run_format(self, target_dir: str = None, auto_commit: bool = False, dry_run: bool = False) -> SkillResult:
        projects = self._get_projects(target_dir)
        lines = []
        for name, cfg in projects.items():
            if not cfg.get("formatter") or not os.path.isdir(cfg["path"]):
                continue
            if dry_run:
                lines.append(f"**{name}**: would run `{cfg['formatter']}`")
            else:
                r = await _run(shlex.split(cfg["formatter"]), cfg["path"], timeout=60)
                lines.append(f"**{name}** (exit {r['exit']}):\n```\n{r['stdout'][:1000]}\n```")
        return SkillResult(success=True, output="\n\n".join(lines) or "No formattable projects found.")

    async def _fix_unused_imports(self, target_dir: str = None, auto_commit: bool = False, dry_run: bool = False) -> SkillResult:
        projects = self._get_projects(target_dir)
        lines = []
        for name, cfg in projects.items():
            if not cfg.get("unused_imports") or not os.path.isdir(cfg["path"]):
                continue
            r = await _run(shlex.split(cfg["unused_imports"]), cfg["path"], timeout=60)
            lines.append(f"**{name}** (exit {r['exit']}):\n```\n{r['stdout'][:1000]}\n```")
        return SkillResult(success=True, output="\n\n".join(lines) or "No import cleaners configured.")

    async def _find_dead_code(self, target_dir: str = None) -> SkillResult:
        projects = self._get_projects(target_dir)
        lines = []
        for name, cfg in projects.items():
            cwd = cfg["path"]
            if not os.path.isdir(cwd):
                continue
            if cfg["lang"] == "python":
                # Find commented-out blocks
                r = await _run_shell(
                    "grep -rn '^\\s*#.*def \\|^\\s*#.*class \\|^\\s*# TODO\\|^\\s*# FIXME\\|^\\s*# HACK' --include='*.py' . 2>/dev/null | head -30",
                    cwd, timeout=30
                )
                if r["stdout"]:
                    lines.append(f"**{name}** - commented code / markers:\n```\n{r['stdout']}\n```")
                else:
                    lines.append(f"**{name}**: no dead code patterns found")
            elif cfg["lang"] == "php":
                r = await _run_shell(
                    "grep -rn '// TODO\\|// FIXME\\|// HACK\\|/\\* TODO' --include='*.php' . 2>/dev/null | head -30",
                    cwd, timeout=30
                )
                if r["stdout"]:
                    lines.append(f"**{name}** - markers:\n```\n{r['stdout']}\n```")
                else:
                    lines.append(f"**{name}**: clean")
        return SkillResult(success=True, output="\n\n".join(lines) or "No dead code found.")

    async def _auto_commit(self, cwd: str, message: str) -> None:
        """Stage changes and commit only if there is something to commit."""
        await _run(["git", "add", "-A"], cwd, timeout=30)
        r = await _run(["git", "diff", "--cached", "--quiet"], cwd, timeout=30)
        if r["exit"] != 0:
            await _run(["git", "commit", "-m", message], cwd, timeout=30)

    def _get_projects(self, target_dir: str = None) -> dict:
        if target_dir:
            return {"custom": {
                "path": target_dir,
                "lang": "python" if os.path.exists(os.path.join(target_dir, "requirements.txt")) or os.path.exists(os.path.join(target_dir, "pyproject.toml")) else "php",
                "linter": "ruff check --fix" if os.path.exists(os.path.join(target_dir, "pyproject.toml")) else None,
                "formatter": "ruff format" if os.path.exists(os.path.join(target_dir, "pyproject.toml")) else None,
                "unused_imports": "ruff check --select F401 --fix" if os.path.exists(os.path.join(target_dir, "pyproject.toml")) else None,
                "test_cmd": None,
            }}
        return PROJECT_ROOTS
