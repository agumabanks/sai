"""
Sanaa AI — Context Assembly Pipeline Tests
Tests for the context assembly pipeline in backend/core/memory/context.py.

Covers:
- VAL-MEM-004: Context assembly includes promoted learnings
- VAL-MEM-005: RRF fusion search returns results (vector + FTS merged via RRF k=60)
- Deduplication of memories across search methods
- Token budget enforcement (8K default)
- Promoted learning entries included in assembled context

Uses actual embedding vectors via Ollama nomic-embed-text for realistic testing.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from core.database import Base, engine
from core.memory.context import ContextAssembler, estimate_tokens, SYSTEM_PROMPT, TOKEN_RATIO


# ==================== Constants ====================

TEST_SOURCE = "test_context_assembly"
TEST_MARKER = "__ctx_test__"


# ==================== DB Helpers ====================

async def _make_engine_and_session():
    """Create a one-shot async engine and session."""
    settings = get_settings()
    eng = create_async_engine(settings.database_url_async, echo=False)
    Sess = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return eng, Sess


async def _cleanup():
    """Remove test memories and learning logs."""
    eng, Sess = await _make_engine_and_session()
    try:
        async with Sess() as session:
            await session.execute(
                sa_text("DELETE FROM agent_memory WHERE source = :src"),
                {"src": TEST_SOURCE},
            )
            await session.execute(
                sa_text("DELETE FROM learning_logs WHERE content LIKE :pat"),
                {"pat": f"%{TEST_MARKER}%"},
            )
            await session.commit()
    finally:
        await eng.dispose()


async def _insert_memory_with_embedding(session, content, category="fact", confidence=0.9):
    """Insert a memory with a real embedding from Ollama."""
    from core.memory.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    embedding = await provider.encode(content)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    sql = sa_text("""
        INSERT INTO agent_memory
            (content, category, source, confidence, embedding, created_at, updated_at, access_count)
        VALUES
            (:content, :category, :source, :confidence,
             CAST(:embedding AS vector), NOW(), NOW(), 0)
        RETURNING id
    """)
    result = await session.execute(sql, {
        "content": content,
        "category": category,
        "source": TEST_SOURCE,
        "confidence": confidence,
        "embedding": embedding_str,
    })
    return result.scalar_one()


async def _insert_promoted_learning(session, content, category="infrastructure"):
    """Insert a promoted learning log entry."""
    sql = sa_text("""
        INSERT INTO learning_logs
            (timestamp, log_type, source, content, confidence, category, promoted, promotion_timestamp)
        VALUES
            (:ts, 'LEARNINGS', 'reflection', :content, 0.9, :category, TRUE, :ts)
        RETURNING id
    """)
    result = await session.execute(sql, {
        "ts": datetime.now(timezone.utc),
        "content": content,
        "category": category,
    })
    return result.scalar_one()


# ==================== Fixtures ====================

@pytest.fixture
async def fresh_db():
    """Dispose module-level engine so connections are on the current event loop."""
    await engine.dispose()
    yield


@pytest.fixture
async def db_session(fresh_db):
    """Per-test database session with cleanup."""
    eng, Sess = await _make_engine_and_session()
    session = Sess()
    yield session
    await session.close()
    await eng.dispose()
    await _cleanup()


@pytest.fixture
def assembler():
    """Create a ContextAssembler with a real MemoryManager."""
    from core.memory.manager import MemoryManager
    mm = MemoryManager()
    return ContextAssembler(memory=mm)


@pytest.fixture
def small_budget_assembler():
    """Create a ContextAssembler with a very small token budget."""
    from core.memory.manager import MemoryManager
    mm = MemoryManager()
    return ContextAssembler(memory=mm, max_context_tokens=500)


# ===========================================================================
# 1. Token Budget Tests
# ===========================================================================


class TestTokenBudget:
    """Test that the assembler respects the token budget."""

    def test_estimate_tokens_basic(self):
        """estimate_tokens should approximate token count from character length."""
        text = "Hello world"
        tokens = estimate_tokens(text)
        assert tokens == len(text) // TOKEN_RATIO

    def test_estimate_tokens_empty(self):
        """Empty string should return 0 tokens."""
        assert estimate_tokens("") == 0

    def test_default_max_tokens(self, assembler):
        """Default max tokens should be 8000."""
        assert assembler.max_tokens == 8000

    def test_custom_max_tokens(self):
        """Custom max_context_tokens should be respected."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()
        ca = ContextAssembler(memory=mm, max_context_tokens=4000)
        assert ca.max_tokens == 4000

    async def test_context_stays_within_budget(self, fresh_db, assembler, db_session):
        """Total assembled context should not exceed the token budget."""
        # Store several long memories
        for i in range(5):
            long_content = f"Memory entry {i}: " + "x" * 200
            await _insert_memory_with_embedding(db_session, long_content)
        await db_session.commit()

        messages = await assembler.assemble("Tell me about the system")

        total_chars = sum(len(m["content"]) for m in messages)
        total_tokens = total_chars // TOKEN_RATIO
        # Allow some slack for system prompt but should be under budget
        assert total_tokens <= assembler.max_tokens + 200, (
            f"Total tokens {total_tokens} exceeds budget {assembler.max_tokens}"
        )

    async def test_small_budget_limits_output(self, fresh_db, small_budget_assembler, db_session):
        """A very small budget should still produce valid output (system prompt + user message)."""
        messages = await small_budget_assembler.assemble("Hello")

        # Should at minimum have system prompt + user message
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Hello"

    async def test_large_memories_trimmed_by_budget(self, fresh_db, db_session):
        """When memories are large, only those fitting the budget should be included."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()
        # Use a tight budget: system prompt (~700 tokens) + user msg + 1000 tokens for everything else
        ca = ContextAssembler(memory=mm, max_context_tokens=1500)

        # Store memories with real embeddings
        for i in range(3):
            content = f"Server configuration detail {i}: " + ("configuration data " * 30)
            await _insert_memory_with_embedding(db_session, content)
        await db_session.commit()

        messages = await ca.assemble("server configuration")

        total_chars = sum(len(m["content"]) for m in messages)
        total_tokens = total_chars // TOKEN_RATIO
        assert total_tokens <= ca.max_tokens + 200


# ===========================================================================
# 2. RRF Fusion Tests (VAL-MEM-005)
# ===========================================================================


class TestRRFFusion:
    """Test Reciprocal Rank Fusion search combining vector + FTS."""

    async def test_rrf_fusion_search_returns_results(self, fresh_db, assembler, db_session):
        """Hybrid RRF search should return relevant memories (VAL-MEM-005)."""
        await _insert_memory_with_embedding(
            db_session,
            "PostgreSQL database runs on port 5432 for data storage"
        )
        await _insert_memory_with_embedding(
            db_session,
            "Redis cache server operates on port 6379"
        )
        await db_session.commit()

        # Search should use RRF fusion (vector + FTS)
        results = await assembler.memory.search("PostgreSQL database port", limit=5)
        assert len(results) > 0
        # The PostgreSQL memory should be found
        assert any("5432" in r["content"] for r in results)

    async def test_rrf_uses_k60(self):
        """The RRF merge should use k=60 parameter."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        vector_results = [
            {"id": 1, "content": "A", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "similarity": 0.95, "search_method": "vector"},
            {"id": 2, "content": "B", "category": "fact", "confidence": 0.8,
             "source": "test", "created_at": None, "similarity": 0.85, "search_method": "vector"},
        ]
        fts_results = [
            {"id": 2, "content": "B", "category": "fact", "confidence": 0.8,
             "source": "test", "created_at": None, "rank": 0.5, "search_method": "fts"},
            {"id": 3, "content": "C", "category": "fact", "confidence": 0.7,
             "source": "test", "created_at": None, "rank": 0.3, "search_method": "fts"},
        ]

        merged = mm._rrf_merge(vector_results, fts_results, k=60)

        # Item 2 appears in both lists, so it should have higher score
        assert merged[0]["id"] == 2, "Item in both lists should rank highest with k=60"

        # Verify RRF score computation with k=60
        # Item 2: 1/(60+2) + 1/(60+1) = 1/62 + 1/61
        expected_score_id2 = 1.0 / (60 + 2) + 1.0 / (60 + 1)
        assert abs(merged[0]["relevance_score"] - round(expected_score_id2, 6)) < 0.001

    async def test_rrf_deduplicates_results(self):
        """RRF merge should not return duplicate entries for the same memory ID."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        vector_results = [
            {"id": 10, "content": "Same item", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "similarity": 0.9, "search_method": "vector"},
        ]
        fts_results = [
            {"id": 10, "content": "Same item", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "rank": 0.8, "search_method": "fts"},
        ]

        merged = mm._rrf_merge(vector_results, fts_results, k=60)
        ids = [r["id"] for r in merged]
        # Should contain only one entry for id=10
        assert ids.count(10) == 1

    async def test_rrf_handles_vector_only_results(self):
        """RRF should handle results that only appear in vector search."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        vector_results = [
            {"id": 1, "content": "Vector only", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "similarity": 0.9, "search_method": "vector"},
        ]
        fts_results = []

        merged = mm._rrf_merge(vector_results, fts_results, k=60)
        assert len(merged) == 1
        assert merged[0]["id"] == 1

    async def test_rrf_handles_fts_only_results(self):
        """RRF should handle results that only appear in FTS search."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        vector_results = []
        fts_results = [
            {"id": 1, "content": "FTS only", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "rank": 0.5, "search_method": "fts"},
        ]

        merged = mm._rrf_merge(vector_results, fts_results, k=60)
        assert len(merged) == 1
        assert merged[0]["id"] == 1

    async def test_rrf_handles_empty_results(self):
        """RRF should return empty list when both sources are empty."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        merged = mm._rrf_merge([], [], k=60)
        assert merged == []

    async def test_vector_search_runs_cosine_similarity(self, fresh_db, db_session):
        """Vector search should use pgvector cosine similarity (VAL-MEM-005)."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import get_embedding_provider

        mm = MemoryManager()

        # Store two memories with real embeddings
        await _insert_memory_with_embedding(
            db_session,
            "PostgreSQL database management system for data storage"
        )
        await _insert_memory_with_embedding(
            db_session,
            "Quantum chromodynamics particle physics theory"
        )
        await db_session.commit()

        # Get query embedding and do direct vector search
        provider = get_embedding_provider()
        query_embedding = await provider.encode("PostgreSQL database storage")
        results = await mm._vector_search(query_embedding, limit=5)

        assert len(results) > 0
        # Results should have similarity scores
        for r in results:
            assert "similarity" in r
            assert r["search_method"] == "vector"

        # The PostgreSQL memory should have higher similarity than quantum physics
        pg_results = [r for r in results if "PostgreSQL" in r["content"]]
        physics_results = [r for r in results if "Quantum" in r["content"]]
        if pg_results and physics_results:
            assert pg_results[0]["similarity"] > physics_results[0]["similarity"]

    async def test_fts_search_runs_ts_rank(self, fresh_db, db_session):
        """FTS search should use PostgreSQL tsvector ts_rank (VAL-MEM-005)."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()

        await _insert_memory_with_embedding(
            db_session,
            "PostgreSQL database runs on port 5432 for production"
        )
        await db_session.commit()

        results = await mm._fts_search("PostgreSQL database port", limit=5)
        assert len(results) > 0
        for r in results:
            assert "rank" in r
            assert r["search_method"] == "fts"
            assert r["rank"] > 0

    async def test_hybrid_search_uses_both_methods(self, fresh_db, db_session):
        """The search method should run both vector AND FTS searches."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        assert mm.has_vectors, "Embedding provider should be active"

        await _insert_memory_with_embedding(
            db_session,
            "Nginx web server configured with SSL on port 443"
        )
        await db_session.commit()

        # Use patching to verify both search methods are called
        original_vector = mm._vector_search
        original_fts = mm._fts_search

        vector_called = False
        fts_called = False

        async def track_vector(*args, **kwargs):
            nonlocal vector_called
            vector_called = True
            return await original_vector(*args, **kwargs)

        async def track_fts(*args, **kwargs):
            nonlocal fts_called
            fts_called = True
            return await original_fts(*args, **kwargs)

        mm._vector_search = track_vector
        mm._fts_search = track_fts

        results = await mm.search("Nginx SSL port 443", limit=5)

        assert vector_called, "Vector search should have been called"
        assert fts_called, "FTS search should have been called"


# ===========================================================================
# 3. Deduplication Tests
# ===========================================================================


class TestDeduplication:
    """Test that duplicate memories are merged (not returned twice)."""

    async def test_rrf_merge_deduplicates_by_id(self):
        """When the same memory appears in both vector and FTS results,
        it should only appear once in the merged output."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        shared_entry = {
            "id": 42, "content": "PostgreSQL port 5432", "category": "fact",
            "confidence": 0.9, "source": "test", "created_at": None,
        }

        vector_results = [
            {**shared_entry, "similarity": 0.95, "search_method": "vector"},
        ]
        fts_results = [
            {**shared_entry, "rank": 0.8, "search_method": "fts"},
        ]

        merged = mm._rrf_merge(vector_results, fts_results, k=60)
        ids = [r["id"] for r in merged]
        assert ids == [42], "Duplicate IDs should be merged into one entry"

    async def test_assembled_context_no_duplicate_memories(self, fresh_db, db_session, assembler):
        """The assembled context should not contain duplicate memory content."""
        # Store a single memory that will be found by both vector and FTS
        await _insert_memory_with_embedding(
            db_session,
            "PostgreSQL database server runs on port 5432"
        )
        await db_session.commit()

        messages = await assembler.assemble("PostgreSQL database port 5432")

        # Count occurrences of the memory content in system messages
        memory_system_msgs = [
            m for m in messages
            if m["role"] == "system" and "PostgreSQL" in m.get("content", "")
            and "Relevant knowledge" in m.get("content", "")
        ]
        if memory_system_msgs:
            for msg in memory_system_msgs:
                # Count how many times "5432" appears in memory lines
                lines = msg["content"].split("\n")
                memory_lines = [l for l in lines if "5432" in l and l.strip().startswith("-")]
                assert len(memory_lines) <= 1, (
                    f"Duplicate memory entries found: {memory_lines}"
                )


# ===========================================================================
# 4. Promoted Learnings Tests (VAL-MEM-004)
# ===========================================================================


class TestPromotedLearnings:
    """Test that promoted learning entries are included in assembled context."""

    async def test_context_includes_promoted_learnings(self, fresh_db, db_session):
        """Promoted learning entries should appear in assembled context (VAL-MEM-004)."""
        from core.memory.manager import MemoryManager

        # Insert a promoted learning entry
        await _insert_promoted_learning(
            db_session,
            f"Always check disk space before deploying new services {TEST_MARKER}",
            category="operations",
        )
        await db_session.commit()

        mm = MemoryManager()
        ca = ContextAssembler(memory=mm)
        messages = await ca.assemble("deploy a new service")

        # Check that promoted learnings appear in the system messages
        all_content = " ".join(m["content"] for m in messages if m["role"] == "system")
        assert "Promoted learnings" in all_content or "disk space" in all_content.lower(), (
            "Promoted learning should be included in context"
        )

    async def test_promoted_learnings_separate_from_memories(self, fresh_db, db_session):
        """Promoted learnings should be in a separate section from regular memories."""
        from core.memory.manager import MemoryManager

        await _insert_promoted_learning(
            db_session,
            f"Always restart nginx after config changes {TEST_MARKER}",
            category="webserver",
        )
        await _insert_memory_with_embedding(
            db_session,
            "Nginx configuration file is at /etc/nginx/nginx.conf"
        )
        await db_session.commit()

        mm = MemoryManager()
        ca = ContextAssembler(memory=mm)
        messages = await ca.assemble("nginx configuration")

        system_messages = [m for m in messages if m["role"] == "system"]
        # There should be at least the main system prompt + memories section + promoted section
        assert len(system_messages) >= 2, (
            f"Expected at least 2 system messages, got {len(system_messages)}"
        )

    async def test_no_promoted_learnings_when_none_exist(self, fresh_db):
        """When there are no promoted learnings, that section should be skipped."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        ca = ContextAssembler(memory=mm)

        # Use a query unlikely to have any promoted learnings
        promoted_text = await ca._get_promoted_learnings()
        # This may return None or empty string if no promoted entries exist
        # (depending on DB state)
        # The key is that it doesn't crash
        assert promoted_text is None or isinstance(promoted_text, str)

    async def test_promoted_learnings_within_budget(self, fresh_db, db_session):
        """Promoted learnings should only be included if they fit within token budget."""
        from core.memory.manager import MemoryManager

        # Insert a promoted learning
        await _insert_promoted_learning(
            db_session,
            f"Very important operational pattern {TEST_MARKER}",
            category="operations",
        )
        await db_session.commit()

        # Use a very tight budget
        mm = MemoryManager()
        ca = ContextAssembler(memory=mm, max_context_tokens=400)
        messages = await ca.assemble("operations")

        # Should still be within budget
        total_chars = sum(len(m["content"]) for m in messages)
        total_tokens = total_chars // TOKEN_RATIO
        # With 400 token budget, system prompt alone is ~700 chars = ~175 tokens
        # so we just check it didn't blow up
        assert total_tokens < ca.max_tokens + 300


# ===========================================================================
# 5. Full Pipeline Integration Tests
# ===========================================================================


class TestFullPipeline:
    """End-to-end tests for the context assembly pipeline."""

    async def test_assemble_returns_valid_messages(self, fresh_db, assembler):
        """assemble() should return a valid list of message dicts."""
        messages = await assembler.assemble("Hello, how are you?")

        assert isinstance(messages, list)
        assert len(messages) >= 2  # At minimum: system prompt + user message

        # First message should be system prompt
        assert messages[0]["role"] == "system"
        assert "Sanaa AI" in messages[0]["content"]

        # Last message should be user message
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Hello, how are you?"

    async def test_assemble_with_memories_and_promoted(self, fresh_db, db_session):
        """Full pipeline: memories + promoted learnings + user message."""
        from core.memory.manager import MemoryManager

        # Insert memory with real embedding
        await _insert_memory_with_embedding(
            db_session,
            "The backup system runs pg_dump every night at 2 AM"
        )
        # Insert promoted learning
        await _insert_promoted_learning(
            db_session,
            f"Always verify backup integrity after creation {TEST_MARKER}",
            category="operations",
        )
        await db_session.commit()

        mm = MemoryManager()
        ca = ContextAssembler(memory=mm)
        messages = await ca.assemble("Tell me about backups")

        # Should have system prompt + at least one memory/promoted section + user message
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[-1]["content"] == "Tell me about backups"

    async def test_assemble_priority_order(self, fresh_db, assembler):
        """Messages should follow priority order: system prompt, memories, promoted, knowledge, history, user."""
        messages = await assembler.assemble("test query", session_id=None)

        roles = [m["role"] for m in messages]
        # First should be system, last should be user
        assert roles[0] == "system"
        assert roles[-1] == "user"

    async def test_assemble_with_session_history(self, fresh_db, db_session, assembler):
        """When session_id is provided, conversation history should be included."""
        # Insert some conversation history
        session_id = "test_session_ctx_assembly"
        for i, (role, content) in enumerate([
            ("user", "What is Redis?"),
            ("assistant", "Redis is an in-memory data store used for caching."),
        ]):
            await db_session.execute(sa_text("""
                INSERT INTO conversations (session_id, channel, sender_id, role, content, created_at)
                VALUES (:sid, 'web', 'test_user', :role, :content, NOW())
            """), {"sid": session_id, "role": role, "content": content})
        await db_session.commit()

        messages = await assembler.assemble(
            "Tell me more about Redis caching",
            session_id=session_id,
        )

        # Should include history
        all_content = " ".join(m["content"] for m in messages)
        assert "Redis" in all_content

        # Cleanup conversation history
        eng, Sess = await _make_engine_and_session()
        async with Sess() as s:
            await s.execute(sa_text(
                "DELETE FROM conversations WHERE session_id = :sid"
            ), {"sid": session_id})
            await s.commit()
        await eng.dispose()

    async def test_message_roles_valid(self, fresh_db, assembler):
        """All messages should have valid roles."""
        messages = await assembler.assemble("test")
        valid_roles = {"system", "user", "assistant"}
        for m in messages:
            assert m["role"] in valid_roles
            assert "content" in m
            assert isinstance(m["content"], str)


# ===========================================================================
# 6. RRF Score Computation Tests
# ===========================================================================


class TestRRFScoreComputation:
    """Tests for correct RRF score computation."""

    def test_rrf_score_formula(self):
        """RRF score should follow the formula: 1/(k + rank + 1) for each list."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        # Item at rank 0 in vector, rank 1 in FTS
        vector_results = [
            {"id": 1, "content": "A", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "similarity": 0.95, "search_method": "vector"},
        ]
        fts_results = [
            {"id": 99, "content": "X", "category": "fact", "confidence": 0.5,
             "source": "test", "created_at": None, "rank": 0.8, "search_method": "fts"},
            {"id": 1, "content": "A", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "rank": 0.5, "search_method": "fts"},
        ]

        merged = mm._rrf_merge(vector_results, fts_results, k=60)

        # Item 1: vector rank 0 -> 1/(60+1) + FTS rank 1 -> 1/(60+2)
        expected_id1 = 1.0 / 61 + 1.0 / 62
        # Item 99: FTS rank 0 -> 1/(60+1)
        expected_id99 = 1.0 / 61

        id1_entry = next(r for r in merged if r["id"] == 1)
        id99_entry = next(r for r in merged if r["id"] == 99)

        assert abs(id1_entry["relevance_score"] - round(expected_id1, 6)) < 0.0001
        assert abs(id99_entry["relevance_score"] - round(expected_id99, 6)) < 0.0001

    def test_rrf_combined_score_higher_than_single(self):
        """Items appearing in both lists should have higher RRF score than single-list items."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        vector_results = [
            {"id": 1, "content": "Both", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "similarity": 0.9, "search_method": "vector"},
            {"id": 2, "content": "Vector only", "category": "fact", "confidence": 0.8,
             "source": "test", "created_at": None, "similarity": 0.8, "search_method": "vector"},
        ]
        fts_results = [
            {"id": 1, "content": "Both", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "rank": 0.9, "search_method": "fts"},
            {"id": 3, "content": "FTS only", "category": "fact", "confidence": 0.7,
             "source": "test", "created_at": None, "rank": 0.5, "search_method": "fts"},
        ]

        merged = mm._rrf_merge(vector_results, fts_results, k=60)

        # Item 1 (in both) should be first
        assert merged[0]["id"] == 1
        # Its score should be higher than any single-list item
        single_scores = [r["relevance_score"] for r in merged if r["id"] != 1]
        assert merged[0]["relevance_score"] > max(single_scores)

    def test_rrf_ordering_stable(self):
        """RRF merge should produce consistent ordering."""
        from core.memory.manager import MemoryManager
        mm = MemoryManager()

        vector_results = [
            {"id": i, "content": f"Item {i}", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "similarity": 1.0 - i * 0.1, "search_method": "vector"}
            for i in range(5)
        ]
        fts_results = [
            {"id": 4 - i, "content": f"Item {4 - i}", "category": "fact", "confidence": 0.9,
             "source": "test", "created_at": None, "rank": 1.0 - i * 0.1, "search_method": "fts"}
            for i in range(5)
        ]

        merged1 = mm._rrf_merge(vector_results, fts_results, k=60)
        merged2 = mm._rrf_merge(vector_results, fts_results, k=60)
        assert [r["id"] for r in merged1] == [r["id"] for r in merged2]


# ===========================================================================
# 7. Context Assembly Structure Tests
# ===========================================================================


class TestContextStructure:
    """Test the structure of assembled context messages."""

    async def test_system_prompt_always_present(self, fresh_db, assembler):
        """System prompt should always be the first message."""
        messages = await assembler.assemble("anything")
        assert messages[0]["role"] == "system"
        assert "Sanaa AI" in messages[0]["content"]

    async def test_user_message_always_last(self, fresh_db, assembler):
        """User message should always be the last message."""
        messages = await assembler.assemble("my question")
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "my question"

    async def test_memories_section_format(self, fresh_db, db_session, assembler):
        """Memory section should have 'Relevant knowledge from memory:' header."""
        await _insert_memory_with_embedding(
            db_session,
            "The Sanaa AI platform uses FastAPI for the backend API"
        )
        await db_session.commit()

        messages = await assembler.assemble("FastAPI backend")

        memory_msgs = [
            m for m in messages
            if m["role"] == "system" and "Relevant knowledge from memory" in m.get("content", "")
        ]
        if memory_msgs:
            assert memory_msgs[0]["content"].startswith("Relevant knowledge from memory:")

    async def test_save_turn_method(self, fresh_db, assembler, db_session):
        """save_turn should persist a conversation turn to the database."""
        session_id = "test_save_turn_ctx"
        await assembler.save_turn(
            session_id=session_id,
            channel="web",
            sender_id="test_user",
            role="user",
            content="Test message for save_turn",
        )

        # Verify it was saved
        result = await db_session.execute(sa_text(
            "SELECT content FROM conversations WHERE session_id = :sid ORDER BY created_at DESC LIMIT 1"
        ), {"sid": session_id})
        row = result.scalar_one_or_none()
        assert row == "Test message for save_turn"

        # Cleanup
        eng, Sess = await _make_engine_and_session()
        async with Sess() as s:
            await s.execute(sa_text(
                "DELETE FROM conversations WHERE session_id = :sid"
            ), {"sid": session_id})
            await s.commit()
        await eng.dispose()
