"""
Learning Promotion Engine — auto-promote recurring learning patterns.

When the same pattern (similar content) appears N times (configurable, default 3)
in learning logs, the PromotionEngine automatically promotes it to system context.

Similarity is measured via fuzzy text matching (normalized n-gram overlap) to avoid
requiring real-time embedding generation for every comparison. This is efficient
for batch processing of learning logs.

Promoted entries get:
- promoted = True
- promotion_timestamp = current UTC time

Promoted entries are included in the Brain's system context assembly via
get_promoted_entries() and get_promoted_context_text().
"""

import hashlib
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import get_settings

logger = logging.getLogger(__name__)

# Default similarity threshold for grouping entries as "same pattern"
SIMILARITY_THRESHOLD = 0.60


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip markers."""
    text = text.lower().strip()
    # Remove common test markers and version suffixes
    text = re.sub(r'__\w+__', '', text)
    text = re.sub(r'\bv\d+\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _text_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two texts using SequenceMatcher.

    Returns a float between 0.0 (completely different) and 1.0 (identical).
    Uses Python's built-in SequenceMatcher which is based on Ratcliff/Obershelp.
    """
    norm_a = _normalize_text(a)
    norm_b = _normalize_text(b)
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _content_signature(text: str) -> str:
    """Create a stable hash signature for content grouping."""
    normalized = _normalize_text(text)[:200]
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


class PromotionEngine:
    """
    Scans learning log entries, groups by content similarity, and promotes
    entries exceeding the configurable threshold.

    Usage:
        engine = PromotionEngine(threshold=3)
        promoted_count = await engine.run_promotion_cycle()
    """

    def __init__(self, threshold: int = 3, similarity_threshold: float = SIMILARITY_THRESHOLD):
        """
        Args:
            threshold: Number of similar entries required before promotion. Default 3.
            similarity_threshold: Minimum text similarity ratio for grouping. Default 0.60.
        """
        self.threshold = max(1, threshold)
        self.similarity_threshold = similarity_threshold

    async def _get_session(self):
        """Create a fresh async session to avoid event-loop conflicts."""
        settings = get_settings()
        eng = create_async_engine(settings.database_url_async, echo=False)
        Sess = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        session = Sess()
        return session, eng

    # ------------------------------------------------------------------
    # PROMOTION CYCLE
    # ------------------------------------------------------------------

    async def run_promotion_cycle(self) -> int:
        """
        Scan all unpromoted learning entries, group by similarity, and promote
        groups that meet the threshold.

        Returns:
            Number of entries promoted in this cycle.
        """
        # 1. Fetch all unpromoted entries
        entries = await self._get_unpromoted_entries()
        if not entries:
            logger.debug("No unpromoted learning entries to process.")
            return 0

        # 2. Group by content similarity
        groups = self._group_by_similarity(entries)

        # 3. Promote groups that meet the threshold
        promoted_count = 0
        for group_key, group_entries in groups.items():
            if len(group_entries) >= self.threshold:
                count = await self._promote_group(group_entries)
                promoted_count += count

        if promoted_count > 0:
            logger.info(f"Promotion cycle complete: {promoted_count} entries promoted.")
        else:
            logger.debug("Promotion cycle complete: no entries met the threshold.")

        return promoted_count

    # ------------------------------------------------------------------
    # GROUPING
    # ------------------------------------------------------------------

    def _group_by_similarity(self, entries: list[dict]) -> dict[str, list[dict]]:
        """
        Group entries by content similarity using fuzzy text matching.

        Uses a greedy clustering approach: for each entry, find the first
        existing group whose representative entry has similarity >= threshold.
        If no match, start a new group.

        Returns:
            Dict mapping group_key -> list of entry dicts.
        """
        groups: dict[str, list[dict]] = {}
        representatives: dict[str, str] = {}  # group_key -> representative content

        for entry in entries:
            content = entry["content"]
            matched_group = None

            # Compare against existing group representatives
            for group_key, rep_content in representatives.items():
                sim = _text_similarity(content, rep_content)
                if sim >= self.similarity_threshold:
                    matched_group = group_key
                    break

            if matched_group:
                groups[matched_group].append(entry)
            else:
                # Start a new group
                group_key = _content_signature(content)
                groups[group_key] = [entry]
                representatives[group_key] = content

        return groups

    # ------------------------------------------------------------------
    # PROMOTE
    # ------------------------------------------------------------------

    async def _promote_group(self, entries: list[dict]) -> int:
        """
        Mark all entries in the group as promoted.

        Sets promoted=True and promotion_timestamp for each entry.

        Returns:
            Number of entries actually promoted.
        """
        now = datetime.now(timezone.utc)
        entry_ids = [e["id"] for e in entries]

        session, eng = await self._get_session()
        try:
            # Use raw SQL with ANY() for array parameter
            sql = sa_text("""
                UPDATE learning_logs
                SET promoted = TRUE, promotion_timestamp = :ts
                WHERE id = ANY(:ids) AND promoted = FALSE
            """)
            result = await session.execute(sql, {"ts": now, "ids": entry_ids})
            await session.commit()
            promoted_count = result.rowcount
        finally:
            await session.close()
            await eng.dispose()

        if promoted_count > 0:
            sample_content = entries[0]["content"][:200]
            entries_first = entries[0]
            entry_source = entries_first.get("source", "unknown")
            entry_category = entries_first.get("category", "unknown")
            project_name = f"autolearn_{entry_category}"

            try:
                bridge_session, bridge_eng = await self._get_session()
                try:
                    import json as _json
                    # Store promoted insight as agent_memory
                    mem_sql = sa_text("""
                        INSERT INTO agent_memory
                            (content, category, source, confidence, metadata,
                             created_at, updated_at, access_count, verified)
                        VALUES
                            (:content, :category, :source, :confidence, :metadata,
                             :now, :now, 0, true)
                    """)
                    await bridge_session.execute(mem_sql, {
                        "content": f"[Promoted] {sample_content} — recurring pattern detected ({promoted_count} occurrences)",
                        "category": f"promoted_{entry_category}",
                        "source": "promotion_engine",
                        "confidence": round(min(1.0, 0.5 + promoted_count * 0.1), 2),
                        "metadata": _json.dumps({
                            "type": "promoted_insight",
                            "source_type": "learning_logs",
                            "entry_source": entry_source,
                            "entry_category": entry_category,
                            "occurrence_count": promoted_count,
                            "group_size": len(entries),
                            "threshold": self.threshold,
                            "promoted_at": now.isoformat(),
                        }),
                        "now": now,
                    })
                    await bridge_session.commit()
                finally:
                    await bridge_session.close()
                    await bridge_eng.dispose()
            except Exception as e:
                logger.warning(f"Failed to bridge promoted insight to memory: {e}")

            try:
                audit_session, audit_eng = await self._get_session()
                try:
                    import json as _json
                    audit_sql = sa_text("""
                        INSERT INTO audit_log (timestamp, actor, action, resource, details, success)
                        VALUES (:ts, :actor, :action, :resource, :details, :success)
                    """)
                    await audit_session.execute(audit_sql, {
                        "ts": now,
                        "actor": "promotion_engine",
                        "action": "learning.promoted",
                        "resource": "learning_logs",
                        "details": _json.dumps({
                            "entries_promoted": promoted_count,
                            "group_size": len(entries),
                            "sample_content": sample_content,
                            "threshold": self.threshold,
                        }),
                        "success": True,
                    })
                    await audit_session.commit()
                finally:
                    await audit_session.close()
                    await audit_eng.dispose()
            except Exception:
                pass  # Audit logging is best-effort

            logger.info(
                f"Promoted {promoted_count} entries in group "
                f"(sample: {sample_content[:80]}...)"
            )

        return promoted_count

    # ------------------------------------------------------------------
    # QUERY PROMOTED ENTRIES
    # ------------------------------------------------------------------

    async def get_promoted_entries(self, limit: int = 50) -> list[dict]:
        """
        Retrieve all promoted learning entries.

        Returns:
            List of promoted entry dicts, ordered by promotion_timestamp descending.
        """
        session, eng = await self._get_session()
        try:
            sql = sa_text("""
                SELECT id, timestamp, log_type, source, content, confidence,
                       category, promoted, promotion_timestamp
                FROM learning_logs
                WHERE promoted = TRUE
                ORDER BY promotion_timestamp DESC
                LIMIT :limit
            """)
            result = await session.execute(sql, {"limit": limit})
            rows = result.mappings().all()
        finally:
            await session.close()
            await eng.dispose()

        return [self._row_to_dict(r) for r in rows]

    async def get_promoted_context_text(self) -> str:
        """
        Build a formatted text block of promoted learnings suitable for
        inclusion in the Brain's system context.

        Returns:
            A formatted string with promoted learnings, or empty string if none.
        """
        entries = await self.get_promoted_entries(limit=20)
        if not entries:
            return ""

        lines = ["Promoted learnings (recurring patterns):"]
        seen_sigs = set()

        for entry in entries:
            # Deduplicate by content signature
            sig = _content_signature(entry["content"])
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)

            conf = f" (confidence: {entry['confidence']:.0%})" if entry.get("confidence") else ""
            lines.append(f"- [{entry['category']}] {entry['content']}{conf}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    async def _get_unpromoted_entries(self) -> list[dict]:
        """Fetch all unpromoted learning entries from the database."""
        session, eng = await self._get_session()
        try:
            sql = sa_text("""
                SELECT id, timestamp, log_type, source, content, confidence,
                       category, promoted, promotion_timestamp
                FROM learning_logs
                WHERE promoted = FALSE
                ORDER BY timestamp ASC
            """)
            result = await session.execute(sql)
            rows = result.mappings().all()
        finally:
            await session.close()
            await eng.dispose()

        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a raw SQL result mapping to a dict."""
        return {
            "id": row["id"],
            "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
            "log_type": row["log_type"],
            "source": row["source"],
            "content": row["content"],
            "confidence": float(row["confidence"]) if row["confidence"] is not None else 0.5,
            "category": row["category"],
            "promoted": bool(row["promoted"]),
            "promotion_timestamp": (
                row["promotion_timestamp"].isoformat()
                if row["promotion_timestamp"] else None
            ),
        }
