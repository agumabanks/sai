"""Sanaa-native wrapper for the FX autonomous operations runtime."""

import asyncio
import json
import logging
from pathlib import Path

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

SKILL_ROOT = Path(__file__).resolve().parent
SCRIPT_PATH = SKILL_ROOT / "scripts" / "fx_autopilot.py"
INSTALLER_PATH = SKILL_ROOT / "scripts" / "install_systemd.sh"
CONTRACT_PATH = SKILL_ROOT / "references" / "fx-runtime-contract.md"
INCIDENT_LOG = Path("/var/lib/fx-autonomous-ops/incidents.jsonl")
REPO_ROOT = Path("/var/www/fx.sanaa.co/sanaa-fx/sanaa-fx")
PUBLIC_HOST = "fx.sanaa.co"


async def _run_exec(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "timeout"

    output = stdout.decode().strip()
    errors = stderr.decode().strip()
    return proc.returncode, output if output else errors


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


class FxAutonomousOpsSkill(BaseSkill):
    name = "fx_autonomous_ops"
    description = (
        "Monitor and self-heal fx.sanaa.co using a bounded action catalog and "
        "re-validation against the known runtime contract."
    )
    version = "1.0.0"
    permissions = ["shell", "network", "filesystem"]
    # Manifest keeps approval on for LLM/tool policy; dashboard/manual use is the approval gate.
    requires_approval = False
    timeout = 2100
    tags = ["fx", "operations", "monitoring", "self-heal", "infrastructure"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "dry_run")

        dispatch = {
            "run_once": self._run_once,
            "dry_run": self._dry_run,
            "validate": self._validate,
            "incidents": self._incidents,
            "install_timer": self._install_timer,
            "show_contract": self._show_contract,
        }

        handler = dispatch.get(action)
        if not handler:
            return SkillResult(success=False, error=f"Unknown action: {action}")

        return await handler(args)

    async def _run_once(self, args: dict) -> SkillResult:
        return await self._run_autopilot(dry_run=False, no_email=bool(args.get("no_email", False)))

    async def _dry_run(self, args: dict) -> SkillResult:
        return await self._run_autopilot(dry_run=True, no_email=bool(args.get("no_email", False)))

    async def _run_autopilot(self, dry_run: bool, no_email: bool) -> SkillResult:
        cmd = ["python3", str(SCRIPT_PATH), "--run-once"]
        if dry_run:
            cmd.append("--dry-run")
        if no_email:
            cmd.append("--no-email")

        rc, output = await _run_exec(cmd, timeout=self.timeout)
        headline = "FX autonomous ops completed." if rc == 0 else "FX autonomous ops reported an unhealthy stack."
        lines = [
            headline,
            "",
            output or "No output returned.",
            "",
            f"Script: {SCRIPT_PATH}",
            f"Contract: {CONTRACT_PATH}",
            f"Incident log: {INCIDENT_LOG}",
        ]
        return SkillResult(
            success=rc == 0,
            output="\n".join(lines).strip(),
            data={
                "dry_run": dry_run,
                "script_path": str(SCRIPT_PATH),
                "contract_path": str(CONTRACT_PATH),
                "incident_log": str(INCIDENT_LOG),
            },
        )

    async def _validate(self, args: dict) -> SkillResult:
        checks = [
            ("pnpm check:fx", ["pnpm", "check:fx"], REPO_ROOT, 180),
            ("public /en", ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"https://{PUBLIC_HOST}/en"], None, 45),
            ("public /", ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"https://{PUBLIC_HOST}/"], None, 45),
            ("public /api", ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"https://{PUBLIC_HOST}/api"], None, 45),
            ("pm2 ls", ["pm2", "ls"], None, 60),
        ]

        lines = ["FX validation", "=" * 40, ""]
        data = {}
        overall_ok = True

        for label, cmd, cwd, timeout in checks:
            rc, output = await _run_exec(cmd, cwd=cwd, timeout=timeout)
            if label == "pnpm check:fx":
                ok = rc == 0 and "CHECK PASSED" in output
            elif label == "public /en":
                ok = output == "200"
            elif label == "public /":
                ok = output in {"200", "307"}
            elif label == "public /api":
                ok = output == "200"
            else:
                ok = rc == 0 and "fx-frontend" in output and "fx-backend" in output

            overall_ok = overall_ok and ok
            data[label] = {"ok": ok, "output": output}
            lines.append(f"{label}: {'OK' if ok else 'FAILED'}")
            if output:
                lines.append(output[:3000])
            lines.append("")

        return SkillResult(success=overall_ok, output="\n".join(lines).strip(), data=data)

    async def _incidents(self, args: dict) -> SkillResult:
        limit = args.get("limit", 10)
        if not isinstance(limit, int):
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 10
        limit = max(1, min(limit, 50))

        if not INCIDENT_LOG.exists():
            return SkillResult(
                success=True,
                output=f"No incident history found yet at {INCIDENT_LOG}.",
                data={"count": 0, "incident_log": str(INCIDENT_LOG)},
            )

        records = []
        for raw in INCIDENT_LOG.read_text().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                continue

        records = records[-limit:]
        lines = [f"FX incident history ({len(records)} entries)", "=" * 40, ""]
        for record in reversed(records):
            actions = ", ".join(action.get("action", "unknown") for action in record.get("actions", [])) or "none"
            validation = record.get("validation", {})
            lines.append(
                f"{record.get('ts', 'unknown')} | {record.get('signature', 'unknown')} | "
                f"validation={'ok' if validation.get('ok') else 'failed'}"
            )
            lines.append(f"symptoms: {', '.join(record.get('symptoms', [])) or 'none'}")
            lines.append(f"actions: {actions}")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines).strip(),
            data={"count": len(records), "incident_log": str(INCIDENT_LOG)},
        )

    async def _install_timer(self, args: dict) -> SkillResult:
        cmd = ["bash", str(INSTALLER_PATH)]
        if args.get("enable_now"):
            cmd.append("--enable-now")
        if args.get("allow_without_email"):
            cmd.append("--allow-without-email")

        rc, output = await _run_exec(cmd, timeout=180)
        return SkillResult(
            success=rc == 0,
            output=output or "Installer returned no output.",
            data={
                "installer_path": str(INSTALLER_PATH),
                "enabled": bool(args.get("enable_now")),
                "allow_without_email": bool(args.get("allow_without_email")),
            },
        )

    async def _show_contract(self, args: dict) -> SkillResult:
        contract = _read_text(CONTRACT_PATH)
        skill_doc = _read_text(SKILL_ROOT / "SKILL.md")
        if not contract:
            return SkillResult(success=False, error=f"Contract reference missing: {CONTRACT_PATH}")

        lines = [
            "FX runtime contract",
            "=" * 40,
            "",
            contract,
        ]
        if skill_doc:
            lines.extend(["", "Sanaa skill notes", "=" * 40, "", skill_doc[:4000]])

        return SkillResult(
            success=True,
            output="\n".join(lines).strip(),
            data={
                "contract_path": str(CONTRACT_PATH),
                "skill_doc_path": str(SKILL_ROOT / 'SKILL.md'),
            },
        )
