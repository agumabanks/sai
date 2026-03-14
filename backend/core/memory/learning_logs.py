"""
Learning Logs — OpenClaw-inspired structured learning system.

Manages three types of learning entries:
- LEARNINGS: Insights and facts discovered during conversations or reflection.
- ERRORS: Mistakes, failures, and issues encountered.
- FEATURE_REQUESTS: Suggestions and requests from users.

Each entry tracks source, confidence, category, and promotion status.
Promoted entries are surfaced in the Brain's system context.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, desc, and_, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, LearningLog, utcnow

logger = logging.getLogger(__name__)

# Valid values for log_type and source fields
VALID_LOG_TYPES = {"LEARNINGS", "ERRORS", "FEATURE_REQUESTS"}
VALID_SOURCES = {"conversation", "reflection", "error", "user"}


class LearningLogManager:
    """
    Manages structured learning log entries in the learning_logs table.

    Provides CRUD operations with filtering by type, date range, category,
    and full-text search on content.
    """

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    async def add_entry(
        self,
        log_type: str,
        source: str,
        content: str,
        category: str,
        confidence: float = 0.5,
    ) -> dict:
        """
        Create a new learning log entry.

        Args:
            log_type: One of LEARNINGS, ERRORS, FEATURE_REQUESTS.
            source: One of conversation, reflection, error, user.
            content: The learning content text.
            category: A free-form category tag (e.g. "infrastructure", "ui").
            confidence: Float 0.0–1.0 (clamped if out of range). Default 0.5.

        Returns:
            Dict representation of the created entry.

        Raises:
            ValueError: If log_type or source is invalid.
        """
        # Validate log_type
        if log_type not in VALID_LOG_TYPES:
            raise ValueError(
                f"Invalid log_type '{log_type}'. Must be one of: {', '.join(sorted(VALID_LOG_TYPES))}"
            )

        # Validate source
        if source not in VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{source}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}"
            )

        # Clamp confidence to [0.0, 1.0]
        confidence = max(0.0, min(1.0, float(confidence)))

        now = utcnow()

        sql = sa_text("""
            INSERT INTO learning_logs
                (timestamp, log_type, source, content, confidence, category, promoted, promotion_timestamp)
            VALUES
                (:timestamp, :log_type, :source, :content, :confidence, :category, :promoted, :promotion_timestamp)
            RETURNING id, timestamp, log_type, source, content, confidence, category, promoted, promotion_timestamp
        """)

        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, {
                "timestamp": now,
                "log_type": log_type,
                "source": source,
                "content": content,
                "confidence": confidence,
                "category": category,
                "promoted": False,
                "promotion_timestamp": None,
            })
            row = result.mappings().first()
            await session.commit()

        logger.info(
            f"Learning log entry created: [{log_type}] {content[:80]}... "
            f"(source={source}, confidence={confidence:.2f}, category={category})"
        )
        return self._row_to_dict(row)

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    async def get_entries(
        self,
        log_type: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Retrieve learning log entries with optional filtering.

        Args:
            log_type: Filter by type (LEARNINGS, ERRORS, FEATURE_REQUESTS) or None for all.
            from_date: Include entries on or after this datetime.
            to_date: Include entries on or before this datetime.
            limit: Maximum number of entries to return. Default 50.

        Returns:
            List of entry dicts ordered by timestamp descending (newest first).
        """
        conditions = []
        params: dict = {"limit": limit}

        if log_type is not None:
            conditions.append("log_type = :log_type")
            params["log_type"] = log_type
        if from_date is not None:
            conditions.append("timestamp >= :from_date")
            params["from_date"] = from_date
        if to_date is not None:
            conditions.append("timestamp <= :to_date")
            params["to_date"] = to_date

        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = sa_text(f"""
            SELECT id, timestamp, log_type, source, content, confidence,
                   category, promoted, promotion_timestamp
            FROM learning_logs
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT :limit
        """)

        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, params)
            rows = result.mappings().all()

        return [self._row_to_dict(r) for r in rows]

    async def get_by_category(self, category: str, limit: int = 50) -> list[dict]:
        """
        Retrieve entries filtered by category.

        Args:
            category: The category tag to filter on.
            limit: Maximum number of entries. Default 50.

        Returns:
            List of matching entry dicts ordered by timestamp descending.
        """
        sql = sa_text("""
            SELECT id, timestamp, log_type, source, content, confidence,
                   category, promoted, promotion_timestamp
            FROM learning_logs
            WHERE category = :category
            ORDER BY timestamp DESC
            LIMIT :limit
        """)

        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, {"category": category, "limit": limit})
            rows = result.mappings().all()

        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------

    async def search_entries(self, query: str, limit: int = 20) -> list[dict]:
        """
        Full-text search on learning log content using PostgreSQL tsvector.

        Args:
            query: Search query string. Empty returns empty list.
            limit: Maximum results. Default 20.

        Returns:
            List of matching entry dicts ranked by relevance.
        """
        if not query or not query.strip():
            return []

        # Build OR-separated tsquery for better recall
        words = [w.strip() for w in query.split() if w.strip() and len(w.strip()) > 1]
        if not words:
            return []
        or_query = " | ".join(words)

        sql = sa_text("""
            SELECT id, timestamp, log_type, source, content, confidence,
                   category, promoted, promotion_timestamp,
                   ts_rank(to_tsvector('english', content),
                           to_tsquery('english', :query)) AS rank
            FROM learning_logs
            WHERE to_tsvector('english', content) @@ to_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """)

        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, {"query": or_query, "limit": limit})
            rows = result.mappings().all()

        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(entry: LearningLog) -> dict:
        """Convert a LearningLog ORM instance to a plain dict."""
        return {
            "id": entry.id,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "log_type": entry.log_type,
            "source": entry.source,
            "content": entry.content,
            "confidence": float(entry.confidence) if entry.confidence is not None else 0.5,
            "category": entry.category,
            "promoted": bool(entry.promoted),
            "promotion_timestamp": (
                entry.promotion_timestamp.isoformat()
                if entry.promotion_timestamp else None
            ),
        }

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
