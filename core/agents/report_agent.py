"""Report Agent — Generates and sends email reports"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

class ReportAgent:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")
        self.from_addr = os.getenv("SMTP_FROM")
        self.recipients = os.getenv("ALERT_RECIPIENTS", "").split(",")

    async def send_alert_email(self, subject: str, body: str):
        """Send an alert email immediately"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.recipients)

            html_body = f"""
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; background: #0a0a0a; color: #e0e0e0;">
                <div style="max-width: 600px; margin: 0 auto; background: #1a1a2e; border-radius: 12px; padding: 24px; border: 1px solid #2a2a4a;">
                    <div style="display: flex; align-items: center; margin-bottom: 16px;">
                        <span style="font-size: 24px; margin-right: 8px;">🛸</span>
                        <h2 style="margin: 0; color: #00d4ff;">Sanaa AI Alert</h2>
                    </div>
                    <div style="background: #0d0d1a; border-radius: 8px; padding: 16px; margin: 16px 0;">
                        <pre style="white-space: pre-wrap; color: #b0b0b0; margin: 0;">{body}</pre>
                    </div>
                    <p style="color: #666; font-size: 12px; margin-top: 16px;">
                        Sent by Sanaa AI at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} EAT
                        <br>Manage at <a href="https://ai.sanaa.co" style="color: #00d4ff;">ai.sanaa.co</a>
                    </p>
                </div>
            </body>
            </html>
            """

            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Simple synchronous SMTP for now, could be async with aiosmtplib if needed
            # Blueprint used smtplib
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.from_addr, self.recipients, msg.as_string())

            return True
        except Exception as e:
            print(f"Email send failed: {e}")
            return False

    async def list_reports(self):
        # Placeholder for reporting feature
        return []

    async def send_daily_report(self, health: dict, alerts: list, email_summary: dict, news: dict):
        """Send the daily morning report"""
        from agents.llm_brain import LLMBrain
        brain = LLMBrain()

        # Let LLM compose a natural report
        report_prompt = f"""Compose a concise daily operations report for Banks.
        Include only what matters. Be direct.

        SERVER HEALTH: {health}
        ALERTS (last 24h): {alerts}
        EMAIL SUMMARY: {email_summary}
        NEWS HIGHLIGHTS: {news}

        Format as a clean email. Start with overall status emoji:
        🟢 All clear | 🟡 Needs attention | 🔴 Critical issues
        """

        report = await brain.think(report_prompt, complexity="low")

        await self.send_alert_email(
            subject=f"[Sanaa AI] Daily Report — {datetime.now().strftime('%b %d, %Y')}",
            body=report
        )
