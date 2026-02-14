"""Celery tasks — the heartbeat of Sanaa AI"""

import sys
sys.path.insert(0, '/opt/antigravity/core')

from celery import Celery
from celery.schedules import crontab
import os

app = Celery('sanaa_ai', broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"))

app.conf.timezone = 'Africa/Kampala'

app.conf.beat_schedule = {

    # ===== EVERY 2 MINUTES — WATCHDOG =====
    'watchdog-check': {
        'task': 'tasks.watchdog_check',
        'schedule': 120,  # 2 minutes — high frequency for critical monitoring
    },

    # ===== EVERY 5 MINUTES =====
    'server-health-check': {
        'task': 'tasks.check_server_health',
        'schedule': 300,  # 5 minutes
    },

    # ===== EVERY 15 MINUTES =====
    'app-error-scan': {
        'task': 'tasks.scan_app_errors',
        'schedule': 900,  # 15 minutes
    },

    'webapp-uptime-test': {
        'task': 'tasks.test_webapp_uptime',
        'schedule': 900,
    },

    # ===== EVERY HOUR =====
    'email-inbox-check': {
        'task': 'tasks.check_email_inbox',
        'schedule': 3600,
    },

    # ===== DAILY =====
    'morning-report': {
        'task': 'tasks.send_daily_report',
        'schedule': crontab(hour=7, minute=0),  # 7 AM EAT
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
    from agents.watchdog import ServerWatchdog
    from agents.healer import SelfHealer
    from agents.report_agent import ReportAgent

    async def _run():
        wd = ServerWatchdog()
        heal = SelfHealer()
        reporter = ReportAgent()

        events = await wd.run_full_check()

        if not events:
            return  # All clear

        # Auto-heal
        actions = await heal.process_events(events)

        # Persist critical/high alerts to database
        from database import Alert, AuditLog
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
                detail=a.get("output", ""),
                success=a.get("success", False),
            )

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
    from agents.server_health import ServerHealthAgent
    from agents.report_agent import ReportAgent

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
    from agents.app_monitor import AppMonitorAgent
    from agents.report_agent import ReportAgent

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
    from agents.web_test_agent import WebTestAgent
    from agents.report_agent import ReportAgent

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
    from agents.server_health import ServerHealthAgent
    from agents.email_agent import EmailInboxAgent
    from agents.news_agent import NewsAgent
    from agents.report_agent import ReportAgent

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
    from agents.email_agent import EmailInboxAgent

    async def _run():
        agent = EmailInboxAgent()
        await agent.check_and_log()

    _run_async(_run())
