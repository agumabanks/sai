"""
Finance Monitor Skill — cross-tenant operational intelligence for Sanaa Finance.

Connects directly to each tenant's MySQL database to pull real-time metrics,
check queue health, monitor arrears, SMS credits, and failed jobs.

This is the "central nervous system" for all finance tenants.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tenant discovery
# ---------------------------------------------------------------------------
TENANT_BASE = "/var/www"
NGINX_AVAILABLE = "/etc/nginx/sites-available"
NGINX_ENABLED = "/etc/nginx/sites-enabled"
DB_HOST = os.getenv("FINANCE_MYSQL_HOST", "127.0.0.1")
DB_PORT = os.getenv("FINANCE_MYSQL_PORT", "3306")
DB_USER = os.getenv("FINANCE_MYSQL_USER")
DB_PASS = os.getenv("FINANCE_MYSQL_PASS")


def _mysql_credentials_ok() -> bool:
    """Fail closed if finance MySQL credentials are not configured."""
    return bool(DB_USER and DB_PASS)


def _discover_tenants() -> list[dict]:
    """Find all active finance tenants by parsing nginx configs for mbalala roots."""
    tenants = []
    if not os.path.isdir(NGINX_AVAILABLE):
        return tenants

    for f in sorted(os.listdir(NGINX_AVAILABLE)):
        if not (f.endswith(".conf") and "sanaa" in f):
            continue

        domain = f.replace(".conf", "")
        enabled = os.path.islink(f"{NGINX_ENABLED}/{f}")
        if not enabled:
            continue

        # Parse the nginx config to find the actual root path
        conf_path = f"{NGINX_AVAILABLE}/{f}"
        app_root = None
        try:
            with open(conf_path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("root ") and "mbalala/public" in line:
                        # e.g. "root /var/www/finance/mbalala/public;"
                        root_path = line.split("root ", 1)[1].rstrip(";").strip()
                        # Go up from .../mbalala/public to .../mbalala
                        if root_path.endswith("/public"):
                            app_root = root_path[:-7]  # strip /public
                        break
        except Exception:
            continue

        if not app_root or not os.path.isdir(app_root):
            continue

        # Derive path (parent of mbalala) and app_name from .env DB_DATABASE
        path = os.path.dirname(app_root)
        app_name = domain.split(".")[0]

        # Try to read actual DB_DATABASE from .env
        env_file = f"{app_root}/.env"
        db_name = app_name
        if os.path.isfile(env_file):
            try:
                with open(env_file) as ef:
                    for line in ef:
                        if line.startswith("DB_DATABASE="):
                            db_name = line.strip().split("=", 1)[1]
                            break
            except Exception:
                pass

        tenants.append({
            "domain": domain,
            "app_name": db_name,  # use actual DB name
            "path": path,
            "app_root": app_root,
            "db": db_name,
        })
    return tenants


def _filter_tenants(tenants: list[dict], domain: str | None) -> list[dict]:
    if not domain:
        return tenants
    return [t for t in tenants if t["domain"] == domain]


async def _mysql(db: str, query: str, timeout: int = 10) -> tuple[int, str]:
    """Run a MySQL query using an explicit argument list and return (returncode, output)."""
    if not _mysql_credentials_ok():
        return -1, "finance mysql credentials not configured"

    # Validate db name to avoid accidental shell injection via legacy call sites.
    if not re.match(r"^[A-Za-z0-9_-]+$", db):
        return -1, f"invalid database name: {db}"

    proc = await asyncio.create_subprocess_exec(
        "mysql",
        "-h", DB_HOST,
        "-P", DB_PORT,
        "-u", DB_USER,
        f"-p{DB_PASS}",
        "-N",
        "-e", query,
        db,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "timeout"
    return proc.returncode, stdout.decode().strip()


async def _run(args: list[str], timeout: int = 15, cwd: str | None = None) -> tuple[int, str]:
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
    return proc.returncode or 0, stdout.decode().strip()


class FinanceMonitorSkill(BaseSkill):
    name = "finance_monitor"
    description = (
        "Cross-tenant monitoring for Sanaa Finance — metrics, failed jobs, "
        "queue health, scheduler status, arrears, SMS credits, portfolio overview."
    )
    version = "1.0.0"
    permissions = ["shell", "network"]
    requires_approval = False
    timeout = 60
    tags = ["monitoring", "finance", "tenant", "operations"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "overview")
        tenant_filter = args.get("tenant")
        limit = args.get("limit", 20)

        if not _mysql_credentials_ok():
            return SkillResult(
                success=False,
                error="Finance MySQL credentials not configured (FINANCE_MYSQL_USER / FINANCE_MYSQL_PASS)",
            )

        tenants = _discover_tenants()
        tenants = _filter_tenants(tenants, tenant_filter)

        if not tenants:
            return SkillResult(success=False, error="No finance tenants found")

        dispatch = {
            "overview": self._overview,
            "failed_jobs": self._failed_jobs,
            "queue_health": self._queue_health,
            "scheduler_check": self._scheduler_check,
            "arrears": self._arrears,
            "sms_credits": self._sms_credits,
            "metrics": self._metrics,
            "fix_failed_jobs": self._fix_failed_jobs,
            "daily_summary": self._daily_summary,
            "escalate_arrears": self._escalate_arrears,
            "risk_score": self._risk_score,
            "anomaly_detection": self._anomaly_detection,
        }

        handler = dispatch.get(action)
        if not handler:
            return SkillResult(success=False, error=f"Unknown action: {action}")

        return await handler(tenants, limit)

    # ------------------------------------------------------------------
    # overview — the big picture
    # ------------------------------------------------------------------
    async def _overview(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = [f"SANAA FINANCE — CENTRAL OVERVIEW ({len(tenants)} tenants)", "=" * 55, ""]
        all_data = {}
        alerts = []

        for t in tenants:
            db = t["db"]
            domain = t["domain"]
            data: dict = {"domain": domain}

            # Clients
            rc, out = await _mysql(db, "SELECT COUNT(*) FROM clients;")
            data["clients"] = int(out) if rc == 0 and out.isdigit() else 0

            # Active loans
            rc, out = await _mysql(db, "SELECT COUNT(*) FROM user_loans WHERE status='active';")
            data["active_loans"] = int(out) if rc == 0 and out.isdigit() else 0

            # Loan arrears
            rc, out = await _mysql(db, "SELECT COUNT(*) FROM loan_arrears WHERE resolved_at IS NULL;")
            data["open_arrears"] = int(out) if rc == 0 and out.isdigit() else 0

            # Failed jobs
            rc, out = await _mysql(db, "SELECT COUNT(*) FROM failed_jobs;")
            data["failed_jobs"] = int(out) if rc == 0 and out.isdigit() else 0

            # Total disbursed (this month)
            rc, out = await _mysql(db,
                "SELECT COALESCE(ROUND(SUM(amount),0),0) FROM user_loans WHERE MONTH(created_at)=MONTH(NOW()) AND YEAR(created_at)=YEAR(NOW());"
            )
            data["monthly_disbursed"] = out if rc == 0 else "N/A"

            # Total collections (this month)
            rc, out = await _mysql(db,
                "SELECT COALESCE(ROUND(SUM(total_amount),0),0) FROM loan_payments WHERE MONTH(created_at)=MONTH(NOW()) AND YEAR(created_at)=YEAR(NOW());"
            )
            data["monthly_collections"] = out if rc == 0 else "N/A"

            # Queue worker status
            rc, out = await _run(["supervisorctl", "status", f"{t['app_name']}-worker"])
            data["worker"] = "RUNNING" if "RUNNING" in (out.splitlines()[0] if out else "") else "DOWN"

            # Build alerts
            if data["failed_jobs"] > 0:
                alerts.append(f"  {domain}: {data['failed_jobs']} failed jobs")
            if data["open_arrears"] > 10:
                alerts.append(f"  {domain}: {data['open_arrears']} open arrears")
            if data["worker"] != "RUNNING":
                alerts.append(f"  {domain}: Queue worker DOWN")

            all_data[domain] = data

            lines.append(f"  {domain}")
            lines.append(f"    Clients: {data['clients']:>8,}    Active loans: {data['active_loans']:>6,}")
            lines.append(f"    Arrears: {data['open_arrears']:>8,}    Failed jobs:  {data['failed_jobs']:>6,}")
            lines.append(f"    Month disbursed: {data['monthly_disbursed']:>10}    Collections: {data['monthly_collections']:>10}")
            lines.append(f"    Worker: {data['worker']}")
            lines.append("")

        if alerts:
            lines.append("ALERTS:")
            lines.extend(alerts)
        else:
            lines.append("No alerts. All systems healthy.")

        has_issues = len(alerts) > 0
        return SkillResult(
            success=not has_issues,
            output="\n".join(lines),
            data={"tenants": all_data, "alerts": alerts, "tenant_count": len(tenants)},
        )

    # ------------------------------------------------------------------
    # failed_jobs — check failed_jobs table per tenant
    # ------------------------------------------------------------------
    async def _failed_jobs(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["FAILED JOBS ACROSS TENANTS", "=" * 40, ""]
        total = 0
        all_failures = {}

        for t in tenants:
            rc, out = await _mysql(t["db"],
                f"SELECT id, SUBSTRING(payload, 1, 80), failed_at FROM failed_jobs ORDER BY failed_at DESC LIMIT {limit};"
            )
            rc_count, count = await _mysql(t["db"], "SELECT COUNT(*) FROM failed_jobs;")
            count_num = int(count) if rc_count == 0 and count.isdigit() else 0
            total += count_num

            if count_num > 0:
                lines.append(f"  {t['domain']}: {count_num} failed jobs")
                if out:
                    for row in out.splitlines()[:5]:
                        lines.append(f"    {row}")
                lines.append("")
                all_failures[t["domain"]] = count_num

        if total == 0:
            lines.append("  No failed jobs across any tenant.")

        lines.append(f"\nTotal failed jobs: {total}")

        return SkillResult(
            success=total == 0,
            output="\n".join(lines),
            data={"total": total, "per_tenant": all_failures},
        )

    # ------------------------------------------------------------------
    # fix_failed_jobs — retry or flush
    # ------------------------------------------------------------------
    async def _fix_failed_jobs(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["RETRYING FAILED JOBS", "=" * 40, ""]
        retried = {}

        for t in tenants:
            rc_count, count = await _mysql(t["db"], "SELECT COUNT(*) FROM failed_jobs;")
            count_num = int(count) if rc_count == 0 and count.isdigit() else 0

            if count_num == 0:
                continue

            rc, out = await _run(
                ["php", f"{t['app_root']}/artisan", "queue:retry", "all"],
                cwd=t["app_root"],
                timeout=30,
            )
            retried[t["domain"]] = count_num
            lines.append(f"  {t['domain']}: retried {count_num} jobs — {'OK' if rc == 0 else out}")

        if not retried:
            lines.append("  No failed jobs to retry.")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={"retried": retried},
        )

    # ------------------------------------------------------------------
    # queue_health — supervisor + pending jobs
    # ------------------------------------------------------------------
    async def _queue_health(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["QUEUE WORKER HEALTH", "=" * 40, ""]
        all_ok = True
        statuses = {}

        for t in tenants:
            worker_name = f"{t['app_name']}-worker"
            rc, out = await _run(["supervisorctl", "status", worker_name])
            running = "RUNNING" in (out.splitlines()[0] if out else "")

            # Pending jobs count
            rc2, pending = await _mysql(t["db"],
                "SELECT COUNT(*) FROM jobs;"
            )
            pending_count = int(pending) if rc2 == 0 and pending.isdigit() else 0

            # Failed jobs count
            rc3, failed = await _mysql(t["db"], "SELECT COUNT(*) FROM failed_jobs;")
            failed_count = int(failed) if rc3 == 0 and failed.isdigit() else 0

            status = "OK" if running else "DOWN"
            if not running:
                all_ok = False

            statuses[t["domain"]] = {
                "worker": status,
                "pending": pending_count,
                "failed": failed_count,
            }

            lines.append(f"  {t['domain']}")
            lines.append(f"    Worker: {status:8s}  Pending: {pending_count:>5}  Failed: {failed_count:>5}")

        return SkillResult(
            success=all_ok,
            output="\n".join(lines),
            data=statuses,
        )

    # ------------------------------------------------------------------
    # scheduler_check — verify cron is active + last runs
    # ------------------------------------------------------------------
    async def _scheduler_check(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["SCHEDULER STATUS", "=" * 40, ""]
        all_ok = True

        # Check crontab entries
        rc, crontab = await _run(["crontab", "-l"])

        for t in tenants:
            has_cron = t["app_root"] in crontab if rc == 0 else False
            log_path = f"{t['app_root']}/storage/logs/scheduler.log"

            # Check last scheduler run from log
            last_run = "never"
            if os.path.isfile(log_path):
                rc2, tail = await _run(["tail", "-n", "1", log_path])
                if rc2 == 0 and tail:
                    last_run = tail[:60]

            # Check last backup
            rc3, backup_time = await _mysql(t["db"],
                "SELECT value FROM business_settings WHERE key='last_backup_time' LIMIT 1;"
            )
            last_backup = backup_time if rc3 == 0 and backup_time else "unknown"

            status = "OK" if has_cron else "NO CRON"
            if not has_cron:
                all_ok = False

            lines.append(f"  {t['domain']}")
            lines.append(f"    Cron entry: {status}")
            lines.append(f"    Last scheduler output: {last_run}")
            lines.append(f"    Last backup: {last_backup}")
            lines.append("")

        return SkillResult(
            success=all_ok,
            output="\n".join(lines),
        )

    # ------------------------------------------------------------------
    # arrears — open arrears across tenants
    # ------------------------------------------------------------------
    async def _arrears(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["LOAN ARREARS OVERVIEW", "=" * 40, ""]
        total_arrears = 0
        data = {}

        for t in tenants:
            # Count open arrears
            rc, count = await _mysql(t["db"],
                "SELECT COUNT(*) FROM loan_arrears WHERE resolved_at IS NULL;"
            )
            open_count = int(count) if rc == 0 and count.isdigit() else 0
            total_arrears += open_count

            # Arrears by age
            rc2, age_breakdown = await _mysql(t["db"], """
                SELECT
                    SUM(CASE WHEN DATEDIFF(NOW(), created_at) <= 7 THEN 1 ELSE 0 END) as '<=7d',
                    SUM(CASE WHEN DATEDIFF(NOW(), created_at) BETWEEN 8 AND 30 THEN 1 ELSE 0 END) as '8-30d',
                    SUM(CASE WHEN DATEDIFF(NOW(), created_at) BETWEEN 31 AND 90 THEN 1 ELSE 0 END) as '31-90d',
                    SUM(CASE WHEN DATEDIFF(NOW(), created_at) > 90 THEN 1 ELSE 0 END) as '>90d'
                FROM loan_arrears WHERE resolved_at IS NULL;
            """)

            data[t["domain"]] = {"open": open_count, "breakdown": age_breakdown}

            lines.append(f"  {t['domain']}: {open_count} open arrears")
            if age_breakdown and rc2 == 0:
                parts = age_breakdown.split("\t")
                if len(parts) == 4:
                    lines.append(f"    <=7d: {parts[0]}  |  8-30d: {parts[1]}  |  31-90d: {parts[2]}  |  >90d: {parts[3]}")
            lines.append("")

        lines.append(f"Total open arrears: {total_arrears}")

        return SkillResult(
            success=total_arrears < 50,  # alert threshold
            output="\n".join(lines),
            data={"total": total_arrears, "per_tenant": data},
        )

    # ------------------------------------------------------------------
    # sms_credits — SMS credit balance per tenant
    # ------------------------------------------------------------------
    async def _sms_credits(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["SMS CREDIT STATUS", "=" * 40, ""]
        alerts = []
        data = {}

        for t in tenants:
            # Check if SMS tables exist
            rc, out = await _mysql(t["db"],
                "SELECT SUM(credits) FROM sms_credit_transactions WHERE type='purchase';"
            )
            purchased = float(out) if rc == 0 and out and out != "NULL" else 0

            rc2, out2 = await _mysql(t["db"],
                "SELECT SUM(credits) FROM sms_credit_transactions WHERE type='usage';"
            )
            used = float(out2) if rc2 == 0 and out2 and out2 != "NULL" else 0

            balance = purchased - used

            # Recent sends
            rc3, sent_count = await _mysql(t["db"],
                "SELECT COUNT(*) FROM sms_logs WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY);"
            )
            recent_sends = int(sent_count) if rc3 == 0 and sent_count.isdigit() else 0

            data[t["domain"]] = {
                "balance": balance,
                "purchased": purchased,
                "used": used,
                "recent_sends_7d": recent_sends,
            }

            if balance < 100 and purchased > 0:
                alerts.append(f"  LOW: {t['domain']} has only {balance:.0f} credits remaining")

            lines.append(f"  {t['domain']}")
            lines.append(f"    Balance: {balance:>8.0f}    Purchased: {purchased:>8.0f}    Used: {used:>8.0f}")
            lines.append(f"    Sent (7d): {recent_sends}")
            lines.append("")

        if alerts:
            lines.append("ALERTS:")
            lines.extend(alerts)

        return SkillResult(
            success=len(alerts) == 0,
            output="\n".join(lines),
            data=data,
        )

    # ------------------------------------------------------------------
    # metrics — detailed financial metrics
    # ------------------------------------------------------------------
    async def _metrics(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["FINANCIAL METRICS", "=" * 55, ""]
        all_metrics = {}

        for t in tenants:
            db = t["db"]
            m: dict = {}

            queries = {
                "total_clients": "SELECT COUNT(*) FROM clients;",
                "active_loans": "SELECT COUNT(*) FROM user_loans WHERE status='active';",
                "total_loan_portfolio": "SELECT COALESCE(ROUND(SUM(amount),0),0) FROM user_loans WHERE status='active';",
                "monthly_disbursements": (
                    "SELECT COALESCE(ROUND(SUM(amount),0),0) FROM user_loans "
                    "WHERE MONTH(created_at)=MONTH(NOW()) AND YEAR(created_at)=YEAR(NOW());"
                ),
                "monthly_collections": (
                    "SELECT COALESCE(ROUND(SUM(total_amount),0),0) FROM loan_payments "
                    "WHERE MONTH(created_at)=MONTH(NOW()) AND YEAR(created_at)=YEAR(NOW());"
                ),
                "today_disbursements": (
                    "SELECT COALESCE(ROUND(SUM(amount),0),0) FROM user_loans "
                    "WHERE DATE(created_at)=CURDATE();"
                ),
                "today_collections": (
                    "SELECT COALESCE(ROUND(SUM(total_amount),0),0) FROM loan_payments "
                    "WHERE DATE(created_at)=CURDATE();"
                ),
                "open_arrears": "SELECT COUNT(*) FROM loan_arrears WHERE resolved_at IS NULL;",
                "active_agents": "SELECT COUNT(*) FROM users WHERE type=1 AND status='active';",
                "savings_balance": "SELECT COALESCE(ROUND(SUM(balance),0),0) FROM savings_accounts WHERE status='active';",
            }

            # Run all queries concurrently
            results = await asyncio.gather(
                *[_mysql(db, q) for q in queries.values()]
            )

            for (key, _), (rc, out) in zip(queries.items(), results):
                m[key] = out if rc == 0 and out else "0"

            all_metrics[t["domain"]] = m

            lines.append(f"  {t['domain']}")
            lines.append(f"    Clients:        {m['total_clients']:>10}     Agents:      {m['active_agents']:>8}")
            lines.append(f"    Active Loans:   {m['active_loans']:>10}     Portfolio:   {m['total_loan_portfolio']:>10}")
            lines.append(f"    Open Arrears:   {m['open_arrears']:>10}     Savings:     {m['savings_balance']:>10}")
            lines.append(f"    Today disbursed: {m['today_disbursements']:>9}     Today collected: {m['today_collections']:>7}")
            lines.append(f"    Month disbursed: {m['monthly_disbursements']:>9}     Month collected: {m['monthly_collections']:>7}")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data=all_metrics,
        )

    # ------------------------------------------------------------------
    # daily_summary — brief WhatsApp-friendly financial summary
    # ------------------------------------------------------------------
    async def _daily_summary(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["📅 *Sanaa Finance Daily Summary*", ""]
        overall_collected = 0
        overall_disbursed = 0

        for t in tenants:
            db = t["db"]
            # Today collections
            rc1, coll = await _mysql(db, "SELECT COALESCE(ROUND(SUM(total_amount),0),0) FROM loan_payments WHERE DATE(created_at)=CURDATE();")
            # Today disbursements
            rc2, disb = await _mysql(db, "SELECT COALESCE(ROUND(SUM(amount),0),0) FROM user_loans WHERE DATE(created_at)=CURDATE();")
            
            c = float(coll) if rc1 == 0 and coll else 0
            d = float(disb) if rc2 == 0 and disb else 0
            
            overall_collected += c
            overall_disbursed += d
            
            lines.append(f"🏢 *{t['domain']}*")
            lines.append(f"  • Collected: UGX {c:,.0f}")
            lines.append(f"  • Disbursed: UGX {d:,.0f}")
            lines.append("")

        lines.append("📊 *Total Across Platform*")
        lines.append(f"• Total Collected: UGX {overall_collected:,.0f}")
        lines.append(f"• Total Disbursed: UGX {overall_disbursed:,.0f}")
        
        return SkillResult(success=True, output="\n".join(lines), data={"collected": overall_collected, "disbursed": overall_disbursed})

    # ------------------------------------------------------------------
    # escalate_arrears — identify uncontacted bad arrears 
    # ------------------------------------------------------------------
    async def _escalate_arrears(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["⚠️ *Arrears Escalation Report*", "Loans > 14 days in arrears that need immediate action.", ""]
        found = False

        for t in tenants:
            rc, out = await _mysql(t["db"], f"""
                SELECT loan_id, DATEDIFF(NOW(), created_at) as days_late 
                FROM loan_arrears 
                WHERE resolved_at IS NULL AND DATEDIFF(NOW(), created_at) > 14 
                ORDER BY days_late DESC LIMIT {limit};
            """)
            if rc == 0 and out:
                found = True
                lines.append(f"🏢 *{t['domain']}*")
                for row in out.splitlines():
                    parts = row.split("\t")
                    if len(parts) == 2:
                        lines.append(f"  • Loan #{parts[0]} is {parts[1]} days late -> Schedule SMS Warning")
                lines.append("")

        if not found:
            lines.append("✅ No critical arrears (>14 days) found.")

        return SkillResult(success=True, output="\n".join(lines))

    # ------------------------------------------------------------------
    # risk_score — Portfolio heuristic risk analysis
    # ------------------------------------------------------------------
    async def _risk_score(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["🚨 *Portfolio Risk Scoring*", "Calculated risk index based on delayed payments vs total portfolio.", ""]
        
        for t in tenants:
            db = t["db"]
            rc1, active_count = await _mysql(db, "SELECT COUNT(*) FROM user_loans WHERE status='active';")
            rc2, arrear_count = await _mysql(db, "SELECT COUNT(DISTINCT loan_id) FROM loan_arrears WHERE resolved_at IS NULL;")
            
            ac = int(active_count) if rc1 == 0 and active_count.isdigit() else 0
            rr = int(arrear_count) if rc2 == 0 and arrear_count.isdigit() else 0
            
            risk_percent = (rr / ac * 100) if ac > 0 else 0
            
            status = "🟢 HEALTHY"
            if risk_percent > 15:
                status = "🔴 HIGH RISK"
            elif risk_percent > 5:
                status = "🟡 ELEVATED RISK"
            
            lines.append(f"🏢 *{t['domain']}*")
            lines.append(f"  • Active Loans: {ac}")
            lines.append(f"  • Loans in Arrears: {rr}")
            lines.append(f"  • Portfolio Risk Index: {risk_percent:.1f}% -> {status}")
            lines.append("")

        return SkillResult(success=True, output="\n".join(lines))

    # ------------------------------------------------------------------
    # anomaly_detection — Financial anomaly detection
    # ------------------------------------------------------------------
    async def _anomaly_detection(self, tenants: list[dict], limit: int) -> SkillResult:
        lines = ["🔍 *Financial Anomaly Detection*", "Looking for unusual transaction velocity or collection drops.", ""]
        anomalies_found = False

        for t in tenants:
            db = t["db"]
            
            # Check for sudden drop in collections today vs average daily this month
            rc1, today = await _mysql(db, "SELECT COALESCE(ROUND(SUM(total_amount),0),0) FROM loan_payments WHERE DATE(created_at)=CURDATE();")
            rc2, month_total = await _mysql(db, "SELECT COALESCE(ROUND(SUM(total_amount),0),0) FROM loan_payments WHERE MONTH(created_at)=MONTH(NOW()) AND YEAR(created_at)=YEAR(NOW());")
            
            today_coll = float(today) if rc1 == 0 and today else 0
            month_coll = float(month_total) if rc2 == 0 and month_total else 0
            
            day_of_month = datetime.now().day
            avg_daily = month_coll / day_of_month if day_of_month > 0 else 0
            
            # Anomaly: Today's collection is less than 20% of the daily average (and we're past 2 PM)
            if datetime.now().hour >= 14 and avg_daily > 100000 and today_coll < (avg_daily * 0.2):
                anomalies_found = True
                lines.append(f"🔴 *{t['domain']}*")
                lines.append(f"  • Unusually low collections today (UGX {today_coll:,.0f}) compared to daily average (UGX {avg_daily:,.0f}).")
                lines.append("")

        if not anomalies_found:
            lines.append("✅ No financial anomalies detected today.")

        return SkillResult(success=True, output="\n".join(lines))
