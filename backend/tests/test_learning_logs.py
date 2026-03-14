"""
Sanaa AI — Learning Logs Tests
Tests for the OpenClaw-inspired structured learning logs system.
Covers: LearningLog model, LearningLogManager CRUD, search, and filtering.

Validated assertions: VAL-MEM-001, VAL-MEM-002
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.database import AsyncSessionLocal, Base, LearningLog, engine
from core.config import get_settings

# Marker for test data so cleanup can find them
TEST_MARKER = "__test__"


# ==================== Helpers ====================

async def _cleanup():
    """Remove test entries using a one-shot engine to avoid asyncpg cross-loop issues."""
    settings = get_settings()
    _engine = create_async_engine(settings.database_url_async, echo=False)
    _Session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with _Session() as session:
            await session.execute(
                text("DELETE FROM learning_logs WHERE content LIKE :pat"),
                {"pat": f"%{TEST_MARKER}%"},
            )
            await session.commit()
    finally:
        await _engine.dispose()


# ==================== Fixtures ====================

_table_created = False


@pytest.fixture
async def ensure_table():
    """Ensure the learning_logs table exists.

    Uses a one-shot engine to avoid asyncpg concurrency issues.
    """
    global _table_created
    if not _table_created:
        settings = get_settings()
        one_shot = create_async_engine(settings.database_url_async, echo=False)
        async with one_shot.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await one_shot.dispose()
        _table_created = True
    yield


@pytest.fixture
async def fresh_db(ensure_table):
    """Dispose the module-level engine so connections are created on the current
    event loop. Required because LearningLogManager uses AsyncSessionLocal internally."""
    await engine.dispose()
    yield


@pytest.fixture
async def manager(fresh_db):
    """Provide a LearningLogManager instance and clean up after each test."""
    from core.memory.learning_logs import LearningLogManager
    mgr = LearningLogManager()
    yield mgr
    await _cleanup()


# ==================== Model Tests ====================

class TestLearningLogModel:
    """Test the LearningLog SQLAlchemy model schema."""

    async def test_model_exists(self, ensure_table):
        """LearningLog model should be importable and have correct tablename."""
        from core.database import LearningLog
        assert LearningLog.__tablename__ == "learning_logs"

    async def test_model_has_required_columns(self, ensure_table):
        """Model must have all required fields per feature spec."""
        from core.database import LearningLog
        columns = {c.name for c in LearningLog.__table__.columns}
        required = {
            "id", "timestamp", "source", "content", "confidence",
            "category", "promoted", "promotion_timestamp", "log_type",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    async def test_table_exists_in_db(self, ensure_table):
        """The learning_logs table should exist in the database."""
        settings = get_settings()
        one_shot = create_async_engine(settings.database_url_async, echo=False)
        try:
            async with AsyncSession(one_shot) as session:
                result = await session.execute(text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = 'learning_logs')"
                ))
                exists = result.scalar()
            assert exists is True
        finally:
            await one_shot.dispose()

    async def test_model_column_types(self, ensure_table):
        """Verify column types are correct."""
        from core.database import LearningLog
        col_map = {c.name: c for c in LearningLog.__table__.columns}
        # confidence should be Float
        assert "Float" in str(type(col_map["confidence"].type)) or "FLOAT" in str(col_map["confidence"].type).upper()
        # promoted should be Boolean
        assert "Boolean" in str(type(col_map["promoted"].type)) or "BOOL" in str(col_map["promoted"].type).upper()


# ==================== LearningLogManager Tests ====================

class TestAddEntry:
    """Test LearningLogManager.add_entry()."""

    async def test_add_learning_entry(self, manager):
        """Adding a LEARNINGS entry should return an entry dict with all fields."""
        entry = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="The server IP is 10.0.0.1 __test__",
            confidence=0.8,
            category="infrastructure",
        )
        assert entry is not None
        assert entry["id"] is not None
        assert entry["log_type"] == "LEARNINGS"
        assert entry["source"] == "conversation"
        assert entry["content"] == "The server IP is 10.0.0.1 __test__"
        assert entry["confidence"] == 0.8
        assert entry["category"] == "infrastructure"
        assert entry["promoted"] is False
        assert entry["promotion_timestamp"] is None
        assert entry["timestamp"] is not None

    async def test_add_error_entry(self, manager):
        """Adding an ERRORS entry should work correctly."""
        entry = await manager.add_entry(
            log_type="ERRORS",
            source="error",
            content="Failed to connect to Redis on port 6380 __test__",
            confidence=0.9,
            category="connectivity",
        )
        assert entry["log_type"] == "ERRORS"
        assert entry["source"] == "error"
        assert entry["confidence"] == 0.9

    async def test_add_feature_request_entry(self, manager):
        """Adding a FEATURE_REQUESTS entry should work correctly."""
        entry = await manager.add_entry(
            log_type="FEATURE_REQUESTS",
            source="user",
            content="User wants dark mode for dashboard __test__",
            confidence=0.7,
            category="ui",
        )
        assert entry["log_type"] == "FEATURE_REQUESTS"
        assert entry["source"] == "user"

    async def test_add_entry_default_confidence(self, manager):
        """Confidence should default to 0.5 if not provided."""
        entry = await manager.add_entry(
            log_type="LEARNINGS",
            source="reflection",
            content="Default confidence test __test__",
            category="general",
        )
        assert entry["confidence"] == 0.5

    async def test_add_entry_default_promoted(self, manager):
        """Promoted should default to False."""
        entry = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="Promoted default test __test__",
            category="general",
        )
        assert entry["promoted"] is False

    async def test_add_entry_invalid_log_type(self, manager):
        """Invalid log_type should raise ValueError."""
        with pytest.raises(ValueError, match="log_type"):
            await manager.add_entry(
                log_type="INVALID_TYPE",
                source="conversation",
                content="Should fail __test__",
                category="general",
            )

    async def test_add_entry_invalid_source(self, manager):
        """Invalid source should raise ValueError."""
        with pytest.raises(ValueError, match="source"):
            await manager.add_entry(
                log_type="LEARNINGS",
                source="invalid_source",
                content="Should fail __test__",
                category="general",
            )

    async def test_add_entry_confidence_clamped(self, manager):
        """Confidence values outside 0.0-1.0 should be clamped."""
        entry_high = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="High confidence clamp __test__",
            confidence=1.5,
            category="general",
        )
        assert entry_high["confidence"] == 1.0

        entry_low = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="Low confidence clamp __test__",
            confidence=-0.5,
            category="general",
        )
        assert entry_low["confidence"] == 0.0

    async def test_add_entry_timestamp_auto_set(self, manager):
        """Timestamp should be automatically set to current UTC time."""
        before = datetime.now(timezone.utc)
        entry = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="Timestamp auto test __test__",
            category="general",
        )
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(entry["timestamp"])
        assert before <= ts <= after


# ==================== GetEntries Tests ====================

class TestGetEntries:
    """Test LearningLogManager.get_entries()."""

    async def test_get_entries_by_type(self, manager):
        """Should return only entries of the specified log_type."""
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="Learning alpha __test__", category="general",
        )
        await manager.add_entry(
            log_type="ERRORS", source="error",
            content="Error alpha __test__", category="general",
        )

        learnings = await manager.get_entries(log_type="LEARNINGS")
        for entry in learnings:
            assert entry["log_type"] == "LEARNINGS"

    async def test_get_entries_by_date_range(self, manager):
        """Should filter entries by date range."""
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="Date range test __test__", category="general",
        )

        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        entries = await manager.get_entries(
            log_type="LEARNINGS",
            from_date=yesterday,
            to_date=tomorrow,
        )
        assert len(entries) >= 1
        assert any("Date range test" in e["content"] for e in entries)

    async def test_get_entries_empty_for_future_range(self, manager):
        """No entries should match a future date range."""
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="Future range test __test__", category="general",
        )
        future_start = datetime.now(timezone.utc) + timedelta(days=1)
        future_end = datetime.now(timezone.utc) + timedelta(days=2)
        entries = await manager.get_entries(
            log_type="LEARNINGS",
            from_date=future_start,
            to_date=future_end,
        )
        # Only our __test__ entries should be considered, and none in the future
        test_entries = [e for e in entries if "__test__" in e["content"]]
        assert len(test_entries) == 0

    async def test_get_entries_all_types(self, manager):
        """When log_type is None, return all entries."""
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="All types learning __test__", category="general",
        )
        await manager.add_entry(
            log_type="ERRORS", source="error",
            content="All types error __test__", category="general",
        )
        entries = await manager.get_entries()
        types = {e["log_type"] for e in entries if "__test__" in e["content"]}
        assert "LEARNINGS" in types
        assert "ERRORS" in types

    async def test_get_entries_with_limit(self, manager):
        """Limit parameter should cap results."""
        for i in range(5):
            await manager.add_entry(
                log_type="LEARNINGS", source="conversation",
                content=f"Limit test {i} __test__", category="general",
            )
        entries = await manager.get_entries(log_type="LEARNINGS", limit=2)
        assert len(entries) <= 2


# ==================== SearchEntries Tests ====================

class TestSearchEntries:
    """Test LearningLogManager.search_entries()."""

    async def test_search_by_content(self, manager):
        """Text search should find entries by content match."""
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="PostgreSQL uses port 5432 for connections __test__",
            category="database",
        )
        results = await manager.search_entries("PostgreSQL port __test__")
        assert len(results) >= 1
        assert any("5432" in r["content"] for r in results)

    async def test_search_empty_query(self, manager):
        """Empty search query should return empty results or all entries."""
        results = await manager.search_entries("")
        # Should handle gracefully (no crash)
        assert isinstance(results, list)

    async def test_search_no_results(self, manager):
        """Search for nonexistent content should return empty list."""
        results = await manager.search_entries("xyzzynonexistent12345 __test__")
        assert results == []

    async def test_search_case_insensitive(self, manager):
        """Search should be case-insensitive."""
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="Nginx configuration updated __test__",
            category="webserver",
        )
        results = await manager.search_entries("nginx __test__")
        assert len(results) >= 1


# ==================== GetByCategory Tests ====================

class TestGetByCategory:
    """Test LearningLogManager.get_by_category()."""

    async def test_get_by_category(self, manager):
        """Should return only entries with matching category."""
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="Redis is fast __test__", category="caching",
        )
        await manager.add_entry(
            log_type="LEARNINGS", source="conversation",
            content="Postgres is reliable __test__", category="database",
        )

        results = await manager.get_by_category("caching")
        for r in results:
            assert r["category"] == "caching"

    async def test_get_by_category_empty(self, manager):
        """Non-existent category should return empty list."""
        results = await manager.get_by_category("nonexistent_category_xyz")
        assert results == []


# ==================== Entry Schema Tests ====================

class TestLearningEntrySchema:
    """Test that entries conform to the required schema (VAL-MEM-002)."""

    async def test_entry_has_all_required_fields(self, manager):
        """Each entry must have: timestamp, source, content, confidence, category."""
        entry = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="Schema validation test __test__",
            confidence=0.75,
            category="testing",
        )
        # Required by VAL-MEM-002
        assert "timestamp" in entry
        assert "source" in entry
        assert "content" in entry
        assert "confidence" in entry
        assert "category" in entry
        # Additional required fields from feature spec
        assert "id" in entry
        assert "promoted" in entry
        assert "promotion_timestamp" in entry
        assert "log_type" in entry

    async def test_source_values_are_valid(self, manager):
        """Source must be one of: conversation, reflection, error, user."""
        valid_sources = ["conversation", "reflection", "error", "user"]
        for src in valid_sources:
            entry = await manager.add_entry(
                log_type="LEARNINGS",
                source=src,
                content=f"Source {src} test __test__",
                category="general",
            )
            assert entry["source"] == src

    async def test_log_type_values_are_valid(self, manager):
        """Log type must be one of: LEARNINGS, ERRORS, FEATURE_REQUESTS."""
        valid_types = ["LEARNINGS", "ERRORS", "FEATURE_REQUESTS"]
        for lt in valid_types:
            entry = await manager.add_entry(
                log_type=lt,
                source="conversation",
                content=f"LogType {lt} test __test__",
                category="general",
            )
            assert entry["log_type"] == lt

    async def test_confidence_is_float_in_range(self, manager):
        """Confidence must be a float between 0.0 and 1.0."""
        entry = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="Confidence range test __test__",
            confidence=0.65,
            category="general",
        )
        assert isinstance(entry["confidence"], float)
        assert 0.0 <= entry["confidence"] <= 1.0

    async def test_promoted_flag_and_timestamp(self, manager):
        """Promoted should be bool; promotion_timestamp null when not promoted."""
        entry = await manager.add_entry(
            log_type="LEARNINGS",
            source="conversation",
            content="Promoted flag test __test__",
            category="general",
        )
        assert isinstance(entry["promoted"], bool)
        assert entry["promoted"] is False
        assert entry["promotion_timestamp"] is None
