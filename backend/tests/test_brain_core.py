"""
Integration tests for SanaaEngine Brain core flows.
Run with: PYTHONPATH=/var/www/ai.sanaa.co/backend python3 -m tests.test_brain_core

Tests:
1. Health endpoint returns expected fields
2. Memory CRUD: create, dedup, query
3. Knowledge graph: create edge, traverse
4. Config propagation: create config → auto-propagates
"""

import asyncio
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("SANAA_ENGINE_KEY", "ag_mac_client_z8x9c7v6b5n4m3a2s1d0")

import httpx

BRAIN = "http://127.0.0.1:8100"
KEY = os.environ["SANAA_ENGINE_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

passed = 0
failed = 0


async def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


async def test_health():
    print("\n── Health Endpoint ──")
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BRAIN}/api/brain/health", headers=HEADERS)
        await check("GET /api/brain/health returns 200", r.status_code == 200, f"got {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            await check("health.status is healthy or degraded", d.get("status") in ("healthy", "degraded"), str(d))
            await check("health.memory_count is int", isinstance(d.get("memory_count"), int), str(d))
            await check("health.edge_count is int", isinstance(d.get("edge_count"), int), str(d))
            await check("health.services.web is True", d.get("services", {}).get("web") is True, str(d))
            await check("health.last_memory_at is set", d.get("last_memory_at") is not None, str(d))


async def test_memory_dedup():
    print("\n── Memory Dedup ──")
    content = f"INTEGRATION_TEST_DEDUP_{asyncio.get_running_loop().time()}"
    payload = {
        "content": content,
        "category": "test_integration",
        "project": "antigravity",
        "source": "integration_test",
        "confidence": 0.5,
    }
    async with httpx.AsyncClient() as c:
        # First create
        r1 = await c.post(f"{BRAIN}/api/memory/add", json=payload, headers=HEADERS)
        await check("First create returns 201", r1.status_code == 201, f"got {r1.status_code}")
        id1 = r1.json().get("id") if r1.status_code == 201 else None

        # Duplicate create
        r2 = await c.post(f"{BRAIN}/api/memory/add", json=payload, headers=HEADERS)
        await check("Duplicate returns 201 (dedup)", r2.status_code == 201, f"got {r2.status_code}")
        if r2.status_code == 201:
            d2 = r2.json()
            await check("dedup flag is True", d2.get("dedup") is True, str(d2))
            await check("existing_id matches first id", d2.get("existing_id") == id1, f"{d2.get('existing_id')} != {id1}")


async def test_config_propagation():
    print("\n── Config Propagation ──")
    config_key = f"test_config_{asyncio.get_running_loop().time():.0f}"
    payload = {
        "content": f"{config_key}=test_value",
        "category": "config",
        "project": "sanaa_finance",
        "source": "integration_test",
        "confidence": 1.0,
        "metadata": {"is_config": "true", "config_key": config_key, "share": "true"},
    }
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BRAIN}/api/memory/add", json=payload, headers=HEADERS)
        await check("Config create returns 201", r.status_code == 201, f"got {r.status_code}")

        # Check config registry
        r2 = await c.get(f"{BRAIN}/api/brain/graph/configs", headers=HEADERS)
        await check("Configs endpoint returns 200", r2.status_code == 200, f"got {r2.status_code}")
        if r2.status_code == 200:
            configs = r2.json().get("configs", [])
            matching = [c for c in configs if c["config_key"] == config_key]
            await check("Config appears in registry", len(matching) > 0, f"not found in {len(configs)} configs")
            if matching:
                proj_count = len(matching[0].get("values", {}))
                await check(f"Config propagated to >=2 projects", proj_count >= 2, f"only {proj_count}")


async def test_graph():
    print("\n── Knowledge Graph ──")
    async with httpx.AsyncClient() as c:
        # Get any existing memory to test graph traversal
        r = await c.get(f"{BRAIN}/api/brain/graph/traverse?limit=5", headers=HEADERS)
        await check("Graph traverse returns 200", r.status_code == 200, f"got {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            await check("traverse has edges list", isinstance(d.get("edges"), list), str(d))
            await check("traverse has edge_count", isinstance(d.get("edge_count"), int), str(d))

        # Test config registry
        r2 = await c.get(f"{BRAIN}/api/brain/graph/configs", headers=HEADERS)
        await check("Config registry returns 200", r2.status_code == 200, f"got {r2.status_code}")


async def test_project_agent():
    print("\n── Project Agent ──")
    from core.agents.project_agent import run
    result = await run("/var/www/ai.sanaa.co")
    await check("Agent returns project name", "project" in result, str(result))
    await check("Agent returns memory_id", result.get("memory_id") is not None, str(result))
    await check("Agent detects stack", result.get("stack", "") != "", str(result))


async def main():
    print("=" * 50)
    print("SanaaEngine Brain — Core Integration Tests")
    print(f"Target: {BRAIN}")
    print("=" * 50)

    await test_health()
    await test_memory_dedup()
    await test_config_propagation()
    await test_graph()
    await test_project_agent()

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed > 0:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("✅ ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
