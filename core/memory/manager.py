"""
Memory Manager — hybrid vector + full-text search with Reciprocal Rank Fusion.
Inspired by OpenClaw's SQLite-vec pattern, built on PostgreSQL pgvector.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from database import AsyncSessionLocal, AgentMemory
from memory.embeddings import EmbeddingProvider, NullEmbeddings, get_embedding_provider

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Hybrid memory search combining:
    1. pgvector cosine similarity (semantic meaning)
    2. PostgreSQL tsvector full-text search (exact keywords)
    3. Reciprocal Rank Fusion to merge both result sets
    """

    def __init__(self, embedding_provider: Optional[EmbeddingProvider] = None):
        self._embeddings = embedding_provider

    @property
    def embeddings(self) -> EmbeddingProvider:
        if self._embeddings is None:
            self._embeddings = get_embedding_provider()
        return self._embeddings

    @property
    def has_vectors(self) -> bool:
        return not isinstance(self.embeddings, NullEmbeddings)

    # ==================== SEARCH ====================

    async def search(
        self,
        query: str,
        limit: int = 10,
        category: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> list[dict]:
        """
        Hybrid search: vector + FTS merged via Reciprocal Rank Fusion.
        Falls back to FTS-only if no embedding provider is available.
        """
        fts_results = await self._fts_search(query, limit=limit * 2, category=category)

        if self.has_vectors:
            try:
                query_embedding = await self.embeddings.encode(query)
                vector_results = await self._vector_search(
                    query_embedding, limit=limit * 2, category=category
                )
                merged = self._rrf_merge(vector_results, fts_results, k=60)
            except Exception as e:
                logger.warning(f"Vector search failed, using FTS only: {e}")
                merged = fts_results
        else:
            merged = fts_results

        # Filter by confidence and apply limit
        results = [r for r in merged if r.get("confidence", 0) >= min_confidence][:limit]

        # Update access tracking for returned results
        if results:
            await self._track_access([r["id"] for r in results])

        return results

    async def _vector_search(
        self,
        embedding: list[float],
        limit: int = 20,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Cosine similarity search via pgvector."""
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        if category:
            query = text("""
                SELECT id, content, category, confidence, source, created_at,
                       1 - (embedding <=> :embedding::vector) AS similarity
                FROM agent_memory
                WHERE embedding IS NOT NULL
                  AND category = :category
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY embedding <=> :embedding::vector
                LIMIT :limit
            """)
            params = {"embedding": embedding_str, "category": category, "limit": limit}
        else:
            query = text("""
                SELECT id, content, category, confidence, source, created_at,
                       1 - (embedding <=> :embedding::vector) AS similarity
                FROM agent_memory
                WHERE embedding IS NOT NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY embedding <=> :embedding::vector
                LIMIT :limit
            """)
            params = {"embedding": embedding_str, "limit": limit}

        async with AsyncSessionLocal() as session:
            result = await session.execute(query, params)
            rows = result.mappings().all()

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "category": row["category"],
                "confidence": row["confidence"] or 0.5,
                "source": row["source"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "similarity": float(row["similarity"]) if row["similarity"] else 0.0,
                "search_method": "vector",
            }
            for row in rows
        ]

    @staticmethod
    def _to_or_tsquery(query_text: str) -> str:
        """Convert 'server IP address' to 'server | IP | address' for OR-based FTS."""
        words = [w.strip() for w in query_text.split() if w.strip() and len(w.strip()) > 1]
        if not words:
            return query_text
        return " | ".join(words)

    async def _fts_search(
        self,
        query_text: str,
        limit: int = 20,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Full-text search via PostgreSQL tsvector. Uses OR matching for better recall."""
        or_query = self._to_or_tsquery(query_text)

        if category:
            query = text("""
                SELECT id, content, category, confidence, source, created_at,
                       ts_rank(to_tsvector('english', content),
                               to_tsquery('english', :query)) AS rank
                FROM agent_memory
                WHERE to_tsvector('english', content) @@ to_tsquery('english', :query)
                  AND category = :category
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY rank DESC
                LIMIT :limit
            """)
            params = {"query": or_query, "category": category, "limit": limit}
        else:
            query = text("""
                SELECT id, content, category, confidence, source, created_at,
                       ts_rank(to_tsvector('english', content),
                               to_tsquery('english', :query)) AS rank
                FROM agent_memory
                WHERE to_tsvector('english', content) @@ to_tsquery('english', :query)
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY rank DESC
                LIMIT :limit
            """)
            params = {"query": or_query, "limit": limit}

        async with AsyncSessionLocal() as session:
            result = await session.execute(query, params)
            rows = result.mappings().all()

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "category": row["category"],
                "confidence": row["confidence"] or 0.5,
                "source": row["source"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "rank": float(row["rank"]) if row["rank"] else 0.0,
                "search_method": "fts",
            }
            for row in rows
        ]

    def _rrf_merge(
        self,
        vector_results: list[dict],
        fts_results: list[dict],
        k: int = 60,
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion: merge two ranked lists.
        RRF score = sum(1 / (k + rank_i)) across retrieval methods.
        """
        scores: dict[int, float] = {}
        data: dict[int, dict] = {}

        for rank, result in enumerate(vector_results):
            rid = result["id"]
            scores[rid] = scores.get(rid, 0) + 1.0 / (k + rank + 1)
            data[rid] = result

        for rank, result in enumerate(fts_results):
            rid = result["id"]
            scores[rid] = scores.get(rid, 0) + 1.0 / (k + rank + 1)
            if rid not in data:
                data[rid] = result

        # Sort by combined RRF score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        return [
            {**data[rid], "relevance_score": round(score, 6)}
            for rid, score in ranked
            if rid in data
        ]

    # ==================== STORE ====================

    async def store(
        self,
        content: str,
        category: str = "fact",
        source: Optional[str] = None,
        confidence: float = 0.5,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """Store a new memory with embedding."""
        # Check for near-duplicates first
        existing = await self.search(content, limit=1)
        if existing and existing[0].get("relevance_score", 0) > 0.03:
            # Very high similarity — bump existing confidence instead
            await self._bump_confidence(existing[0]["id"])
            logger.info(f"Memory near-duplicate detected, bumped ID {existing[0]['id']}")
            return existing[0]["id"]

        # Generate embedding
        embedding = None
        if self.has_vectors:
            try:
                embedding = await self.embeddings.encode(content)
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")

        # Insert
        if embedding:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            query = text("""
                INSERT INTO agent_memory
                    (content, category, source, confidence, expires_at, metadata,
                     embedding, created_at, updated_at, access_count)
                VALUES
                    (:content, :category, :source, :confidence, :expires_at,
                     :metadata, :embedding::vector, NOW(), NOW(), 0)
                RETURNING id
            """)
            async with AsyncSessionLocal() as session:
                result = await session.execute(query, {
                    "content": content,
                    "category": category,
                    "source": source,
                    "confidence": confidence,
                    "expires_at": expires_at,
                    "metadata": json.dumps(metadata) if metadata else None,
                    "embedding": embedding_str,
                })
                memory_id = result.scalar_one()
                await session.commit()
        else:
            memory = await AgentMemory.create(
                content=content,
                category=category,
                source=source,
                confidence=confidence,
                expires_at=expires_at,
                metadata_=metadata,
            )
            memory_id = memory.id

        logger.info(f"Stored memory ID {memory_id}: [{category}] {content[:80]}...")
        return memory_id

    async def store_batch(self, memories: list[dict]) -> list[int]:
        """Store multiple memories efficiently."""
        ids = []
        for mem in memories:
            mid = await self.store(
                content=mem["content"],
                category=mem.get("category", "fact"),
                source=mem.get("source"),
                confidence=mem.get("confidence", 0.5),
            )
            ids.append(mid)
        return ids

    # ==================== UPDATE / DELETE ====================

    async def update_confidence(self, memory_id: int, confidence: float):
        """Set confidence score for a memory."""
        await AgentMemory.update_by_id(memory_id, confidence=confidence)

    async def verify(self, memory_id: int):
        """Mark a memory as admin-verified (won't be pruned)."""
        await AgentMemory.update_by_id(memory_id, verified=True, confidence=1.0)

    async def delete(self, memory_id: int):
        """Delete a memory permanently."""
        async with AsyncSessionLocal() as session:
            memory = await session.get(AgentMemory, memory_id)
            if memory:
                await session.delete(memory)
                await session.commit()

    async def _bump_confidence(self, memory_id: int):
        """Increase confidence when a memory is re-confirmed."""
        query = text("""
            UPDATE agent_memory
            SET confidence = LEAST(confidence + 0.1, 1.0),
                access_count = access_count + 1,
                last_accessed_at = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """)
        async with AsyncSessionLocal() as session:
            await session.execute(query, {"id": memory_id})
            await session.commit()

    async def _track_access(self, memory_ids: list[int]):
        """Update access tracking for retrieved memories."""
        query = text("""
            UPDATE agent_memory
            SET access_count = access_count + 1,
                last_accessed_at = NOW()
            WHERE id = ANY(:ids)
        """)
        async with AsyncSessionLocal() as session:
            await session.execute(query, {"ids": memory_ids})
            await session.commit()

    # ==================== MAINTENANCE ====================

    async def prune(self) -> dict:
        """Remove expired, low-confidence, and stale memories. Returns stats."""
        stats = {"expired": 0, "decayed": 0, "deleted": 0}

        async with AsyncSessionLocal() as session:
            # Delete expired
            result = await session.execute(
                text("DELETE FROM agent_memory WHERE expires_at IS NOT NULL AND expires_at < NOW()")
            )
            stats["expired"] = result.rowcount

            # Decay confidence of unaccessed memories
            result = await session.execute(text("""
                UPDATE agent_memory
                SET confidence = confidence * 0.95
                WHERE last_accessed_at < NOW() - INTERVAL '30 days'
                  AND confidence > 0.1
                  AND verified = FALSE
            """))
            stats["decayed"] = result.rowcount

            # Delete very low confidence, old, unverified memories
            result = await session.execute(text("""
                DELETE FROM agent_memory
                WHERE confidence < 0.1
                  AND created_at < NOW() - INTERVAL '90 days'
                  AND verified = FALSE
            """))
            stats["deleted"] = result.rowcount

            await session.commit()

        logger.info(f"Memory prune: {stats}")
        return stats

    async def stats(self) -> dict:
        """Get memory system statistics."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN category = 'fact' THEN 1 END) AS facts,
                    COUNT(CASE WHEN category = 'procedure' THEN 1 END) AS procedures,
                    COUNT(CASE WHEN category = 'preference' THEN 1 END) AS preferences,
                    COUNT(CASE WHEN category = 'observation' THEN 1 END) AS observations,
                    COUNT(CASE WHEN verified = TRUE THEN 1 END) AS verified,
                    COUNT(CASE WHEN embedding IS NOT NULL THEN 1 END) AS with_embedding,
                    COUNT(CASE WHEN expires_at IS NOT NULL AND expires_at < NOW() + INTERVAL '7 days' THEN 1 END) AS expiring_soon,
                    AVG(confidence) AS avg_confidence
                FROM agent_memory
                WHERE expires_at IS NULL OR expires_at > NOW()
            """))
            row = result.mappings().first()

        return {
            "total_memories": row["total"],
            "by_category": {
                "fact": row["facts"],
                "procedure": row["procedures"],
                "preference": row["preferences"],
                "observation": row["observations"],
            },
            "verified": row["verified"],
            "with_embedding": row["with_embedding"],
            "expiring_soon": row["expiring_soon"],
            "avg_confidence": round(float(row["avg_confidence"] or 0), 3),
            "embedding_coverage": (
                round(row["with_embedding"] / max(row["total"], 1) * 100, 1)
            ),
        }
