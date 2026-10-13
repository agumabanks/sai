"""Email Agent — Monitors IMAP inbox"""

import asyncio
import hashlib
import logging
import json
from email import message_from_bytes
from imapclient import IMAPClient
from core.brain import get_shared_brain
from core.config import get_settings

logger = logging.getLogger(__name__)

class EmailInboxAgent:
    def __init__(self, brain=None):
        self.brain = brain or get_shared_brain()
        cfg = get_settings()
        self.host = cfg.imap_host
        self.port = cfg.imap_port
        self.user = cfg.imap_user
        self.password = cfg.imap_pass

    def _get_text_from_email(self, msg) -> str:
        text_parts = []
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        text_parts.append(part.get_payload(decode=True).decode('utf-8', errors='ignore'))
                    except Exception:
                        pass
        else:
            try:
                text_parts.append(msg.get_payload(decode=True).decode('utf-8', errors='ignore'))
            except Exception:
                pass
        return "\n".join(text_parts)[:1000] # Limit to 1000 chars for summary

    def _fetch_unseen_sync(self, limit: int):
        """Synchronous IMAP fetch; runs in a thread so it never blocks the event loop."""
        with IMAPClient(self.host, port=self.port, ssl=True) as client:
            client.login(self.user, self.password)
            client.select_folder('INBOX')
            messages = client.search('UNSEEN')

            if not messages:
                return {"count": 0, "summary": "No unread emails", "emails": []}

            fetch_data = client.fetch(messages[-limit:], ['RFC822'])

            processed_emails = []
            for msg_id, data in fetch_data.items():
                raw_email = data[b'RFC822']
                msg = message_from_bytes(raw_email)

                subject = msg.get("Subject", "(No Subject)")
                sender = msg.get("From", "Unknown")
                body = self._get_text_from_email(msg)

                processed_emails.append({
                    "id": msg_id,
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                })

            return {
                "count": len(messages),
                "emails": processed_emails,
            }

    async def get_inbox_summary(self, limit=5):
        """Get summary and categorize unread emails using local LLM"""
        if not self.host or not self.user:
            return {"count": 0, "summary": "Email not configured", "emails": []}

        try:
            fetch_result = await asyncio.to_thread(self._fetch_unseen_sync, limit)

            if not fetch_result.get("emails"):
                return fetch_result

            processed_emails = []
            for e in fetch_result["emails"]:
                subject = e["subject"]
                sender = e["sender"]
                body = e["body"]

                # Use local/Tier 1 LLM to categorize
                prompt = f"""Categorize this email.
Sender: {sender}
Subject: {subject}
Body: {body}

Respond ONLY with a JSON object:
{{"category": "Urgent|Newsletter|Spam|General", "one_line_summary": "..."}}"""

                try:
                    # Force low complexity to use Ollama/Local instead of Groq
                    analysis = await self.brain.think(prompt, complexity="low")
                    # Try to extract JSON
                    import re
                    match = re.search(r'\{[\s\S]*\}', analysis)
                    if match:
                        cat_data = json.loads(match.group())
                    else:
                        cat_data = {"category": "General", "one_line_summary": subject}
                except Exception:
                    cat_data = {"category": "General", "one_line_summary": subject}

                processed_emails.append({
                    "id": e["id"],
                    "sender": sender,
                    "subject": subject,
                    "category": cat_data.get("category", "General"),
                    "summary": cat_data.get("one_line_summary", subject)
                })

            # Build final summary string
            summary_lines = []
            for e in processed_emails:
                summary_lines.append(f"[{e['category']}] From {e['sender']}: {e['summary']}")

            return {
                "count": fetch_result["count"],
                "summary": "\n".join(summary_lines),
                "emails": processed_emails
            }
        except Exception as e:
            logger.error(f"Email fetch failed: {e}")
            return {"count": 0, "summary": f"Error checking email: {e}", "emails": []}

    async def check_and_log(self):
        """Task: Check email and log to DB if important"""
        result = await self.get_inbox_summary(limit=10)
        
        # If there are urgent emails, emit a watchdog or memory event
        urgent_count = sum(1 for e in result.get("emails", []) if e.get("category") == "Urgent")
        
        if urgent_count > 0:
            from core.intelligence.memory import IntelligenceMemory
            mem = IntelligenceMemory()
            await mem.add_strategic_signal({
                "category": "email",
                "title": f"You have {urgent_count} urgent unread emails",
                "summary": "\n".join([e["summary"] for e in result["emails"] if e["category"] == "Urgent"]),
                "severity": "high",
                "score": 8
            })
            
        return result
