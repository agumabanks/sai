"""
Structured Learning Logs — OpenClaw-inspired self-improvement system.

Implements the learning loop:
1. Error logging: skill failures with context
2. Correction detection: user corrections during conversations
3. Feature request detection: user-requested capabilities
4. Knowledge gap detection: outdated or missing knowledge
5. Learning promotion: graduate proven learnings into system prompt

Based on OpenClaw's self-improving-agent pattern (pskoett, 191k+ downloads).
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from core.database import SystemKnowledge, AsyncSessionLocal, AuditLog
from sqlalchemy import text, select

logger = logging.getLogger(__name__)

# Detection patterns for auto-categorization
CORRECTION_PATTERNS = [
    r"no[,.]?\s+(that'?s?\s+)?(not|wrong|incorrect)",
    r"actually[,.]?\s+(it'?s?|that'?s?|the)",
    r"i\s+meant\s+",
    r"that'?s?\s+not\s+what\s+i\s+(asked|meant|wanted)",
    r"you'?re\s+wrong",
    r"incorrect[,.]",
    r"please\s+fix\s+that",
    r"no[,.]?\s+i\s+(said|asked|wanted)",
]

FEATURE_REQUEST_PATTERNS = [
    r"can\s+you\s+also\s+",
    r"i\s+wish\s+you\s+could\s+",
    r"it\s+would\s+be\s+(nice|great|helpful)\s+if\s+",
    r"could\s+you\s+add\s+",
    r"is\s+there\s+a\s+way\s+to\s+",
    r"please\s+add\s+",
    r"feature\s+request[:\s]",
    r"you\s+should\s+be\s+able\s+to\s+",
]

KNOWLEDGE_GAP_PATTERNS = [
    r"(actually|fyi|for\s+your\s+info)[,.]?\s+",
    r"you\s+didn'?t\s+know\s+",
    r"(here'?s?|this\s+is)\s+(some\s+)?(new\s+)?info",
    r"let\s+me\s+tell\s+you\s+about\s+",
    r"you\s+(might|should)\s+know\s+that\s+",
]


class LearningEntry:
    """A single learning log entry."""

    def __init__(
        self,
        category: str,
        summary: str,
        details: str = "",
        area: str = "general",
        priority: str = "medium",
        source_session: str = "",
        source_channel: str = "",
    ):
        self.id = f"LRN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self.category = category  # correction, feature_request, knowledge_gap, error, best_practice
        self.summary = summary
        self.details = details
        self.area = area  # frontend, backend, infra, skills, config, general
        self.priority = priority  # low, medium, high, critical
        self.status = "pending"  # pending, in_progress, resolved, promoted, wont_fix
        self.source_session = source_session
        self.source_channel = source_channel
        self.created_at = datetime.now(timezone.utc)
        self.recurrence_count = 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "summary": self.summary,
            "details": self.details,
            "area": self.area,
            "priority": self.priority,
            "status": self.status,
            "source_session": self.source_session,
            "source_channel": self.source_channel,
            "created_at": self.created_at.isoformat(),
            "recurrence_count": self.recurrence_count,
        }


class LearningLogManager:
    """Manages structured learning logs with auto-detection and promotion."""

    PROMOTION_THRESHOLD = 3  # Recurrence count to trigger promotion

    async def detect_and_log(
        self,
        user_message: str,
        ai_response: str,
        session_id: str = "",
        channel: str = "web",
    ) -> Optional[LearningEntry]:
        """Auto-detect learning opportunities from conversation patterns."""
        text_lower = user_message.lower()

        # Check correction patterns
        for pattern in CORRECTION_PATTERNS:
            if re.search(pattern, text_lower):
                return await self.log_learning(
                    category="correction",
                    summary=f"User corrected AI response",
                    details=f"User said: {user_message[:500]}\nAI had said: {ai_response[:500]}",
                    source_session=session_id,
                    source_channel=channel,
                    priority="high",
                )

        # Check feature request patterns
        for pattern in FEATURE_REQUEST_PATTERNS:
            if re.search(pattern, text_lower):
                return await self.log_learning(
                    category="feature_request",
                    summary=f"User requested feature: {user_message[:200]}",
                    details=user_message,
                    source_session=session_id,
                    source_channel=channel,
                    priority="medium",
                )

        # Check knowledge gap patterns
        for pattern in KNOWLEDGE_GAP_PATTERNS:
            if re.search(pattern, text_lower):
                return await self.log_learning(
                    category="knowledge_gap",
                    summary=f"User provided new information",
                    details=user_message,
                    source_session=session_id,
                    source_channel=channel,
                    priority="medium",
                )

        return None

    async def log_skill_error(
        self,
        skill_name: str,
        action: str,
        error: str,
        args: dict = None,
        session_id: str = "",
    ) -> LearningEntry:
        """Log a skill execution error."""
        return await self.log_learning(
            category="error",
            summary=f"Skill '{skill_name}' action '{action}' failed: {error[:200]}",
            details=f"Skill: {skill_name}\nAction: {action}\nArgs: {args}\nError: {error}",
            area="skills",
            source_session=session_id,
            priority="high",
        )

    async def log_learning(
        self,
        category: str,
        summary: str,
        details: str = "",
        area: str = "general",
        priority: str = "medium",
        source_session: str = "",
        source_channel: str = "",
    ) -> LearningEntry:
        """Create and persist a learning log entry."""
        # Check for similar existing entries to bump recurrence
        similar = await self._find_similar(category, summary)

        if similar:
            # Bump recurrence count
            count = int(similar.get("recurrence_count", "1")) + 1
            await SystemKnowledge.set_pref(
                similar["key"],
                str(count),
                source="learning_logs",
                domain="learning",
            )
            # Auto-promote if threshold reached
            if count >= self.PROMOTION_THRESHOLD:
                await self._promote_learning(similar["key"], category, summary, details)

            logger.info(f"Learning recurrence bumped: {summary[:80]} (count={count})")
            entry = LearningEntry(category, summary, details, area, priority, source_session, source_channel)
            entry.recurrence_count = count
            return entry

        entry = LearningEntry(category, summary, details, area, priority, source_session, source_channel)

        # Persist to system_knowledge
        import json
        key = f"learning.{entry.id}"
        value = json.dumps(entry.to_dict())
        await SystemKnowledge.set_pref(key, value, source="learning_logs", domain="learning")

        # Also store a recurrence tracker
        tracker_key = f"learning.tracker.{category}.{self._signature(summary)}"
        await SystemKnowledge.set_pref(tracker_key, "1", source="learning_logs", domain="learning")

        logger.info(f"Learning logged: [{category}] {summary[:80]}")
        return entry

    async def _find_similar(self, category: str, summary: str) -> Optional[dict]:
        """Find a similar existing learning entry to avoid duplicates."""
        sig = self._signature(summary)
        tracker_key = f"learning.tracker.{category}.{sig}"
        count = await SystemKnowledge.get_pref(tracker_key, default=None, domain="learning")
        if count:
            return {"key": tracker_key, "recurrence_count": count, "category": category, "summary": summary}
        return None

    async def _promote_learning(self, key: str, category: str, summary: str, details: str):
        """Promote a recurring learning into the system prompt context."""
        promotion_domain = {
            "correction": "user_profile",
            "feature_request": "project_context",
            "knowledge_gap": "infrastructure",
            "error": "infrastructure",
            "best_practice": "preference",
        }.get(category, "preference")

        promotion_key = f"promoted_learning.{self._signature(summary)}"

        await SystemKnowledge.set_pref(
            promotion_key,
            f"[LEARNED] {summary}: {details[:500]}",
            source="learning_promotion",
            domain=promotion_domain,
        )

        try:
            await AuditLog.log(
                actor="learning_logs",
                action="learning.promoted",
                resource=key,
                details={"category": category, "summary": summary, "domain": promotion_domain},
                success=True,
            )
        except Exception:
            pass

        logger.info(f"Learning PROMOTED to {promotion_domain}: {summary[:80]}")

    async def get_learnings(self, category: str = None, limit: int = 50) -> list[dict]:
        """Retrieve learning log entries."""
        import json
        sql = text("""
            SELECT key, value FROM system_knowledge
            WHERE domain = 'learning' AND key LIKE 'learning.LRN-%'
            ORDER BY last_verified DESC NULLS LAST
            LIMIT :limit
        """)
        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, {"limit": limit})
            rows = result.mappings().all()

        entries = []
        for row in rows:
            try:
                entry = json.loads(row["value"])
                if category and entry.get("category") != category:
                    continue
                entries.append(entry)
            except (json.JSONDecodeError, TypeError):
                pass
        return entries

    async def get_stats(self) -> dict:
        """Get learning log statistics."""
        sql = text("""
            SELECT
                COUNT(*) FILTER (WHERE key LIKE 'learning.LRN-%') as total_learnings,
                COUNT(*) FILTER (WHERE key LIKE 'learning.tracker.correction%') as corrections,
                COUNT(*) FILTER (WHERE key LIKE 'learning.tracker.feature_request%') as feature_requests,
                COUNT(*) FILTER (WHERE key LIKE 'learning.tracker.knowledge_gap%') as knowledge_gaps,
                COUNT(*) FILTER (WHERE key LIKE 'learning.tracker.error%') as errors
            FROM system_knowledge
            WHERE domain = 'learning'
        """)
        async with AsyncSessionLocal() as session:
            result = await session.execute(sql)
            row = result.mappings().first()
        return dict(row) if row else {}

    @staticmethod
    def _signature(text: str) -> str:
        """Create a stable signature for deduplication."""
        import hashlib
        normalized = re.sub(r'\s+', ' ', text.lower().strip())[:200]
        return hashlib.md5(normalized.encode()).hexdigest()[:12]


# Singleton
learning_log_manager = LearningLogManager()
