"""
Sanaa AI — SanaaBrain Memory API
Persistent project-scoped memory REST layer on top of agent_memory + pgvector.

Endpoints:
  POST   /api/memory/add
  GET    /api/memory/search
  GET    /api/memory/all
  GET    /api/memory/briefing/{project}
  POST   /api/memory/session/save
  PUT    /api/memory/{memory_id}
  DELETE /api/memory/clear/{project}
  DELETE /api/memory/{memory_id}
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text, select, desc

from core.database import AgentMemory, AsyncSessionLocal
from core.routes.deps import require_auth
from core.memory.embeddings import get_embedding_provider, NullEmbeddings

logger = logging.getLogger(__name__)
router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _embedding_str(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def _row_to_dict(row) -> dict:
    """Serialize an AgentMemory ORM row to a JSON-safe dict."""
    meta = row.metadata_
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    return {
        "id": row.id,
        "content": row.content,
        "category": row.category,
        "source": row.source,
        "confidence": row.confidence or 0.5,
        "verified": row.verified or False,
        "access_count": row.access_count or 0,
        "metadata": meta or {},
        "project": (meta or {}).get("project", ""),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _mapping_to_dict(row) -> dict:
    """Serialize a raw SQL result row to a dict."""
    meta_raw = row.get("metadata")
    if isinstance(meta_raw, str):
        try:
            meta = json.loads(meta_raw)
        except Exception:
            meta = {}
    elif isinstance(meta_raw, dict):
        meta = meta_raw
    else:
        meta = {}

    return {
        "id": row["id"],
        "content": row["content"],
        "category": row["category"],
        "source": row.get("source"),
        "confidence": float(row.get("confidence") or 0.5),
        "verified": bool(row.get("verified", False)),
        "access_count": int(row.get("access_count") or 0),
        "metadata": meta,
        "project": meta.get("project", ""),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "similarity_score": round(float(row["similarity"]), 4) if row.get("similarity") is not None else None,
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class MemoryAddRequest(BaseModel):
    content: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1, max_length=50)
    project: str = Field(..., min_length=1, max_length=100)
    source: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    metadata: Optional[dict] = None


class SessionSaveRequest(BaseModel):
    content: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default="api")
    project: Optional[str] = None


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    verified: Optional[bool] = None
    metadata: Optional[dict] = None


# ── POST /api/memory/add ─────────────────────────────────────────────────────

@router.post("/api/memory/add", status_code=201)
async def add_memory(payload: MemoryAddRequest, user: dict = Depends(require_auth)):
    """Store a new memory entry with embedding, scoped to a project.

    Dedup: for configs (metadata.is_config=true), checks config_key+project.
    For all others, checks content[:200] + project + category.
    Returns existing memory if duplicate found.
    """
    # Merge project into metadata
    meta = dict(payload.metadata or {})
    meta["project"] = payload.project

    # Generate embedding
    provider = get_embedding_provider()
    embedding = None
    if not isinstance(provider, NullEmbeddings):
        try:
            embedding = await provider.encode(payload.content)
        except Exception as e:
            logger.warning(f"Memory add: embedding failed, storing without vector: {e}")

    async with AsyncSessionLocal() as session:
        # ── Dedup check (single session with insert) ──────────────────────
        is_config = meta.get("is_config") in (True, "true", "True")
        config_key = meta.get("config_key")
        try:
            if is_config and config_key:
                existing = await session.execute(
                    text("""
                        SELECT id, created_at FROM agent_memory
                        WHERE metadata->>'config_key' = :key
                          AND metadata->>'project' = :project
                        LIMIT 1
                    """),
                    {"key": config_key, "project": payload.project},
                )
                row = existing.mappings().first()
                if row:
                    logger.info(f"Dedup: config {config_key} already exists for {payload.project} (mem {row['id']})")
                    return {
                        "id": row["id"],
                        "dedup": True,
                        "message": f"Config '{config_key}' already exists for project '{payload.project}'",
                        "existing_id": row["id"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    }
            else:
                content_preview = payload.content[:200]
                existing = await session.execute(
                    text("""
                        SELECT id, created_at FROM agent_memory
                        WHERE LEFT(content, 200) = :preview
                          AND metadata->>'project' = :project
                          AND category = :category
                        LIMIT 1
                    """),
                    {"preview": content_preview, "project": payload.project, "category": payload.category},
                )
                row = existing.mappings().first()
                if row:
                    logger.info(f"Dedup: content matches existing memory {row['id']} for {payload.project}")
                    return {
                        "id": row["id"],
                        "dedup": True,
                        "message": "Duplicate content — existing memory returned",
                        "existing_id": row["id"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    }
        except Exception as e:
            logger.warning(f"Dedup check failed (proceeding with insert): {e}")

        if embedding:
            emb_str = _embedding_str(embedding)
            result = await session.execute(
                text("""
                    INSERT INTO agent_memory
                        (content, category, source, confidence, metadata,
                         embedding, created_at, updated_at, access_count, verified)
                    VALUES
                        (:content, :category, :source, :confidence, :metadata,
                         CAST(:embedding AS vector), NOW(), NOW(), 0, false)
                    RETURNING id, created_at
                """),
                {
                    "content": payload.content,
                    "category": payload.category,
                    "source": payload.source or "sanaabrain_api",
                    "confidence": payload.confidence,
                    "metadata": json.dumps(meta),
                    "embedding": emb_str,
                },
            )
        else:
            result = await session.execute(
                text("""
                    INSERT INTO agent_memory
                        (content, category, source, confidence, metadata,
                         created_at, updated_at, access_count, verified)
                    VALUES
                        (:content, :category, :source, :confidence, :metadata,
                         NOW(), NOW(), 0, false)
                    RETURNING id, created_at
                """),
                {
                    "content": payload.content,
                    "category": payload.category,
                    "source": payload.source or "sanaabrain_api",
                    "confidence": payload.confidence,
                    "metadata": json.dumps(meta),
                },
            )
        row = result.mappings().first()
        await session.commit()

    logger.info(f"Memory stored: [{payload.category}] project={payload.project} id={row['id']}")

    # ── Auto-propagation to knowledge graph ─────────────────────────────
    propagated_to = []
    is_config = meta.get("is_config") in (True, "true", "True")
    should_share = meta.get("share") in (True, "true", "True") or meta.get("propagate") in (True, "true", "True")

    if is_config or should_share:
        config_key = meta.get("config_key")
        try:
            async with AsyncSessionLocal() as session:
                if config_key:
                    # Link to same config_key in other projects
                    link_result = await session.execute(
                        text("""
                            SELECT id, metadata->>'project' AS project FROM agent_memory
                            WHERE metadata->>'config_key' = :key
                              AND metadata->>'project' != :project
                              AND id != :mem_id
                            LIMIT 20
                        """),
                        {"key": config_key, "project": payload.project, "mem_id": row["id"]},
                    )
                    for link_row in link_result.mappings().all():
                        await session.execute(
                            text("""
                                INSERT INTO memory_edges (source_id, target_id, relation_type, weight, metadata, created_at, updated_at)
                                VALUES (:src, :tgt, 'same_as', 0.95, :meta, NOW(), NOW())
                                ON CONFLICT DO NOTHING
                            """),
                            {
                                "src": row["id"], "tgt": link_row["id"],
                                "meta": json.dumps({
                                    "auto": True, "reason": "shared_config",
                                    "config_key": config_key,
                                }),
                            },
                        )
                        propagated_to.append(link_row["project"])

                if should_share and config_key:
                    # Propagate to ALL known projects that don't have this config yet
                    proj_result = await session.execute(text("""
                        SELECT DISTINCT metadata->>'project' AS project FROM agent_memory
                        WHERE metadata->>'project' IS NOT NULL
                          AND metadata->>'project' != ''
                          AND metadata->>'project' != :src_project
                          AND metadata->>'project' != 'banks'
                        ORDER BY project
                    """), {"src_project": payload.project})
                    all_projects = [r["project"] for r in proj_result.mappings().all()]

                    # Filter out projects that already have this config_key
                    for target_project in all_projects:
                        if target_project in propagated_to:
                            continue
                        has_config = await session.execute(
                            text("""
                                SELECT COUNT(*) FROM agent_memory
                                WHERE metadata->>'config_key' = :key
                                  AND metadata->>'project' = :project
                            """),
                            {"key": config_key, "project": target_project},
                        )
                        if has_config.scalar() == 0:
                            # Create a propagated copy in the target project
                            tgt_meta = dict(meta)
                            tgt_meta["project"] = target_project
                            tgt_meta["propagated_from"] = payload.project
                            tgt_meta["propagated_at"] = _utcnow_iso()

                            await session.execute(
                                text("""
                                    INSERT INTO agent_memory
                                        (content, category, source, confidence, metadata,
                                         created_at, updated_at, access_count, verified)
                                    VALUES
                                        (:content, :category, 'propagation_engine', :confidence, :metadata,
                                         NOW(), NOW(), 0, false)
                                """),
                                {
                                    "content": payload.content,
                                    "category": payload.category or "config",
                                    "confidence": payload.confidence * 0.9,
                                    "metadata": json.dumps(tgt_meta),
                                },
                            )
                            propagated_to.append(target_project)

                await session.commit()
        except Exception as e:
            logger.warning(f"Auto-propagation failed for memory {row['id']}: {e}")

    return {
        "id": row["id"],
        "content": payload.content,
        "category": payload.category,
        "project": payload.project,
        "confidence": payload.confidence,
        "metadata": meta,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "has_embedding": embedding is not None,
        "propagated_to": propagated_to,
        "dedup": False,
    }


# ── GET /api/memory/search ───────────────────────────────────────────────────

@router.get("/api/memory/search")
async def search_memory(
    query: str,
    project: Optional[str] = None,
    limit: int = 10,
    user: dict = Depends(require_auth),
):
    """Semantic + cosine similarity search over agent_memory."""
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    provider = get_embedding_provider()
    results = []

    if not isinstance(provider, NullEmbeddings):
        try:
            embedding = await provider.encode(query)
            emb_str = _embedding_str(embedding)

            if project:
                sql = text("""
                    SELECT id, content, category, source, confidence, verified,
                           access_count, metadata, created_at, updated_at,
                           1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM agent_memory
                    WHERE embedding IS NOT NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                      AND metadata->>'project' = :project
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                """)
                params = {"embedding": emb_str, "project": project, "limit": limit}
            else:
                sql = text("""
                    SELECT id, content, category, source, confidence, verified,
                           access_count, metadata, created_at, updated_at,
                           1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM agent_memory
                    WHERE embedding IS NOT NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                """)
                params = {"embedding": emb_str, "limit": limit}

            async with AsyncSessionLocal() as session:
                result = await session.execute(sql, params)
                rows = result.mappings().all()

            results = [_mapping_to_dict(dict(r)) for r in rows]

            # Increment access_count for returned rows
            if results:
                ids = [r["id"] for r in results]
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        text("UPDATE agent_memory SET access_count = access_count + 1, last_accessed_at = NOW() WHERE id = ANY(:ids)"),
                        {"ids": ids},
                    )
                    await session.commit()

        except Exception as e:
            logger.warning(f"Vector search failed, falling back to FTS: {e}")

    # FTS fallback if no vector results
    if not results:
        words = [w.strip() for w in query.split() if w.strip() and len(w.strip()) > 1]
        or_query = " | ".join(words) if words else query

        if project:
            sql = text("""
                SELECT id, content, category, source, confidence, verified,
                       access_count, metadata, created_at, updated_at,
                       ts_rank(to_tsvector('english', content),
                               to_tsquery('english', :q)) AS similarity
                FROM agent_memory
                WHERE to_tsvector('english', content) @@ to_tsquery('english', :q)
                  AND (expires_at IS NULL OR expires_at > NOW())
                  AND metadata->>'project' = :project
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            params = {"q": or_query, "project": project, "limit": limit}
        else:
            sql = text("""
                SELECT id, content, category, source, confidence, verified,
                       access_count, metadata, created_at, updated_at,
                       ts_rank(to_tsvector('english', content),
                               to_tsquery('english', :q)) AS similarity
                FROM agent_memory
                WHERE to_tsvector('english', content) @@ to_tsquery('english', :q)
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            params = {"q": or_query, "limit": limit}

        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, params)
            rows = result.mappings().all()

        results = [_mapping_to_dict(dict(r)) for r in rows]

    return {
        "query": query,
        "project": project,
        "count": len(results),
        "results": results,
    }


# ── GET /api/memory/all ──────────────────────────────────────────────────────

@router.get("/api/memory/all")
async def get_all_memories(
    project: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_auth),
):
    """List all memories with optional project/category filters and pagination."""
    # Build dynamic WHERE clauses
    conditions = ["(expires_at IS NULL OR expires_at > NOW())"]
    params: dict = {"limit": limit, "offset": offset}

    if project:
        conditions.append("metadata->>'project' = :project")
        params["project"] = project

    if category:
        conditions.append("category = :category")
        params["category"] = category

    where_clause = " AND ".join(conditions)

    count_sql = text(f"SELECT COUNT(*) FROM agent_memory WHERE {where_clause}")
    items_sql = text(f"""
        SELECT id, content, category, source, confidence, verified,
               access_count, metadata, created_at, updated_at
        FROM agent_memory
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    async with AsyncSessionLocal() as session:
        total_result = await session.execute(count_sql, params)
        total = total_result.scalar_one()

        items_result = await session.execute(items_sql, params)
        rows = items_result.mappings().all()

    items = []
    for r in rows:
        d = dict(r)
        meta = d.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        elif not isinstance(meta, dict):
            meta = {}
        items.append({
            "id": d["id"],
            "content": d["content"],
            "category": d["category"],
            "source": d.get("source"),
            "confidence": float(d.get("confidence") or 0.5),
            "verified": bool(d.get("verified", False)),
            "access_count": int(d.get("access_count") or 0),
            "metadata": meta,
            "project": meta.get("project", ""),
            "created_at": d["created_at"].isoformat() if d.get("created_at") else None,
            "updated_at": d["updated_at"].isoformat() if d.get("updated_at") else None,
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "project": project,
        "category": category,
        "memories": items,
    }


# ── GET /api/memory/briefing/{project} ───────────────────────────────────────

@router.get("/api/memory/briefing/{project}")
async def get_memory_briefing(project: str, user: dict = Depends(require_auth)):
    """Return the top 20 memories for a project formatted as a markdown context block."""
    sql = text("""
        SELECT id, content, category, confidence, created_at
        FROM agent_memory
        WHERE metadata->>'project' = :project
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY access_count DESC, confidence DESC
        LIMIT 20
    """)

    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, {"project": project})
        rows = result.mappings().all()

    if not rows:
        return {
            "project": project,
            "memory_count": 0,
            "briefing": f"## SanaaBrain Context — {project}\n\nNo memories stored yet for this project.\n",
        }

    # Find most recent created_at
    timestamps = [r["created_at"] for r in rows if r.get("created_at")]
    last_updated = max(timestamps).isoformat() if timestamps else "unknown"

    lines = [
        f"## SanaaBrain Context — {project}",
        f"Generated: {_utcnow_iso()}",
        "",
        "### What we know:",
    ]
    for r in rows:
        conf_str = f"{float(r['confidence'] or 0.5):.2f}"
        lines.append(f"- {r['content']} [confidence: {conf_str}]")

    lines.extend([
        "",
        "### Last updated:",
        last_updated,
    ])

    briefing_text = "\n".join(lines)

    return {
        "project": project,
        "memory_count": len(rows),
        "briefing": briefing_text,
        "generated_at": _utcnow_iso(),
    }


# ── POST /api/memory/session/save ────────────────────────────────────────────

@router.post("/api/memory/session/save", status_code=201)
async def save_session(payload: SessionSaveRequest, user: dict = Depends(require_auth)):
    """Persist a session log as a single memory entry (category=session_log)."""
    content = payload.content
    meta = {
        "session_id": payload.session_id or "api",
        "type": "session",
        "saved_at": _utcnow_iso(),
    }
    if payload.project:
        meta["project"] = payload.project

    # Generate embedding
    provider = get_embedding_provider()
    embedding = None
    if not isinstance(provider, NullEmbeddings):
        try:
            embedding = await provider.encode(content)
        except Exception as e:
            logger.warning(f"Session save: embedding failed: {e}")

    source = f"session:{payload.session_id or 'api'}"

    async with AsyncSessionLocal() as session:
        if embedding:
            emb_str = _embedding_str(embedding)
            result = await session.execute(
                text("""
                    INSERT INTO agent_memory
                        (content, category, source, confidence, metadata,
                         embedding, created_at, updated_at, access_count, verified)
                    VALUES
                        (:content, 'session_log', :source, 1.0, :metadata,
                         CAST(:embedding AS vector), NOW(), NOW(), 0, false)
                    RETURNING id
                """),
                {
                    "content": content,
                    "source": source,
                    "metadata": json.dumps(meta),
                    "embedding": emb_str,
                },
            )
        else:
            result = await session.execute(
                text("""
                    INSERT INTO agent_memory
                        (content, category, source, confidence, metadata,
                         created_at, updated_at, access_count, verified)
                    VALUES
                        (:content, 'session_log', :source, 1.0, :metadata,
                         NOW(), NOW(), 0, false)
                    RETURNING id
                """),
                {
                    "content": content,
                    "source": source,
                    "metadata": json.dumps(meta),
                },
            )
        row = result.mappings().first()
        await session.commit()

    logger.info(f"Session memory saved: session_id={payload.session_id} id={row['id']}")
    return {"id": row["id"], "saved": True, "project": payload.project}


# ── PUT /api/memory/{memory_id} ──────────────────────────────────────────────

@router.put("/api/memory/{memory_id}")
async def update_memory(
    memory_id: int,
    payload: MemoryUpdateRequest,
    user: dict = Depends(require_auth),
):
    """Partial update: content (regenerates embedding), confidence, verified, metadata."""
    async with AsyncSessionLocal() as session:
        mem = await session.get(AgentMemory, memory_id)
        if not mem:
            raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")

        content_changed = payload.content is not None and payload.content != mem.content

        if payload.content is not None:
            mem.content = payload.content
        if payload.confidence is not None:
            mem.confidence = payload.confidence
        if payload.verified is not None:
            mem.verified = payload.verified
        if payload.metadata is not None:
            existing_meta = mem.metadata_ or {}
            if isinstance(existing_meta, str):
                try:
                    existing_meta = json.loads(existing_meta)
                except Exception:
                    existing_meta = {}
            merged_meta = {**existing_meta, **payload.metadata}
            mem.metadata_ = merged_meta

        await session.commit()
        await session.refresh(mem)

    # Regenerate embedding outside transaction if content changed
    if content_changed:
        provider = get_embedding_provider()
        if not isinstance(provider, NullEmbeddings):
            try:
                embedding = await provider.encode(mem.content)
                emb_str = _embedding_str(embedding)
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        text("UPDATE agent_memory SET embedding = CAST(:emb AS vector), updated_at = NOW() WHERE id = :id"),
                        {"emb": emb_str, "id": memory_id},
                    )
                    await session.commit()
            except Exception as e:
                logger.warning(f"Embedding regen failed for memory {memory_id}: {e}")

    return _row_to_dict(mem)


# ── DELETE /api/memory/clear/{project} ───────────────────────────────────────
# NOTE: must appear BEFORE /api/memory/{memory_id} to avoid integer-parsing conflict

@router.delete("/api/memory/clear/{project}")
async def clear_project_memory(project: str, user: dict = Depends(require_auth)):
    """Delete all memories for a given project."""
    if not project.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM agent_memory WHERE metadata->>'project' = :project"),
            {"project": project},
        )
        deleted_count = result.rowcount
        await session.commit()

    logger.info(f"Cleared {deleted_count} memories for project={project}")
    return {"deleted": deleted_count, "project": project}


# ── DELETE /api/memory/{memory_id} ───────────────────────────────────────────

@router.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: int, user: dict = Depends(require_auth)):
    """Hard delete a single memory by ID."""
    async with AsyncSessionLocal() as session:
        mem = await session.get(AgentMemory, memory_id)
        if not mem:
            raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
        await session.delete(mem)
        await session.commit()

    logger.info(f"Deleted memory id={memory_id}")
    return {"deleted": True, "id": memory_id}
