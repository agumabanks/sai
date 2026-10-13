"""
SanaaEngine Knowledge Graph
============================
Directed weighted edges between agent_memory entries, forming a cross-project
knowledge graph. Supports traversal, conflict detection, config registry,
and auto-propagation.

Endpoints:
  POST   /api/brain/graph/relate          — create an edge
  DELETE /api/brain/graph/relate/{id}     — remove an edge
  GET    /api/brain/graph/{memory_id}     — get neighbors (depth=1)
  GET    /api/brain/graph/traverse        — BFS traversal
  GET    /api/brain/graph/project/{project} — full project subgraph
  GET    /api/brain/graph/configs         — cross-project config registry
  GET    /api/brain/graph/conflicts       — conflicting values across projects
  POST   /api/brain/graph/auto-link       — auto-create edges between similar memories
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text, and_

from core.database import AsyncSessionLocal, MemoryEdge
from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

RELATION_TYPES = {
    "relates_to", "same_as", "depends_on", "conflicts_with",
    "implements", "references", "config_of", "propagates_to",
    "extends", "version_of", "replaces", "triggers",
}


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Schemas ──────────────────────────────────────────────────────────────────

class RelateRequest(BaseModel):
    source_id: int = Field(..., gt=0)
    target_id: int = Field(..., gt=0)
    relation_type: str = Field(..., min_length=1, max_length=50)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: Optional[dict] = None


class AutoLinkRequest(BaseModel):
    project: str = Field(..., min_length=1)
    relation_type: str = Field(default="relates_to", max_length=50)
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)


# ── Edge helpers ─────────────────────────────────────────────────────────────

def _edge_to_dict(edge) -> dict:
    meta = edge.metadata_ or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "relation_type": edge.relation_type,
        "weight": edge.weight or 1.0,
        "metadata": meta,
        "created_at": edge.created_at.isoformat() if edge.created_at else None,
    }


async def _resolve_memory(session, memory_id: int) -> Optional[dict]:
    """Fetch a single memory's summary for graph display."""
    result = await session.execute(
        text("""
            SELECT id, content, category, metadata, created_at
            FROM agent_memory WHERE id = :id
        """),
        {"id": memory_id},
    )
    row = result.mappings().first()
    if not row:
        return None
    meta = row["metadata"]
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    return {
        "id": row["id"],
        "content": (row["content"] or "")[:200],
        "category": row["category"],
        "project": meta.get("project", ""),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


# ── POST /api/brain/graph/relate ──────────────────────────────────────────────

@router.post("/api/brain/graph/relate", status_code=201)
async def create_relation(payload: RelateRequest, user: dict = Depends(require_auth)):
    """Create a weighted directed edge between two memories."""
    if payload.relation_type not in RELATION_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid relation type. Valid: {sorted(RELATION_TYPES)}")

    if payload.source_id == payload.target_id:
        raise HTTPException(status_code=400, detail="Cannot relate a memory to itself")

    meta = dict(payload.metadata or {})
    meta["created_by"] = user.get("email", "api")

    async with AsyncSessionLocal() as session:
        # Verify both memories exist
        source = await session.execute(
            text("SELECT id FROM agent_memory WHERE id = :id"), {"id": payload.source_id}
        )
        target = await session.execute(
            text("SELECT id FROM agent_memory WHERE id = :id"), {"id": payload.target_id}
        )
        if not source.mappings().first():
            raise HTTPException(status_code=404, detail=f"Source memory {payload.source_id} not found")
        if not target.mappings().first():
            raise HTTPException(status_code=404, detail=f"Target memory {payload.target_id} not found")

        # Upsert edge (update weight if exists)
        existing = await session.execute(
            text("""
                SELECT id FROM memory_edges
                WHERE source_id = :src AND target_id = :tgt AND relation_type = :rel
            """),
            {"src": payload.source_id, "tgt": payload.target_id, "rel": payload.relation_type},
        )
        existing_row = existing.mappings().first()

        if existing_row:
            await session.execute(
                text("""
                    UPDATE memory_edges
                    SET weight = :weight, metadata = :meta, updated_at = NOW()
                    WHERE id = :id
                """),
                {"weight": payload.weight, "meta": json.dumps(meta), "id": existing_row["id"]},
            )
            edge_id = existing_row["id"]
            created = False
        else:
            result = await session.execute(
                text("""
                    INSERT INTO memory_edges (source_id, target_id, relation_type, weight, metadata, created_at, updated_at)
                    VALUES (:src, :tgt, :rel, :weight, :meta, NOW(), NOW())
                    RETURNING id
                """),
                {
                    "src": payload.source_id, "tgt": payload.target_id,
                    "rel": payload.relation_type, "weight": payload.weight,
                    "meta": json.dumps(meta),
                },
            )
            edge_id = result.scalar()
            created = True

        await session.commit()

    return {
        "id": edge_id,
        "relation_type": payload.relation_type,
        "source_id": payload.source_id,
        "target_id": payload.target_id,
        "weight": payload.weight,
        "created": created,
    }


# ── DELETE /api/brain/graph/relate/{edge_id} ──────────────────────────────────

@router.delete("/api/brain/graph/relate/{edge_id}")
async def delete_relation(edge_id: int, user: dict = Depends(require_auth)):
    """Remove a relation edge."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM memory_edges WHERE id = :id RETURNING id"),
            {"id": edge_id},
        )
        deleted = result.scalar()
        await session.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found")
    return {"deleted": True, "id": edge_id}


# ── GET /api/brain/graph/traverse ─────────────────────────────────────────────

@router.get("/api/brain/graph/traverse")
async def traverse_graph(
    relation: Optional[str] = Query(default=None, description="Filter by relation type"),
    project: Optional[str] = Query(default=None, description="Filter by project"),
    limit: int = Query(default=50, ge=1, le=500),
    user: dict = Depends(require_auth),
):
    """Traverse the graph filtered by relation type and/or project."""
    conditions = []
    params: dict = {"limit": limit}

    if relation:
        conditions.append("e.relation_type = :rel")
        params["rel"] = relation
    if project:
        conditions.append("(src.metadata->>'project' = :proj OR tgt.metadata->>'project' = :proj)")
        params["proj"] = project

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    sql = text(f"""
        SELECT
            e.id, e.source_id, e.target_id, e.relation_type, e.weight, e.metadata,
            e.created_at,
            src.content AS src_content, src.category AS src_category,
            src.metadata AS src_meta,
            tgt.content AS tgt_content, tgt.category AS tgt_category,
            tgt.metadata AS tgt_meta
        FROM memory_edges e
        JOIN agent_memory src ON src.id = e.source_id
        JOIN agent_memory tgt ON tgt.id = e.target_id
        WHERE {where_clause}
        ORDER BY e.weight DESC, e.created_at DESC
        LIMIT :limit
    """)

    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, params)
        rows = result.mappings().all()

    edges_out = []
    node_ids = set()
    for r in rows:
        src_meta = r["src_meta"]
        tgt_meta = r["tgt_meta"]
        if isinstance(src_meta, str):
            try:
                src_meta = json.loads(src_meta)
            except Exception:
                src_meta = {}
        if isinstance(tgt_meta, str):
            try:
                tgt_meta = json.loads(tgt_meta)
            except Exception:
                tgt_meta = {}

        edges_out.append({
            "id": r["id"],
            "source_id": r["source_id"],
            "target_id": r["target_id"],
            "relation_type": r["relation_type"],
            "weight": float(r["weight"] or 1.0),
            "source_project": src_meta.get("project", ""),
            "target_project": tgt_meta.get("project", ""),
            "source_content": (r["src_content"] or "")[:120],
            "target_content": (r["tgt_content"] or "")[:120],
            "source_category": r["src_category"],
            "target_category": r["tgt_category"],
        })
        node_ids.add(r["source_id"])
        node_ids.add(r["target_id"])

    return {
        "edges": edges_out,
        "edge_count": len(edges_out),
        "unique_node_count": len(node_ids),
        "filters": {"relation": relation, "project": project},
    }


# ── GET /api/brain/graph/project/{project} ────────────────────────────────────

@router.get("/api/brain/graph/project/{project}")
async def get_project_subgraph(
    project: str,
    user: dict = Depends(require_auth),
):
    """Get the full subgraph for a project: all memories + edges between them."""
    async with AsyncSessionLocal() as session:
        # All memories for this project
        mem_result = await session.execute(text("""
            SELECT id, content, category, metadata, created_at
            FROM agent_memory
            WHERE metadata->>'project' = :project
            ORDER BY created_at DESC
        """), {"project": project})
        memories = {}
        for r in mem_result.mappings().all():
            mem_id = r["id"]
            meta = r["metadata"]
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            memories[mem_id] = {
                "id": mem_id,
                "content": (r["content"] or "")[:200],
                "category": r["category"],
                "project": project,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }

        if not memories:
            return {"project": project, "nodes": [], "edges": [], "node_count": 0, "edge_count": 0}

        ids = list(memories.keys())
        placeholders = ",".join(str(i) for i in ids)

        # Edges where source OR target is in this project's memories
        edge_result = await session.execute(text(f"""
            SELECT e.id, e.source_id, e.target_id, e.relation_type, e.weight, e.metadata, e.created_at
            FROM memory_edges e
            WHERE e.source_id IN ({placeholders})
               OR e.target_id IN ({placeholders})
            ORDER BY e.weight DESC
        """))
        edges_out = []
        for r in edge_result.mappings().all():
            edges_out.append({
                "id": r["id"],
                "source_id": r["source_id"],
                "target_id": r["target_id"],
                "relation_type": r["relation_type"],
                "weight": float(r["weight"] or 1.0),
            })
            # Include related nodes from other projects
            for nid in (r["source_id"], r["target_id"]):
                if nid not in memories:
                    memories[nid] = {"id": nid, "content": "(external)", "category": "", "project": "?"}

    return {
        "project": project,
        "nodes": list(memories.values()),
        "edges": edges_out,
        "node_count": len(memories),
        "edge_count": len(edges_out),
    }


# ── GET /api/brain/graph/configs ──────────────────────────────────────────────

@router.get("/api/brain/graph/configs")
async def get_config_registry(user: dict = Depends(require_auth)):
    """Cross-project config registry: all memories tagged as config with their values across projects."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT m.id, m.content, m.category, m.metadata, m.created_at, m.confidence,
                   e.relation_type, e.source_id, e.target_id
            FROM agent_memory m
            LEFT JOIN memory_edges e ON e.source_id = m.id
            WHERE m.metadata->>'is_config' = 'true'
               OR m.category IN ('config', 'preference', 'system_config')
            ORDER BY m.created_at DESC
            LIMIT 100
        """))
        rows = result.mappings().all()

    configs = {}
    for r in rows:
        meta = r["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        key = meta.get("config_key") or f"mem_{r['id']}"
        proj = meta.get("project", "?")

        if key not in configs:
            configs[key] = {
                "config_key": key,
                "description": (r["content"] or "")[:200],
                "category": r["category"],
                "values": {},
            }

        if proj not in configs[key]["values"]:
            configs[key]["values"][proj] = {
                "memory_id": r["id"],
                "content": (r["content"] or "")[:200],
                "confidence": r["confidence"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }

    return {
        "config_count": len(configs),
        "configs": list(configs.values()),
    }


# ── GET /api/brain/graph/conflicts ────────────────────────────────────────────

@router.get("/api/brain/graph/conflicts")
async def detect_conflicts(user: dict = Depends(require_auth)):
    """Detect conflicting values across projects using conflicts_with edges."""
    async with AsyncSessionLocal() as session:
        # Edges with conflicts_with relation
        result = await session.execute(text("""
            SELECT e.id, e.source_id, e.target_id, e.weight, e.metadata,
                   src.content AS src_content, src.metadata AS src_meta,
                   src.category AS src_cat,
                   tgt.content AS tgt_content, tgt.metadata AS tgt_meta,
                   tgt.category AS tgt_cat
            FROM memory_edges e
            JOIN agent_memory src ON src.id = e.source_id
            JOIN agent_memory tgt ON tgt.id = e.target_id
            WHERE e.relation_type = 'conflicts_with'
            ORDER BY e.weight DESC
        """))
        rows = result.mappings().all()

        conflicts = []
        for r in rows:
            src_meta = r["src_meta"]
            tgt_meta = r["tgt_meta"]
            if isinstance(src_meta, str):
                try:
                    src_meta = json.loads(src_meta)
                except Exception:
                    src_meta = {}
            if isinstance(tgt_meta, str):
                try:
                    tgt_meta = json.loads(tgt_meta)
                except Exception:
                    tgt_meta = {}

            conflicts.append({
                "edge_id": r["id"],
                "severity": 1.0 - float(r["weight"] or 0.5),
                "source": {
                    "id": r["source_id"],
                    "content": (r["src_content"] or "")[:200],
                    "project": src_meta.get("project", "?"),
                    "category": r["src_cat"],
                },
                "target": {
                    "id": r["target_id"],
                    "content": (r["tgt_content"] or "")[:200],
                    "project": tgt_meta.get("project", "?"),
                    "category": r["tgt_cat"],
                },
            })

        # Also check for configs with same key but different content across projects
        config_result = await session.execute(text("""
            SELECT m1.id AS id1, m1.content AS content1, m1.metadata AS meta1,
                   m2.id AS id2, m2.content AS content2, m2.metadata AS meta2
            FROM agent_memory m1
            JOIN agent_memory m2 ON m1.metadata->>'config_key' = m2.metadata->>'config_key'
                AND m1.metadata->>'project' < m2.metadata->>'project'
            WHERE m1.metadata->>'is_config' = 'true'
              AND m2.metadata->>'is_config' = 'true'
              AND m1.content != m2.content
        """))
        for r in config_result.mappings().all():
            meta1 = r["meta1"]
            meta2 = r["meta2"]
            if isinstance(meta1, str):
                try:
                    meta1 = json.loads(meta1)
                except Exception:
                    meta1 = {}
            if isinstance(meta2, str):
                try:
                    meta2 = json.loads(meta2)
                except Exception:
                    meta2 = {}

            # Avoid duplicates if already has conflicts_with edge
            already_reported = any(
                c["source"]["id"] == r["id1"] and c["target"]["id"] == r["id2"]
                for c in conflicts
            )
            if not already_reported:
                conflicts.append({
                    "edge_id": None,
                    "severity": 0.7,
                    "source": {
                        "id": r["id1"],
                        "content": (r["content1"] or "")[:200],
                        "project": meta1.get("project", "?"),
                        "category": "config_conflict",
                    },
                    "target": {
                        "id": r["id2"],
                        "content": (r["content2"] or "")[:200],
                        "project": meta2.get("project", "?"),
                        "category": "config_conflict",
                    },
                })

    return {
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


# ── POST /api/brain/graph/auto-link ───────────────────────────────────────────

@router.post("/api/brain/graph/auto-link", status_code=201)
async def auto_link_memories(payload: AutoLinkRequest, user: dict = Depends(require_auth)):
    """
    Auto-create edges between memories in the same project that share categories,
    and cross-project memories that share config_key or similar content patterns.
    """
    links_created = 0

    async with AsyncSessionLocal() as session:
        # 1. Intra-project: link memories with same category (but not autolearn noise)
        cat_result = await session.execute(text("""
            SELECT m1.id AS id1, m2.id AS id2, m1.category
            FROM agent_memory m1
            JOIN agent_memory m2 ON m1.category = m2.category AND m1.id < m2.id
            WHERE m1.metadata->>'project' = :project
              AND m2.metadata->>'project' = :project
              AND m1.source NOT LIKE 'autolearn_%'
              AND m2.source NOT LIKE 'autolearn_%'
              AND NOT EXISTS (
                  SELECT 1 FROM memory_edges e
                  WHERE e.source_id = m1.id AND e.target_id = m2.id AND e.relation_type = 'relates_to'
              )
            LIMIT 50
        """), {"project": payload.project})
        cat_pairs = cat_result.mappings().all()

        for pair in cat_pairs:
            try:
                await session.execute(
                    text("""
                        INSERT INTO memory_edges (source_id, target_id, relation_type, weight, metadata, created_at, updated_at)
                        VALUES (:src, :tgt, 'relates_to', 0.7, :meta, NOW(), NOW())
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "src": pair["id1"], "tgt": pair["id2"],
                        "meta": json.dumps({"auto": True, "reason": "same_category", "category": pair["category"]}),
                    },
                )
                links_created += 1
            except Exception:
                pass

        # 2. Cross-project: link memories with same config_key
        config_result = await session.execute(text("""
            SELECT m1.id AS id1, m2.id AS id2, m1.metadata->>'config_key' AS config_key,
                   m1.metadata->>'project' AS proj1, m2.metadata->>'project' AS proj2
            FROM agent_memory m1
            JOIN agent_memory m2 ON m1.metadata->>'config_key' = m2.metadata->>'config_key'
                AND m1.metadata->>'project' != m2.metadata->>'project'
            WHERE (m1.metadata->>'project' = :project OR m2.metadata->>'project' = :project)
              AND m1.metadata->>'is_config' = 'true'
              AND m2.metadata->>'is_config' = 'true'
              AND NOT EXISTS (
                  SELECT 1 FROM memory_edges e
                  WHERE e.source_id = m1.id AND e.target_id = m2.id AND e.relation_type = 'same_as'
              )
            LIMIT 50
        """), {"project": payload.project})
        config_pairs = config_result.mappings().all()

        for pair in config_pairs:
            # Determine if values conflict
            rel_type = "same_as"
            weight = 0.9

            try:
                await session.execute(
                    text("""
                        INSERT INTO memory_edges (source_id, target_id, relation_type, weight, metadata, created_at, updated_at)
                        VALUES (:src, :tgt, :rel, :weight, :meta, NOW(), NOW())
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "src": pair["id1"], "tgt": pair["id2"], "rel": rel_type, "weight": weight,
                        "meta": json.dumps({
                            "auto": True, "reason": "shared_config",
                            "config_key": pair["config_key"],
                            "project_from": pair["proj1"], "project_to": pair["proj2"],
                        }),
                    },
                )
                links_created += 1
            except Exception:
                pass

        await session.commit()

    return {
        "project": payload.project,
        "links_created": links_created,
    }


# ── POST /api/brain/graph/propagate/{memory_id} ───────────────────────────────

@router.post("/api/brain/graph/propagate/{memory_id}", status_code=201)
async def propagate_memory(memory_id: int, user: dict = Depends(require_auth)):
    """Propagate a config memory to all known projects that don't have it yet."""
    propagated_to = []

    async with AsyncSessionLocal() as session:
        mem = await _resolve_memory(session, memory_id)
        if not mem:
            raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")

        # Get the full content
        full = await session.execute(
            text("SELECT content, category, confidence, metadata FROM agent_memory WHERE id = :id"),
            {"id": memory_id},
        )
        row = full.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Memory not found")

        meta = row["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        config_key = meta.get("config_key")
        if not config_key:
            # Auto-generate a config_key if none exists
            config_key = f"propagated_mem_{memory_id}"

        source_project = meta.get("project", "?")

        # Get all projects
        proj_result = await session.execute(text("""
            SELECT DISTINCT metadata->>'project' AS project FROM agent_memory
            WHERE metadata->>'project' IS NOT NULL AND metadata->>'project' != ''
              AND metadata->>'project' != :src_proj
              AND metadata->>'project' != 'banks'
        """), {"src_proj": source_project})
        all_projects = [r["project"] for r in proj_result.mappings().all()]

        for target_project in all_projects:
            # Check if already exists
            existing = await session.execute(
                text("""
                    SELECT id FROM agent_memory
                    WHERE metadata->>'config_key' = :k
                      AND metadata->>'project' = :p
                    LIMIT 1
                """),
                {"k": config_key, "p": target_project},
            )
            if existing.mappings().first():
                continue

            # Create propagated copy
            tgt_meta = dict(meta)
            tgt_meta["project"] = target_project
            tgt_meta["propagated_from"] = source_project
            tgt_meta["propagated_at"] = _utcnow_iso()
            tgt_meta["is_config"] = "true"
            tgt_meta["config_key"] = config_key

            ins_result = await session.execute(
                text("""
                    INSERT INTO agent_memory
                        (content, category, source, confidence, metadata,
                         created_at, updated_at, access_count, verified)
                    VALUES
                        (:content, :category, 'propagation_engine', :confidence, :metadata,
                         NOW(), NOW(), 0, false)
                    RETURNING id
                """),
                {
                    "content": row["content"],
                    "category": row["category"] or "config",
                    "confidence": float(row["confidence"] or 0.7) * 0.9,
                    "metadata": json.dumps(tgt_meta),
                },
            )
            new_id = ins_result.scalar()

            # Create same_as edge between original and propagated copy
            await session.execute(
                text("""
                    INSERT INTO memory_edges (source_id, target_id, relation_type, weight, metadata, created_at, updated_at)
                    VALUES (:src, :tgt, 'propagates_to', 0.95, :meta, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """),
                {
                    "src": memory_id, "tgt": new_id,
                    "meta": json.dumps({"auto": True, "reason": "propagation", "config_key": config_key}),
                },
            )
            propagated_to.append({"project": target_project, "new_memory_id": new_id})

        await session.commit()

    return {
        "source_memory_id": memory_id,
        "config_key": config_key,
        "propagated_to": propagated_to,
        "count": len(propagated_to),
    }


# ── GET /api/brain/graph/{memory_id} (MUST be last — catches all paths) ───────

@router.get("/api/brain/graph/{memory_id}")
async def get_memory_graph(
    memory_id: int,
    depth: int = Query(default=1, ge=1, le=3),
    user: dict = Depends(require_auth),
):
    """Get the subgraph around a memory node with BFS up to N depth."""
    async with AsyncSessionLocal() as session:
        memory = await _resolve_memory(session, memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")

        nodes = {memory_id: memory}
        edges = []
        visited = {memory_id}
        current_level = {memory_id}

        for _ in range(depth):
            if not current_level:
                break

            ids = list(current_level)
            placeholders = ",".join(str(i) for i in ids)

            out_result = await session.execute(text(f"""
                SELECT e.id, e.source_id, e.target_id, e.relation_type, e.weight, e.metadata, e.created_at
                FROM memory_edges e
                WHERE e.source_id IN ({placeholders})
            """))
            out_rows = out_result.mappings().all()

            in_result = await session.execute(text(f"""
                SELECT e.id, e.source_id, e.target_id, e.relation_type, e.weight, e.metadata, e.created_at
                FROM memory_edges e
                WHERE e.target_id IN ({placeholders})
            """))
            in_rows = in_result.mappings().all()

            next_level = set()
            for r in out_rows + in_rows:
                edge = {
                    "id": r["id"],
                    "source_id": r["source_id"],
                    "target_id": r["target_id"],
                    "relation_type": r["relation_type"],
                    "weight": float(r["weight"] or 1.0),
                }
                if edge not in edges:
                    edges.append(edge)
                for nid in (r["source_id"], r["target_id"]):
                    if nid not in visited:
                        next_level.add(nid)

            if next_level:
                nl_placeholders = ",".join(str(i) for i in next_level)
                node_result = await session.execute(text(f"""
                    SELECT id, content, category, metadata, created_at
                    FROM agent_memory WHERE id IN ({nl_placeholders})
                """))
                for row in node_result.mappings().all():
                    nid = row["id"]
                    if nid not in nodes:
                        meta = row["metadata"]
                        if isinstance(meta, str):
                            try:
                                meta = json.loads(meta)
                            except Exception:
                                meta = {}
                        nodes[nid] = {
                            "id": nid,
                            "content": (row["content"] or "")[:200],
                            "category": row["category"],
                            "project": meta.get("project", ""),
                            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        }
                    visited.add(nid)

            current_level = next_level

    return {
        "root": memory_id,
        "depth": depth,
        "nodes": list(nodes.values()),
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
