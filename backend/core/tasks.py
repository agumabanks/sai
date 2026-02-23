"""Celery tasks — the heartbeat of Sanaa AI"""


from celery import Celery
from celery.schedules import crontab
import os
import json

app = Celery('sanaa_ai', broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"))

app.conf.timezone = 'Africa/Kampala'

app.conf.beat_schedule = {

    # ===== EVERY 2 MINUTES — WATCHDOG =====
    'watchdog-check': {
        'task': 'core.tasks.watchdog_check',
        'schedule': 120,  # 2 minutes — high frequency for critical monitoring
    },

    # ===== EVERY 5 MINUTES =====
    'server-health-check': {
        'task': 'core.tasks.check_server_health',
        'schedule': 300,  # 5 minutes
    },

    # ===== EVERY 15 MINUTES =====
    'app-error-scan': {
        'task': 'core.tasks.scan_app_errors',
        'schedule': 900,  # 15 minutes
    },

    'webapp-uptime-test': {
        'task': 'core.tasks.test_webapp_uptime',
        'schedule': 900,
    },

    # ===== EVERY HOUR =====
    'email-inbox-check': {
        'task': 'core.tasks.check_email_inbox',
        'schedule': 3600,
    },

    # ===== DAILY =====
    'morning-report': {
        'task': 'core.tasks.send_daily_report',
        'schedule': crontab(hour=7, minute=0),  # 7 AM EAT
    },

    # ===== DAILY MAINTENANCE =====
    'memory-prune': {
        'task': 'core.tasks.memory_prune',
        'schedule': crontab(hour=2, minute=0),  # 2 AM EAT — prune stale memories
    },
    'intelligence-scan': {
        'task': 'core.tasks.intelligence_scan',
        'schedule': crontab(hour=3, minute=0),  # 3 AM EAT — domain intelligence refresh
    },
    'llm-usage-report': {
        'task': 'core.tasks.llm_usage_report',
        'schedule': crontab(hour=6, minute=0),  # 6 AM EAT — summarize LLM usage
    },
}


def _run_async(coro):
    """Helper to run async code in Celery sync tasks."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@app.task
def watchdog_check():
    """Run watchdog check + self-healing cycle. Runs every 2 minutes."""
    from core.agents.watchdog import ServerWatchdog
    from core.agents.healer import SelfHealer
    from core.agents.report_agent import ReportAgent

    async def _run():
        wd = ServerWatchdog()
        heal = SelfHealer()
        reporter = ReportAgent()

        events, checked_metrics = await wd.run_full_check()

        # Always process events (even if empty) to allow SelfHealer to detect recoveries 
        # and reset failure escalation counters in the database.
        actions = await heal.process_events(events, checked_metrics)

        # Persist critical/high alerts to database
        from core.database import Alert, AuditLog
        for e in events:
            if e.severity in ("critical", "high"):
                await Alert.create(
                    severity=e.severity,
                    message=e.message,
                    metric=e.metric,
                )

        # Log healing actions
        for a in actions:
            await AuditLog.log(
                actor="watchdog:healer",
                action=f"auto_heal.{a['action']}",
                resource=a.get("target", ""),
                details={"output": a.get("output", ""), "trigger": a.get("trigger", "")},
                success=a.get("success", False),
            )

        # Ask sanaa-clade for an operator-grade RCA / prediction summary (OpenClaw-style advisor)
        try:
            from core.config import get_settings
            from core.brain.sanaa_clade_bridge import SanaaCladeBridge
            from core.database import SystemKnowledge
            from datetime import datetime, timezone

            cfg = get_settings()
            if cfg.sanaa_clade_enabled:
                bridge = SanaaCladeBridge()
                if bridge.is_available():
                    compact_events = [
                        {
                            "category": e.category,
                            "severity": e.severity,
                            "metric": e.metric,
                            "message": e.message,
                            "value": e.value,
                        }
                        for e in events[:20]
                    ]
                    prompt = (
                        "You are Sanaa AI Operations Brain. Analyze this watchdog cycle and produce a short JSON object with: "
                        "root_cause_hypothesis, predict_next_risk, immediate_actions (list), preventive_actions (list), confidence (1-10).\n\n"
                        f"WATCHDOG_EVENTS={json.dumps(compact_events)}\n"
                        f"HEALER_ACTIONS={json.dumps(actions[:20])}\n"
                        f"CHECKED_METRICS={json.dumps(checked_metrics[:50])}"
                    )
                    advisor = await bridge.ask(prompt)
                    if advisor.success and advisor.output:
                        advisor_payload = advisor.output
                        try:
                            parsed = json.loads(advisor.output)
                            if isinstance(parsed, dict):
                                parsed.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
                                advisor_payload = json.dumps(parsed)
                                await SystemKnowledge.set_pref(
                                    f"watchdog.advisor.history.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                                    advisor_payload,
                                    source="watchdog:sanaa_clade",
                                    domain="wisdom",
                                )
                        except Exception:
                            pass
                        await SystemKnowledge.set_pref(
                            "watchdog.advisor.latest",
                            advisor_payload,
                            source="watchdog:sanaa_clade",
                            domain="wisdom",
                        )
                        await AuditLog.log(
                            actor="watchdog:sanaa_clade",
                            action="watchdog.advisory.generated",
                            resource="watchdog",
                            details={"latency_ms": advisor.latency_ms, "summary": advisor.output[:500]},
                            success=True,
                        )
        except Exception:
            # Advisory is best-effort only; never break monitoring loop.
            pass

        # Email alert for critical events
        critical = [e for e in events if e.severity == "critical"]
        if critical:
            body = "CRITICAL SERVER ALERTS:\n\n"
            for e in critical:
                body += f"[{e.category}] {e.message}\n"
                if e.remediation:
                    body += f"  Fix: {e.remediation}\n"
                body += "\n"

            if actions:
                body += "\nAUTO-HEALING ACTIONS:\n"
                for a in actions:
                    status = "OK" if a.get("success") else "FAILED"
                    body += f"  - {a['action']} on {a.get('target','')} — {status}\n"

            await reporter.send_alert_email(
                subject=f"[Sanaa AI] CRITICAL: {len(critical)} server issue(s) detected",
                body=body,
            )

        # Also email for high-severity
        high = [e for e in events if e.severity == "high" and e not in critical]
        if high and not critical:
            body = "HIGH PRIORITY ALERTS:\n\n"
            for e in high:
                body += f"[{e.category}] {e.message}\n"
            await reporter.send_alert_email(
                subject=f"[Sanaa AI] WARNING: {len(high)} issue(s) need attention",
                body=body,
            )

    _run_async(_run())


@app.task
def check_server_health():
    """Check server health and alert if thresholds exceeded"""
    from core.agents.server_health import ServerHealthAgent
    from core.agents.report_agent import ReportAgent

    async def _run():
        agent = ServerHealthAgent()
        reporter = ReportAgent()
        alerts = await agent.get_alerts()

        if alerts:
            critical = [a for a in alerts if a["severity"] == "critical"]
            if critical:
                body = "CRITICAL ALERTS:\n\n" + "\n".join(
                    f"- {a['message']}" for a in critical
                )
                await reporter.send_alert_email(
                    subject="[Sanaa AI] CRITICAL SERVER ALERT",
                    body=body
                )

    _run_async(_run())


@app.task
def scan_app_errors():
    """Scan logs for new errors"""
    from core.agents.app_monitor import AppMonitorAgent
    from core.agents.report_agent import ReportAgent

    async def _run():
        monitor = AppMonitorAgent()
        reporter = ReportAgent()
        errors = await monitor.scan_for_new_errors()

        if errors:
            body = f"{len(errors)} new error(s) detected:\n\n"
            for err in errors[:5]:
                body += f"- [{err['app']}] {err.get('raw','error')[:200]}\n"

            await reporter.send_alert_email(
                subject=f"[Sanaa AI] {len(errors)} App Error(s) Detected",
                body=body
            )

    _run_async(_run())


@app.task
def test_webapp_uptime():
    """Test all Sanaa webapps are responding"""
    from core.agents.web_test_agent import WebTestAgent
    from core.agents.report_agent import ReportAgent

    async def _run():
        tester = WebTestAgent()
        reporter = ReportAgent()
        results = await tester.test_all()

        down = [r for r in results if r["status"] != "up"]
        if down:
            body = "WEBAPP(S) DOWN:\n\n" + "\n".join(
                f"- {r['url']} -- {r.get('error', 'Unknown error')}" for r in down
            )
            await reporter.send_alert_email(
                subject="[Sanaa AI] Webapp Down!",
                body=body
            )

    _run_async(_run())


@app.task
def send_daily_report():
    """Compile and send the daily morning report"""
    from core.agents.server_health import ServerHealthAgent
    from core.agents.email_agent import EmailInboxAgent
    from core.agents.news_agent import NewsAgent
    from core.agents.report_agent import ReportAgent

    async def _run():
        health = await ServerHealthAgent().get_snapshot()
        alerts = await ServerHealthAgent().get_alerts()
        try:
            email_summary = await EmailInboxAgent().get_inbox_summary()
        except:
            email_summary = "Email check failed"

        try:
            news = await NewsAgent().get_daily_summary()
        except:
            news = "News fetch failed"

        await ReportAgent().send_daily_report(health, alerts, email_summary, news)

    _run_async(_run())


@app.task
def check_email_inbox():
    """Check email inbox"""
    from core.agents.email_agent import EmailInboxAgent

    async def _run():
        agent = EmailInboxAgent()
        await agent.check_and_log()

    _run_async(_run())


@app.task
def memory_prune():
    """Prune stale agent memories — runs daily at 2 AM."""
    async def _run():
        from core.memory import MemoryManager
        from core.database import AuditLog

        manager = MemoryManager()
        result = await manager.prune()

        await AuditLog.log(
            actor="celery:memory_prune",
            action="memory.prune",
            resource="agent_memory",
            details={"summary": f"Pruned {result.get('deleted', 0)} stale records"},
            success=True,
        )

    _run_async(_run())


@app.task
def intelligence_scan():
    """Run autonomous domain intelligence scan — daily at 3 AM."""
    async def _run():
        from core.intelligence.scanner import IntelligenceScanner
        from core.database import AuditLog

        scanner = IntelligenceScanner()
        results = await scanner.scan_all()

        total_findings = sum(
            len(r.get("security_findings", []))
            for r in results
            if isinstance(r, dict) and "security_findings" in r
        )

        await AuditLog.log(
            actor="celery:intelligence_scan",
            action="intelligence.scan",
            resource="repos",
            details={"summary": f"Scanned {len(results)} repos, {total_findings} security findings"},
            success=True,
        )

    _run_async(_run())


@app.task
def llm_usage_report():
    """Summarize LLM usage and costs — daily at 6 AM."""
    async def _run():
        from core.database import LLMUsage, AuditLog
        from core.agents.report_agent import ReportAgent
        from datetime import datetime, timedelta, timezone

        # Query last 24 hours of LLM usage
        yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
        try:
            usage = await LLMUsage.get_since(yesterday)
        except Exception:
            usage = []

        if not usage:
            return

        # Aggregate stats
        total_requests = len(usage)
        total_tokens = sum(getattr(u, "total_tokens", 0) or 0 for u in usage)
        total_cost = sum(getattr(u, "cost_usd", 0.0) or 0.0 for u in usage)
        providers = {}
        for u in usage:
            p = getattr(u, "provider", "unknown") or "unknown"
            providers[p] = providers.get(p, 0) + 1

        summary = (
            f"LLM Usage Report (Last 24h):\n"
            f"  Total requests: {total_requests}\n"
            f"  Total tokens: {total_tokens:,}\n"
            f"  Estimated cost: ${total_cost:.4f}\n"
            f"  By provider: {providers}\n"
        )

        await AuditLog.log(
            actor="celery:llm_usage_report",
            action="report.llm_usage",
            resource="llm_usage",
            details={"summary": summary},
            success=True,
        )

        # Email report if costs are notable
        if total_cost > 0.50:
            reporter = ReportAgent()
            await reporter.send_alert_email(
                subject=f"[Sanaa AI] LLM Usage: {total_requests} requests, ${total_cost:.2f}",
                body=summary,
            )

    _run_async(_run())
