"""
SanaaEngine Brain MCP Server
==============================
Model Context Protocol server that exposes the knowledge graph as tools
for Claude Code (and any MCP-compatible client).

When you type in Claude Code, the AI can automatically query your project's
knowledge: past decisions, configs, architecture, related work — without
you having to explain context.

Tools:
  get_briefing      — Smart briefing for any project
  search_memories   — Semantic search across brain memories
  get_configs       — Cross-project config registry
  get_related       — Graph neighbors of a memory
  log_decision      — Record a decision/commitment
  get_health        — Brain engine health status

Usage (add to .claude/settings.json):
  "mcpServers": {
    "sanaa-brain": {
      "command": "/opt/antigravity/venv/bin/python3",
      "args": ["-m", "core.mcp_brain_server"]
    }
  }
"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ── Config ──────────────────────────────────────────────────────────────────
BRAIN_URL = os.getenv("BRAIN_URL", "http://127.0.0.1:8100")
ENGINE_KEY_FILE = Path(os.getenv("ENGINE_KEY_FILE", "/var/www/ai.sanaa.co/backend/.env"))

mcp = FastMCP("SanaaEngine Brain")


def _get_key() -> Optional[str]:
    try:
        with open(ENGINE_KEY_FILE) as f:
            for line in f:
                if "SANAA_ENGINE_KEY=" in line:
                    return line.split("=", 1)[1].strip()
    except Exception:
        return os.getenv("SANAA_ENGINE_KEY")


def _headers() -> dict:
    key = _get_key()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _get(url: str, timeout: int = 10) -> Optional[dict]:
    """Synchronous HTTP GET — avoids async issues with MCP stdio transport."""
    try:
        req = urllib.request.Request(f"{BRAIN_URL}{url}", headers=_headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _post(url: str, data: dict, timeout: int = 10) -> Optional[dict]:
    """Synchronous HTTP POST — avoids async issues with MCP stdio transport."""
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{BRAIN_URL}{url}", data=body, headers=_headers(), method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ── Tools ───────────────────────────────────────────────────────────────────

@mcp.tool()
def get_briefing(project: str = "sanaa_finance", scope: str = "brief") -> str:
    """Get a project briefing from the SanaaEngine brain.

    Returns project context, client status, cross-project knowledge,
    configs, and recent changes for any known project.
    Use scope="brief" (default) unless you explicitly need more detail.
    Brief scope returns ~500-800 tokens. Full scope can return 3000+ tokens.

    Args:
        project: Project name (sanaa_finance, antigravity, farzone, soko24, baraka24)
        scope: Detail level — brief (default, token-cheap), normal, or full
    """
    # Enforce brief as default if an invalid scope is passed
    if scope not in ("brief", "normal", "full"):
        scope = "brief"
    data = _get(f"/api/brain/smart_briefing/{project}?scope={scope}")
    if not data:
        return f"No briefing available for project '{project}'. The brain might not have data yet."
    briefing = data.get("smart_briefing", "No briefing content.")
    # Safety cap: truncate if somehow still massive
    if len(briefing) > 15000:
        briefing = briefing[:15000] + "\n\n[...truncated for token budget]"
    return briefing


@mcp.tool()
def search_memories(query: str, project: Optional[str] = None, limit: int = 5) -> str:
    """Search across all brain memories using semantic/full-text search.

    Finds relevant past work, decisions, configs, and project knowledge.

    Args:
        query: What to search for (e.g., "session timeout", "brand color", "Flutter auth")
        project: Optional project to narrow search (sanaa_finance, antigravity, etc.)
        limit: Max results (1-20)
    """
    params = f"?query={urllib.parse.quote(query)}&limit={min(limit, 20)}"
    if project:
        params += f"&project={urllib.parse.quote(project)}"
    data = _get(f"/api/memory/search{params}")
    if not data:
        return "Search failed or no results."
    results = data.get("results", [])
    if not results:
        return f"No memories found for '{query}'."

    lines = [f"## Search: \"{query}\" ({len(results)} results)\n"]
    for r in results:
        proj = r.get("project", "?")
        cat = r.get("category", "?")
        conf = r.get("confidence", 0)
        score = r.get("similarity_score", 0)
        lines.append(f"- [{proj}] ({cat}, conf={conf:.2f}, sim={score:.4f})")
        lines.append(f"  {r['content'][:200]}")
    return "\n".join(lines)


@mcp.tool()
def get_configs(config_key: Optional[str] = None) -> str:
    """Get cross-project configuration values.

    Shows what configs exist, which projects they're set in, and their values.
    Useful for checking if a config exists before creating a new one.
    Maximum 50 configs returned to stay within token budget.

    Args:
        config_key: Optional specific config to look up (e.g., "session_timeout", "brand_primary_color")
    """
    data = _get("/api/brain/graph/configs")
    if not data:
        return "Config registry unavailable."

    configs = data.get("configs", [])
    if not configs:
        return "No shared configs found."

    if config_key:
        configs = [c for c in configs if config_key.lower() in c.get("config_key", "").lower()]
        if not configs:
            return f"No config found matching '{config_key}'."

    # Hard cap to protect token budget
    configs = configs[:50]

    lines = [f"## Config Registry ({len(configs)} keys)\n"]
    for c in configs:
        key = c.get("config_key", "?")
        values = c.get("values", {})
        lines.append(f"### {key} ({len(values)} projects)")
        for proj, val in list(values.items())[:5]:  # cap projects per config
            lines.append(f"- **{proj}**: {val.get('content', '')[:80]}")
        if len(values) > 5:
            lines.append(f"- ... and {len(values) - 5} more projects")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def get_related(memory_id: int, depth: int = 1) -> str:
    """Find related memories in the knowledge graph connected to a given memory.

    Traverses the graph edges to surface connected context.

    Args:
        memory_id: Memory ID to explore (get from search_memories)
        depth: How deep to traverse (1-3). 1=direct neighbors, 2=neighbors of neighbors
    """
    data = _get(f"/api/brain/graph/{memory_id}?depth={min(depth, 3)}")
    if not data:
        return f"Memory {memory_id} not found or graph unavailable."

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not nodes:
        return f"No data for memory {memory_id}."

    target = next((n for n in nodes if n["id"] == memory_id), None)
    lines = [f"## Memory #{memory_id}"]
    if target:
        lines.append(f"Project: {target.get('project', '?')}")
        lines.append(f"Content: {target.get('content', '')[:200]}")
    lines.append(f"\n### Graph ({len(nodes)} nodes, {len(edges)} edges)\n")

    for e in edges:
        other_id = e["target_id"] if e["source_id"] == memory_id else e["source_id"]
        other = next((n for n in nodes if n["id"] == other_id), None)
        rel = e.get("relation_type", "?")
        if other:
            lines.append(f"- [{rel}] → #{other_id} ({other.get('project', '?')})")
            lines.append(f"  {other.get('content', '')[:120]}")
    return "\n".join(lines)


@mcp.tool()
def log_decision(content: str, project: str = "antigravity", owner: str = "") -> str:
    """Record a decision or commitment in the SanaaEngine brain.

    This persists decisions so they appear in future project briefings
    and can be found via search. Use this whenever a meaningful choice is made.

    Args:
        content: What was decided (e.g., "Use 5min session timeout for all Sanaa apps")
        project: Project this decision belongs to
        owner: Who owns this decision (optional)
    """
    data = _post("/api/brain/decision", {
        "content": content,
        "project": project,
        "type": "decision",
        "owner": owner,
    })
    if data:
        mem_id = data.get("id", "?")
        return f"Decision recorded (memory #{mem_id}): {content}"
    return "Failed to record decision."


@mcp.tool()
def get_health() -> str:
    """Get the brain engine's health status.

    Returns memory count, edge count, service status, last learn time.
    Use this to verify the brain is operational.
    """
    data = _get("/api/brain/health")
    if not data:
        return "Brain health endpoint unavailable."

    status = data.get("status", "unknown")
    mems = data.get("memory_count", 0)
    edges = data.get("edge_count", 0)
    learn = data.get("learn_activity_24h", 0)
    last = data.get("last_memory_at", "never")
    services = data.get("services", {})
    issues = data.get("issues", [])

    lines = [f"## Brain Health: {status.upper()}"]
    lines.append(f"- Memories: {mems}")
    lines.append(f"- Graph edges: {edges}")
    lines.append(f"- Learn activity (24h): {learn}")
    lines.append(f"- Last memory: {last}")
    lines.append(f"- Services: web={services.get('web')} worker={services.get('worker')} beat={services.get('beat')}")
    if issues:
        lines.append(f"- Issues: {', '.join(issues)}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
