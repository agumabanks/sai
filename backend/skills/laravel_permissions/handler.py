"""
Laravel Permissions Skill

Detects root-owned files inside Laravel storage/ and bootstrap/cache/ directories
that prevent PHP-FPM (www-data) from writing logs — the root cause of 500 errors
on routes that call Log::info() (e.g. the /login page on soko24.co).

Actions:
  check         — scan and report drift without touching anything
  fix           — run the shared repair script to restore correct ownership
  check_and_fix — scan, report, then fix if any drift found (default)
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

REPAIR_SCRIPT = "/usr/local/sbin/repair_finance_tenant_permissions.sh"


async def _run(args: list[str], timeout: int = 30) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "timeout"
    out = stdout.decode().strip()
    err = stderr.decode().strip()
    return proc.returncode or 0, out if out else err

# All Laravel apps whose storage must stay www-data owned.
# Matches what repair_finance_tenant_permissions.sh covers.
KNOWN_APP_ROOTS = [
    "/var/www/soko/apps/backend-laravel",
    "/var/www/finance/mbalala",
    "/var/www/kalamba.sanaa.co/mbalala",
    "/var/www/bukuya.sanaa.ug/mbalala",
    "/var/www/kasawo.sanaa.ug/mbalala",
    "/var/www/mityana.sanaa.ug/mbalala",
    "/var/www/kyaliwajjala.sanaa.ug/mbalala",
    "/var/www/mslink.sanaa.ug/mbalala",
    "/var/www/kijura.sanaa.ug/mbalala",
    "/var/www/bweyale.sanaa.ug/mbalala",
    "/var/www/bukomero.sanaa.co/mbalala",
    "/var/www/mafubira.sanaa.co/mbalala",
]


def _find_drifted_files(app_root: str) -> list[dict]:
    """Return files inside storage/ and bootstrap/cache/ not owned by www-data."""
    drifted = []
    for subdir in ("storage", "bootstrap/cache"):
        path = os.path.join(app_root, subdir)
        if not os.path.isdir(path):
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            for name in filenames:
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                    # uid 33 = www-data on Debian/Ubuntu
                    if st.st_uid != 33:
                        import pwd
                        try:
                            owner = pwd.getpwuid(st.st_uid).pw_name
                        except KeyError:
                            owner = str(st.st_uid)
                        drifted.append({"path": full, "owner": owner})
                except OSError:
                    pass
    return drifted


class LaravelPermissionsSkill(BaseSkill):
    name = "laravel_permissions"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "check_and_fix")
        specific_root = args.get("app_root")

        roots = [specific_root] if specific_root else KNOWN_APP_ROOTS
        roots = [r for r in roots if os.path.isdir(r)]

        if not roots:
            return SkillResult(
                success=False,
                error=f"No valid app roots found. Checked: {specific_root or KNOWN_APP_ROOTS}",
            )

        # ── CHECK ─────────────────────────────────────────────────────────────
        drift_by_app: dict[str, list] = {}
        for root in roots:
            drifted = await asyncio.get_event_loop().run_in_executor(
                None, _find_drifted_files, root
            )
            if drifted:
                drift_by_app[root] = drifted

        total_drifted = sum(len(v) for v in drift_by_app.values())

        if action == "check":
            if not drift_by_app:
                return SkillResult(
                    success=True,
                    output="✅ All Laravel storage paths are correctly owned by www-data.",
                    data={"drifted_count": 0, "apps_checked": len(roots)},
                )
            lines = [f"⚠️ Permission drift found in {len(drift_by_app)} app(s) — {total_drifted} file(s) not owned by www-data:\n"]
            for app, files in drift_by_app.items():
                lines.append(f"**{app}** ({len(files)} files):")
                for f in files[:5]:
                    lines.append(f"  - {f['path']} (owner: {f['owner']})")
                if len(files) > 5:
                    lines.append(f"  ... and {len(files) - 5} more")
            return SkillResult(
                success=True,
                output="\n".join(lines),
                data={"drifted_count": total_drifted, "drift_by_app": {k: len(v) for k, v in drift_by_app.items()}},
            )

        # ── FIX / CHECK_AND_FIX ───────────────────────────────────────────────
        if action == "check_and_fix" and not drift_by_app:
            return SkillResult(
                success=True,
                output="✅ All Laravel storage paths are correctly owned by www-data. Nothing to fix.",
                data={"drifted_count": 0, "fixed": 0},
            )

        # Run the repair script (covers all known apps in one pass)
        if not os.path.isfile(REPAIR_SCRIPT):
            return SkillResult(
                success=False,
                error=f"Repair script not found: {REPAIR_SCRIPT}",
                data={"drifted_before": total_drifted},
            )
        rc, output = await _run(["bash", REPAIR_SCRIPT], timeout=55)
        if rc != 0:
            return SkillResult(
                success=False,
                error=f"Repair script exited {rc}: {output}",
                data={"drifted_before": total_drifted},
            )

        # Re-check to confirm
        remaining: dict[str, list] = {}
        for root in roots:
            drifted = await asyncio.get_event_loop().run_in_executor(
                None, _find_drifted_files, root
            )
            if drifted:
                remaining[root] = drifted

        total_remaining = sum(len(v) for v in remaining.values())
        fixed = total_drifted - total_remaining
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if total_remaining == 0:
            summary = (
                f"✅ Laravel permissions repaired at {ts}.\n"
                f"  - {total_drifted} file(s) were drifted across {len(drift_by_app)} app(s)\n"
                f"  - {fixed} file(s) fixed, 0 remaining"
            )
        else:
            summary = (
                f"⚠️ Repair ran at {ts} but {total_remaining} file(s) still have wrong ownership.\n"
                f"  - Fixed: {fixed}, Still drifted: {total_remaining}\n"
                "  Manual intervention may be needed."
            )

        return SkillResult(
            success=total_remaining == 0,
            output=summary,
            data={
                "drifted_before": total_drifted,
                "fixed": fixed,
                "remaining": total_remaining,
            },
        )


handler = LaravelPermissionsSkill
