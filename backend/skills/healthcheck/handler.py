"""Healthcheck — monitor external endpoints with a dynamic DB-backed registry."""
import time
import json
import logging
import httpx
from sqlalchemy import text
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal, Alert

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINTS = [
    {"name": "Sanaa AI", "url": "https://ai.sanaa.co/health", "timeout": 10},
    {"name": "Soko Marketplace", "url": "https://soko.sanaa.ug", "timeout": 10},
    {"name": "FX Platform", "url": "https://fx.sanaa.co", "timeout": 10},
    {"name": "Cards/Identity", "url": "https://cards.sanaa.ug", "timeout": 10},
    {"name": "WhatsApp SaaS", "url": "https://wa.sanaa.co", "timeout": 10},
    {"name": "Google DNS", "url": "https://dns.google", "timeout": 5},
]


class HealthcheckSkill(BaseSkill):
    name = "healthcheck"

    async def _check_url(self, url: str, timeout: int = 10) -> dict:
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "SanaaAI-Healthcheck/1.0"})
            latency = round((time.time() - start) * 1000)
            return {"url": url, "status": resp.status_code,
                    "latency_ms": latency, "ok": 200 <= resp.status_code < 400}
        except Exception as e:
            latency = round((time.time() - start) * 1000)
            return {"url": url, "status": 0, "latency_ms": latency,
                    "ok": False, "error": str(e)[:120]}

    async def _load_custom_endpoints(self) -> list[dict]:
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(text(
                    "SELECT value FROM system_knowledge WHERE domain = 'healthcheck_endpoints'"
                ))
                rows = res.scalars().all()
            return [json.loads(r) for r in rows]
        except Exception:
            return []

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "check_all")

        if action == "check_url":
            url = args.get("url")
            if not url:
                return SkillResult(success=False, error="'url' is required.")
            result = await self._check_url(url)
            status = "UP" if result["ok"] else "DOWN"
            return SkillResult(
                success=True,
                output=f"{url}: {status} (HTTP {result['status']}, {result['latency_ms']}ms)",
                data=result,
            )

        elif action == "check_all":
            custom = await self._load_custom_endpoints()
            all_endpoints = DEFAULT_ENDPOINTS + custom
            results = []
            for ep in all_endpoints:
                r = await self._check_url(ep["url"], ep.get("timeout", 10))
                r["name"] = ep.get("name", ep["url"])
                results.append(r)

            lines = []
            for r in results:
                icon = "✅" if r["ok"] else "❌"
                lines.append(f"{icon} {r['name']}: HTTP {r['status']} ({r['latency_ms']}ms)")
                if r.get("error"):
                    lines.append(f"   Error: {r['error']}")

            down = [r for r in results if not r["ok"]]
            summary = (
                f"\n{len(down)}/{len(results)} endpoints DOWN."
                if down else f"\nAll {len(results)} endpoints UP."
            )

            for r in down:
                try:
                    await Alert.create(
                        severity="warning",
                        message="Healthcheck: {} is DOWN ({})".format(r['name'], r.get('error', f"HTTP {r['status']}")),
                        metric=f"healthcheck.{r['name'].lower().replace(' ', '_')}",
                    )
                except Exception:
                    pass

            return SkillResult(
                success=True,
                output="\n".join(lines) + summary,
                data={"results": results, "down_count": len(down)},
            )

        elif action == "add_endpoint":
            url = args.get("url")
            name = args.get("name") or url
            timeout = int(args.get("timeout", 10))
            if not url:
                return SkillResult(success=False, error="'url' is required.")
            try:
                async with AsyncSessionLocal() as session:
                    await session.execute(text("""
                        INSERT INTO system_knowledge (domain, key, value, last_verified)
                        VALUES ('healthcheck_endpoints', :key, :val, NOW())
                        ON CONFLICT (domain, key) DO UPDATE SET value = :val
                    """), {
                        "key": f"ep.{url}",
                        "val": json.dumps({"name": name, "url": url, "timeout": timeout}),
                    })
                    await session.commit()
                return SkillResult(success=True, output=f"Added to healthcheck registry: {name} ({url})")
            except Exception as e:
                return SkillResult(success=False, error=str(e))

        elif action == "remove_endpoint":
            url = args.get("url")
            if not url:
                return SkillResult(success=False, error="'url' is required.")
            try:
                async with AsyncSessionLocal() as session:
                    await session.execute(text(
                        "DELETE FROM system_knowledge WHERE domain = 'healthcheck_endpoints' AND key = :key"
                    ), {"key": f"ep.{url}"})
                    await session.commit()
                return SkillResult(success=True, output=f"Removed from registry: {url}")
            except Exception as e:
                return SkillResult(success=False, error=str(e))

        elif action == "list_endpoints":
            custom = await self._load_custom_endpoints()
            lines = [f"Built-in ({len(DEFAULT_ENDPOINTS)}):"]
            for ep in DEFAULT_ENDPOINTS:
                lines.append(f"  • {ep['name']}: {ep['url']}")
            if custom:
                lines.append(f"\nCustom ({len(custom)}):")
                for ep in custom:
                    lines.append(f"  • {ep.get('name', ep['url'])}: {ep['url']}")
            else:
                lines.append("\nNo custom endpoints added yet.")
            return SkillResult(success=True, output="\n".join(lines))

        return SkillResult(success=False, error=f"Unknown action: {action}")
