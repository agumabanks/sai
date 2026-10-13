"""
Sanaa AI — SanaaBrain Intelligence Routes
Provides read endpoints for auto-learned insights and a synchronous
learn_now trigger. All endpoints require require_auth.

Endpoints:
  GET  /api/brain/insights
  GET  /api/brain/habits
  GET  /api/brain/health_patterns
  GET  /api/brain/client_intelligence
  GET  /api/brain/resource_usage
  POST /api/brain/learn_now
  GET  /api/brain/smart_briefing/{project}
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text

from core.database import AsyncSessionLocal
from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()


# ── GET /api/brain/health ──────────────────────────────────────────────────

@router.get("/api/brain/health")
async def brain_health(user: dict = Depends(require_auth)):
    """Production health check for the brain engine."""
    now_iso = _utcnow_iso()
    issues = []
    async with AsyncSessionLocal() as session:
        # Memory count
        mem_count = (await session.execute(text("SELECT COUNT(*) FROM agent_memory"))).scalar() or 0
        edge_count = (await session.execute(text("SELECT COUNT(*) FROM memory_edges"))).scalar() or 0
        learn_count = (await session.execute(
            text("SELECT COUNT(*) FROM agent_memory WHERE source = 'brain_watcher' AND created_at > NOW() - INTERVAL '24 hours'")
        )).scalar() or 0
        last_mem = (await session.execute(
            text("SELECT MAX(created_at) FROM agent_memory")
        )).scalar()
        last_learn = (await session.execute(
            text("""
                SELECT MAX(created_at) FROM agent_memory
                WHERE source IN ('brain_watcher', 'autolearn_health', 'autolearn_clients')
            """)
        )).scalar()

        # Error count (agent_memory category=audit with errors)
        error_count = (await session.execute(
            text("SELECT COUNT(*) FROM agent_memory WHERE category = 'audit'")
        )).scalar() or 0

        # Check for stale learner (> 48 hours since last learn)
        if last_learn:
            stale = (datetime.now(timezone.utc) - last_learn.replace(tzinfo=timezone.utc)).total_seconds() > 172800
            if stale:
                issues.append("LEARNER_STALE: no learning activity in 48+ hours")

        # Check for zero edges (graph not used)
        if edge_count == 0:
            issues.append("NO_EDGES: knowledge graph has no relations")

        # Check for empty memory
        if mem_count == 0:
            issues.append("EMPTY_BRAIN: no memories stored")

    services = {"web": True, "worker": None, "beat": None}
    try:
        import subprocess
        for svc in ["sanaa-ai-worker", "sanaa-ai-beat"]:
            r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True, timeout=5)
            services[svc.replace("sanaa-ai-", "")] = r.stdout.strip() == "active"
    except Exception:
        pass

    status = "degraded" if issues else "healthy"

    return {
        "status": status,
        "generated_at": now_iso,
        "memory_count": mem_count,
        "edge_count": edge_count,
        "learn_activity_24h": learn_count,
        "last_memory_at": last_learn.isoformat() if last_learn else None,
        "errors": error_count,
        "issues": issues,
        "services": services,
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_meta(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _row_to_insight(r: dict) -> dict:
    meta = _parse_meta(r.get("metadata"))
    return {
        "id": r.get("id"),
        "content": r.get("content"),
        "category": r.get("category"),
        "source": r.get("source"),
        "confidence": float(r.get("confidence") or 0.9),
        "metadata": meta,
        "project": meta.get("project", ""),
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
    }


# ── GET /api/brain/insights ────────────────────────────────────────────────

@router.get("/api/brain/insights")
async def get_brain_insights(
    category: Optional[str] = None,
    project: Optional[str] = None,
    limit: int = 20,
    user: dict = Depends(require_auth),
):
    """List all auto-learned insights (source LIKE 'autolearn_%')."""
    conditions = ["source LIKE 'autolearn_%'", "(expires_at IS NULL OR expires_at > NOW())"]
    params: dict = {"limit": min(limit, 200)}

    if category:
        conditions.append("category = :category")
        params["category"] = category
    if project:
        conditions.append("metadata->>'project' = :project")
        params["project"] = project

    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT id, content, category, source, confidence, metadata, created_at
        FROM agent_memory
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit
    """)

    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, params)
        rows = [dict(r._mapping) for r in result.fetchall()]

        # Total count
        count_sql = text(f"SELECT COUNT(*) FROM agent_memory WHERE {where}")
        count_result = await session.execute(count_sql, {k: v for k, v in params.items() if k != "limit"})
        total = count_result.scalar() or 0

    return {
        "total": total,
        "limit": limit,
        "category": category,
        "project": project,
        "items": [_row_to_insight(r) for r in rows],
    }


# ── GET /api/brain/habits ──────────────────────────────────────────────────

@router.get("/api/brain/habits")
async def get_brain_habits(user: dict = Depends(require_auth)):
    """Return the last 4 weekly habit intelligence entries."""
    sql = text("""
        SELECT id, content, category, source, confidence, metadata, created_at
        FROM agent_memory
        WHERE category = 'habit_intelligence'
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY created_at DESC
        LIMIT 4
    """)
    async with AsyncSessionLocal() as session:
        result = await session.execute(sql)
        rows = [dict(r._mapping) for r in result.fetchall()]

    return {"habits": [_row_to_insight(r) for r in rows]}


# ── GET /api/brain/health_patterns ────────────────────────────────────────

@router.get("/api/brain/health_patterns")
async def get_health_patterns(user: dict = Depends(require_auth)):
    """Return the latest health insight per tenant/app."""
    sql = text("""
        SELECT DISTINCT ON (metadata->>'tenant')
            id, content, category, source, confidence, metadata, created_at
        FROM agent_memory
        WHERE category = 'system_health'
          AND source = 'autolearn_health'
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY metadata->>'tenant', created_at DESC
    """)
    async with AsyncSessionLocal() as session:
        result = await session.execute(sql)
        rows = [dict(r._mapping) for r in result.fetchall()]

    apps: dict = {}
    for r in rows:
        meta = _parse_meta(r.get("metadata"))
        key = meta.get("tenant") or meta.get("app") or "unknown"
        apps[key] = _row_to_insight(r)

    return {"apps": apps, "count": len(apps)}


# ── GET /api/brain/client_intelligence ───────────────────────────────────

@router.get("/api/brain/client_intelligence")
async def get_client_intelligence(user: dict = Depends(require_auth)):
    """Return the last 20 client intelligence entries."""
    sql = text("""
        SELECT id, content, category, source, confidence, metadata, created_at
        FROM agent_memory
        WHERE category = 'client_intelligence'
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY created_at DESC
        LIMIT 20
    """)
    async with AsyncSessionLocal() as session:
        result = await session.execute(sql)
        rows = [dict(r._mapping) for r in result.fetchall()]

    return {"clients": [_row_to_insight(r) for r in rows]}


# ── GET /api/brain/resource_usage ────────────────────────────────────────

@router.get("/api/brain/resource_usage")
async def get_resource_usage(user: dict = Depends(require_auth)):
    """Return resource usage summaries from the last 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    sql = text("""
        SELECT id, content, category, source, confidence, metadata, created_at
        FROM agent_memory
        WHERE category = 'resource_usage'
          AND created_at > :cutoff
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY created_at DESC
    """)
    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, {"cutoff": cutoff})
        rows = [dict(r._mapping) for r in result.fetchall()]

    items = [_row_to_insight(r) for r in rows]

    # Sum total_cost from metadata
    total_cost = 0.0
    for item in items:
        try:
            total_cost += float(item["metadata"].get("total_cost") or 0)
        except (TypeError, ValueError):
            pass

    return {
        "usage": items,
        "total_cost_usd": round(total_cost, 6),
        "period_days": 7,
    }


# ── POST /api/brain/learn_now ──────────────────────────────────────────────

@router.post("/api/brain/learn_now")
async def learn_now(user: dict = Depends(require_auth)):
    """Immediately trigger the SanaaBrain learner + watcher synchronously."""
    try:
        from core.brain.sanaabrain_learner import SanaabrainLearner
        from core.agents.brain_watcher import scan_and_learn

        learner = SanaabrainLearner()
        result = await learner.run_all(hours_back=24)
        watch_result = await scan_and_learn(hours_back=24)
        result["brain_watcher"] = watch_result

        logger.info(f"[BrainIntelligence] learn_now triggered by {user.get('email')}: {result}")
        return result
    except Exception as e:
        logger.error(f"[BrainIntelligence] learn_now failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Learning failed: {e}")


@router.post("/api/brain/decision")
async def record_decision(request: Request, user: dict = Depends(require_auth)):
    """Record a decision or commitment in the brain."""
    import json as _json
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    content = body.get("content", "").strip()
    project = body.get("project", "antigravity")
    decision_type = body.get("type", "decision")  # decision, commitment, action_item
    owner = body.get("owner", "")
    related_config = body.get("config_key", "")

    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    meta = {
        "type": decision_type,
        "project": project,
        "recorded_by": user.get("email", "api"),
        "owner": owner,
    }
    if related_config:
        meta["config_key"] = related_config
        meta["is_config"] = "true"

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                INSERT INTO agent_memory
                    (content, category, source, confidence, metadata,
                     created_at, updated_at, access_count, verified)
                VALUES
                    (:content, :cat, 'commander', 1.0, :meta,
                     NOW(), NOW(), 0, true)
                RETURNING id
            """),
            {
                "content": f"[Decision] {content}",
                "cat": f"decision_{decision_type}",
                "meta": _json.dumps(meta),
            },
        )
        mem_id = result.scalar()
        await session.commit()

    logger.info(f"Decision recorded: id={mem_id} type={decision_type} project={project}")
    return {"id": mem_id, "type": decision_type, "project": project, "content": content}


@router.post("/api/brain/scan_vps")
async def scan_vps(user: dict = Depends(require_auth)):
    """Manually trigger a VPS scan to discover projects, changes, and skills."""
    try:
        from core.agents.brain_watcher import scan_and_learn
        result = await scan_and_learn(hours_back=168)
        logger.info(f"[BrainIntelligence] VPS scan triggered by {user.get('email')}: {result}")
        return result
    except Exception as e:
        logger.error(f"[BrainIntelligence] VPS scan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"VPS scan failed: {e}")


# ── GET /api/brain/smart_briefing/{project} ────────────────────────────────
# Shared personal project that is always included for habit/work data
PERSONAL_PROJECT = "banks"

# Map projects to their associated tenants/domains for scoped system health
PROJECT_TENANT_MAP: dict[str, set[str]] = {
    "antigravity": {"alerts", "corr", "case", "detail", "monitor"},
    "sanaa_finance": {"finance", "mbalala", "sacco"},
    "soko24": {"soko", "marketplace"},
    "farzone": {"farzone", "agency"},
    "baraka24": {"drc", "logistics"},
}


@router.get("/api/brain/smart_briefing/{project}")
async def get_smart_briefing(
    project: str,
    scope: str = "brief",
    user: dict = Depends(require_auth),
):
    """
    Generate a project-scoped smart briefing.

    Parameters:
    - project: Project name (sanaa_finance, antigravity, etc.)
    - scope: 'brief' (default, concise) | 'normal' | 'full' (all available data)
    """
    if scope not in ("brief", "normal", "full"):
        scope = "brief"
    now_iso = _utcnow_iso()
    sections_included = []
    lines = [
        f"## SanaaBrain Briefing — {project}",
        f"Generated: {now_iso} | Scope: {scope}",
        "",
    ]

    async with AsyncSessionLocal() as session:

        # ── Section 1: Project Context ────────────────────────────────────
        ctx_limit = 5 if scope == "brief" else 10
        result = await session.execute(text("""
            SELECT id, content, category, confidence, created_at, metadata
            FROM agent_memory
            WHERE metadata->>'project' = :project
              AND source NOT LIKE 'autolearn_%'
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY access_count DESC, confidence DESC
            LIMIT :limit
        """), {"project": project, "limit": ctx_limit})
        ctx_rows = result.mappings().all()

        if ctx_rows:
            lines.append("### Project Context")
            for r in ctx_rows:
                conf = float(r.get("confidence") or 0.5)
                lines.append(f"- {r['content'][:300]} [conf: {conf:.2f}]")
            lines.append("")
            sections_included.append("project_context")

        # ── Section 2: System Health (project-scoped) ─────────────────────
        health_limit = 3 if scope == "brief" else 8
        health_result = await session.execute(text("""
            SELECT DISTINCT ON (metadata->>'tenant')
                id, content, metadata, created_at
            FROM agent_memory
            WHERE category = 'system_health'
              AND source = 'autolearn_health'
              AND metadata->>'project' = :project
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY metadata->>'tenant', created_at DESC
            LIMIT :limit
        """), {"project": project, "limit": health_limit})
        health_rows = health_result.mappings().all()

        if health_rows:
            lines.append("### System Health")
            for r in health_rows:
                meta = _parse_meta(r.get("metadata"))
                tenant = meta.get("tenant", "?")
                score = meta.get("health_score")
                score_str = f"{score:.0f}/100" if score is not None else "N/A"
                lines.append(f"- **{tenant}** (score: {score_str})")
            lines.append("")
            sections_included.append("system_health")

        # ── Section 3: Client Intelligence (project-scoped) ──────────────
        ci_limit = 3 if scope == "brief" else 5
        ci_result = await session.execute(text("""
            SELECT content, metadata, created_at FROM agent_memory
            WHERE category = 'client_intelligence'
              AND metadata->>'project' = :project
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"project": project, "limit": ci_limit})
        ci_rows = ci_result.mappings().all()

        if ci_rows:
            lines.append("### Client Status")
            for r in ci_rows:
                lines.append(f"- {r['content'][:250]}")
            lines.append("")
            sections_included.append("client_intelligence")

        # ── Section 4: Recurring Issues (project-scoped) ─────────────────
        issue_limit = 3 if scope == "brief" else 5
        issue_result = await session.execute(text("""
            SELECT content, metadata, created_at FROM agent_memory
            WHERE category = 'recurring_issues'
              AND source LIKE 'autolearn_%'
              AND metadata->>'project' = :project
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"project": project, "limit": issue_limit})
        issue_rows = issue_result.mappings().all()

        if issue_rows:
            lines.append("### Recurring Issues")
            for r in issue_rows:
                lines.append(f"- {r['content'][:200]}")
            lines.append("")
            sections_included.append("recurring_issues")

        # ── Section 5: Habits & Work Patterns (personal, from PERSONAL_PROJECT) ──
        if scope != "brief":
            habit_row = None
            if scope == "full":
                habit_result = await session.execute(text("""
                    SELECT content, created_at FROM agent_memory
                    WHERE category = 'habit_intelligence'
                      AND metadata->>'project' = :personal
                      AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"personal": PERSONAL_PROJECT})
                habit_row = habit_result.mappings().first()
            elif scope == "normal":
                habit_result = await session.execute(text("""
                    SELECT content, created_at FROM agent_memory
                    WHERE category = 'habit_intelligence'
                      AND metadata->>'project' IN (:personal, :project)
                      AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"personal": PERSONAL_PROJECT, "project": project})
                habit_row = habit_result.mappings().first()

            if habit_row:
                lines.append("### Habits & Work Patterns")
                lines.append(habit_row["content"])
                lines.append("")
                sections_included.append("habit_intelligence")

            # Work pattern (only in full scope)
            if scope == "full":
                work_result = await session.execute(text("""
                    SELECT content, created_at FROM agent_memory
                    WHERE category = 'work_pattern'
                      AND metadata->>'project' IN (:personal, :project)
                      AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"personal": PERSONAL_PROJECT, "project": project})
                work_row = work_result.mappings().first()

                if work_row:
                    lines.append("### Recent Work Pattern")
                    lines.append(work_row["content"])
                    lines.append("")
                    sections_included.append("work_pattern")

        # ── Section 6: Auto-Learned Insights for Project ─────────────────
        if scope != "brief":
            auto_limit = 3 if scope == "normal" else 5
            auto_result = await session.execute(text("""
                SELECT content, category, source, created_at FROM agent_memory
                WHERE source LIKE 'autolearn_%'
                  AND metadata->>'project' = :project
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"project": project, "limit": auto_limit})
            auto_rows = auto_result.mappings().all()

            if auto_rows:
                lines.append("### Auto-Learned Insights")
                for r in auto_rows:
                    lines.append(f"- [{r['category']}] {r['content'][:200]}")
                lines.append("")
                sections_included.append("auto_learned")

        # ── Section 7: Cross-Project Knowledge Graph ───────────────────
        try:
            xp_limit = 3 if scope == "brief" else (5 if scope == "normal" else 10)
            xp_result = await session.execute(text("""
                SELECT
                    e.relation_type, e.weight,
                    src.id AS src_id, src.content AS src_content, src.metadata AS src_meta,
                    tgt.id AS tgt_id, tgt.content AS tgt_content, tgt.metadata AS tgt_meta
                FROM memory_edges e
                JOIN agent_memory src ON src.id = e.source_id
                JOIN agent_memory tgt ON tgt.id = e.target_id
                WHERE (src.metadata->>'project' = :project
                   OR tgt.metadata->>'project' = :project)
                  AND (src.metadata->>'project' != tgt.metadata->>'project'
                       OR (src.metadata->>'project' = :project
                           AND tgt.metadata->>'project' = :project
                           AND e.relation_type IN ('same_as', 'config_of', 'conflicts_with')))
                ORDER BY e.weight DESC, e.created_at DESC
                LIMIT :limit
            """), {"project": project, "limit": xp_limit})
            xp_rows = xp_result.mappings().all()

            if xp_rows:
                cross_lines = []
                for r in xp_rows:
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

                    src_proj = src_meta.get("project", "?")
                    tgt_proj = tgt_meta.get("project", "?")
                    rtype = r["relation_type"]

                    if src_proj == project and tgt_proj != project:
                        cross_lines.append(f"- **{tgt_proj}** ({rtype}): {r['tgt_content'][:200]}")
                    elif tgt_proj == project and src_proj != project:
                        cross_lines.append(f"- **{src_proj}** ({rtype}): {r['src_content'][:200]}")
                    else:
                        cross_lines.append(f"- **{src_proj}** ↔ **{tgt_proj}** ({rtype}): {r['src_content'][:150]}")

                if cross_lines:
                    lines.append("### Cross-Project Knowledge")
                    lines.extend(cross_lines[:xp_limit])
                    lines.append("")
                    sections_included.append("cross_project")
        except Exception as e:
            logger.warning(f"Cross-project section failed: {e}")

    briefing_text = "\n".join(lines)

    return {
        "project": project,
        "smart_briefing": briefing_text,
        "sections_included": sections_included,
        "scope": scope,
        "generated_at": now_iso,
    }
