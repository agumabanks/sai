"""
Sanaa AI — Cross-service health monitoring for tenants.

Provides TenantHealthChecker that performs health checks per tenant type:
  - finance: HTTP GET to tenant URL, check for 200 response
  - ecommerce: HTTP GET to Soko URL, check for 200 response
  - email: Docker container status check for Mailcow containers

Used by:
  - GET /api/tenants/health (aggregated health)
  - GET /api/tenants/{id}/health (individual live check)
  - Celery periodic task (every 5 min) for background updates
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from core.database import Tenant, AsyncSessionLocal, utcnow
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Timeout for HTTP health checks (seconds)
HTTP_TIMEOUT = 10.0

# Key Mailcow containers to check for email health
MAILCOW_KEY_CONTAINERS = [
    "mailcowdockerized-postfix-mailcow-1",
    "mailcowdockerized-dovecot-mailcow-1",
    "mailcowdockerized-nginx-mailcow-1",
    "mailcowdockerized-redis-mailcow-1",
    "mailcowdockerized-mysql-mailcow-1",
    "mailcowdockerized-sogo-mailcow-1",
]


class TenantHealthChecker:
    """Cross-service health monitoring for tenants.

    Checks tenant health based on type:
      - finance/ecommerce: HTTP GET → 200 = healthy
      - email: Docker container status check for Mailcow
    """

    async def check_single_tenant(self, tenant_data: dict) -> dict:
        """Perform a live health check on a single tenant.

        Args:
            tenant_data: Dict with keys: id, name, type, url, status

        Returns:
            Dict with: tenant_id, name, type, status, health_score,
                       response_time_ms, checked_at, error (if any), skipped
        """
        tenant_id = tenant_data.get("id")
        name = tenant_data.get("name", "unknown")
        tenant_type = tenant_data.get("type", "other")
        url = tenant_data.get("url")
        current_status = tenant_data.get("status", "active")

        # Skip inactive tenants
        if current_status == "inactive":
            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": "inactive",
                "health_score": 0,
                "response_time_ms": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "skipped": True,
            }

        return await self._dispatch_check(tenant_data)

    async def check_single_tenant_forced(self, tenant_data: dict) -> dict:
        """Perform a live health check on a single tenant, ignoring status.

        Unlike check_single_tenant, this does NOT skip inactive tenants.
        Used by the POST /api/tenants/{id}/check endpoint to trigger
        immediate checks regardless of tenant state.

        Args:
            tenant_data: Dict with keys: id, name, type, url, status

        Returns:
            Dict with: tenant_id, name, type, status, health_score,
                       response_time_ms, checked_at, error (if any), skipped
        """
        return await self._dispatch_check(tenant_data)

    async def _dispatch_check(self, tenant_data: dict) -> dict:
        """Dispatch health check to the appropriate type-specific checker.

        Args:
            tenant_data: Dict with keys: id, name, type, url, status

        Returns:
            Health check result dict
        """
        tenant_id = tenant_data.get("id")
        name = tenant_data.get("name", "unknown")
        tenant_type = tenant_data.get("type", "other")
        url = tenant_data.get("url")

        # Dispatch to type-specific check
        if tenant_type in ("finance", "ecommerce"):
            return await self._check_http_tenant(tenant_data)
        elif tenant_type == "email":
            return await self._check_email_tenant(tenant_data)
        else:
            # Default: try HTTP check if URL is available
            if url:
                return await self._check_http_tenant(tenant_data)
            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": "degraded",
                "health_score": 50,
                "response_time_ms": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": "No URL configured and unknown tenant type",
                "skipped": False,
            }

    async def _check_http_tenant(self, tenant_data: dict) -> dict:
        """Check health via HTTP GET request (for finance and ecommerce tenants).

        Returns healthy (score=100) for 200 response, degraded (score=50) for
        non-200, down (score=0) for connection errors.
        """
        tenant_id = tenant_data.get("id")
        name = tenant_data.get("name", "unknown")
        tenant_type = tenant_data.get("type", "other")
        url = tenant_data.get("url")

        if not url:
            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": "degraded",
                "health_score": 50,
                "response_time_ms": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": "No URL configured",
                "skipped": False,
            }

        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT,
                follow_redirects=True,
                verify=False,  # Allow self-signed certs
            ) as client:
                response = await client.get(url)
                response_time_ms = round(response.elapsed.total_seconds() * 1000, 1)

                if response.status_code == 200:
                    return {
                        "tenant_id": tenant_id,
                        "name": name,
                        "type": tenant_type,
                        "status": "healthy",
                        "health_score": 100,
                        "response_time_ms": response_time_ms,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        "error": None,
                        "skipped": False,
                    }
                else:
                    return {
                        "tenant_id": tenant_id,
                        "name": name,
                        "type": tenant_type,
                        "status": "degraded",
                        "health_score": 50,
                        "response_time_ms": response_time_ms,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        "error": f"HTTP {response.status_code}",
                        "skipped": False,
                    }

        except httpx.TimeoutException:
            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": "degraded",
                "health_score": 25,
                "response_time_ms": HTTP_TIMEOUT * 1000,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": "Request timed out",
                "skipped": False,
            }
        except (httpx.ConnectError, httpx.RequestError) as e:
            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": "down",
                "health_score": 0,
                "response_time_ms": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "skipped": False,
            }
        except Exception as e:
            logger.error(f"Unexpected error checking tenant {name}: {e}")
            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": "down",
                "health_score": 0,
                "response_time_ms": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": f"Unexpected: {e}",
                "skipped": False,
            }

    async def _check_email_tenant(self, tenant_data: dict) -> dict:
        """Check Mailcow health via Docker container status.

        Checks key Mailcow containers (postfix, dovecot, nginx, redis, mysql, sogo).
        All running = healthy (100), some running = degraded (50), none = down (0).
        """
        tenant_id = tenant_data.get("id")
        name = tenant_data.get("name", "unknown")
        tenant_type = tenant_data.get("type", "email")

        try:
            # Use docker inspect to check container statuses
            # Build command: docker inspect --format '{{.State.Status}}' container1 container2 ...
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "--format", "{{.State.Status}}",
                *MAILCOW_KEY_CONTAINERS,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                # Docker command failed entirely
                error_msg = stderr.decode().strip() if stderr else "Docker inspect failed"
                return {
                    "tenant_id": tenant_id,
                    "name": name,
                    "type": tenant_type,
                    "status": "down",
                    "health_score": 0,
                    "response_time_ms": 0,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "error": error_msg,
                    "skipped": False,
                }

            statuses = stdout.decode().strip().split("\n")
            running_count = sum(1 for s in statuses if s.strip() == "running")
            total = len(MAILCOW_KEY_CONTAINERS)

            if running_count == total:
                status = "healthy"
                health_score = 100
            elif running_count > 0:
                status = "degraded"
                health_score = round((running_count / total) * 100, 1)
            else:
                status = "down"
                health_score = 0

            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": status,
                "health_score": health_score,
                "response_time_ms": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": None if status == "healthy" else f"{running_count}/{total} containers running",
                "skipped": False,
                "containers": {
                    "total": total,
                    "running": running_count,
                },
            }

        except Exception as e:
            logger.error(f"Error checking email tenant {name}: {e}")
            return {
                "tenant_id": tenant_id,
                "name": name,
                "type": tenant_type,
                "status": "down",
                "health_score": 0,
                "response_time_ms": 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "skipped": False,
            }

    def compute_overall_score(self, results: list[dict]) -> float:
        """Compute overall health score from individual tenant results.

        Calculates the average health_score across all non-skipped tenants.

        Args:
            results: List of health check result dicts with 'health_score' key

        Returns:
            Float 0.0 - 100.0 representing overall health
        """
        active_results = [r for r in results if not r.get("skipped")]
        if not active_results:
            return 100.0
        total = sum(r.get("health_score", 0) for r in active_results)
        return round(total / len(active_results), 1)

    def compute_overall_status(self, overall_score: float) -> str:
        """Determine overall status string from score.

        Args:
            overall_score: Float 0-100

        Returns:
            'healthy' (>=80), 'degraded' (>=30), or 'down' (<30)
        """
        if overall_score >= 80:
            return "healthy"
        elif overall_score >= 30:
            return "degraded"
        else:
            return "down"

    async def check_all_tenants(self) -> dict:
        """Check health of all active tenants and return aggregated result.

        Inactive tenants are excluded from polling — only active, degraded,
        and down tenants are checked. Disabling a tenant (status='inactive')
        stops it from being polled here.

        Returns:
            Dict with: overall_score, overall_status, tenants (list), checked_at
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Tenant).where(
                    Tenant.status != "inactive"
                ).order_by(Tenant.name)
            )
            tenants = result.scalars().all()

        # Build tenant data dicts
        tenant_dicts = []
        for t in tenants:
            tenant_dicts.append({
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "url": t.url,
                "status": t.status,
            })

        # Run health checks concurrently
        results = await asyncio.gather(
            *[self.check_single_tenant(td) for td in tenant_dicts],
            return_exceptions=True,
        )

        # Handle any exceptions that leaked through
        check_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"Health check exception for tenant {tenant_dicts[i]['name']}: {r}")
                check_results.append({
                    "tenant_id": tenant_dicts[i]["id"],
                    "name": tenant_dicts[i]["name"],
                    "type": tenant_dicts[i]["type"],
                    "status": "down",
                    "health_score": 0,
                    "response_time_ms": 0,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(r),
                    "skipped": False,
                })
            else:
                check_results.append(r)

        overall_score = self.compute_overall_score(check_results)
        overall_status = self.compute_overall_status(overall_score)

        return {
            "overall_score": overall_score,
            "overall_status": overall_status,
            "tenants": check_results,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "total_tenants": len(check_results),
            "active_tenants": len([r for r in check_results if not r.get("skipped")]),
        }

    async def update_tenant_health_in_db(self, check_result: dict) -> None:
        """Persist a health check result back to the Tenant row.

        Updates status, health_score, and last_checked for the tenant.
        """
        tenant_id = check_result.get("tenant_id")
        if not tenant_id or check_result.get("skipped"):
            return

        new_status = check_result.get("status", "down")
        health_score = check_result.get("health_score", 0)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalars().first()
            if not tenant:
                return

            tenant.status = new_status
            tenant.health_score = health_score
            tenant.last_checked = utcnow()
            tenant.updated_at = utcnow()
            await session.commit()

    async def handle_degradation_alert(self, check_result: dict) -> None:
        """Create an alert and send email notification when tenant health degrades.

        Called when a tenant's health status is 'degraded' or 'down'.
        Creates an Alert record associated with the tenant and sends an
        email notification to configured recipients via ReportAgent.
        """
        from core.database import Alert

        tenant_id = check_result.get("tenant_id")
        name = check_result.get("name", "unknown")
        status = check_result.get("status", "unknown")
        health_score = check_result.get("health_score", 0)
        error = check_result.get("error", "")

        if status not in ("degraded", "down"):
            return

        severity = "critical" if status == "down" else "high"
        title = f"Tenant {name} is {status}"
        message = (
            f"Tenant '{name}' health check detected {status} status.\n"
            f"Health score: {health_score}\n"
            f"Error: {error or 'N/A'}\n"
            f"Checked at: {check_result.get('checked_at', 'N/A')}"
        )

        try:
            await Alert.create(
                severity=severity,
                source=f"tenant_health:{name}",
                title=title,
                message=message,
                metric="health_score",
                tenant_id=tenant_id,
            )
            logger.info(f"[TenantHealth] Created {severity} alert for tenant '{name}' ({status})")
        except Exception as e:
            logger.error(f"[TenantHealth] Failed to create alert for tenant '{name}': {e}")

        # Send email notification via ReportAgent
        try:
            from core.agents.report_agent import ReportAgent
            reporter = ReportAgent()
            email_subject = f"[Sanaa AI] Tenant {status.upper()}: {name}"
            email_body = (
                f"TENANT HEALTH ALERT\n"
                f"{'=' * 40}\n\n"
                f"Tenant: {name}\n"
                f"Status: {status.upper()}\n"
                f"Severity: {severity.upper()}\n"
                f"Health Score: {health_score}/100\n"
                f"Error: {error or 'N/A'}\n"
                f"Checked at: {check_result.get('checked_at', 'N/A')}\n\n"
                f"Please investigate immediately."
            )
            await reporter.send_alert_email(email_subject, email_body)
            logger.info(f"[TenantHealth] Sent degradation email for tenant '{name}'")
        except Exception as e:
            logger.error(f"[TenantHealth] Failed to send degradation email for tenant '{name}': {e}")

    async def run_health_update_cycle(self) -> dict:
        """Run a full health check cycle: check all tenants and persist results.

        Called by the Celery periodic task (every 5 min).

        Returns:
            Aggregated health result dict
        """
        health_data = await self.check_all_tenants()

        # Persist results to DB and handle degradation alerts
        for tenant_result in health_data.get("tenants", []):
            try:
                await self.update_tenant_health_in_db(tenant_result)
            except Exception as e:
                logger.error(
                    f"Failed to update health for tenant "
                    f"{tenant_result.get('name', '?')}: {e}"
                )

            # Auto-create alert + email for degraded/down tenants
            try:
                await self.handle_degradation_alert(tenant_result)
            except Exception as e:
                logger.error(
                    f"Failed to handle degradation alert for tenant "
                    f"{tenant_result.get('name', '?')}: {e}"
                )

        logger.info(
            f"[TenantHealth] Cycle complete: "
            f"{health_data['active_tenants']}/{health_data['total_tenants']} active, "
            f"overall={health_data['overall_status']} ({health_data['overall_score']})"
        )

        return health_data
