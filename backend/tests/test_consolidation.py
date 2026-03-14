"""
Tests for the memory consolidation system.

Covers:
- Merging similar memories (>0.9 cosine similarity)
- Confidence decay for memories unaccessed 30+ days
- Pruning low-confidence old memories
- Deduplication on store (>0.95 cosine similarity)
- Consolidation logging
- Celery Beat task registration
"""

import json
import logging
import math
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import get_settings


# ==================== HELPERS ====================

def _make_fake_embedding(seed: float, dim: int = 1536) -> list[float]:
    """Create a fake embedding vector with a known seed for testing.

    Uses a deterministic pattern so we can control similarity between vectors.
    Two vectors created from the same seed will be identical (similarity=1.0).
    Vectors from different seeds will have controlled similarity.
    """
    import math
    vec = []
    for i in range(dim):
        val = math.sin(seed * (i + 1)) * 0.5 + 0.5
        vec.append(val)
    # Normalize to unit vector for cosine similarity
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _make_similar_embedding(base: list[float], noise: float = 0.01) -> list[float]:
    """Create a vector very similar to `base` by adding small noise.

    Lower noise -> higher similarity. noise=0.01 gives ~0.99+ similarity.
    """
    import random
    random.seed(42)
    vec = [v + random.uniform(-noise, noise) for v in base]
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _get_session():
    """Create a fresh async session for test operations."""
    settings = get_settings()
    eng = create_async_engine(settings.database_url_async, echo=False)
    Sess = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    session = Sess()
    return session, eng


async def _insert_memory(
    session,
    content: str,
    confidence: float = 0.5,
    created_at: datetime = None,
    last_accessed_at: datetime = None,
    embedding: list[float] = None,
    category: str = "fact",
    verified: bool = False,
    access_count: int = 0,
) -> int:
    """Insert a test memory directly into the database."""
    now = datetime.now(timezone.utc)
    created_at = created_at or now
    last_accessed_at = last_accessed_at or now

    if embedding:
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        sql = sa_text("""
            INSERT INTO agent_memory
                (content, category, source, confidence, verified, access_count,
                 last_accessed_at, created_at, updated_at, embedding)
            VALUES
                (:content, :category, 'test', :confidence, :verified, :access_count,
                 :last_accessed_at, :created_at, :updated_at, CAST(:embedding AS vector))
            RETURNING id
        """)
        result = await session.execute(sql, {
            "content": content,
            "category": category,
            "confidence": confidence,
            "verified": verified,
            "access_count": access_count,
            "last_accessed_at": last_accessed_at,
            "created_at": created_at,
            "updated_at": now,
            "embedding": embedding_str,
        })
    else:
        sql = sa_text("""
            INSERT INTO agent_memory
                (content, category, source, confidence, verified, access_count,
                 last_accessed_at, created_at, updated_at)
            VALUES
                (:content, :category, 'test', :confidence, :verified, :access_count,
                 :last_accessed_at, :created_at, :updated_at)
            RETURNING id
        """)
        result = await session.execute(sql, {
            "content": content,
            "category": category,
            "confidence": confidence,
            "verified": verified,
            "access_count": access_count,
            "last_accessed_at": last_accessed_at,
            "created_at": created_at,
            "updated_at": now,
        })

    memory_id = result.scalar_one()
    return memory_id


async def _get_memory_by_id(session, memory_id: int) -> dict:
    """Fetch a memory by ID."""
    sql = sa_text("""
        SELECT id, content, category, confidence, verified, access_count,
               last_accessed_at, created_at, updated_at, source
        FROM agent_memory WHERE id = :id
    """)
    result = await session.execute(sql, {"id": memory_id})
    row = result.mappings().first()
    return dict(row) if row else None


async def _count_memories(session) -> int:
    """Count all memories in the table."""
    result = await session.execute(sa_text("SELECT COUNT(*) FROM agent_memory"))
    return result.scalar_one()


async def _cleanup_test_memories(session, ids: list[int]):
    """Remove test memories by ID."""
    if ids:
        await session.execute(
            sa_text("DELETE FROM agent_memory WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        await session.commit()


# ==================== FIXTURES ====================

@pytest.fixture
async def consolidator():
    """Provide a MemoryConsolidator instance."""
    from core.memory.consolidation import MemoryConsolidator
    return MemoryConsolidator()


@pytest.fixture
async def db():
    """Provide a database session for test operations, with cleanup."""
    session, eng = await _get_session()
    created_ids = []
    yield session, created_ids
    # Cleanup
    try:
        if created_ids:
            await session.execute(
                sa_text("DELETE FROM agent_memory WHERE id = ANY(:ids)"),
                {"ids": created_ids},
            )
            await session.commit()
    except Exception:
        pass
    finally:
        await session.close()
        await eng.dispose()


# ==================== TEST: MERGE SIMILAR MEMORIES ====================

class TestMergeSimilarMemories:
    """Test merging memories with >0.9 cosine similarity."""

    async def test_similar_memories_are_merged(self, consolidator, db):
        """Two memories with >0.9 similarity should be merged into one with combined confidence."""
        session, created_ids = db

        # Create two highly similar embeddings
        base_emb = _make_fake_embedding(seed=1.0)
        similar_emb = _make_similar_embedding(base_emb, noise=0.005)  # >0.99 similarity

        # Verify our test embeddings are actually similar
        sim = _cosine_similarity(base_emb, similar_emb)
        assert sim > 0.9, f"Test embeddings should be >0.9 similar, got {sim}"

        id1 = await _insert_memory(session, "Server A runs PostgreSQL on port 5432",
                                   confidence=0.6, embedding=base_emb)
        id2 = await _insert_memory(session, "Server A runs PostgreSQL on port 5432 and handles data",
                                   confidence=0.4, embedding=similar_emb)
        await session.commit()
        created_ids.extend([id1, id2])

        result = await consolidator.merge_similar_memories()

        assert result["merged_count"] >= 1

        # One of the memories should be deleted, the survivor should have combined confidence
        m1 = await _get_memory_by_id(session, id1)
        m2 = await _get_memory_by_id(session, id2)

        # At least one should be gone
        assert m1 is None or m2 is None, "One memory should be deleted after merge"

        # The surviving one should have higher confidence
        survivor = m1 if m1 is not None else m2
        assert survivor is not None
        # Combined confidence should be at least the max of the two originals
        assert survivor["confidence"] >= 0.6

    async def test_dissimilar_memories_not_merged(self, consolidator, db):
        """Memories with <0.9 similarity should NOT be merged."""
        session, created_ids = db

        emb1 = _make_fake_embedding(seed=1.0)
        emb2 = _make_fake_embedding(seed=100.0)  # Very different

        sim = _cosine_similarity(emb1, emb2)
        assert sim < 0.9, f"Test embeddings should be <0.9 similar, got {sim}"

        id1 = await _insert_memory(session, "The server uses Ubuntu 22.04",
                                   confidence=0.5, embedding=emb1)
        id2 = await _insert_memory(session, "Redis cache hit ratio is 95%",
                                   confidence=0.5, embedding=emb2)
        await session.commit()
        created_ids.extend([id1, id2])

        result = await consolidator.merge_similar_memories()

        # Both should still exist
        m1 = await _get_memory_by_id(session, id1)
        m2 = await _get_memory_by_id(session, id2)
        assert m1 is not None, "First memory should still exist"
        assert m2 is not None, "Second memory should still exist"

    async def test_verified_memories_not_merged_away(self, consolidator, db):
        """Verified memories should always survive merges (never be deleted)."""
        session, created_ids = db

        base_emb = _make_fake_embedding(seed=2.0)
        similar_emb = _make_similar_embedding(base_emb, noise=0.005)

        id1 = await _insert_memory(session, "Critical: server admin password is rotated monthly",
                                   confidence=0.4, embedding=base_emb, verified=True)
        id2 = await _insert_memory(session, "Critical: server admin password is rotated monthly, always",
                                   confidence=0.6, embedding=similar_emb, verified=False)
        await session.commit()
        created_ids.extend([id1, id2])

        await consolidator.merge_similar_memories()

        # Verified memory should survive
        m1 = await _get_memory_by_id(session, id1)
        assert m1 is not None, "Verified memory should never be deleted"


# ==================== TEST: CONFIDENCE DECAY ====================

class TestConfidenceDecay:
    """Test confidence decay for memories not accessed in 30+ days."""

    async def test_decay_applied_to_stale_memories(self, consolidator, db):
        """Memories unaccessed for 30+ days should get confidence * 0.95."""
        session, created_ids = db

        stale_date = datetime.now(timezone.utc) - timedelta(days=35)
        id1 = await _insert_memory(
            session, "Old memory that should decay",
            confidence=0.8,
            last_accessed_at=stale_date,
        )
        await session.commit()
        created_ids.append(id1)

        result = await consolidator.apply_confidence_decay()

        assert result["decayed_count"] >= 1

        # Check the confidence was reduced
        mem = await _get_memory_by_id(session, id1)
        assert mem is not None
        expected = 0.8 * 0.95
        assert abs(mem["confidence"] - expected) < 0.01, \
            f"Expected confidence ~{expected}, got {mem['confidence']}"

    async def test_recent_memories_not_decayed(self, consolidator, db):
        """Memories accessed recently should NOT be decayed."""
        session, created_ids = db

        recent_date = datetime.now(timezone.utc) - timedelta(days=5)
        id1 = await _insert_memory(
            session, "Recent memory that should not decay",
            confidence=0.8,
            last_accessed_at=recent_date,
        )
        await session.commit()
        created_ids.append(id1)

        await consolidator.apply_confidence_decay()

        mem = await _get_memory_by_id(session, id1)
        assert mem is not None
        assert abs(mem["confidence"] - 0.8) < 0.01, \
            f"Recent memory should not decay, confidence is {mem['confidence']}"

    async def test_verified_memories_not_decayed(self, consolidator, db):
        """Verified memories should never be decayed."""
        session, created_ids = db

        stale_date = datetime.now(timezone.utc) - timedelta(days=60)
        id1 = await _insert_memory(
            session, "Verified memory should never decay",
            confidence=0.8,
            last_accessed_at=stale_date,
            verified=True,
        )
        await session.commit()
        created_ids.append(id1)

        await consolidator.apply_confidence_decay()

        mem = await _get_memory_by_id(session, id1)
        assert mem is not None
        assert abs(mem["confidence"] - 0.8) < 0.01, \
            f"Verified memory should not decay, confidence is {mem['confidence']}"

    async def test_decay_persists_new_confidence(self, consolidator, db):
        """Decayed confidence should be persisted in the database."""
        session, created_ids = db

        stale_date = datetime.now(timezone.utc) - timedelta(days=40)
        id1 = await _insert_memory(
            session, "Memory for persistence check",
            confidence=0.5,
            last_accessed_at=stale_date,
        )
        await session.commit()
        created_ids.append(id1)

        await consolidator.apply_confidence_decay()

        # Re-fetch and verify
        mem = await _get_memory_by_id(session, id1)
        assert mem is not None
        expected = 0.5 * 0.95
        assert abs(mem["confidence"] - expected) < 0.01


# ==================== TEST: PRUNE OLD LOW-CONFIDENCE ====================

class TestPruneOldMemories:
    """Test deletion of memories with confidence < 0.1 and age > 90 days."""

    async def test_old_low_confidence_deleted(self, consolidator, db):
        """Memories older than 90 days with confidence < 0.1 should be deleted."""
        session, created_ids = db

        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        id1 = await _insert_memory(
            session, "Old low-confidence memory to delete",
            confidence=0.05,
            created_at=old_date,
            last_accessed_at=old_date,
        )
        await session.commit()
        created_ids.append(id1)

        result = await consolidator.prune_old_memories()

        assert result["pruned_count"] >= 1

        mem = await _get_memory_by_id(session, id1)
        assert mem is None, "Old low-confidence memory should be deleted"

    async def test_old_high_confidence_kept(self, consolidator, db):
        """Old memories with confidence >= 0.1 should NOT be deleted."""
        session, created_ids = db

        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        id1 = await _insert_memory(
            session, "Old but confident memory",
            confidence=0.5,
            created_at=old_date,
            last_accessed_at=old_date,
        )
        await session.commit()
        created_ids.append(id1)

        await consolidator.prune_old_memories()

        mem = await _get_memory_by_id(session, id1)
        assert mem is not None, "Old memory with good confidence should survive"

    async def test_new_low_confidence_kept(self, consolidator, db):
        """Recent memories with low confidence should NOT be deleted."""
        session, created_ids = db

        recent_date = datetime.now(timezone.utc) - timedelta(days=30)
        id1 = await _insert_memory(
            session, "New low-confidence memory",
            confidence=0.05,
            created_at=recent_date,
            last_accessed_at=recent_date,
        )
        await session.commit()
        created_ids.append(id1)

        await consolidator.prune_old_memories()

        mem = await _get_memory_by_id(session, id1)
        assert mem is not None, "Recent low-confidence memory should survive"

    async def test_verified_old_low_confidence_kept(self, consolidator, db):
        """Verified memories should never be deleted regardless of confidence/age."""
        session, created_ids = db

        old_date = datetime.now(timezone.utc) - timedelta(days=200)
        id1 = await _insert_memory(
            session, "Verified old low-confidence memory",
            confidence=0.05,
            created_at=old_date,
            last_accessed_at=old_date,
            verified=True,
        )
        await session.commit()
        created_ids.append(id1)

        await consolidator.prune_old_memories()

        mem = await _get_memory_by_id(session, id1)
        assert mem is not None, "Verified memory should never be deleted"


# ==================== TEST: DEDUPLICATION ON STORE ====================

class TestMemoryDeduplication:
    """Test that storing a near-duplicate memory updates existing instead of creating new."""

    async def test_duplicate_updates_existing_confidence(self, db):
        """Storing a memory with >0.95 cosine similarity to existing should update confidence."""
        session, created_ids = db

        base_emb = _make_fake_embedding(seed=5.0)

        id1 = await _insert_memory(
            session, "The database server runs on port 5432",
            confidence=0.5,
            embedding=base_emb,
        )
        await session.commit()
        created_ids.append(id1)

        # Now store a near-duplicate through the MemoryManager
        from core.memory.consolidation import check_duplicate_before_store

        result = await check_duplicate_before_store(
            content="The database server runs on port 5432",
            embedding=base_emb,  # Identical embedding -> similarity = 1.0
        )

        assert result is not None, "Should detect duplicate"
        assert result["existing_id"] == id1, "Should return the existing memory ID"
        assert result["action"] == "update"

    async def test_unique_memory_not_flagged(self, db):
        """Storing a unique memory should not be flagged as duplicate."""
        session, created_ids = db

        emb1 = _make_fake_embedding(seed=6.0)
        emb2 = _make_fake_embedding(seed=200.0)

        id1 = await _insert_memory(
            session, "Ubuntu server with nginx",
            confidence=0.5,
            embedding=emb1,
        )
        await session.commit()
        created_ids.append(id1)

        from core.memory.consolidation import check_duplicate_before_store

        result = await check_duplicate_before_store(
            content="Redis caching layer performance",
            embedding=emb2,
        )

        assert result is None, "Unique memory should not be flagged as duplicate"


# ==================== TEST: FULL CONSOLIDATION RUN ====================

class TestFullConsolidation:
    """Test the full consolidation pipeline."""

    async def test_run_consolidation_returns_stats(self, consolidator, db):
        """The full consolidation should return stats with merged, decayed, and pruned counts."""
        session, created_ids = db

        # Insert some test data
        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        stale_date = datetime.now(timezone.utc) - timedelta(days=35)

        id1 = await _insert_memory(session, "Test memory for full consolidation",
                                   confidence=0.05, created_at=old_date,
                                   last_accessed_at=old_date)
        id2 = await _insert_memory(session, "Stale memory for decay test",
                                   confidence=0.8, last_accessed_at=stale_date)
        await session.commit()
        created_ids.extend([id1, id2])

        result = await consolidator.run_consolidation()

        assert "merged_count" in result
        assert "decayed_count" in result
        assert "pruned_count" in result
        assert isinstance(result["merged_count"], int)
        assert isinstance(result["decayed_count"], int)
        assert isinstance(result["pruned_count"], int)

    async def test_consolidation_logs_results(self, consolidator, db, caplog):
        """Consolidation should log its results."""
        session, created_ids = db

        with caplog.at_level(logging.INFO, logger="core.memory.consolidation"):
            await consolidator.run_consolidation()

        # Check that consolidation logged something
        assert any("consolidation" in r.message.lower() or "Consolidation" in r.message
                    for r in caplog.records), \
            f"Expected consolidation log message, got: {[r.message for r in caplog.records]}"


# ==================== TEST: CELERY TASK REGISTRATION ====================

class TestCeleryTaskRegistration:
    """Test that consolidation is registered as a Celery Beat task."""

    def test_celery_beat_schedule_includes_consolidation(self):
        """The Celery Beat schedule should include a daily memory consolidation task."""
        from core.tasks import app as celery_app

        schedule = celery_app.conf.beat_schedule
        # Find a task that references consolidation
        consolidation_tasks = [
            name for name, config in schedule.items()
            if "consolidat" in name.lower() or "consolidat" in config.get("task", "").lower()
        ]
        assert len(consolidation_tasks) > 0, \
            f"No consolidation task found in beat_schedule. Tasks: {list(schedule.keys())}"

    def test_consolidation_task_runs_daily(self):
        """The consolidation task should be scheduled to run daily."""
        from core.tasks import app as celery_app
        from celery.schedules import crontab

        schedule = celery_app.conf.beat_schedule
        for name, config in schedule.items():
            if "consolidat" in name.lower() or "consolidat" in config.get("task", "").lower():
                sched = config["schedule"]
                # Should be a crontab
                assert isinstance(sched, crontab), \
                    f"Consolidation task should use crontab schedule, got {type(sched)}"
                # Should run at hour 3 (3 AM EAT)
                assert "3" in str(sched), \
                    f"Consolidation should run at 3 AM, schedule: {sched}"
                return

        pytest.fail("No consolidation crontab task found")

    def test_consolidation_task_callable(self):
        """The consolidation Celery task should be callable."""
        from core.tasks import memory_consolidation
        assert callable(memory_consolidation)
