"""
Sanaa AI — Learning Promotion Engine Tests
Tests for the PromotionEngine that detects recurring learning patterns
and promotes them to system context.

Covers:
- Grouping similar learning entries by content similarity
- Promoting entries exceeding the configurable threshold (default 3)
- Setting promoted=True and promotion_timestamp on promoted entries
- Context assembly including promoted learnings
- Celery task registration for periodic promotion
- Configurable threshold via settings
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from datetime import datetime, timezone
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.database import Base
from core.config import get_settings


# ==================== DB Helpers ====================

async def _make_engine_and_session():
    """Create a one-shot async engine and session to avoid asyncpg event-loop issues."""
    settings = get_settings()
    eng = create_async_engine(settings.database_url_async, echo=False)
    Sess = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return eng, Sess


async def _ensure_tables():
    """Create tables if they don't exist."""
    settings = get_settings()
    eng = create_async_engine(settings.database_url_async, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await eng.dispose()


async def _insert_entry(session, content, log_type="LEARNINGS", source="conversation",
                        confidence=0.8, category="infrastructure", promoted=False):
    """Insert a learning log entry directly via SQL and return the entry dict."""
    sql = sa_text("""
        INSERT INTO learning_logs
            (timestamp, log_type, source, content, confidence, category, promoted, promotion_timestamp)
        VALUES
            (:ts, :log_type, :source, :content, :confidence, :category, :promoted, NULL)
        RETURNING id, timestamp, log_type, source, content, confidence, category, promoted, promotion_timestamp
    """)
    result = await session.execute(sql, {
        "ts": datetime.now(timezone.utc),
        "log_type": log_type,
        "source": source,
        "content": content,
        "confidence": confidence,
        "category": category,
        "promoted": promoted,
    })
    row = result.mappings().first()
    return dict(row) if row else None


async def _get_test_entries(session, promoted_only=False):
    """Get test entries from DB."""
    if promoted_only:
        sql = sa_text(
            "SELECT id, content, promoted, promotion_timestamp FROM learning_logs "
            "WHERE content LIKE '%__promo_test__%' AND promoted = TRUE ORDER BY id"
        )
    else:
        sql = sa_text(
            "SELECT id, content, promoted, promotion_timestamp FROM learning_logs "
            "WHERE content LIKE '%__promo_test__%' ORDER BY id"
        )
    result = await session.execute(sql)
    return [dict(r) for r in result.mappings().all()]


async def _cleanup(session):
    """Delete test entries."""
    await session.execute(
        sa_text("DELETE FROM learning_logs WHERE content LIKE '%__promo_test__%'")
    )
    await session.commit()


# ==================== Fixtures ====================

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def db_setup():
    """Module-level DB setup: ensure tables exist."""
    await _ensure_tables()


@pytest.fixture
async def db():
    """Per-test DB session with cleanup. Returns (session, engine)."""
    eng, Sess = await _make_engine_and_session()
    session = Sess()
    # Cleanup before test
    try:
        await _cleanup(session)
    except Exception:
        pass
    yield session
    # Cleanup after test
    try:
        await _cleanup(session)
    except Exception:
        pass
    await session.close()
    await eng.dispose()


@pytest.fixture
def promotion_engine():
    """Provide a PromotionEngine instance (no DB dependency in constructor)."""
    from core.memory.promotion import PromotionEngine
    return PromotionEngine()


# ==================== Threshold Tests ====================

class TestPromotionThreshold:
    """Tests for promotion threshold logic (VAL-MEM-003)."""

    async def test_entries_below_threshold_not_promoted(
        self, db_setup, db, promotion_engine
    ):
        """Entries appearing fewer than 3 times should NOT be promoted."""
        await _insert_entry(db, "Redis runs on port 6379 __promo_test__")
        await _insert_entry(db, "Redis server runs on port 6379 __promo_test__")
        await db.commit()

        promoted = await promotion_engine.run_promotion_cycle()
        assert promoted == 0

    async def test_entries_at_threshold_get_promoted(
        self, db_setup, db, promotion_engine
    ):
        """Entries appearing 3+ times should be flagged promoted=True (VAL-MEM-003)."""
        for i in range(3):
            await _insert_entry(
                db,
                f"PostgreSQL runs on port 5432 for database connections __promo_test__ v{i}",
                category="database",
            )
        await db.commit()

        promoted_count = await promotion_engine.run_promotion_cycle()
        assert promoted_count >= 1

        entries = await _get_test_entries(db, promoted_only=True)
        assert len(entries) >= 1

    async def test_promoted_entries_have_timestamp(
        self, db_setup, db, promotion_engine
    ):
        """Promoted entries must have promotion_timestamp set (VAL-MEM-003)."""
        for i in range(3):
            await _insert_entry(
                db,
                f"Nginx listens on port 443 for HTTPS __promo_test__ v{i}",
                category="webserver", confidence=0.9,
            )
        await db.commit()

        await promotion_engine.run_promotion_cycle()

        entries = await _get_test_entries(db, promoted_only=True)
        assert len(entries) >= 1
        for entry in entries:
            assert entry["promotion_timestamp"] is not None

    async def test_promotion_above_threshold(
        self, db_setup, db, promotion_engine
    ):
        """5 similar entries should definitely trigger promotion."""
        for i in range(5):
            await _insert_entry(
                db,
                f"Ollama provides local LLM inference __promo_test__ v{i}",
                category="ai", confidence=0.85,
            )
        await db.commit()

        promoted_count = await promotion_engine.run_promotion_cycle()
        assert promoted_count >= 1

    async def test_dissimilar_entries_not_grouped(
        self, db_setup, db, promotion_engine
    ):
        """Entries with different content should not be grouped together."""
        await _insert_entry(db, "Redis is a fast in-memory cache __promo_test__")
        await _insert_entry(db, "Celery handles async task processing __promo_test__")
        await _insert_entry(db, "Nginx serves static files efficiently __promo_test__")
        await db.commit()

        promoted_count = await promotion_engine.run_promotion_cycle()
        assert promoted_count == 0


class TestConfigurableThreshold:
    """Tests for configurable promotion threshold."""

    async def test_custom_threshold(self, db_setup, db):
        """Threshold should be configurable (e.g., set to 2)."""
        from core.memory.promotion import PromotionEngine
        engine = PromotionEngine(threshold=2)

        for i in range(2):
            await _insert_entry(
                db,
                f"Custom threshold test: Disk usage above 80% __promo_test__ v{i}",
                category="monitoring", confidence=0.7,
            )
        await db.commit()

        promoted_count = await engine.run_promotion_cycle()
        assert promoted_count >= 1

    async def test_default_threshold_is_three(self):
        """Default threshold should be 3."""
        from core.memory.promotion import PromotionEngine
        engine = PromotionEngine()
        assert engine.threshold == 3

    async def test_threshold_via_settings(self):
        """PromotionEngine should respect threshold from constructor."""
        from core.memory.promotion import PromotionEngine
        engine = PromotionEngine(threshold=5)
        assert engine.threshold == 5


# ==================== Grouping Tests ====================

class TestSimilarityGrouping:
    """Tests for grouping similar learning entries."""

    async def test_groups_similar_entries(
        self, db_setup, db, promotion_engine
    ):
        """Should group entries with similar content together."""
        for i in range(3):
            await _insert_entry(
                db,
                f"The API rate limit is 100 requests per minute __promo_test__ v{i}",
                category="api",
            )
        # One entry about a different topic
        await _insert_entry(
            db,
            "Server backup runs at 3 AM daily __promo_test__",
            category="backup",
        )
        await db.commit()

        promoted_count = await promotion_engine.run_promotion_cycle()
        assert promoted_count >= 1

        # The backup entry should not be promoted
        result = await db.execute(sa_text(
            "SELECT promoted FROM learning_logs "
            "WHERE content LIKE '%Server backup%__promo_test__%'"
        ))
        row = result.fetchone()
        if row:
            assert row[0] is False

    async def test_groups_across_log_types(
        self, db_setup, db, promotion_engine
    ):
        """Similar entries from different log_types should be grouped."""
        await _insert_entry(
            db,
            "Memory usage spikes during nightly cron __promo_test__",
            log_type="LEARNINGS", category="monitoring",
        )
        await _insert_entry(
            db,
            "Memory usage spikes during nightly cron jobs __promo_test__",
            log_type="ERRORS", category="monitoring",
        )
        await _insert_entry(
            db,
            "Memory usage spikes when nightly cron runs __promo_test__",
            log_type="LEARNINGS", source="reflection", category="monitoring",
        )
        await db.commit()

        promoted_count = await promotion_engine.run_promotion_cycle()
        assert promoted_count >= 1


# ==================== Auto-Promote Tests (VAL-MEM-009) ====================

class TestAutoPromote:
    """Tests for automatic promotion without manual intervention (VAL-MEM-009)."""

    async def test_auto_promote_at_threshold(
        self, db_setup, db, promotion_engine
    ):
        """When 3+ similar entries detected, system auto-promotes (VAL-MEM-009)."""
        for i in range(4):
            await _insert_entry(
                db,
                f"Celery worker should be restarted after code deploy __promo_test__ v{i}",
                category="operations",
            )
        await db.commit()

        promoted_count = await promotion_engine.run_promotion_cycle()
        assert promoted_count >= 1

        entries = await _get_test_entries(db, promoted_only=True)
        assert len(entries) >= 1
        for entry in entries:
            assert entry["promoted"] is True
            assert entry["promotion_timestamp"] is not None

    async def test_already_promoted_entries_skipped(
        self, db_setup, db, promotion_engine
    ):
        """Already promoted entries should not be re-promoted."""
        for i in range(3):
            await _insert_entry(
                db,
                f"Docker containers auto-restart on failure __promo_test__ v{i}",
                category="infrastructure",
            )
        await db.commit()

        first_count = await promotion_engine.run_promotion_cycle()
        assert first_count >= 1

        # Second promotion cycle should not re-promote
        second_count = await promotion_engine.run_promotion_cycle()
        assert second_count == 0


# ==================== Context Assembly Tests (VAL-MEM-004) ====================

class TestContextAssembly:
    """Tests for promoted learnings in context assembly (VAL-MEM-004)."""

    async def test_context_includes_promoted_learnings(
        self, db_setup, db, promotion_engine
    ):
        """Context assembly should include promoted learning entries (VAL-MEM-004)."""
        for i in range(3):
            await _insert_entry(
                db,
                f"Always check disk space before deployment __promo_test__ v{i}",
                category="operations", confidence=0.9,
            )
        await db.commit()

        await promotion_engine.run_promotion_cycle()

        promoted_entries = await promotion_engine.get_promoted_entries()
        assert len(promoted_entries) >= 1
        assert any("disk space" in e["content"].lower() for e in promoted_entries)

    async def test_get_promoted_entries_returns_only_promoted(
        self, db_setup, db, promotion_engine
    ):
        """get_promoted_entries() should return only promoted=True entries."""
        await _insert_entry(
            db, "Unpromoted test entry alpha __promo_test__",
            category="general", confidence=0.5,
        )
        for i in range(3):
            await _insert_entry(
                db,
                f"Must restart nginx after config changes __promo_test__ v{i}",
                category="webserver", confidence=0.9,
            )
        await db.commit()

        await promotion_engine.run_promotion_cycle()

        promoted = await promotion_engine.get_promoted_entries()
        for entry in promoted:
            assert entry["promoted"] is True

    async def test_promoted_learnings_format_for_context(
        self, db_setup, db, promotion_engine
    ):
        """Promoted entries should be formatted as context strings."""
        for i in range(3):
            await _insert_entry(
                db,
                f"Use pgvector for semantic search __promo_test__ v{i}",
                category="database", confidence=0.85,
            )
        await db.commit()

        await promotion_engine.run_promotion_cycle()

        context_text = await promotion_engine.get_promoted_context_text()
        assert isinstance(context_text, str)
        assert len(context_text) > 0
        assert "pgvector" in context_text.lower() or "semantic search" in context_text.lower()

    async def test_context_assembler_includes_promoted(
        self, db_setup, db, promotion_engine
    ):
        """The ContextAssembler._get_promoted_learnings() should return text when promoted entries exist."""
        for i in range(3):
            await _insert_entry(
                db,
                f"Always monitor CPU usage on production __promo_test__ v{i}",
                category="monitoring", confidence=0.9,
            )
        await db.commit()
        await promotion_engine.run_promotion_cycle()

        from core.memory.context import ContextAssembler
        from core.memory.manager import MemoryManager
        assembler = ContextAssembler(memory=MemoryManager())
        promoted_text = await assembler._get_promoted_learnings()
        assert promoted_text is not None
        assert "Promoted learnings" in promoted_text


# ==================== Celery Task Tests ====================

class TestCeleryTask:
    """Tests for the Celery periodic task registration."""

    def test_celery_task_registered(self):
        """promotion_check task should be registered in Celery."""
        from core.tasks import app as celery_app
        task_names = list(celery_app.conf.beat_schedule.keys())
        assert "learning-promotion-check" in task_names

    def test_celery_task_schedule(self):
        """Promotion task should run periodically."""
        from core.tasks import app as celery_app
        schedule = celery_app.conf.beat_schedule.get("learning-promotion-check", {})
        assert "schedule" in schedule
        assert "task" in schedule
        assert schedule["task"] == "core.tasks.learning_promotion_check"

    def test_promotion_task_callable(self):
        """The promotion Celery task should be importable."""
        from core.tasks import learning_promotion_check
        assert callable(learning_promotion_check)


# ==================== Unit Tests for Similarity Logic ====================

class TestSimilarityLogic:
    """Unit tests for the text similarity and grouping logic."""

    def test_normalize_text(self):
        """Text normalization should lowercase and collapse whitespace."""
        from core.memory.promotion import _normalize_text
        assert _normalize_text("  Hello   World  ") == "hello world"

    def test_text_similarity_identical(self):
        """Identical texts should have similarity 1.0."""
        from core.memory.promotion import _text_similarity
        assert _text_similarity("Redis runs on port 6379", "Redis runs on port 6379") == 1.0

    def test_text_similarity_similar(self):
        """Similar texts should have high similarity."""
        from core.memory.promotion import _text_similarity
        sim = _text_similarity(
            "PostgreSQL runs on port 5432",
            "PostgreSQL server runs on port 5432"
        )
        assert sim > 0.7

    def test_text_similarity_different(self):
        """Different texts should have low similarity."""
        from core.memory.promotion import _text_similarity
        sim = _text_similarity(
            "Redis is a caching system",
            "Celery handles task queues"
        )
        assert sim < 0.5

    def test_text_similarity_empty(self):
        """Empty strings should return 0.0."""
        from core.memory.promotion import _text_similarity
        assert _text_similarity("", "something") == 0.0
        assert _text_similarity("something", "") == 0.0

    def test_grouping_logic(self):
        """Groups entries correctly by similarity."""
        from core.memory.promotion import PromotionEngine
        engine = PromotionEngine()
        entries = [
            {"id": 1, "content": "Redis runs on port 6379"},
            {"id": 2, "content": "Redis server runs on port 6379"},
            {"id": 3, "content": "Redis is running on port 6379"},
            {"id": 4, "content": "Nginx serves files on port 80"},
        ]
        groups = engine._group_by_similarity(entries)
        # Should have 2 groups: Redis group (3 entries) and Nginx group (1 entry)
        group_sizes = sorted([len(g) for g in groups.values()], reverse=True)
        assert group_sizes[0] == 3  # Redis group
        assert group_sizes[1] == 1  # Nginx group
