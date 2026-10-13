"""Site Watcher — watch websites for content changes with AI-powered diff summaries."""
import os
import hashlib
import logging
import json
import difflib
import re
from datetime import datetime, timezone
import httpx
from sqlalchemy import text
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html, flags=re.IGNORECASE)
    text_out = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text_out).strip()


class SiteWatcherSkill(BaseSkill):
    name = "site_watcher"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "add_watch":
            return await self._add_watch(args)
        elif action == "remove_watch":
            return await self._remove_watch(args)
        elif action == "list_watches":
            return await self._list_watches()
        elif action == "check_now":
            return await self._check_all(context)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ── add_watch ─────────────────────────────────────────────────────────────
    async def _add_watch(self, args: dict) -> SkillResult:
        url = args.get("url")
        label = args.get("label", url)
        if not url:
            return SkillResult(success=False, error="'url' is required.")
        key = f"watch.{hashlib.md5(url.encode()).hexdigest()[:8]}"
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("""
                    INSERT INTO system_knowledge (domain, key, value, last_verified)
                    VALUES ('site_watch', :key, :val, :ts)
                    ON CONFLICT (domain, key) DO UPDATE SET value = :val
                """), {
                    "key": key,
                    "val": json.dumps({"url": url, "label": label,
                                       "last_hash": "", "last_text": "", "last_check": ""}),
                    "ts": datetime.now(timezone.utc),
                })
                await session.commit()
            return SkillResult(success=True, output=f"Now watching: {label} ({url})")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── remove_watch ──────────────────────────────────────────────────────────
    async def _remove_watch(self, args: dict) -> SkillResult:
        url = args.get("url")
        if not url:
            return SkillResult(success=False, error="'url' is required.")
        key = f"watch.{hashlib.md5(url.encode()).hexdigest()[:8]}"
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text(
                    "DELETE FROM system_knowledge WHERE domain = 'site_watch' AND key = :key"
                ), {"key": key})
                await session.commit()
            return SkillResult(success=True, output=f"Stopped watching: {url}")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── list_watches ──────────────────────────────────────────────────────────
    async def _list_watches(self) -> SkillResult:
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(text(
                    "SELECT key, value FROM system_knowledge WHERE domain = 'site_watch'"
                ))
                rows = res.mappings().all()
            if not rows:
                return SkillResult(success=True, output="No watched sites.")
            lines = []
            for r in rows:
                d = json.loads(r["value"])
                last = d.get("last_check", "never")
                lines.append(f"• {d.get('label', r['key'])}: {d.get('url')} (last checked: {last})")
            return SkillResult(success=True, output="\n".join(lines))
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── check_now ─────────────────────────────────────────────────────────────
    async def _check_all(self, context: SkillContext) -> SkillResult:
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(text(
                    "SELECT id, key, value FROM system_knowledge WHERE domain = 'site_watch'"
                ))
                rows = res.mappings().all()

            if not rows:
                return SkillResult(success=True, output="No watched sites configured.")

            changes = []
            for r in rows:
                d = json.loads(r["value"])
                url = d.get("url")
                label = d.get("label", url)
                old_hash = d.get("last_hash", "")
                old_text = d.get("last_text", "")

                try:
                    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                        resp = await client.get(url, headers={"User-Agent": "SanaaAI-SiteWatcher/1.0"})
                    new_text = _strip_html(resp.text)[:5000]
                    new_hash = hashlib.md5(new_text.encode()).hexdigest()

                    if old_hash and new_hash != old_hash:
                        # Compute text diff
                        diff_lines = list(difflib.unified_diff(
                            old_text.splitlines()[:100],
                            new_text.splitlines()[:100],
                            lineterm="", n=1,
                        ))
                        diff_snippet = "\n".join(diff_lines[:30])

                        # AI summary of changes
                        ai_summary = ""
                        try:
                            brain = context.brain
                            if brain:
                                ai_summary = await brain.think(
                                    f"Summarize what changed on {label} ({url}) in 2 sentences. "
                                    f"Then, answer YES or NO on a new line: Is this a strategic change (pricing, new features, major strategy shifts) requiring immediate attention?\n\n"
                                    f"DIFF:\n{diff_snippet}",
                                    complexity="low",
                                )
                                
                                # Proactive Alerting Logic
                                if "YES" in ai_summary.upper().split("\n")[-1]:
                                    # Write high priority alert
                                    async with AsyncSessionLocal() as session:
                                        await session.execute(text(
                                            """INSERT INTO alerts (type, message, severity, status, created_at, updated_at)
                                            VALUES ('intelligence', :msg, 'high', 'new', :ts, :ts)"""
                                        ), {
                                            "msg": f"🚨 Strategic Competitor Insight ({label}):\n{ai_summary}",
                                            "ts": datetime.now(timezone.utc)
                                        })
                                        await session.commit()
                                    ai_summary = ai_summary + "\n[ALERT GENERATED: Strategic Change Detected]"

                        except Exception as e:
                            logger.error(f"Site watcher AI summary failed: {e}")

                        change_entry = (
                            f"🔔 CHANGE DETECTED: {label} ({url})\n"
                            f"   Diff snippet:\n{diff_snippet[:400]}"
                        )
                        if ai_summary:
                            change_entry += f"\n\n   AI Insight:\n{ai_summary}"
                        changes.append(change_entry)

                    d["last_hash"] = new_hash
                    d["last_text"] = new_text[:5000]
                    d["last_check"] = datetime.now(timezone.utc).isoformat()

                    async with AsyncSessionLocal() as session:
                        await session.execute(text(
                            "UPDATE system_knowledge SET value = :val WHERE id = :id"
                        ), {"val": json.dumps(d), "id": r["id"]})
                        await session.commit()

                except Exception as e:
                    changes.append(f"⚠️ Error checking {label}: {e}")

            if changes:
                return SkillResult(success=True, output="\n\n".join(changes))
            return SkillResult(success=True, output=f"All {len(rows)} watched sites unchanged.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))
