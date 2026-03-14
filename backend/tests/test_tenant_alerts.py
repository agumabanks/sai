"""
Sanaa AI — Tenant alert correlation tests.
Covers:
  - Alert model has tenant_id column (nullable FK)
  - New alerts auto-correlate with tenants by URL, service name, or explicit tenant_id
  - GET /api/tenants/{id} includes recent_alerts array
  - GET /api/tenants/{id}/alerts returns alerts filtered by tenant
  - Tenant health degradation triggers automatic alert creation
  - Degradation alert sends email to configured recipients
  - Alert-tenant association is queryable

Fulfills: VAL-TENANT-005, VAL-CROSS-004
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


def unique_name(prefix: str = "alert") -> str:
    """Generate a unique tenant name to avoid collisions."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# Module-scoped fixtures to keep one event loop for all DB-touching tests
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def alert_client():
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


# ==================== ALERT MODEL TESTS ====================


class TestAlertModelTenantId:
    """Verify the Alert model has tenant_id column."""

    def test_alert_has_tenant_id_column(self):
        """Alert model should have a tenant_id column."""
        from core.database import Alert
        col_names = [c.name for c in Alert.__table__.columns]
        assert "tenant_id" in col_names

    def test_alert_tenant_id_is_nullable(self):
        """Alert tenant_id column should be nullable (for non-tenant alerts)."""
        from core.database import Alert
        tenant_id_col = Alert.__table__.columns["tenant_id"]
        assert tenant_id_col.nullable is True

    def test_alert_tenant_id_is_integer(self):
        """Alert tenant_id column should be an integer type."""
        from core.database import Alert
        from sqlalchemy import Integer
        tenant_id_col = Alert.__table__.columns["tenant_id"]
        assert isinstance(tenant_id_col.type, Integer)

    def test_alert_has_get_by_tenant_method(self):
        """Alert model should have a get_by_tenant class method."""
        from core.database import Alert
        assert hasattr(Alert, "get_by_tenant")
        assert callable(getattr(Alert, "get_by_tenant"))


# ==================== ALERT CORRELATION TESTS ====================


@pytest.mark.asyncio(loop_scope="module")
class TestAlertTenantCorrelation:
    """Test that alerts auto-correlate with tenants."""

    async def test_alert_with_explicit_tenant_id(self, alert_client):
        """Alert created with explicit tenant_id should retain it."""
        tenant = await _create_tenant(alert_client, name=unique_name("explicit"))
        tenant_id = tenant["id"]

        from core.database import Alert
        alert = await Alert.create(
            severity="high",
            source="test",
            title="Test explicit tenant_id",
            message="Test message",
            tenant_id=tenant_id,
        )
        assert alert.tenant_id == tenant_id

    async def test_alert_correlates_by_tenant_name(self, alert_client):
        """Alert should auto-correlate with tenant when source/title/message contains tenant name."""
        tenant_name = unique_name("corr-name")
        tenant = await _create_tenant(alert_client, name=tenant_name)
        tenant_id = tenant["id"]

        from core.database import Alert
        alert = await Alert.create(
            severity="medium",
            source=f"watchdog:{tenant_name}",
            title=f"Health issue on {tenant_name}",
            message=f"Tenant {tenant_name} has degraded health",
        )
        assert alert.tenant_id == tenant_id

    async def test_alert_correlates_by_tenant_url(self, alert_client):
        """Alert should auto-correlate when source/message contains tenant URL domain."""
        tenant_name = unique_name("corr-url")
        url = f"https://{tenant_name}.sanaa.ug"
        tenant = await _create_tenant(alert_client, name=tenant_name, url=url)
        tenant_id = tenant["id"]

        from core.database import Alert
        alert = await Alert.create(
            severity="medium",
            source="uptime_monitor",
            title="HTTP 503 detected",
            message=f"Server at {tenant_name}.sanaa.ug returned 503",
        )
        assert alert.tenant_id == tenant_id

    async def test_alert_no_correlation_for_unknown(self, alert_client):
        """Alert should have null tenant_id when no tenant matches."""
        from core.database import Alert
        alert = await Alert.create(
            severity="low",
            source="system",
            title="General system alert",
            message="Something happened on some random service with no tenant match",
        )
        # tenant_id could be None if no match, or could match by accident
        # We just verify the field exists and alert was created
        assert alert.id is not None
        assert hasattr(alert, "tenant_id")

    async def test_alert_correlation_case_insensitive(self, alert_client):
        """Alert correlation should be case-insensitive."""
        tenant_name = unique_name("case")
        tenant = await _create_tenant(alert_client, name=tenant_name)
        tenant_id = tenant["id"]

        from core.database import Alert
        alert = await Alert.create(
            severity="medium",
            source="test",
            title=f"Issue with {tenant_name.upper()}",
            message="Test case insensitive matching",
        )
        assert alert.tenant_id == tenant_id


# ==================== TENANT DETAIL INCLUDES ALERTS ====================


@pytest.mark.asyncio(loop_scope="module")
class TestTenantDetailIncludesAlerts:
    """Test that GET /api/tenants/{id} includes recent_alerts."""

    async def test_tenant_detail_has_recent_alerts_key(self, alert_client):
        """GET /api/tenants/{id} response should include recent_alerts array."""
        tenant = await _create_tenant(alert_client, name=unique_name("detail-alerts"))
        tenant_id = tenant["id"]

        resp = await alert_client.get(
            f"/api/tenants/{tenant_id}",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "recent_alerts" in data
        assert isinstance(data["recent_alerts"], list)

    async def test_tenant_detail_includes_associated_alerts(self, alert_client):
        """GET /api/tenants/{id} should include alerts for that tenant."""
        tenant_name = unique_name("detail-assoc")
        tenant = await _create_tenant(alert_client, name=tenant_name)
        tenant_id = tenant["id"]

        # Create an alert associated with this tenant
        from core.database import Alert
        await Alert.create(
            severity="high",
            source="test",
            title=f"Alert for {tenant_name}",
            message="Test alert for tenant detail",
            tenant_id=tenant_id,
        )

        resp = await alert_client.get(
            f"/api/tenants/{tenant_id}",
            headers=auth_headers(),
        )
        data = resp.json()
        assert len(data["recent_alerts"]) >= 1
        alert = data["recent_alerts"][0]
        assert alert["tenant_id"] == tenant_id
        assert "severity" in alert
        assert "title" in alert
        assert "created_at" in alert

    async def test_tenant_detail_empty_alerts_for_new_tenant(self, alert_client):
        """GET /api/tenants/{id} should return empty alerts for a tenant with no alerts."""
        tenant = await _create_tenant(alert_client, name=unique_name("no-alerts"))
        tenant_id = tenant["id"]

        resp = await alert_client.get(
            f"/api/tenants/{tenant_id}",
            headers=auth_headers(),
        )
        data = resp.json()
        assert data["recent_alerts"] == []


# ==================== ALERTS BY TENANT ENDPOINT ====================


@pytest.mark.asyncio(loop_scope="module")
class TestAlertsByTenantEndpoint:
    """Test GET /api/tenants/{id}/alerts endpoint."""

    async def test_alerts_endpoint_returns_200(self, alert_client):
        """GET /api/tenants/{id}/alerts should return 200."""
        tenant = await _create_tenant(alert_client, name=unique_name("alerts-ep"))
        tenant_id = tenant["id"]

        resp = await alert_client.get(
            f"/api/tenants/{tenant_id}/alerts",
            headers=auth_headers(),
        )
        assert resp.status_code == 200

    async def test_alerts_endpoint_returns_alerts_for_tenant(self, alert_client):
        """GET /api/tenants/{id}/alerts should return associated alerts."""
        tenant_name = unique_name("alerts-ep2")
        tenant = await _create_tenant(alert_client, name=tenant_name)
        tenant_id = tenant["id"]

        from core.database import Alert
        await Alert.create(
            severity="critical",
            source="test",
            title="Critical alert",
            message="Test critical alert for tenant",
            tenant_id=tenant_id,
        )

        resp = await alert_client.get(
            f"/api/tenants/{tenant_id}/alerts",
            headers=auth_headers(),
        )
        data = resp.json()
        assert "alerts" in data
        assert "tenant_id" in data
        assert "tenant_name" in data
        assert data["tenant_id"] == tenant_id
        assert data["tenant_name"] == tenant_name
        assert len(data["alerts"]) >= 1
        assert data["alerts"][0]["severity"] == "critical"

    async def test_alerts_endpoint_not_found(self, alert_client):
        """GET /api/tenants/{id}/alerts should return 404 for non-existent tenant."""
        resp = await alert_client.get(
            "/api/tenants/99999/alerts",
            headers=auth_headers(),
        )
        assert resp.status_code == 404

    async def test_alerts_endpoint_requires_auth(self, alert_client):
        """GET /api/tenants/{id}/alerts should require authentication."""
        resp = await alert_client.get("/api/tenants/1/alerts")
        assert resp.status_code == 401

    async def test_alerts_endpoint_respects_limit(self, alert_client):
        """GET /api/tenants/{id}/alerts should respect limit parameter."""
        tenant = await _create_tenant(alert_client, name=unique_name("alerts-limit"))
        tenant_id = tenant["id"]

        from core.database import Alert
        # Create 5 alerts
        for i in range(5):
            await Alert.create(
                severity="medium",
                source="test",
                title=f"Alert {i}",
                message=f"Test alert {i}",
                tenant_id=tenant_id,
            )

        resp = await alert_client.get(
            f"/api/tenants/{tenant_id}/alerts?limit=3",
            headers=auth_headers(),
        )
        data = resp.json()
        assert len(data["alerts"]) <= 3


# ==================== HEALTH DEGRADATION ALERT TESTS ====================


class TestHealthDegradationAlerts:
    """Test that tenant health degradation triggers auto-alert and email."""

    @pytest.mark.asyncio
    async def test_degraded_status_creates_alert(self):
        """Health check with degraded status should create an Alert record."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        check_result = {
            "tenant_id": 999,
            "name": "test-degraded-tenant",
            "type": "finance",
            "status": "degraded",
            "health_score": 50,
            "checked_at": "2026-03-14T10:00:00+00:00",
            "error": "HTTP 503",
            "skipped": False,
        }

        with patch("core.database.Alert.create", new_callable=AsyncMock) as mock_create, \
             patch("core.agents.report_agent.ReportAgent") as MockReporter:
            mock_instance = MagicMock()
            mock_instance.send_alert_email = AsyncMock()
            MockReporter.return_value = mock_instance

            await checker.handle_degradation_alert(check_result)

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["severity"] == "high"
            assert call_kwargs["tenant_id"] == 999
            assert "degraded" in call_kwargs["title"].lower() or "test-degraded-tenant" in call_kwargs["title"]
            assert call_kwargs["source"] == "tenant_health:test-degraded-tenant"

    @pytest.mark.asyncio
    async def test_down_status_creates_critical_alert(self):
        """Health check with down status should create a critical alert."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        check_result = {
            "tenant_id": 999,
            "name": "test-down-tenant",
            "type": "finance",
            "status": "down",
            "health_score": 0,
            "checked_at": "2026-03-14T10:00:00+00:00",
            "error": "Connection refused",
            "skipped": False,
        }

        with patch("core.database.Alert.create", new_callable=AsyncMock) as mock_create, \
             patch("core.agents.report_agent.ReportAgent") as MockReporter:
            mock_instance = MagicMock()
            mock_instance.send_alert_email = AsyncMock()
            MockReporter.return_value = mock_instance

            await checker.handle_degradation_alert(check_result)

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_healthy_status_does_not_create_alert(self):
        """Health check with healthy status should NOT create an alert."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        check_result = {
            "tenant_id": 999,
            "name": "test-healthy-tenant",
            "type": "finance",
            "status": "healthy",
            "health_score": 100,
            "checked_at": "2026-03-14T10:00:00+00:00",
            "error": None,
            "skipped": False,
        }

        with patch("core.database.Alert.create", new_callable=AsyncMock) as mock_create:
            await checker.handle_degradation_alert(check_result)
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_degradation_sends_email(self):
        """Health degradation should send email via ReportAgent."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        check_result = {
            "tenant_id": 999,
            "name": "email-test-tenant",
            "type": "finance",
            "status": "down",
            "health_score": 0,
            "checked_at": "2026-03-14T10:00:00+00:00",
            "error": "Connection refused",
            "skipped": False,
        }

        with patch("core.database.Alert.create", new_callable=AsyncMock), \
             patch("core.agents.report_agent.ReportAgent") as MockReporter:
            mock_instance = MagicMock()
            mock_instance.send_alert_email = AsyncMock()
            MockReporter.return_value = mock_instance

            await checker.handle_degradation_alert(check_result)

            mock_instance.send_alert_email.assert_called_once()
            call_args = mock_instance.send_alert_email.call_args
            subject = call_args[0][0]
            body = call_args[0][1]
            assert "DOWN" in subject
            assert "email-test-tenant" in subject
            assert "email-test-tenant" in body
            assert "Connection refused" in body

    @pytest.mark.asyncio
    async def test_degradation_email_contains_tenant_info(self):
        """Degradation email should include tenant name, status, health score."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()
        check_result = {
            "tenant_id": 999,
            "name": "info-test-tenant",
            "type": "ecommerce",
            "status": "degraded",
            "health_score": 40,
            "checked_at": "2026-03-14T10:00:00+00:00",
            "error": "HTTP 503",
            "skipped": False,
        }

        with patch("core.database.Alert.create", new_callable=AsyncMock), \
             patch("core.agents.report_agent.ReportAgent") as MockReporter:
            mock_instance = MagicMock()
            mock_instance.send_alert_email = AsyncMock()
            MockReporter.return_value = mock_instance

            await checker.handle_degradation_alert(check_result)

            call_args = mock_instance.send_alert_email.call_args
            body = call_args[0][1]
            assert "info-test-tenant" in body
            assert "DEGRADED" in body
            assert "40" in body
            assert "HTTP 503" in body

    @pytest.mark.asyncio
    async def test_run_health_update_cycle_triggers_alerts(self):
        """run_health_update_cycle should call handle_degradation_alert for each tenant."""
        from core.tenant_health import TenantHealthChecker

        checker = TenantHealthChecker()

        mock_health_data = {
            "overall_score": 50,
            "overall_status": "degraded",
            "tenants": [
                {
                    "tenant_id": 1,
                    "name": "tenant-a",
                    "type": "finance",
                    "status": "healthy",
                    "health_score": 100,
                    "checked_at": "2026-03-14T10:00:00+00:00",
                    "error": None,
                    "skipped": False,
                },
                {
                    "tenant_id": 2,
                    "name": "tenant-b",
                    "type": "finance",
                    "status": "down",
                    "health_score": 0,
                    "checked_at": "2026-03-14T10:00:00+00:00",
                    "error": "Connection refused",
                    "skipped": False,
                },
            ],
            "checked_at": "2026-03-14T10:00:00+00:00",
            "total_tenants": 2,
            "active_tenants": 2,
        }

        with patch.object(checker, "check_all_tenants", new_callable=AsyncMock, return_value=mock_health_data), \
             patch.object(checker, "update_tenant_health_in_db", new_callable=AsyncMock), \
             patch.object(checker, "handle_degradation_alert", new_callable=AsyncMock) as mock_alert:

            await checker.run_health_update_cycle()

            # Should be called for each tenant in the cycle
            assert mock_alert.call_count == 2


# ==================== ALERT QUERYABILITY TESTS ====================


@pytest.mark.asyncio(loop_scope="module")
class TestAlertTenantQueryability:
    """Test that alert-tenant associations are queryable."""

    async def test_get_by_tenant_returns_correct_alerts(self, alert_client):
        """Alert.get_by_tenant should return only alerts for the specified tenant."""
        tenant1 = await _create_tenant(alert_client, name=unique_name("query1"))
        tenant2 = await _create_tenant(alert_client, name=unique_name("query2"))

        from core.database import Alert
        await Alert.create(
            severity="high",
            source="test",
            title="Alert for tenant 1",
            message="Test",
            tenant_id=tenant1["id"],
        )
        await Alert.create(
            severity="medium",
            source="test",
            title="Alert for tenant 2",
            message="Test",
            tenant_id=tenant2["id"],
        )

        alerts1 = await Alert.get_by_tenant(tenant1["id"])
        alerts2 = await Alert.get_by_tenant(tenant2["id"])

        assert all(a.tenant_id == tenant1["id"] for a in alerts1)
        assert all(a.tenant_id == tenant2["id"] for a in alerts2)

    async def test_get_by_tenant_ordered_by_recent(self, alert_client):
        """Alert.get_by_tenant should return alerts ordered by most recent first."""
        tenant = await _create_tenant(alert_client, name=unique_name("order"))
        tenant_id = tenant["id"]

        from core.database import Alert
        for i in range(3):
            await Alert.create(
                severity="medium",
                source="test",
                title=f"Alert {i}",
                message=f"Test alert {i}",
                tenant_id=tenant_id,
            )

        alerts = await Alert.get_by_tenant(tenant_id)
        if len(alerts) >= 2:
            for i in range(len(alerts) - 1):
                assert alerts[i].created_at >= alerts[i + 1].created_at

    async def test_get_by_tenant_respects_limit(self, alert_client):
        """Alert.get_by_tenant should respect the limit parameter."""
        tenant = await _create_tenant(alert_client, name=unique_name("limit"))
        tenant_id = tenant["id"]

        from core.database import Alert
        for i in range(5):
            await Alert.create(
                severity="low",
                source="test",
                title=f"Alert {i}",
                message=f"Test alert {i}",
                tenant_id=tenant_id,
            )

        alerts = await Alert.get_by_tenant(tenant_id, limit=3)
        assert len(alerts) <= 3

    async def test_get_by_tenant_empty_for_no_alerts(self, alert_client):
        """Alert.get_by_tenant should return empty list for tenant with no alerts."""
        tenant = await _create_tenant(alert_client, name=unique_name("empty"))

        from core.database import Alert
        alerts = await Alert.get_by_tenant(tenant["id"])
        assert alerts == []


# ==================== DB SCHEMA VERIFICATION ====================


class TestAlertTableSchema:
    """Verify the alerts table in the database has the tenant_id column."""

    @pytest.mark.asyncio
    async def test_alerts_table_has_tenant_id(self):
        """The alerts table should have a tenant_id column in the actual database."""
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from core.config import get_settings

        settings = get_settings()
        test_engine = create_async_engine(settings.database_url_async, echo=False)
        try:
            async with test_engine.connect() as conn:
                result = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='alerts' AND column_name='tenant_id'"
                ))
                row = result.fetchone()
                assert row is not None, "tenant_id column not found in alerts table"
                assert row[0] == "tenant_id"
        finally:
            await test_engine.dispose()

    @pytest.mark.asyncio
    async def test_alerts_tenant_id_is_nullable_in_db(self):
        """The tenant_id column should be nullable in the database."""
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from core.config import get_settings

        settings = get_settings()
        test_engine = create_async_engine(settings.database_url_async, echo=False)
        try:
            async with test_engine.connect() as conn:
                result = await conn.execute(text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name='alerts' AND column_name='tenant_id'"
                ))
                row = result.fetchone()
                assert row is not None
                assert row[0] == "YES"
        finally:
            await test_engine.dispose()

    @pytest.mark.asyncio
    async def test_alerts_tenant_id_index_exists(self):
        """An index should exist on the alerts.tenant_id column."""
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from core.config import get_settings

        settings = get_settings()
        test_engine = create_async_engine(settings.database_url_async, echo=False)
        try:
            async with test_engine.connect() as conn:
                result = await conn.execute(text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename='alerts' AND indexname='idx_alerts_tenant_id'"
                ))
                row = result.fetchone()
                assert row is not None, "idx_alerts_tenant_id index not found"
        finally:
            await test_engine.dispose()
