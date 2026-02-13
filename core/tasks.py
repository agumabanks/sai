"""Celery tasks — the heartbeat of Sanaa AI"""

import sys
sys.path.insert(0, '/opt/antigravity/core')

from celery import Celery
from celery.schedules import crontab
import os

app = Celery('sanaa_ai', broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"))

app.conf.timezone = 'Africa/Kampala'

app.conf.beat_schedule = {

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

@app.task
def check_server_health():
    """Check server health and alert if thresholds exceeded"""
    import asyncio
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

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(_run())


@app.task
def scan_app_errors():
    """Scan logs for new errors"""
    import asyncio
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

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_run())


@app.task
def test_webapp_uptime():
    """Test all Sanaa webapps are responding"""
    import asyncio
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

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_run())


@app.task
def send_daily_report():
    """Compile and send the daily morning report"""
    import asyncio
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

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_run())


@app.task
def check_email_inbox():
    """Check email inbox"""
    import asyncio
    from agents.email_agent import EmailInboxAgent

    async def _run():
        agent = EmailInboxAgent()
        await agent.check_and_log()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_run())
