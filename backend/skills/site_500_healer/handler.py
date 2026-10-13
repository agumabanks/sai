"""
Site 500 Healer Skill — detect, diagnose and auto-fix HTTP 500 errors
across all Sanaa web properties.

Flow:
  1. scan    — curl every enabled nginx site; collect any 5xx responses
  2. diagnose— for each 5xx site, read its nginx error log + Laravel log
               to identify the root-cause pattern (PHP fatal, permissions,
               missing config, etc.)
  3. heal    — run a targeted fix sequence:
               a. Fix storage permissions (most common)
               b. Clear Laravel caches (config / route / view / opcache)
               c. Reload php8.4-fpm
               d. Re-check HTTP status
  4. report  — summarise what was found, what was done, and the final status
               (optional email to recipient)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Site catalogue — maps domain → Laravel app root (where artisan lives)
# ---------------------------------------------------------------------------

NGINX_AVAILABLE = "/etc/nginx/sites-available"
NGINX_ENABLED = "/etc/nginx/sites-enabled"
NGINX_LOG_DIR = "/var/log/nginx"

# Known Laravel app roots, keyed by domain.
# Discovered dynamically from nginx configs, but these are hard-coded overrides
# so we never miss the most important ones even if nginx config parsing fails.
KNOWN_LARAVEL_APPS: dict[str, str] = {
    "farzone.sanaa.co": "/var/www/farzone-sos",
    "ai.sanaa.co": "/var/www/ai.sanaa.co/frontend",
    "soko.sanaa.co": "/var/www/soko/apps/backend-laravel",
    "baraka.sanaa.co": "/var/www/baraka.sanaa.co",
}

# Finance tenant sub-sites (mbalala pattern)
FINANCE_TENANTS: dict[str, str] = {
    "finance.sanaa.co": "/var/www/finance/mbalala",
    "kalamba.sanaa.co": "/var/www/kalamba.sanaa.co/mbalala",
    "kasawo.sanaa.ug": "/var/www/kasawo.sanaa.ug/mbalala",
    "bukuya.sanaa.ug": "/var/www/bukuya.sanaa.ug/mbalala",
    "bweyale.sanaa.ug": "/var/www/bweyale.sanaa.ug/mbalala",
    "kijura.sanaa.ug": "/var/www/kijura.sanaa.ug/mbalala",
    "kyaliwajjala.sanaa.ug": "/var/www/kyaliwajjala.sanaa.ug/mbalala",
    "mityana.sanaa.ug": "/var/www/mityana.sanaa.ug/mbalala",
    "mafubira.sanaa.co": "/var/www/mafubira.sanaa.co/mbalala",
    "mslink.sanaa.ug": "/var/www/mslink.sanaa.ug/mbalala",
}

ALL_LARAVEL_APPS = {**KNOWN_LARAVEL_APPS, **FINANCE_TENANTS}

# ---------------------------------------------------------------------------
# Known error patterns and their diagnoses
# ---------------------------------------------------------------------------

ERROR_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"Cannot redeclare (non static|static) .+::\$(\w+) as (static|non static)", re.I),
        "php_static_property",
        "PHP fatal: static property redeclaration (PHP 8.4 incompatibility)",
    ),
    (
        re.compile(r"PHP Fatal error", re.I),
        "php_fatal",
        "PHP fatal error",
    ),
    (
        re.compile(r"No space left on device", re.I),
        "disk_full",
        "Disk full",
    ),
    (
        re.compile(r"(storage|bootstrap/cache|storage/framework).*(Permission denied|not writable)", re.I),
        "permissions",
        "Storage directory not writable (run as root / wrong owner)",
    ),
    (
        re.compile(r"Class .+ not found", re.I),
        "autoload",
        "Class not found — composer autoload may be stale",
    ),
    (
        re.compile(r"SQLSTATE\[", re.I),
        "database",
        "Database error",
    ),
    (
        re.compile(r"Connection refused|ECONNREFUSED", re.I),
        "connection",
        "Service connection refused (Redis / DB / queue)",
    ),
    (
        re.compile(r"(Allowed memory size|memory exhausted)", re.I),
        "memory",
        "PHP memory limit exhausted",
    ),
]


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

async def _run(args: list[str], timeout: int = 20, cwd: str | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "timeout"
    out = stdout.decode(errors="replace").strip()
    if not out:
        out = stderr.decode(errors="replace").strip()
    return proc.returncode or 0, out


# ---------------------------------------------------------------------------
# Site discovery
# ---------------------------------------------------------------------------

def _discover_enabled_sites() -> list[str]:
    """Return all domains with an enabled nginx site config."""
    domains = []
    enabled_dir = NGINX_ENABLED
    if not os.path.isdir(enabled_dir):
        return domains
    for fname in sorted(os.listdir(enabled_dir)):
        if fname in ("default",) or fname.startswith("."):
            continue
        domain = fname.replace(".conf", "")
        domains.append(domain)
    return domains


def _laravel_root(domain: str) -> Optional[str]:
    """Return the Laravel project root for a domain, or None if not a Laravel app."""
    if domain in ALL_LARAVEL_APPS:
        root = ALL_LARAVEL_APPS[domain]
        if os.path.isfile(f"{root}/artisan"):
            return root
    # Fall back to nginx config root parsing
    conf = f"{NGINX_AVAILABLE}/{domain}.conf"
    if os.path.isfile(conf):
        try:
            content = Path(conf).read_text()
            m = re.search(r"root\s+([^;]+);", content)
            if m:
                root = m.group(1).strip().rstrip("/public").rstrip("/")
                if os.path.isfile(f"{root}/artisan"):
                    return root
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Log reading
# ---------------------------------------------------------------------------

def _read_nginx_error_log(domain: str, lines: int = 30) -> str:
    candidates = [
        f"{NGINX_LOG_DIR}/{domain}.error.log",
        f"{NGINX_LOG_DIR}/error.log",
    ]
    for log_path in candidates:
        if os.path.isfile(log_path):
            try:
                result = subprocess.run(
                    ["tail", "-n", str(lines), log_path],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip():
                    return result.stdout.strip()
            except Exception:
                pass
    return ""


def _read_laravel_log(app_root: str, lines: int = 30) -> str:
    log_path = f"{app_root}/storage/logs/laravel.log"
    if not os.path.isfile(log_path):
        return ""
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), log_path],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _diagnose(nginx_log: str, laravel_log: str) -> list[dict]:
    """Return a list of matched diagnoses from error log content."""
    combined = f"{nginx_log}\n{laravel_log}"
    found = []
    seen_types = set()
    for pattern, err_type, description in ERROR_PATTERNS:
        if err_type in seen_types:
            continue
        m = pattern.search(combined)
        if m:
            found.append({
                "type": err_type,
                "description": description,
                "snippet": combined[max(0, m.start() - 20): m.end() + 80].replace("\n", " "),
            })
            seen_types.add(err_type)
    return found


# ---------------------------------------------------------------------------
# HTTP check
# ---------------------------------------------------------------------------

async def _http_check(domain: str) -> str:
    """Return HTTP status code string for the domain's root URL."""
    _, code = await _run(
        [
            "curl", "-sSL", "-o", "/dev/null",
            "-w", "%{http_code}",
            "--max-time", "10",
            f"https://{domain}/",
        ],
        timeout=15,
    )
    return code.strip("'").strip()


# ---------------------------------------------------------------------------
# Healing actions
# ---------------------------------------------------------------------------

async def _heal_site(domain: str, app_root: str, diagnoses: list[dict]) -> list[dict]:
    """
    Run a sequence of healing actions for a site. Returns list of action results.
    """
    actions: list[dict] = []
    err_types = {d["type"] for d in diagnoses}

    storage_paths = [f"{app_root}/storage", f"{app_root}/bootstrap/cache"]

    # 1. Fix storage permissions (always safe to run)
    _, out = await _run(["chown", "-R", "www-data:www-data", *storage_paths], timeout=15)
    _, out2 = await _run(["chmod", "-R", "775", *storage_paths], timeout=15)
    actions.append({"step": "fix_permissions", "output": (out or "ok") + "\n" + (out2 or "ok")})

    # 2. Clear Laravel caches
    php_bin = "/usr/bin/php"
    artisan = f"{app_root}/artisan"
    if os.path.isfile(artisan):
        for cache_cmd in ["config:clear", "cache:clear", "route:clear", "view:clear"]:
            rc, out = await _run([php_bin, artisan, cache_cmd], cwd=app_root, timeout=15)
            actions.append({"step": f"artisan_{cache_cmd.replace(':', '_')}", "rc": rc, "output": out[:200]})

        # 3. Boot-check — does the app boot cleanly?
        rc, boot_out = await _run([php_bin, artisan, "about", "--only=environment"], cwd=app_root, timeout=20)
        actions.append({"step": "boot_check", "rc": rc, "output": boot_out[:300], "ok": rc == 0})

    # 4. Reload php-fpm (safe — graceful reload, no dropped connections)
    rc, out = await _run(["systemctl", "reload", "php8.4-fpm"], timeout=15)
    actions.append({"step": "reload_php_fpm", "rc": rc, "output": out or "ok"})

    # 5. If composer autoload issue — regenerate
    if "autoload" in err_types:
        rc, out = await _run(["composer", "dump-autoload", "--no-interaction"], cwd=app_root, timeout=60)
        actions.append({"step": "composer_dump_autoload", "rc": rc, "output": out[:300]})

    return actions


# ---------------------------------------------------------------------------
# Main skill
# ---------------------------------------------------------------------------

class Site500HealerSkill(BaseSkill):
    name = "site_500_healer"
    description = (
        "Detects HTTP 500 errors across Sanaa sites, diagnoses root causes from "
        "nginx and Laravel logs, auto-heals (cache clear, permissions, php-fpm reload), "
        "and reports what was fixed."
    )
    version = "1.0.0"
    permissions = ["shell", "filesystem", "network"]
    timeout = 120
    tags = ["monitoring", "healing", "laravel", "php", "500", "errors"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "scan")
        target_domain = args.get("domain", "")
        send_report = args.get("send_report", False)
        recipient = args.get("recipient", "")

        try:
            if action == "check":
                if not target_domain:
                    return SkillResult(success=False, error="domain is required for action=check")
                code = await _http_check(target_domain)
                ok = code in ("200", "301", "302")
                icon = "✅" if ok else "🔴"
                return SkillResult(
                    success=True,
                    output=f"{icon} {target_domain} → HTTP {code}",
                    data={"domain": target_domain, "http_code": code, "ok": ok},
                )

            elif action in ("scan", "heal"):
                domains = [target_domain] if target_domain else _discover_enabled_sites()
                results = await self._scan_and_optionally_heal(
                    domains, do_heal=(action == "heal")
                )

                output = self._format_report(results, action)

                if send_report and recipient:
                    await self._email_report(output, recipient, action)

                any_500 = any(r.get("http_code", "").startswith("5") for r in results)
                return SkillResult(
                    success=True,
                    output=output,
                    data={"sites": results, "has_500": any_500},
                )

            else:
                return SkillResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            logger.error(f"site_500_healer [{action}] failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))

    # ------------------------------------------------------------------

    async def _scan_and_optionally_heal(
        self, domains: list[str], do_heal: bool
    ) -> list[dict]:
        results = []

        # Run all HTTP checks concurrently
        codes = await asyncio.gather(*[_http_check(d) for d in domains])

        for domain, code in zip(domains, codes):
            entry: dict = {"domain": domain, "http_code": code}
            is_5xx = code.startswith("5")

            if is_5xx:
                # Read logs
                nginx_log = _read_nginx_error_log(domain)
                app_root = _laravel_root(domain)
                laravel_log = _read_laravel_log(app_root) if app_root else ""

                diagnoses = _diagnose(nginx_log, laravel_log)
                entry["diagnoses"] = diagnoses
                entry["nginx_log_tail"] = nginx_log[-500:] if nginx_log else ""
                entry["laravel_log_tail"] = laravel_log[-500:] if laravel_log else ""
                entry["app_root"] = app_root or ""

                if do_heal and app_root:
                    heal_actions = await _heal_site(domain, app_root, diagnoses)
                    entry["heal_actions"] = heal_actions

                    # Re-check after healing
                    await asyncio.sleep(1)
                    new_code = await _http_check(domain)
                    entry["http_code_after_heal"] = new_code
                    entry["healed"] = not new_code.startswith("5")

            results.append(entry)

        return results

    def _format_report(self, results: list[dict], action: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"🏥 **Site {'Heal' if action == 'heal' else 'Scan'} Report** — {now}\n"]

        ok_sites = [r for r in results if not r["http_code"].startswith("5")]
        bad_sites = [r for r in results if r["http_code"].startswith("5")]

        lines.append(f"Checked **{len(results)} site(s)** — ✅ {len(ok_sites)} OK · 🔴 {len(bad_sites)} with 5xx\n")

        for r in bad_sites:
            domain = r["domain"]
            code = r["http_code"]
            lines.append(f"---\n🔴 **{domain}** — HTTP {code}")

            for d in r.get("diagnoses", []):
                lines.append(f"  🔎 Diagnosis: {d['description']}")
                lines.append(f"     `{d['snippet'][:120]}`")

            if not r.get("diagnoses"):
                lines.append("  🔎 No known pattern matched — manual review needed")

            if action == "heal":
                for a in r.get("heal_actions", []):
                    step = a["step"]
                    rc = a.get("rc", 0)
                    ok = rc == 0
                    icon = "✅" if ok else "⚠️"
                    out = a.get("output", "")[:100]
                    lines.append(f"  {icon} {step}: {out}")

                after = r.get("http_code_after_heal", code)
                healed = r.get("healed", False)
                if healed:
                    lines.append(f"  ✅ **Resolved** — now returning HTTP {after}")
                else:
                    lines.append(f"  ⚠️ **Still returning {after}** — manual intervention needed")

        if not bad_sites:
            lines.append("✅ All sites are returning 2xx/3xx — no issues detected.")

        return "\n".join(lines)

    async def _email_report(self, body: str, recipient: str, action: str) -> None:
        try:
            from core.alerts.email_sender import send_alert_email
            await send_alert_email(
                subject=f"[Sanaa AI] Site {'Heal' if action == 'heal' else 'Scan'} Report — {datetime.now().strftime('%Y-%m-%d')}",
                body=body,
                recipients=[r.strip() for r in recipient.split(",")],
                category="monitoring",
            )
        except Exception as e:
            logger.warning(f"site_500_healer: email report failed: {e}")
