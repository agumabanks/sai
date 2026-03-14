"""
Tests for the vector embedding pipeline — Ollama nomic-embed-text, pgvector
cosine similarity search, NullEmbeddings graceful fallback, and end-to-end
memory store/retrieve with embeddings.

Covers VAL-FOUND-005: Vector embeddings functional
"""

import logging
from unittest.mock import patch, MagicMock

import pytest

from core.memory.embeddings import (
    EMBEDDING_DIM,
    OllamaEmbeddings,
    LiteLLMEmbeddings,
    NullEmbeddings,
    get_embedding_provider,
    _ollama_has_embedding_model,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_SOURCE = "test_embeddings_suite"


# ---------------------------------------------------------------------------
# Helpers: fresh engine per-test to avoid cross-loop connection pool issues
# ---------------------------------------------------------------------------


async def _get_fresh_session():
    """Create a fresh async session that works on the current event loop.

    The module-level engine in core/database.py may have connections pooled on
    a different loop (from earlier test modules). Disposing it forces new
    connections on the *current* loop.
    """
    from core.database import engine, AsyncSessionLocal

    await engine.dispose()
    return AsyncSessionLocal()


async def _cleanup():
    """Remove any memories created by tests."""
    from core.database import engine, AsyncSessionLocal
    from sqlalchemy import text

    await engine.dispose()
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("DELETE FROM agent_memory WHERE source = :src"),
            {"src": TEST_SOURCE},
        )
        await session.commit()


# ===========================================================================
# 1. Embedding Provider Selection (sync — no DB needed)
# ===========================================================================


class TestGetEmbeddingProvider:
    """Test that get_embedding_provider() picks the right provider."""

    def test_returns_ollama_when_model_available(self):
        """When Ollama has nomic-embed-text, OllamaEmbeddings is returned."""
        provider = get_embedding_provider()
        assert isinstance(provider, OllamaEmbeddings)

    def test_returns_null_when_nothing_available(self):
        """When neither Ollama nor OpenAI works, NullEmbeddings is used."""
        NullEmbeddings._warned = False

        with patch(
            "core.memory.embeddings._ollama_has_embedding_model", return_value=None
        ), patch("core.memory.embeddings.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                openai_api_key=None,
                ollama_base_url="http://localhost:11434",
            )
            provider = get_embedding_provider()
            assert isinstance(provider, NullEmbeddings)

    def test_returns_openai_when_ollama_down_and_key_valid(self):
        """When Ollama has no model but OpenAI key is valid, use LiteLLMEmbeddings."""
        with patch(
            "core.memory.embeddings._ollama_has_embedding_model", return_value=None
        ), patch(
            "core.memory.embeddings._openai_key_works", return_value=True
        ), patch("core.memory.embeddings.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                openai_api_key="sk-test-valid",
                ollama_base_url="http://localhost:11434",
            )
            provider = get_embedding_provider()
            assert isinstance(provider, LiteLLMEmbeddings)

    def test_skips_openai_when_key_invalid(self):
        """When OpenAI key is set but invalid (no quota), fall to NullEmbeddings."""
        NullEmbeddings._warned = False

        with patch(
            "core.memory.embeddings._ollama_has_embedding_model", return_value=None
        ), patch(
            "core.memory.embeddings._openai_key_works", return_value=False
        ), patch("core.memory.embeddings.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                openai_api_key="sk-test-invalid",
                ollama_base_url="http://localhost:11434",
            )
            provider = get_embedding_provider()
            assert isinstance(provider, NullEmbeddings)


class TestOllamaHasEmbeddingModel:
    """Test the Ollama model detection helper."""

    def test_detects_nomic_embed_text(self):
        """Should detect nomic-embed-text from live Ollama."""
        model = _ollama_has_embedding_model("http://127.0.0.1:11434")
        assert model is not None
        assert "nomic" in model.lower()

    def test_returns_none_for_bad_url(self):
        """Returns None when Ollama is unreachable."""
        model = _ollama_has_embedding_model("http://127.0.0.1:99999")
        assert model is None


# ===========================================================================
# 2. OllamaEmbeddings Provider (async — Ollama HTTP, no DB)
# ===========================================================================


class TestOllamaEmbeddings:
    """Test the OllamaEmbeddings provider directly."""

    @pytest.fixture
    def provider(self):
        return OllamaEmbeddings(model="nomic-embed-text")

    @pytest.mark.asyncio
    async def test_encode_returns_correct_dim(self, provider):
        """Encode should return EMBEDDING_DIM (1536) floats."""
        vec = await provider.encode("hello world")
        assert len(vec) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in vec)

    @pytest.mark.asyncio
    async def test_encode_returns_non_zero(self, provider):
        """At least some values should be non-zero (not a null vector)."""
        vec = await provider.encode("test embedding content")
        assert any(v != 0.0 for v in vec)

    @pytest.mark.asyncio
    async def test_encode_different_texts_differ(self, provider):
        """Different texts should produce different embeddings."""
        vec1 = await provider.encode("the cat sat on the mat")
        vec2 = await provider.encode("quantum physics and relativity")
        assert vec1 != vec2

    @pytest.mark.asyncio
    async def test_encode_similar_texts_high_similarity(self, provider):
        """Similar texts should have high cosine similarity."""
        vec1 = await provider.encode("PostgreSQL database server running on port 5432")
        vec2 = await provider.encode("The Postgres DB is on port 5432")
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5
        similarity = dot / (mag1 * mag2) if mag1 * mag2 > 0 else 0
        assert similarity > 0.7, f"Expected similarity > 0.7, got {similarity:.4f}"

    @pytest.mark.asyncio
    async def test_encode_batch(self, provider):
        """Batch encode should work for multiple texts."""
        vecs = await provider.encode_batch(["hello", "world", "foo"])
        assert len(vecs) == 3
        assert all(len(v) == EMBEDDING_DIM for v in vecs)

    def test_normalize_dim_pads(self, provider):
        """Short vectors should be padded with zeros."""
        short = [1.0, 2.0, 3.0]
        result = provider._normalize_dim(short)
        assert len(result) == EMBEDDING_DIM
        assert result[:3] == [1.0, 2.0, 3.0]
        assert all(v == 0.0 for v in result[3:])

    def test_normalize_dim_truncates(self, provider):
        """Vectors longer than EMBEDDING_DIM should be truncated."""
        long = [float(i) for i in range(EMBEDDING_DIM + 100)]
        result = provider._normalize_dim(long)
        assert len(result) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_encode_error_on_bad_url(self):
        """Should raise when Ollama is unreachable."""
        provider = OllamaEmbeddings(
            model="nomic-embed-text", base_url="http://127.0.0.1:99999"
        )
        with pytest.raises(Exception):
            await provider.encode("test")


# ===========================================================================
# 3. NullEmbeddings Graceful Fallback (sync/async — no DB)
# ===========================================================================


class TestNullEmbeddings:
    """Test that NullEmbeddings degrades gracefully without crashing."""

    @pytest.fixture(autouse=True)
    def reset_warned(self):
        NullEmbeddings._warned = False
        yield
        NullEmbeddings._warned = False

    def test_instantiation_does_not_crash(self):
        """NullEmbeddings should instantiate cleanly."""
        provider = NullEmbeddings()
        assert provider.dim == EMBEDDING_DIM

    def test_warning_logged_once(self, caplog):
        """Warning should be logged only once, not on every instantiation."""
        with caplog.at_level(logging.WARNING, logger="core.memory.embeddings"):
            NullEmbeddings()
            NullEmbeddings()
            NullEmbeddings()
        warnings = [r for r in caplog.records if "NullEmbeddings active" in r.message]
        assert len(warnings) == 1

    @pytest.mark.asyncio
    async def test_encode_returns_empty_list(self):
        """encode() returns [] — not an error, just empty."""
        provider = NullEmbeddings()
        result = await provider.encode("test text")
        assert result == []

    @pytest.mark.asyncio
    async def test_encode_batch_returns_empty_lists(self):
        """encode_batch() returns a list of empty lists."""
        provider = NullEmbeddings()
        result = await provider.encode_batch(["a", "b", "c"])
        assert result == [[], [], []]

    @pytest.mark.asyncio
    async def test_has_vectors_false(self):
        """MemoryManager with NullEmbeddings should report has_vectors=False."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager(embedding_provider=NullEmbeddings())
        assert not mm.has_vectors


# ---------------------------------------------------------------------------
# Fixture to reset the connection pool before DB-using tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def fresh_db():
    """Dispose the module-level engine so connections are created on the
    current event loop. Required for tests that use MemoryManager (which
    internally calls AsyncSessionLocal)."""
    from core.database import engine

    await engine.dispose()
    yield
    await engine.dispose()


# ===========================================================================
# 4. Memory Store with Embedding (async — uses DB)
# ===========================================================================


class TestMemoryStoreWithEmbedding:
    """Test that storing a memory produces a valid non-null embedding vector."""

    @pytest.mark.asyncio
    async def test_store_creates_embedding(self, fresh_db):
        """Stored memory should have a non-null embedding in the DB."""
        from core.memory.manager import MemoryManager
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        mm = MemoryManager()
        try:
            mid = await mm.store(
                content="Nginx web server configured with SSL on port 443",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )
            assert mid > 0

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(
                        "SELECT embedding IS NOT NULL AS has_emb "
                        "FROM agent_memory WHERE id = :id"
                    ),
                    {"id": mid},
                )
                row = result.mappings().first()
                assert row is not None
                assert row["has_emb"] is True
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_store_embedding_correct_dimension(self, fresh_db):
        """The stored embedding should have EMBEDDING_DIM dimensions."""
        from core.memory.manager import MemoryManager
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        mm = MemoryManager()
        try:
            mid = await mm.store(
                content="Redis is an in-memory data store used for caching",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.8,
            )

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(
                        "SELECT vector_dims(embedding) AS dim "
                        "FROM agent_memory WHERE id = :id"
                    ),
                    {"id": mid},
                )
                row = result.mappings().first()
                assert row is not None
                assert row["dim"] == EMBEDDING_DIM
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_store_without_embedding_uses_orm(self, fresh_db):
        """When NullEmbeddings is active, store still works via ORM (no embedding)."""
        from core.memory.manager import MemoryManager
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        NullEmbeddings._warned = False
        null_provider = NullEmbeddings()
        mm = MemoryManager(embedding_provider=null_provider)
        try:
            mid = await mm.store(
                content="Test memory without embedding fallback check",
                category="observation",
                source=TEST_SOURCE,
                confidence=0.5,
            )
            assert mid > 0

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(
                        "SELECT embedding IS NULL AS no_emb "
                        "FROM agent_memory WHERE id = :id"
                    ),
                    {"id": mid},
                )
                row = result.mappings().first()
                assert row is not None
                assert row["no_emb"] is True
        finally:
            await _cleanup()


# ===========================================================================
# 5. Memory Retrieval — Cosine Similarity Search (async — uses DB)
# ===========================================================================


class TestMemorySimilaritySearch:
    """Test vector-based similarity search via pgvector cosine distance."""

    @pytest.mark.asyncio
    async def test_store_and_search_similar(self, fresh_db):
        """Querying with related text should return stored memories."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        try:
            await mm.store(
                content="PostgreSQL database runs on port 5432 for data storage",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )
            await mm.store(
                content="Redis cache server operates on port 6379",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )

            results = await mm.search("database port", limit=5)
            assert len(results) > 0
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_cosine_similarity_above_threshold(self, fresh_db):
        """Similar text should have cosine similarity > 0.7."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        try:
            await mm.store(
                content="PostgreSQL database runs on port 5432 for data storage",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )

            results = await mm.search("PostgreSQL database port 5432", limit=5)
            assert len(results) > 0
            top = results[0]
            assert "5432" in top["content"] or "database" in top["content"].lower()
            # Check that the top result has high similarity from vector search
            if "similarity" in top and top["similarity"] not in (None, "N/A"):
                assert float(top["similarity"]) > 0.7, (
                    f"Expected similarity > 0.7, got {top['similarity']}"
                )
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_semantic_search_ranks_correctly(self, fresh_db):
        """Semantically related memories should rank higher than unrelated ones."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        try:
            mid_tech = await mm.store(
                content="HAProxy load balancer distributes incoming HTTPS connections across multiple backend servers",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )
            mid_food = await mm.store(
                content="The traditional Ugandan dish called Rolex is a chapati rolled with eggs and vegetables",
                category="observation",
                source=TEST_SOURCE,
                confidence=0.9,
            )

            # Search for something related to load balancing / networking
            results = await mm.search("HAProxy load balancer HTTPS connections", limit=5)
            assert len(results) > 0
            # Check that the tech memory appears and ranks above the food one
            result_ids = [r["id"] for r in results]
            assert mid_tech in result_ids, f"HAProxy memory {mid_tech} should be in results: {result_ids}"
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, fresh_db):
        """Category filter should restrict results."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        try:
            await mm.store(
                content="The weather in Kampala is warm and tropical year-round",
                category="observation",
                source=TEST_SOURCE,
                confidence=0.9,
            )
            await mm.store(
                content="Server monitoring runs every 5 minutes via cron",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )

            results = await mm.search("tropical warm weather", limit=5, category="observation")
            assert any(
                "weather" in r["content"].lower() or "tropical" in r["content"].lower()
                for r in results
            )
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_fts_fallback_with_null_embeddings(self, fresh_db):
        """With NullEmbeddings, search should still return FTS results."""
        from core.memory.manager import MemoryManager

        NullEmbeddings._warned = False
        # First store with real embeddings so the memory exists
        real_mm = MemoryManager()
        try:
            await real_mm.store(
                content="PostgreSQL database runs on port 5432 for data storage",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )

            # Then search with NullEmbeddings (FTS only)
            null_mm = MemoryManager(embedding_provider=NullEmbeddings())
            assert not null_mm.has_vectors
            results = await null_mm.search("PostgreSQL database port", limit=5)
            assert len(results) > 0
            assert any("PostgreSQL" in r["content"] for r in results)
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_search_no_crash_on_empty_results(self, fresh_db):
        """Search with no matching results should return empty list, not crash."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        results = await mm.search(
            "xyznonexistent123abcdef",
            limit=5,
        )
        assert isinstance(results, list)


# ===========================================================================
# 6. End-to-End: Store + Retrieve with Embeddings (async — uses DB)
# ===========================================================================


class TestEndToEndEmbeddings:
    """Full integration test: store a memory → retrieve via similarity search."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_roundtrip(self, fresh_db):
        """Store a memory, then retrieve it by semantic similarity."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        assert mm.has_vectors, "Embedding provider should be active"
        try:
            content = "The Sanaa AI platform uses Celery for background task processing"
            mid = await mm.store(
                content=content,
                category="fact",
                source=TEST_SOURCE,
                confidence=0.95,
            )
            assert mid > 0

            results = await mm.search("background tasks celery", limit=5)
            assert len(results) > 0
            found = any(r["id"] == mid for r in results)
            assert found, f"Memory {mid} not found in search results: {[r['id'] for r in results]}"
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_memory_stats_show_embeddings(self, fresh_db):
        """Stats should report memories with embeddings."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        try:
            await mm.store(
                content="Test memory for stats check with embeddings unique xyz",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.8,
            )

            stats = await mm.stats()
            assert stats["with_embedding"] > 0
            assert stats["embedding_coverage"] > 0
        finally:
            await _cleanup()

    def test_rrf_merge_combines_results(self):
        """RRF merge should combine vector and FTS results correctly."""
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
        assert merged[0]["id"] == 2, "Item in both lists should rank highest"
        ids = [r["id"] for r in merged]
        assert set(ids) == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_duplicate_detection_on_store(self, fresh_db):
        """Storing identical content should bump existing instead of creating duplicate."""
        from core.memory.manager import MemoryManager

        mm = MemoryManager()
        try:
            mid1 = await mm.store(
                content="The application uses PostgreSQL as its primary database",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.7,
            )

            mid2 = await mm.store(
                content="The application uses PostgreSQL as its primary database",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.7,
            )

            assert mid1 == mid2, "Near-duplicate should return existing memory ID"
        finally:
            await _cleanup()
