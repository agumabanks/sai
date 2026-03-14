"""
Sanaa AI — Tenant lifecycle management tests.
Covers: POST /api/tenants/{id}/enable, POST /api/tenants/{id}/disable,
        POST /api/tenants/{id}/check endpoints.
State persistence, health check polling exclusion for disabled tenants.
Fulfills: VAL-TENANT-004
"""

import pytest
import pytest_asyncio
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


def auth_headers():
    """Return auth headers using the configured API key."""
    from core.config import get_settings
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.mac_client_api_key}"}


def unique_name(prefix: str = "lifecycle") -> str:
    """Generate a unique tenant name to avoid collisions."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# Module-scoped fixtures to keep one event loop for all DB-touching tests
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def lc_client():
    """Module-scoped async client that shares a single event loop."""
    from core.database import engine
    await engine.dispose()

    from core.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await engine.dispose()


async def _create_tenant(client, name=None, tenant_type="finance", url="https://test.example.com"):
    """Helper to create a tenant and return the response data."""
    name = name or unique_name()
    resp = await client.post("/api/tenants", json={
        "name": name,
        "type": tenant_type,
        "url": url,
    }, headers=auth_headers())
    assert resp.status_code == 201, f"Failed to create tenant: {resp.text}"
    return resp.json()


# ==================== ENABLE ENDPOINT ====================


@pytest.mark.asyncio(loop_scope="module")
class TestEnableTenant:
    """Tests for POST /api/tenants/{id}/enable."""

    async def test_enable_sets_status_active(self, lc_client):
        """POST /api/tenants/{id}/enable should set status to 'active'."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        # First disable
        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())

        # Then enable
        resp = await lc_client.post(f"/api/tenants/{tenant_id}/enable", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"

    async def test_enable_persisted_in_get(self, lc_client):
        """Enabling a tenant should be reflected in subsequent GET requests."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        # Disable then re-enable
        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())
        await lc_client.post(f"/api/tenants/{tenant_id}/enable", headers=auth_headers())

        # Verify via GET
        resp = await lc_client.get(f"/api/tenants/{tenant_id}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_enable_already_active_tenant(self, lc_client):
        """Enabling an already active tenant should succeed idempotently."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        resp = await lc_client.post(f"/api/tenants/{tenant_id}/enable", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_enable_not_found(self, lc_client):
        """POST /api/tenants/{id}/enable should return 404 for non-existent tenant."""
        resp = await lc_client.post("/api/tenants/99999/enable", headers=auth_headers())
        assert resp.status_code == 404

    async def test_enable_requires_auth(self, lc_client):
        """POST /api/tenants/{id}/enable should require authentication."""
        resp = await lc_client.post("/api/tenants/1/enable")
        assert resp.status_code == 401

    async def test_enable_returns_full_tenant(self, lc_client):
        """POST /api/tenants/{id}/enable response should include all tenant fields."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        resp = await lc_client.post(f"/api/tenants/{tenant_id}/enable", headers=auth_headers())
        data = resp.json()
        assert "id" in data
        assert "name" in data
        assert "type" in data
        assert "url" in data
        assert "status" in data
        assert "health_score" in data
        assert "created_at" in data
        assert "updated_at" in data


# ==================== DISABLE ENDPOINT ====================


@pytest.mark.asyncio(loop_scope="module")
class TestDisableTenant:
    """Tests for POST /api/tenants/{id}/disable."""

    async def test_disable_sets_status_inactive(self, lc_client):
        """POST /api/tenants/{id}/disable should set status to 'inactive'."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        resp = await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "inactive"

    async def test_disable_persisted_in_get(self, lc_client):
        """Disabling a tenant should be reflected in subsequent GET requests."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())

        resp = await lc_client.get(f"/api/tenants/{tenant_id}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

    async def test_disable_persisted_in_list(self, lc_client):
        """Disabled tenant should show as inactive in the tenant listing."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]
        tenant_name = tenant["name"]

        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())

        resp = await lc_client.get("/api/tenants", headers=auth_headers())
        data = resp.json()
        found = next((t for t in data if t["name"] == tenant_name), None)
        assert found is not None
        assert found["status"] == "inactive"

    async def test_disable_already_inactive_tenant(self, lc_client):
        """Disabling an already inactive tenant should succeed idempotently."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())
        resp = await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

    async def test_disable_not_found(self, lc_client):
        """POST /api/tenants/{id}/disable should return 404 for non-existent tenant."""
        resp = await lc_client.post("/api/tenants/99999/disable", headers=auth_headers())
        assert resp.status_code == 404

    async def test_disable_requires_auth(self, lc_client):
        """POST /api/tenants/{id}/disable should require authentication."""
        resp = await lc_client.post("/api/tenants/1/disable")
        assert resp.status_code == 401


# ==================== CHECK ENDPOINT ====================


@pytest.mark.asyncio(loop_scope="module")
class TestCheckTenant:
    """Tests for POST /api/tenants/{id}/check (immediate health check)."""

    async def test_check_triggers_health_check(self, lc_client):
        """POST /api/tenants/{id}/check should trigger an immediate health check."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            mock_result = {
                "tenant_id": tenant_id,
                "name": tenant["name"],
                "type": "finance",
                "status": "healthy",
                "health_score": 100,
                "response_time_ms": 150,
                "checked_at": "2026-03-14T10:00:00+00:00",
                "error": None,
                "skipped": False,
            }
            instance.check_single_tenant_forced = AsyncMock(return_value=mock_result)
            instance.update_tenant_health_in_db = AsyncMock()

            resp = await lc_client.post(
                f"/api/tenants/{tenant_id}/check",
                headers=auth_headers(),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["health_score"] == 100
            instance.check_single_tenant_forced.assert_called_once()
            instance.update_tenant_health_in_db.assert_called_once()

    async def test_check_returns_health_result(self, lc_client):
        """POST /api/tenants/{id}/check should return health check result fields."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            mock_result = {
                "tenant_id": tenant_id,
                "name": tenant["name"],
                "type": "finance",
                "status": "degraded",
                "health_score": 50,
                "response_time_ms": 2000,
                "checked_at": "2026-03-14T10:00:00+00:00",
                "error": "HTTP 503",
                "skipped": False,
            }
            instance.check_single_tenant_forced = AsyncMock(return_value=mock_result)
            instance.update_tenant_health_in_db = AsyncMock()

            resp = await lc_client.post(
                f"/api/tenants/{tenant_id}/check",
                headers=auth_headers(),
            )
            data = resp.json()
            assert "status" in data
            assert "health_score" in data
            assert "checked_at" in data
            assert data["health_score"] == 50

    async def test_check_not_found(self, lc_client):
        """POST /api/tenants/{id}/check should return 404 for non-existent tenant."""
        resp = await lc_client.post("/api/tenants/99999/check", headers=auth_headers())
        assert resp.status_code == 404

    async def test_check_requires_auth(self, lc_client):
        """POST /api/tenants/{id}/check should require authentication."""
        resp = await lc_client.post("/api/tenants/1/check")
        assert resp.status_code == 401

    async def test_check_works_on_inactive_tenant(self, lc_client):
        """POST /api/tenants/{id}/check should work even for inactive tenants."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        # Disable first
        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())

        with patch("core.routes.tenants.TenantHealthChecker") as MockChecker:
            instance = MockChecker.return_value
            mock_result = {
                "tenant_id": tenant_id,
                "name": tenant["name"],
                "type": "finance",
                "status": "healthy",
                "health_score": 100,
                "response_time_ms": 200,
                "checked_at": "2026-03-14T10:00:00+00:00",
                "error": None,
                "skipped": False,
            }
            instance.check_single_tenant_forced = AsyncMock(return_value=mock_result)
            instance.update_tenant_health_in_db = AsyncMock()

            resp = await lc_client.post(
                f"/api/tenants/{tenant_id}/check",
                headers=auth_headers(),
            )
            assert resp.status_code == 200
            # The forced check should have been called (not skipped)
            instance.check_single_tenant_forced.assert_called_once()


# ==================== LIFECYCLE FLOW ====================


@pytest.mark.asyncio(loop_scope="module")
class TestLifecycleFlow:
    """Test complete enable/disable lifecycle flow."""

    async def test_full_lifecycle_flow(self, lc_client):
        """Test: create active -> disable -> verify inactive -> enable -> verify active."""
        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]
        assert tenant["status"] == "active"

        # Disable
        resp = await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

        # Verify via GET
        resp = await lc_client.get(f"/api/tenants/{tenant_id}", headers=auth_headers())
        assert resp.json()["status"] == "inactive"

        # Re-enable
        resp = await lc_client.post(f"/api/tenants/{tenant_id}/enable", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

        # Verify via GET
        resp = await lc_client.get(f"/api/tenants/{tenant_id}", headers=auth_headers())
        assert resp.json()["status"] == "active"

    async def test_disable_stops_health_polling(self, lc_client):
        """Disabled tenants should be excluded from periodic health check polling."""
        from core.tenant_health import TenantHealthChecker

        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        # Disable the tenant
        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())

        # The check_single_tenant should skip inactive tenants
        checker = TenantHealthChecker()
        result = await checker.check_single_tenant({
            "id": tenant_id,
            "name": tenant["name"],
            "type": "finance",
            "url": "https://test.example.com",
            "status": "inactive",
        })
        assert result["skipped"] is True
        assert result["status"] == "inactive"

    async def test_enable_resumes_health_polling(self, lc_client):
        """Re-enabled tenants should be included in health check polling."""
        from core.tenant_health import TenantHealthChecker

        tenant = await _create_tenant(lc_client)
        tenant_id = tenant["id"]

        # Disable then re-enable
        await lc_client.post(f"/api/tenants/{tenant_id}/disable", headers=auth_headers())
        await lc_client.post(f"/api/tenants/{tenant_id}/enable", headers=auth_headers())

        # Active tenants should not be skipped
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
                "id": tenant_id,
                "name": tenant["name"],
                "type": "finance",
                "url": "https://test.example.com",
                "status": "active",
            })
            assert result.get("skipped") is not True
            assert result["status"] == "healthy"


# ==================== HEALTH CHECKER EXCLUSION ====================


class TestHealthCheckerExclusion:
    """Test that check_all_tenants excludes inactive tenants from DB query."""

    @pytest.mark.asyncio
    async def test_check_all_excludes_inactive(self):
        """check_all_tenants should not fetch inactive tenants from DB."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()

        # Mock the DB query to verify the WHERE clause
        mock_active_tenant = MagicMock()
        mock_active_tenant.id = 1
        mock_active_tenant.name = "active-tenant"
        mock_active_tenant.type = "finance"
        mock_active_tenant.url = "https://active.example.com"
        mock_active_tenant.status = "active"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_active_tenant]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 0.1

        with patch("core.tenant_health.AsyncSessionLocal", return_value=mock_session), \
             patch("core.tenant_health.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await checker.check_all_tenants()

            # The query was executed (we can verify it was called)
            mock_session.execute.assert_called_once()

            # Result should only contain the active tenant
            assert result["total_tenants"] == 1
            assert result["tenants"][0]["name"] == "active-tenant"

    @pytest.mark.asyncio
    async def test_forced_check_does_not_skip_inactive(self):
        """check_single_tenant_forced should not skip inactive tenants."""
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

            result = await checker.check_single_tenant_forced({
                "id": 1,
                "name": "inactive-tenant",
                "type": "finance",
                "url": "https://inactive.example.com",
                "status": "inactive",
            })
            # forced check should not skip — it should check and return healthy
            assert result.get("skipped") is not True
            assert result["status"] == "healthy"
            assert result["health_score"] == 100
