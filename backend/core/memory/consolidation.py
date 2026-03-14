"""
Memory Consolidation — daily maintenance for the memory system.

Performs three key operations:
1. Merge similar memories (>0.9 cosine similarity) into single entries with combined confidence
2. Apply confidence decay (×0.95) for memories not accessed in 30+ days
3. Delete memories with confidence < 0.1 that are older than 90 days

Also provides a deduplication check for use before storing new memories:
- check_duplicate_before_store() detects >0.95 cosine similarity to existing memories

Registered as a Celery periodic task running daily at 3:00 AM EAT.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import get_settings

logger = logging.getLogger(__name__)

# Thresholds
MERGE_SIMILARITY_THRESHOLD = 0.9
DEDUP_SIMILARITY_THRESHOLD = 0.95
DECAY_DAYS = 30
DECAY_FACTOR = 0.95
PRUNE_CONFIDENCE_THRESHOLD = 0.1
PRUNE_AGE_DAYS = 90


async def _get_session():
    """Create a fresh async session to avoid event-loop conflicts."""
    settings = get_settings()
    eng = create_async_engine(settings.database_url_async, echo=False)
    Sess = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    session = Sess()
    return session, eng


async def check_duplicate_before_store(
    content: str,
    embedding: list[float],
    similarity_threshold: float = DEDUP_SIMILARITY_THRESHOLD,
) -> Optional[dict]:
    """
    Check if a memory with similar content already exists (>0.95 cosine similarity).

    This should be called before inserting a new memory. If a duplicate is found,
    the caller should update the existing memory's confidence instead of creating a new one.

    Args:
        content: The text content of the memory to store.
        embedding: The embedding vector for the new memory.
        similarity_threshold: Minimum cosine similarity to consider a duplicate. Default 0.95.

    Returns:
        Dict with 'existing_id', 'similarity', and 'action' if duplicate found, else None.
    """
    if not embedding:
        return None

    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    session, eng = await _get_session()
    try:
        sql = sa_text("""
            SELECT id, content, confidence,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM agent_memory
            WHERE embedding IS NOT NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT 1
        """)
        result = await session.execute(sql, {"embedding": embedding_str})
        row = result.mappings().first()
    finally:
        await session.close()
        await eng.dispose()

    if row and float(row["similarity"]) >= similarity_threshold:
        return {
            "existing_id": row["id"],
            "similarity": float(row["similarity"]),
            "action": "update",
            "existing_confidence": float(row["confidence"]) if row["confidence"] else 0.5,
        }

    return None


class MemoryConsolidator:
    """
    Daily memory consolidation engine.

    Operations (run in order during consolidation):
    1. Merge similar memories (>0.9 cosine similarity) → combined confidence, keep best content
    2. Apply confidence decay (×0.95) for memories unaccessed 30+ days
    3. Prune: delete memories with confidence < 0.1 and age > 90 days

    Usage:
        consolidator = MemoryConsolidator()
        stats = await consolidator.run_consolidation()
        # stats = {"merged_count": 3, "decayed_count": 15, "pruned_count": 2}
    """

    async def run_consolidation(self) -> dict:
        """
        Run the full consolidation pipeline.

        Returns:
            Dict with keys: merged_count, decayed_count, pruned_count.
        """
        logger.info("Starting memory consolidation cycle...")

        merge_result = await self.merge_similar_memories()
        decay_result = await self.apply_confidence_decay()
        prune_result = await self.prune_old_memories()

        stats = {
            "merged_count": merge_result["merged_count"],
            "decayed_count": decay_result["decayed_count"],
            "pruned_count": prune_result["pruned_count"],
        }

        logger.info(
            f"Consolidation complete: merged={stats['merged_count']}, "
            f"decayed={stats['decayed_count']}, pruned={stats['pruned_count']}"
        )

        return stats

    # ------------------------------------------------------------------
    # 1. MERGE SIMILAR MEMORIES
    # ------------------------------------------------------------------

    async def merge_similar_memories(
        self,
        similarity_threshold: float = MERGE_SIMILARITY_THRESHOLD,
        batch_size: int = 100,
    ) -> dict:
        """
        Find and merge memories with cosine similarity > threshold.

        Strategy:
        - Fetch all memories with embeddings in batches
        - For each memory, find others with >0.9 similarity using pgvector
        - Merge: keep the one with higher confidence (or verified), delete others
        - Combined confidence = min(survivor.confidence + sum(deleted.confidence), 1.0)

        Returns:
            Dict with 'merged_count' (number of memories removed via merging).
        """
        merged_count = 0
        processed_ids = set()

        session, eng = await _get_session()
        try:
            # Get all memory IDs with embeddings, sorted by confidence descending
            # so we start with the most confident memories
            sql = sa_text("""
                SELECT id, content, confidence, verified, embedding
                FROM agent_memory
                WHERE embedding IS NOT NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC, created_at ASC
            """)
            result = await session.execute(sql)
            all_memories = result.mappings().all()

            for mem in all_memories:
                mem_id = mem["id"]
                if mem_id in processed_ids:
                    continue

                # Find similar memories using pgvector
                # We cast the embedding column to text to get it back for comparison
                find_sql = sa_text("""
                    SELECT id, content, confidence, verified,
                           1 - (embedding <=> (
                               SELECT embedding FROM agent_memory WHERE id = :target_id
                           )) AS similarity
                    FROM agent_memory
                    WHERE id != :target_id
                      AND embedding IS NOT NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                      AND 1 - (embedding <=> (
                          SELECT embedding FROM agent_memory WHERE id = :target_id
                      )) > :threshold
                    ORDER BY similarity DESC
                    LIMIT 20
                """)
                sim_result = await session.execute(find_sql, {
                    "target_id": mem_id,
                    "threshold": similarity_threshold,
                })
                similar = sim_result.mappings().all()

                if not similar:
                    processed_ids.add(mem_id)
                    continue

                # Determine the survivor: prefer verified, then highest confidence
                candidates = [dict(mem)] + [dict(s) for s in similar]
                # Filter out already-processed IDs
                candidates = [c for c in candidates if c["id"] not in processed_ids or c["id"] == mem_id]

                if len(candidates) <= 1:
                    processed_ids.add(mem_id)
                    continue

                # Sort: verified first, then by confidence desc
                candidates.sort(key=lambda c: (c.get("verified", False), c.get("confidence", 0)), reverse=True)
                survivor = candidates[0]
                to_delete = [c for c in candidates[1:] if c["id"] not in processed_ids]

                if not to_delete:
                    processed_ids.add(mem_id)
                    continue

                # Combine confidence: survivor gets sum of all confidences, capped at 1.0
                combined_confidence = survivor["confidence"] or 0.5
                for d in to_delete:
                    combined_confidence += (d.get("confidence") or 0.0) * 0.5  # add half of deleted memories' confidence
                combined_confidence = min(combined_confidence, 1.0)

                # Update survivor
                update_sql = sa_text("""
                    UPDATE agent_memory
                    SET confidence = :confidence,
                        updated_at = NOW()
                    WHERE id = :id
                """)
                await session.execute(update_sql, {
                    "id": survivor["id"],
                    "confidence": combined_confidence,
                })

                # Delete the duplicates
                delete_ids = [d["id"] for d in to_delete]
                delete_sql = sa_text("""
                    DELETE FROM agent_memory WHERE id = ANY(:ids)
                """)
                await session.execute(delete_sql, {"ids": delete_ids})
                merged_count += len(delete_ids)

                # Mark all as processed
                processed_ids.add(survivor["id"])
                for did in delete_ids:
                    processed_ids.add(did)

            await session.commit()
        except Exception as e:
            logger.error(f"Error during memory merge: {e}", exc_info=True)
            await session.rollback()
        finally:
            await session.close()
            await eng.dispose()

        if merged_count > 0:
            logger.info(f"Merged {merged_count} similar memories.")

        return {"merged_count": merged_count}

    # ------------------------------------------------------------------
    # 2. CONFIDENCE DECAY
    # ------------------------------------------------------------------

    async def apply_confidence_decay(
        self,
        decay_days: int = DECAY_DAYS,
        decay_factor: float = DECAY_FACTOR,
    ) -> dict:
        """
        Apply confidence decay to memories not accessed in `decay_days`+ days.

        Multiplies confidence by decay_factor (default 0.95) for unaccessed, unverified memories.

        Returns:
            Dict with 'decayed_count'.
        """
        session, eng = await _get_session()
        try:
            sql = sa_text("""
                UPDATE agent_memory
                SET confidence = confidence * :decay_factor,
                    updated_at = NOW()
                WHERE last_accessed_at < NOW() - MAKE_INTERVAL(days => :days)
                  AND confidence > :min_confidence
                  AND verified = FALSE
            """)
            result = await session.execute(sql, {
                "decay_factor": decay_factor,
                "days": decay_days,
                "min_confidence": PRUNE_CONFIDENCE_THRESHOLD,
            })
            decayed_count = result.rowcount
            await session.commit()
        except Exception as e:
            logger.error(f"Error during confidence decay: {e}", exc_info=True)
            await session.rollback()
            decayed_count = 0
        finally:
            await session.close()
            await eng.dispose()

        if decayed_count > 0:
            logger.info(f"Applied confidence decay to {decayed_count} memories.")

        return {"decayed_count": decayed_count}

    # ------------------------------------------------------------------
    # 3. PRUNE OLD LOW-CONFIDENCE MEMORIES
    # ------------------------------------------------------------------

    async def prune_old_memories(
        self,
        min_confidence: float = PRUNE_CONFIDENCE_THRESHOLD,
        min_age_days: int = PRUNE_AGE_DAYS,
    ) -> dict:
        """
        Delete memories with confidence < min_confidence that are older than min_age_days.

        Never deletes verified memories.

        Returns:
            Dict with 'pruned_count'.
        """
        session, eng = await _get_session()
        try:
            sql = sa_text("""
                DELETE FROM agent_memory
                WHERE confidence < :min_confidence
                  AND created_at < NOW() - MAKE_INTERVAL(days => :days)
                  AND verified = FALSE
            """)
            result = await session.execute(sql, {
                "min_confidence": min_confidence,
                "days": min_age_days,
            })
            pruned_count = result.rowcount
            await session.commit()
        except Exception as e:
            logger.error(f"Error during memory pruning: {e}", exc_info=True)
            await session.rollback()
            pruned_count = 0
        finally:
            await session.close()
            await eng.dispose()

        if pruned_count > 0:
            logger.info(f"Pruned {pruned_count} old low-confidence memories.")

        return {"pruned_count": pruned_count}
