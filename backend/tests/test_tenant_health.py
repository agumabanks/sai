"""
Sanaa AI — Tenant health monitoring tests.
Covers: TenantHealthChecker class, health check endpoints, Celery task registration.
Fulfills: VAL-TENANT-002, VAL-TENANT-003
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

# NOTE: patch targets use 'core.routes.tenants.TenantHealthChecker' because
# the import is lazy (inside the endpoint function body).


def auth_headers():
    """Return auth headers using the configured API key."""
    from core.config import get_settings
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.mac_client_api_key}"}


# ==================== TENANT HEALTH CHECKER UNIT TESTS ====================


class TestTenantHealthChecker:
    """Verify the TenantHealthChecker class functionality."""

    def test_importable(self):
        """TenantHealthChecker should be importable from core.tenant_health."""
        from core.tenant_health import TenantHealthChecker
        assert TenantHealthChecker is not None

    def test_instantiation(self):
        """TenantHealthChecker should be instantiable."""
        from core.tenant_health import TenantHealthChecker
        checker = TenantHealthChecker()
        assert checker is not None

    @pytest.mark.asyncio
    async def test_check_finance_tenant_healthy(self):
        """Finance tenant health check should use HTTP GET and report healthy on 200."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 0.3

        with patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_single_tenant({
                "id": 1,
                "name": "finance.sanaa.ug",
                "type": "finance",
                "url": "https://finance.sanaa.ug",
                "status": "active",
            })

            assert result["status"] == "healthy"
            assert result["response_time_ms"] > 0

    @pytest.mark.asyncio
    async def test_check_finance_tenant_down(self):
        """Finance tenant returns 'down' when HTTP request fails."""
        from core.tenant_health import TenantHealthChecker
        import httpx

        checker = TenantHealthChecker()

        with patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_single_tenant({
                "id": 1,
                "name": "finance.sanaa.ug",
                "type": "finance",
                "url": "https://finance.sanaa.ug",
                "status": "active",
            })

            assert result["status"] in ("down", "degraded")

    @pytest.mark.asyncio
    async def test_check_ecommerce_tenant_healthy(self):
        """Ecommerce (Soko) health check uses HTTP GET."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 0.5

        with patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_single_tenant({
                "id": 4,
                "name": "soko",
                "type": "ecommerce",
                "url": "https://soko.sanaa.ug",
                "status": "active",
            })

            assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_check_email_tenant_healthy(self):
        """Email (Mailcow) health check uses Docker container status."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()

        # Mock subprocess to return docker container statuses
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "running\nrunning\nrunning\n"

        with patch("core.tenant_health.asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"running\nrunning\nrunning\n",
                b"",
            )
            mock_proc.returncode = 0
            mock_subprocess.return_value = mock_proc

            result = await checker.check_single_tenant({
                "id": 5,
                "name": "mailcow",
                "type": "email",
                "url": "https://mail.sanaa.ug",
                "status": "active",
            })

            assert result["status"] in ("healthy", "degraded")

    @pytest.mark.asyncio
    async def test_check_email_tenant_down(self):
        """Email (Mailcow) reports 'down' when Docker check fails."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()

        with patch("core.tenant_health.asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"error")
            mock_proc.returncode = 1
            mock_subprocess.return_value = mock_proc

            result = await checker.check_single_tenant({
                "id": 5,
                "name": "mailcow",
                "type": "email",
                "url": "https://mail.sanaa.ug",
                "status": "active",
            })

            assert result["status"] in ("down", "degraded")

    @pytest.mark.asyncio
    async def test_check_skips_inactive_tenants(self):
        """Inactive tenants should be skipped during health checks."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        result = await checker.check_single_tenant({
            "id": 1,
            "name": "disabled-tenant",
            "type": "finance",
            "url": "https://disabled.example.com",
            "status": "inactive",
        })

        assert result["status"] == "inactive"
        assert result.get("skipped") is True

    @pytest.mark.asyncio
    async def test_health_score_calculation_all_healthy(self):
        """Overall health score should be 100 when all tenants are healthy."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        results = [
            {"tenant_id": 1, "status": "healthy", "health_score": 100},
            {"tenant_id": 2, "status": "healthy", "health_score": 100},
            {"tenant_id": 3, "status": "healthy", "health_score": 100},
        ]
        overall = checker.compute_overall_score(results)
        assert overall == 100.0

    @pytest.mark.asyncio
    async def test_health_score_calculation_mixed(self):
        """Overall health score should reflect mix of healthy and degraded tenants."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        results = [
            {"tenant_id": 1, "status": "healthy", "health_score": 100},
            {"tenant_id": 2, "status": "degraded", "health_score": 50},
            {"tenant_id": 3, "status": "down", "health_score": 0},
        ]
        overall = checker.compute_overall_score(results)
        assert overall == 50.0

    @pytest.mark.asyncio
    async def test_degraded_status_on_slow_response(self):
        """Finance tenant should be 'degraded' on non-200 status code."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 1.0

        with patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_single_tenant({
                "id": 1,
                "name": "finance.sanaa.ug",
                "type": "finance",
                "url": "https://finance.sanaa.ug",
                "status": "active",
            })

            assert result["status"] == "degraded"


# ==================== API ENDPOINT TESTS ====================


class TestHealthMonitoringEndpoints:
    """Test the health monitoring API endpoints.

    Uses mocked TenantHealthChecker to avoid asyncpg event loop conflicts
    when running under httpx's ASGI transport in tests.
    """

    MOCK_AGGREGATED = {
        "overall_score": 83.3,
        "overall_status": "healthy",
        "tenants": [
            {
                "tenant_id": 1,
                "id": 1,
                "name": "finance.sanaa.ug",
                "type": "finance",
                "status": "healthy",
                "health_score": 100,
                "response_time_ms": 250,
                "checked_at": "2026-03-14T10:00:00+00:00",
                "error": None,
                "skipped": False,
            },
            {
                "tenant_id": 2,
                "id": 2,
                "name": "soko",
                "type": "ecommerce",
                "status": "healthy",
                "health_score": 100,
                "response_time_ms": 300,
                "checked_at": "2026-03-14T10:00:00+00:00",
                "error": None,
                "skipped": False,
            },
            {
                "tenant_id": 3,
                "id": 3,
                "name": "mailcow",
                "type": "email",
                "status": "degraded",
                "health_score": 50,
                "response_time_ms": 0,
                "checked_at": "2026-03-14T10:00:00+00:00",
                "error": "4/6 containers running",
                "skipped": False,
            },
        ],
        "checked_at": "2026-03-14T10:00:00+00:00",
        "total_tenants": 3,
        "active_tenants": 3,
    }

    MOCK_INDIVIDUAL = {
        "tenant_id": 1,
        "name": "finance.sanaa.ug",
        "type": "finance",
        "status": "healthy",
        "health_score": 100,
        "response_time_ms": 200,
        "checked_at": "2026-03-14T10:00:00+00:00",
        "error": None,
        "skipped": False,
    }

    async def test_aggregated_health_endpoint_exists(self, client):
        """GET /api/tenants/health should return 200."""
        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_all_tenants = AsyncMock(return_value=self.MOCK_AGGREGATED)
            resp = await client.get(
                "/api/tenants/health",
                headers=auth_headers(),
            )
            assert resp.status_code == 200

    async def test_aggregated_health_returns_overall_score(self, client):
        """GET /api/tenants/health should include overall_score."""
        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_all_tenants = AsyncMock(return_value=self.MOCK_AGGREGATED)
            resp = await client.get(
                "/api/tenants/health",
                headers=auth_headers(),
            )
            data = resp.json()
            assert "overall_score" in data
            assert isinstance(data["overall_score"], (int, float))
            assert 0 <= data["overall_score"] <= 100

    async def test_aggregated_health_returns_overall_status(self, client):
        """GET /api/tenants/health should include overall_status."""
        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_all_tenants = AsyncMock(return_value=self.MOCK_AGGREGATED)
            resp = await client.get(
                "/api/tenants/health",
                headers=auth_headers(),
            )
            data = resp.json()
            assert "overall_status" in data
            assert data["overall_status"] in ("healthy", "degraded", "down")

    async def test_aggregated_health_returns_tenant_breakdown(self, client):
        """GET /api/tenants/health should include per-tenant breakdown."""
        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_all_tenants = AsyncMock(return_value=self.MOCK_AGGREGATED)
            resp = await client.get(
                "/api/tenants/health",
                headers=auth_headers(),
            )
            data = resp.json()
            assert "tenants" in data
            assert isinstance(data["tenants"], list)
            assert len(data["tenants"]) > 0
            # Each tenant entry should have expected fields
            tenant = data["tenants"][0]
            assert "name" in tenant
            assert "type" in tenant
            assert "status" in tenant
            assert "health_score" in tenant

    async def test_aggregated_health_returns_checked_at(self, client):
        """GET /api/tenants/health should include checked_at timestamp."""
        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_all_tenants = AsyncMock(return_value=self.MOCK_AGGREGATED)
            resp = await client.get(
                "/api/tenants/health",
                headers=auth_headers(),
            )
            data = resp.json()
            assert "checked_at" in data

    async def test_individual_health_endpoint_returns_200(self, client):
        """GET /api/tenants/{id}/health should return 200 for valid tenant."""
        from core.database import Tenant

        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = 1
        mock_tenant.name = "finance.sanaa.ug"
        mock_tenant.type = "finance"
        mock_tenant.url = "https://finance.sanaa.ug"
        mock_tenant.status = "active"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_tenant

        with patch("core.routes.tenants.AsyncSessionLocal") as MockSession, \
             patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_session

            instance = MockChecker.return_value
            instance.check_single_tenant = AsyncMock(return_value=self.MOCK_INDIVIDUAL)
            instance.update_tenant_health_in_db = AsyncMock()

            resp = await client.get(
                "/api/tenants/1/health",
                headers=auth_headers(),
            )
            assert resp.status_code == 200

    async def test_individual_health_returns_live_check(self, client):
        """GET /api/tenants/{id}/health should return live health check result."""
        from core.database import Tenant

        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = 1
        mock_tenant.name = "finance.sanaa.ug"
        mock_tenant.type = "finance"
        mock_tenant.url = "https://finance.sanaa.ug"
        mock_tenant.status = "active"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_tenant

        with patch("core.routes.tenants.AsyncSessionLocal") as MockSession, \
             patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_session

            instance = MockChecker.return_value
            instance.check_single_tenant = AsyncMock(return_value=self.MOCK_INDIVIDUAL)
            instance.update_tenant_health_in_db = AsyncMock()

            resp = await client.get(
                "/api/tenants/1/health",
                headers=auth_headers(),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "status" in data
            assert data["status"] in ("healthy", "degraded", "down", "inactive")
            assert "name" in data
            assert "checked_at" in data

    async def test_individual_health_not_found(self, client):
        """GET /api/tenants/{id}/health should return 404 for non-existent tenant."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        with patch("core.routes.tenants.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_session

            resp = await client.get(
                "/api/tenants/99999/health",
                headers=auth_headers(),
            )
            assert resp.status_code == 404

    async def test_individual_health_calls_checker(self, client):
        """GET /api/tenants/{id}/health should invoke TenantHealthChecker."""
        from core.database import Tenant

        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = 1
        mock_tenant.name = "finance.sanaa.ug"
        mock_tenant.type = "finance"
        mock_tenant.url = "https://finance.sanaa.ug"
        mock_tenant.status = "active"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_tenant

        with patch("core.routes.tenants.AsyncSessionLocal") as MockSession, \
             patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_session

            instance = MockChecker.return_value
            instance.check_single_tenant = AsyncMock(return_value=self.MOCK_INDIVIDUAL)
            instance.update_tenant_health_in_db = AsyncMock()

            resp = await client.get(
                "/api/tenants/1/health",
                headers=auth_headers(),
            )
            assert resp.status_code == 200
            instance.check_single_tenant.assert_called_once()
            instance.update_tenant_health_in_db.assert_called_once()

    async def test_aggregated_health_requires_auth(self, client):
        """GET /api/tenants/health should require authentication."""
        resp = await client.get("/api/tenants/health")
        assert resp.status_code == 401

    async def test_individual_health_requires_auth(self, client):
        """GET /api/tenants/{id}/health should require authentication."""
        resp = await client.get("/api/tenants/1/health")
        assert resp.status_code == 401


# ==================== CELERY TASK TESTS ====================


class TestHealthMonitoringCeleryTask:
    """Test Celery periodic task registration for health updates."""

    def test_celery_task_registered(self):
        """tenant_health_update task should be registered in beat_schedule."""
        from core.tasks import app as celery_app
        assert "tenant-health-update" in celery_app.conf.beat_schedule

    def test_celery_task_schedule(self):
        """tenant_health_update should run every 5 minutes (300 seconds)."""
        from core.tasks import app as celery_app
        schedule = celery_app.conf.beat_schedule["tenant-health-update"]
        assert schedule["schedule"] == 300

    def test_celery_task_function_exists(self):
        """The update_tenant_health task function should be importable."""
        from core.tasks import update_tenant_health
        assert callable(update_tenant_health)


# ==================== HEALTH STATUS MAPPING TESTS ====================


class TestHealthStatusMapping:
    """Test that health check results correctly map to status values."""

    @pytest.mark.asyncio
    async def test_healthy_maps_to_100_score(self):
        """A healthy check should produce health_score of 100."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 0.2

        with patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_single_tenant({
                "id": 1,
                "name": "test",
                "type": "finance",
                "url": "https://test.com",
                "status": "active",
            })

            assert result["health_score"] == 100

    @pytest.mark.asyncio
    async def test_degraded_maps_to_50_score(self):
        """A degraded check (non-200 response) should produce health_score of 50."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 1.0

        with patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_single_tenant({
                "id": 1,
                "name": "test",
                "type": "finance",
                "url": "https://test.com",
                "status": "active",
            })

            assert result["health_score"] == 50

    @pytest.mark.asyncio
    async def test_down_maps_to_0_score(self):
        """A down check (connection error) should produce health_score of 0."""
        from core.tenant_health import TenantHealthChecker
        import httpx

        checker = TenantHealthChecker()

        with patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_single_tenant({
                "id": 1,
                "name": "test",
                "type": "finance",
                "url": "https://test.com",
                "status": "active",
            })

            assert result["health_score"] == 0
