"""
SanaaBrain AutoLearner
======================
Reads raw operational data from existing tables and extracts structured
insights, storing them in agent_memory (source='autolearn_*').

Never writes to any table other than agent_memory.
Never modifies core/brain/ existing files.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SanaabrainLearner:
    """Autonomous learning engine — mines existing data tables for insights."""

    def __init__(self):
        self._brain = None
        self._memories_created = 0

    # ── LLM helper ──────────────────────────────────────────────────────────

    async def _llm(self, prompt: str) -> str:
        """Call the shared Brain for LLM inference. Returns empty string on failure."""
        try:
            if self._brain is None:
                from core.brain.engine import Brain
                self._brain = Brain()
            return await self._brain.think(prompt, complexity="medium")
        except Exception as e:
            logger.warning(f"[Learner] LLM call failed: {e}")
            return ""

    # ── Memory storage helper ─────────────────────────────────────────────

    async def _store(
        self,
        content: str,
        category: str,
        project: str,
        metadata: dict,
        source: str,
        confidence: float = 0.9,
    ) -> bool:
        """Insert a single insight into agent_memory. Returns True if stored."""
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        if not content or not content.strip():
            return False

        meta = {**metadata, "project": project}
        now = datetime.now(timezone.utc)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    sq_text("""
                        INSERT INTO agent_memory
                            (content, category, source, confidence, metadata,
                             created_at, updated_at, access_count, verified)
                        VALUES
                            (:content, :category, :source, :confidence, :metadata,
                             :now, :now, 0, false)
                        RETURNING id
                    """),
                    {
                        "content": content.strip()[:4000],
                        "category": category,
                        "source": source,
                        "confidence": confidence,
                        "metadata": json.dumps(meta),
                        "now": now,
                    },
                )
                new_id = result.scalar()
                await session.commit()
            self._memories_created += 1
            logger.info(f"[Learner] Stored insight id={new_id} cat={category} src={source}")
            return True
        except Exception as e:
            logger.error(f"[Learner] Failed to store memory: {e}")
            return False

    async def _already_stored(
        self,
        category: str,
        meta_key: str,
        meta_val: str,
        hours: int = 6,
    ) -> bool:
        """Check if an insight with this category+metadata was stored in last N hours."""
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    sq_text("""
                        SELECT COUNT(*) FROM agent_memory
                        WHERE category = :cat
                          AND metadata->>:key = :val
                          AND created_at > :cutoff
                    """),
                    {"cat": category, "key": meta_key, "val": meta_val, "cutoff": cutoff},
                )
                return (result.scalar() or 0) > 0
        except Exception as e:
            logger.warning(f"[Learner] _already_stored check failed: {e}")
            return False

    # ── Method 1: Tenant Health ──────────────────────────────────────────────

    async def learn_from_health_logs(self, hours_back: int = 24) -> int:
        """
        Reads the tenants table (health_score, status) and recent alerts.
        Generates per-tenant health insights for degraded tenants.
        Returns number of memories stored.
        """
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        stored = 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        try:
            async with AsyncSessionLocal() as session:
                # Get tenants with degraded health or non-active status
                result = await session.execute(sq_text("""
                    SELECT id, name, type, url, status, health_score, last_checked
                    FROM tenants
                    WHERE (health_score < 70 OR status NOT IN ('active', 'healthy'))
                    ORDER BY health_score ASC NULLS LAST
                    LIMIT 20
                """))
                degraded = [dict(r._mapping) for r in result.fetchall()]

                # Get recent alert counts per metric (last 2h, tightly bounded)
                alert_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
                result2 = await session.execute(sq_text("""
                    SELECT metric, severity, COUNT(*) as cnt
                    FROM alerts
                    WHERE created_at > :cutoff
                    GROUP BY metric, severity
                    ORDER BY cnt DESC
                    LIMIT 20
                """), {"cutoff": alert_cutoff})
                recent_alerts = [dict(r._mapping) for r in result2.fetchall()]

        except Exception as e:
            logger.error(f"[Learner] health query failed: {e}")
            return 0

        # Skip if nothing degraded
        if not degraded and not recent_alerts:
            return 0

        for tenant in degraded:
            name = tenant.get("name", "unknown")
            score = tenant.get("health_score")
            status = tenant.get("status", "unknown")

            # Skip if recently stored
            if await self._already_stored("system_health", "tenant", name, hours=6):
                continue

            score_str = f"{score:.0f}" if score is not None else "N/A"
            level = "critical" if (score is not None and score < 50) else "degraded"

            prompt = (
                f"You are Sanaa AI health analyst. Generate a 2-sentence operational insight.\n"
                f"Tenant: {name} (type: {tenant.get('type','?')}, url: {tenant.get('url','?')})\n"
                f"Health score: {score_str}/100, Status: {status}\n"
                f"Last checked: {tenant.get('last_checked','?')}\n"
                f"Recent system alerts (last 2h): {json.dumps(recent_alerts[:5])}\n"
                f"Write a plain English insight about this tenant's health and any action needed."
            )
            insight = await self._llm(prompt)
            if not insight:
                insight = (
                    f"Tenant {name} health score is {score_str}/100 with status '{status}'. "
                    f"Immediate review recommended."
                )

            ok = await self._store(
                content=insight,
                category="system_health",
                project="antigravity",
                metadata={
                    "tenant": name,
                    "health_score": score,
                    "status": status,
                    "level": level,
                    "type": "health_pattern",
                    "period_hours": hours_back,
                },
                source="autolearn_health",
                confidence=0.9,
            )
            if ok:
                stored += 1

        # Store alert pattern summary if significant alerts exist
        if recent_alerts and not await self._already_stored("system_health", "type", "alert_burst", hours=2):
            top = recent_alerts[0]
            insight = (
                f"Alert burst in last 2 hours: {top['cnt']} '{top['metric']}' "
                f"({top['severity']}) alerts. "
                f"{len(recent_alerts)} distinct metrics triggered."
            )
            ok = await self._store(
                content=insight,
                category="system_health",
                project="antigravity",
                metadata={"type": "alert_burst", "top_metric": top["metric"], "count": top["cnt"]},
                source="autolearn_health",
                confidence=0.85,
            )
            if ok:
                stored += 1

        return stored

    # ── Method 2: Skill Runs ─────────────────────────────────────────────────

    async def learn_from_skill_runs(self, hours_back: int = 24) -> int:
        """
        Reads skill_runs from the last N hours.
        Stores insights about frequently used and frequently failing skills.
        """
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        stored = 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(sq_text("""
                    SELECT
                        skill_name,
                        COUNT(*) AS run_count,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                        AVG(duration_ms) AS avg_duration_ms,
                        ARRAY_AGG(DISTINCT error_message) FILTER (WHERE error_message IS NOT NULL) AS errors
                    FROM skill_runs
                    WHERE completed_at > :cutoff
                    GROUP BY skill_name
                    ORDER BY run_count DESC
                    LIMIT 20
                """), {"cutoff": cutoff})
                rows = [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"[Learner] skill_runs query failed: {e}")
            return 0

        if not rows:
            return 0

        for row in rows:
            name = row["skill_name"]
            run_count = int(row["run_count"] or 0)
            success_count = int(row["success_count"] or 0)
            avg_ms = round(float(row["avg_duration_ms"] or 0))
            success_rate = success_count / run_count if run_count else 1.0
            errors = [e for e in (row["errors"] or []) if e] [:3]

            # Only store if heavily used or frequently failing
            if run_count < 3 and success_rate >= 0.7:
                continue

            if await self._already_stored("skill_intelligence", "skill_name", name, hours=6):
                continue

            rate_pct = round(success_rate * 100)
            content = (
                f"{name} ran {run_count} times in the last {hours_back}h "
                f"with {rate_pct}% success rate. "
                f"Avg duration: {avg_ms}ms."
            )
            if errors and success_rate < 0.7:
                top_err = errors[0][:200] if errors else ""
                content += f" Recurring failure: {top_err}"

            ok = await self._store(
                content=content,
                category="skill_intelligence",
                project="antigravity",
                metadata={
                    "skill_name": name,
                    "run_count": run_count,
                    "success_rate": round(success_rate, 3),
                    "avg_duration_ms": avg_ms,
                    "type": "skill_pattern",
                },
                source="autolearn_skills",
                confidence=0.85,
            )
            if ok:
                stored += 1

        return stored

    # ── Method 3: Client Activity (Tenants) ──────────────────────────────────

    async def learn_from_client_activity(self, hours_back: int = 168) -> int:
        """
        Reads tenants table to identify at-risk clients.
        Stores client intelligence entries for non-healthy tenants.
        """
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        stored = 0

        try:
            async with AsyncSessionLocal() as session:
                # Tenants that are not healthy
                result = await session.execute(sq_text("""
                    SELECT id, name, type, url, status, health_score,
                           last_checked, config, created_at, updated_at
                    FROM tenants
                    WHERE status NOT IN ('active', 'healthy')
                       OR health_score < 60
                    ORDER BY health_score ASC NULLS LAST
                    LIMIT 30
                """))
                at_risk = [dict(r._mapping) for r in result.fetchall()]

                # Summary of all tenants
                result2 = await session.execute(sq_text("""
                    SELECT status, COUNT(*) as cnt
                    FROM tenants
                    GROUP BY status
                    ORDER BY cnt DESC
                """))
                status_summary = {r._mapping["status"]: r._mapping["cnt"] for r in result2.fetchall()}

        except Exception as e:
            logger.error(f"[Learner] client_activity query failed: {e}")
            return 0

        # Store overall fleet summary if not done today
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not await self._already_stored("client_intelligence", "summary_date", today_str, hours=20):
            total = sum(status_summary.values())
            active = status_summary.get("active", 0) + status_summary.get("healthy", 0)
            at_risk_count = len(at_risk)
            content = (
                f"Client fleet status: {total} total tenants, {active} healthy/active, "
                f"{at_risk_count} at risk. "
                f"Status breakdown: {json.dumps(status_summary)}."
            )
            await self._store(
                content=content,
                category="client_intelligence",
                project="sanaa_finance",
                metadata={"type": "fleet_summary", "summary_date": today_str, "total": total},
                source="autolearn_clients",
                confidence=1.0,
            )
            stored += 1

        # Individual at-risk tenant entries
        for tenant in at_risk[:10]:
            name = tenant.get("name", "unknown")
            if await self._already_stored("client_intelligence", "tenant_key", name, hours=20):
                continue

            score = tenant.get("health_score")
            status = tenant.get("status", "unknown")
            score_str = f"{score:.0f}/100" if score is not None else "N/A"

            risk_level = "critical" if (score is not None and score < 40) else "high"
            content = (
                f"Client at risk: {name} (type: {tenant.get('type','?')}) — "
                f"status={status}, health={score_str}. "
                f"URL: {tenant.get('url','?')}. Risk level: {risk_level}."
            )
            ok = await self._store(
                content=content,
                category="client_intelligence",
                project="sanaa_finance",
                metadata={
                    "tenant_key": name,
                    "status": status,
                    "health_score": score,
                    "risk_level": risk_level,
                    "type": "client_event",
                },
                source="autolearn_clients",
                confidence=1.0,
            )
            if ok:
                stored += 1

        return stored

    # ── Method 4: LLM Usage ──────────────────────────────────────────────────

    async def learn_from_llm_usage(self, hours_back: int = 24) -> int:
        """
        Reads llm_usage table.
        Stores a daily summary of LLM cost, tokens, models used.
        """
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if await self._already_stored("resource_usage", "date", today_str, hours=20):
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(sq_text("""
                    SELECT
                        COUNT(*) AS total_calls,
                        SUM(cost_usd) AS total_cost,
                        SUM(input_tokens + output_tokens) AS total_tokens,
                        AVG(latency_ms) AS avg_latency_ms,
                        EXTRACT(HOUR FROM timestamp) AS hour,
                        model
                    FROM llm_usage
                    WHERE timestamp > :cutoff
                    GROUP BY EXTRACT(HOUR FROM timestamp), model
                    ORDER BY COUNT(*) DESC
                """), {"cutoff": cutoff})
                rows = [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"[Learner] llm_usage query failed: {e}")
            return 0

        if not rows:
            return 0

        total_calls = sum(int(r.get("total_calls") or 0) for r in rows)
        total_cost = sum(float(r.get("total_cost") or 0) for r in rows)
        total_tokens = sum(int(r.get("total_tokens") or 0) for r in rows)
        avg_latency = round(sum(float(r.get("avg_latency_ms") or 0) for r in rows) / len(rows)) if rows else 0

        # Find peak hour and dominant model
        by_hour: dict[int, int] = {}
        by_model: dict[str, int] = {}
        for r in rows:
            h = int(r.get("hour") or 0)
            c = int(r.get("total_calls") or 0)
            m = r.get("model") or "unknown"
            by_hour[h] = by_hour.get(h, 0) + c
            by_model[m] = by_model.get(m, 0) + c

        peak_hour = max(by_hour, key=by_hour.get) if by_hour else 0
        dominant_model = max(by_model, key=by_model.get) if by_model else "unknown"

        content = (
            f"LLM usage today ({today_str}): {total_calls} calls, "
            f"${total_cost:.4f} USD, {total_tokens:,} tokens. "
            f"Peak hour: {peak_hour}:00. "
            f"Dominant model: {dominant_model}. "
            f"Avg latency: {avg_latency}ms."
        )

        ok = await self._store(
            content=content,
            category="resource_usage",
            project="antigravity",
            metadata={
                "date": today_str,
                "total_cost": round(total_cost, 6),
                "total_tokens": total_tokens,
                "total_calls": total_calls,
                "peak_hour": peak_hour,
                "dominant_model": dominant_model,
                "avg_latency_ms": avg_latency,
                "type": "llm_daily",
            },
            source="autolearn_llm_usage",
            confidence=1.0,
        )
        return 1 if ok else 0

    # ── Method 5: Conversations ──────────────────────────────────────────────

    async def learn_from_conversations(self, hours_back: int = 24) -> int:
        """
        Reads conversations from the last N hours.
        Uses LLM to extract a daily work summary.
        """
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if await self._already_stored("work_pattern", "date", today_str, hours=20):
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(sq_text("""
                    SELECT session_id, channel, role, content, created_at
                    FROM conversations
                    WHERE created_at > :cutoff
                    ORDER BY created_at ASC
                    LIMIT 200
                """), {"cutoff": cutoff})
                rows = [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"[Learner] conversations query failed: {e}")
            return 0

        if not rows:
            return 0

        # Group by session
        sessions: dict = {}
        channels: dict = {}
        for r in rows:
            sid = r.get("session_id") or "unknown"
            if sid not in sessions:
                sessions[sid] = []
            sessions[sid].append(r)
            ch = r.get("channel") or "web"
            channels[ch] = channels.get(ch, 0) + 1

        # Extract first user message per session as topic
        topics = []
        for sid, msgs in list(sessions.items())[:15]:
            user_msgs = [m for m in msgs if m.get("role") == "user"]
            if user_msgs:
                topic = user_msgs[0].get("content", "")[:200]
                if topic:
                    topics.append(f"- [{sid[:20]}] {topic}")

        topics_text = "\n".join(topics[:10]) if topics else "No user messages found."

        prompt = (
            f"You are Sanaa AI. Summarize what was worked on today based on conversation topics.\n"
            f"Date: {today_str}\n"
            f"Sessions: {len(sessions)}, Channels: {channels}\n"
            f"Sample topics:\n{topics_text}\n\n"
            f"Write 2-3 sentences summarizing the main work themes today. Be specific and actionable."
        )
        insight = await self._llm(prompt)
        if not insight:
            insight = (
                f"Today ({today_str}): {len(sessions)} conversation sessions across "
                f"{list(channels.keys())}. Topics: {topics_text[:300]}"
            )

        ok = await self._store(
            content=insight,
            category="work_pattern",
            project="antigravity",
            metadata={
                "date": today_str,
                "session_count": len(sessions),
                "channels": channels,
                "type": "daily_work_summary",
            },
            source="autolearn_conversations",
            confidence=0.8,
        )
        return 1 if ok else 0

    # ── Method 6: Watchdog ───────────────────────────────────────────────────

    async def learn_from_watchdog(self, hours_back: int = 168) -> int:
        """
        Reads watchdog_alert_state for chronic/unresolved issues.
        Also scans recent alerts for recurring patterns.
        """
        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        stored = 0

        try:
            async with AsyncSessionLocal() as session:
                # Chronic unresolved watchdog issues
                result = await session.execute(sq_text("""
                    SELECT fingerprint, category, metric, status, severity,
                           latest_message, heal_attempts, heal_successes,
                           first_seen_at, occurrence_count
                    FROM watchdog_alert_state
                    WHERE status != 'resolved'
                      AND heal_attempts >= 2
                    ORDER BY heal_attempts DESC
                    LIMIT 10
                """))
                chronic = [dict(r._mapping) for r in result.fetchall()]

                # Recent alert patterns from alerts table (last 24h, limited)
                alert_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                result2 = await session.execute(sq_text("""
                    SELECT metric, severity, COUNT(*) as cnt, MIN(created_at) as first_at
                    FROM alerts
                    WHERE created_at > :cutoff
                      AND severity IN ('critical', 'high')
                    GROUP BY metric, severity
                    HAVING COUNT(*) >= 3
                    ORDER BY cnt DESC
                    LIMIT 10
                """), {"cutoff": alert_cutoff})
                patterns = [dict(r._mapping) for r in result2.fetchall()]

        except Exception as e:
            logger.error(f"[Learner] watchdog query failed: {e}")
            return 0

        # Chronic watchdog issues
        for issue in chronic:
            fp = issue.get("fingerprint", "unknown")
            if await self._already_stored("recurring_issues", "fingerprint", fp, hours=12):
                continue

            heals = int(issue.get("heal_attempts") or 0)
            success = int(issue.get("heal_successes") or 0)
            content = (
                f"Chronic issue: {issue.get('category','?')} — {issue.get('latest_message','?')[:200]}. "
                f"{heals} heal attempts, {success} resolved. "
                f"First seen: {issue.get('first_seen_at','?')}. "
                f"Occurrences: {issue.get('occurrence_count',1)}."
            )
            ok = await self._store(
                content=content,
                category="recurring_issues",
                project="antigravity",
                metadata={
                    "fingerprint": fp,
                    "category": issue.get("category"),
                    "heal_attempts": heals,
                    "heal_successes": success,
                    "type": "chronic_issue",
                },
                source="autolearn_watchdog",
                confidence=0.95,
            )
            if ok:
                stored += 1

        # Recurring alert patterns
        for pat in patterns:
            metric = pat.get("metric", "unknown")
            key = f"alert_pattern_{metric}"
            if await self._already_stored("recurring_issues", "alert_metric", metric, hours=12):
                continue

            content = (
                f"Recurring alert: '{metric}' ({pat.get('severity','?')}) fired "
                f"{pat.get('cnt','?')} times in the last 24h."
            )
            ok = await self._store(
                content=content,
                category="recurring_issues",
                project="antigravity",
                metadata={
                    "alert_metric": metric,
                    "severity": pat.get("severity"),
                    "count": pat.get("cnt"),
                    "type": "alert_pattern",
                },
                source="autolearn_watchdog",
                confidence=0.9,
            )
            if ok:
                stored += 1

        return stored

    # ── Method 7: Weekly Habits ──────────────────────────────────────────────

    async def generate_weekly_habits(self, days_back: int = 7) -> int:
        """
        Only runs on Mondays. Reads audit_log + skill_runs to extract
        working patterns and generate a habit summary using LLM.
        """
        # Only run on Mondays
        if datetime.now(timezone.utc).weekday() != 0:  # 0 = Monday
            logger.info("[Learner] generate_weekly_habits skipped (not Monday)")
            return 0

        week_start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        if await self._already_stored("habit_intelligence", "week_start", week_start, hours=160):
            return 0

        from core.database import AsyncSessionLocal
        from sqlalchemy import text as sq_text

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        try:
            async with AsyncSessionLocal() as session:
                # Action distribution by hour and day
                result = await session.execute(sq_text("""
                    SELECT
                        EXTRACT(DOW FROM timestamp) AS dow,
                        EXTRACT(HOUR FROM timestamp) AS hour,
                        action,
                        COUNT(*) AS cnt
                    FROM audit_log
                    WHERE timestamp > :cutoff
                    GROUP BY EXTRACT(DOW FROM timestamp), EXTRACT(HOUR FROM timestamp), action
                    ORDER BY cnt DESC
                    LIMIT 50
                """), {"cutoff": cutoff})
                audit_rows = [dict(r._mapping) for r in result.fetchall()]

                # Top skills by usage
                result2 = await session.execute(sq_text("""
                    SELECT skill_name, COUNT(*) AS cnt,
                           SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes
                    FROM skill_runs
                    WHERE completed_at > :cutoff
                    GROUP BY skill_name
                    ORDER BY cnt DESC
                    LIMIT 10
                """), {"cutoff": cutoff})
                skill_rows = [dict(r._mapping) for r in result2.fetchall()]

        except Exception as e:
            logger.error(f"[Learner] weekly_habits query failed: {e}")
            return 0

        # Aggregate hour distribution
        hour_counts: dict[int, int] = {}
        dow_counts: dict[int, int] = {}
        action_counts: dict[str, int] = {}

        for r in audit_rows:
            h = int(r.get("hour") or 0)
            d = int(r.get("dow") or 0)
            a = r.get("action") or "unknown"
            c = int(r.get("cnt") or 0)
            hour_counts[h] = hour_counts.get(h, 0) + c
            dow_counts[d] = dow_counts.get(d, 0) + c
            action_counts[a] = action_counts.get(a, 0) + c

        # Peak hours (top 3)
        peak_hours = sorted(hour_counts, key=hour_counts.get, reverse=True)[:3]
        peak_hours_str = ", ".join(f"{h}:00" for h in sorted(peak_hours))

        # Busiest day (0=Sunday, 1=Monday, ...)
        day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        busiest_dow = max(dow_counts, key=dow_counts.get) if dow_counts else 1
        busiest_day = day_names[busiest_dow] if busiest_dow < 7 else "Unknown"

        # Top skill
        top_skill = skill_rows[0]["skill_name"] if skill_rows else "none"
        top_action = max(action_counts, key=action_counts.get) if action_counts else "unknown"

        prompt = (
            f"You are Sanaa AI. Generate a 3-sentence weekly habit summary.\n"
            f"Week: {week_start} to today\n"
            f"Peak working hours: {peak_hours_str}\n"
            f"Busiest day: {busiest_day}\n"
            f"Most used skill: {top_skill}\n"
            f"Most common action: {top_action}\n"
            f"Top skills this week: {json.dumps([{'skill': r['skill_name'], 'runs': r['cnt']} for r in skill_rows[:5]])}\n\n"
            f"Write: 'Based on the last 7 days: Banks works most on {busiest_day} between {peak_hours_str}. "
            f"Most built: [fill in]. Recommendation: [actionable insight].'"
        )
        habit_text = await self._llm(prompt)
        if not habit_text:
            habit_text = (
                f"Based on the last 7 days: Peak hours are {peak_hours_str} on {busiest_day}. "
                f"Most used skill: {top_skill}. Most common action: {top_action}."
            )

        ok = await self._store(
            content=habit_text,
            category="habit_intelligence",
            project="banks",
            metadata={
                "week_start": week_start,
                "peak_hours": peak_hours,
                "busiest_day": busiest_day,
                "top_skill": top_skill,
                "type": "weekly_habits",
            },
            source="autolearn_habits",
            confidence=0.75,
        )
        return 1 if ok else 0

    # ── run_all ──────────────────────────────────────────────────────────────

    async def run_all(self, hours_back: int = 24) -> dict:
        """
        Run all learning methods in sequence.
        One failure does not stop the others.
        Returns: { methods_run, memories_created, errors }
        """
        self._memories_created = 0
        errors = []
        methods_run = 0

        methods = [
            ("learn_from_health_logs", self.learn_from_health_logs, {"hours_back": hours_back}),
            ("learn_from_skill_runs", self.learn_from_skill_runs, {"hours_back": hours_back}),
            ("learn_from_client_activity", self.learn_from_client_activity, {"hours_back": max(hours_back, 168)}),
            ("learn_from_llm_usage", self.learn_from_llm_usage, {"hours_back": hours_back}),
            ("learn_from_conversations", self.learn_from_conversations, {"hours_back": hours_back}),
            ("learn_from_watchdog", self.learn_from_watchdog, {"hours_back": max(hours_back, 168)}),
        ]

        for method_name, method_fn, kwargs in methods:
            try:
                count = await method_fn(**kwargs)
                methods_run += 1
                logger.info(f"[Learner] {method_name}: {count} memories stored")
            except Exception as e:
                error_msg = f"{method_name}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                logger.error(f"[Learner] {error_msg}", exc_info=True)

        return {
            "methods_run": methods_run,
            "memories_created": self._memories_created,
            "errors": errors,
        }
