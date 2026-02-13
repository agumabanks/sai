"""Email Agent — Monitors IMAP inbox"""

import os
from imapclient import IMAPClient
from agents.llm_brain import LLMBrain

class EmailInboxAgent:
    def __init__(self):
        self.host = os.getenv("IMAP_HOST")
        self.port = int(os.getenv("IMAP_PORT", 993))
        self.user = os.getenv("IMAP_USER")
        self.password = os.getenv("IMAP_PASS")

    async def get_inbox_summary(self):
        """Get summary of unread emails"""
        if not self.host or not self.user:
            return {"count": 0, "summary": "Email not configured"}

        try:
            # Synchronous IMAP lib, generally fast enough, or run in thread
            with IMAPClient(self.host, port=self.port, ssl=True) as client:
                client.login(self.user, self.password)
                client.select_folder('INBOX')
                messages = client.search('UNSEEN')
                
                if not messages:
                    return {"count": 0, "summary": "No unread emails"}
                
                # Fetch recent 5
                fetch_data = client.fetch(messages[-5:], ['ENVELOPE'])
                summary_lines = []
                for msg_id, data in fetch_data.items():
                    env = data[b'ENVELOPE']
                    subject = env.subject.decode() if env.subject else "(No Subject)"
                    sender = env.from_[0].mailbox.decode() + "@" + env.from_[0].host.decode() if env.from_ else "Unknown"
                    summary_lines.append(f"- From {sender}: {subject}")
                
                return {
                    "count": len(messages),
                    "summary": "\n".join(summary_lines)
                }
        except Exception as e:
            return {"count": 0, "summary": f"Error checking email: {e}"}

    async def check_and_log(self):
        """Task: Check email and log to DB if important"""
        # Placeholder for background task logic
        pass
