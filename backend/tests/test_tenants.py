"""
Sanaa AI — Tenant data model and CRUD API tests.
Covers: Tenant model fields, CRUD endpoints, soft-delete, seeding.
"""

import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport


def auth_headers():
    """Return auth headers using the configured API key."""
    from core.config import get_settings
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.mac_client_api_key}"}


def unique_name(prefix: str = "test") -> str:
    """Generate a unique tenant name to avoid collisions."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# Module-scoped fixtures to keep one event loop for all DB-touching tests
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def tenant_client():
    """Module-scoped async client that shares a single event loop.

    Disposes the engine pool first to reset any stale connections from
    previous test modules that used different event loops.
    """
    from core.database import engine
    await engine.dispose()

    from core.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await engine.dispose()


# ==================== MODEL TESTS ====================


class TestTenantModel:
    """Verify the Tenant SQLAlchemy model exists with all required fields."""

    def test_tenant_model_importable(self):
        """Tenant model should be importable from core.database."""
        from core.database import Tenant
        assert Tenant is not None

    def test_tenant_model_has_required_columns(self):
        """Tenant model should have all required fields."""
        from core.database import Tenant
        mapper = Tenant.__table__.columns
        required = [
            "id", "name", "type", "url", "status",
            "health_score", "last_checked", "config",
            "created_at", "updated_at",
        ]
        col_names = [c.name for c in mapper]
        for field in required:
            assert field in col_names, f"Missing column: {field}"

    def test_tenant_type_values(self):
        """Tenant type should accept finance, ecommerce, email, other."""
        from core.database import Tenant
        for t in ["finance", "ecommerce", "email", "other"]:
            tenant = Tenant(name=f"test-{t}", type=t, url=f"https://{t}.example.com")
            assert tenant.type == t

    def test_tenant_tablename(self):
        """Table name should be 'tenants'."""
        from core.database import Tenant
        assert Tenant.__tablename__ == "tenants"

    def test_tenant_status_column_default(self):
        """Status column should have a default of 'active'."""
        from core.database import Tenant
        status_col = Tenant.__table__.columns["status"]
        assert status_col.default is not None
        assert status_col.default.arg == "active"

    def test_tenant_health_score_column_default(self):
        """Health score column should have a default of 100.0."""
        from core.database import Tenant
        hs_col = Tenant.__table__.columns["health_score"]
        assert hs_col.default is not None
        assert hs_col.default.arg == 100.0


# ==================== CRUD ENDPOINT TESTS ====================


@pytest.mark.asyncio(loop_scope="module")
class TestTenantCRUDEndpoints:
    """Test the tenant CRUD API endpoints."""

    async def test_create_tenant(self, tenant_client):
        """POST /api/tenants should create a new tenant."""
        name = unique_name("create")
        resp = await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "finance",
            "url": "https://test-create.sanaa.ug",
        }, headers=auth_headers())
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == name
        assert data["type"] == "finance"
        assert data["url"] == "https://test-create.sanaa.ug"
        assert data["status"] == "active"
        assert data["health_score"] == 100.0
        assert "id" in data
        assert "created_at" in data

    async def test_create_tenant_with_config(self, tenant_client):
        """POST /api/tenants should accept optional config JSON."""
        name = unique_name("config")
        resp = await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "email",
            "url": "https://mail.test.com",
            "config": {"smtp_port": 587, "imap_port": 993},
        }, headers=auth_headers())
        assert resp.status_code == 201
        data = resp.json()
        assert data["config"]["smtp_port"] == 587

    async def test_create_tenant_invalid_type(self, tenant_client):
        """POST /api/tenants should reject invalid type values."""
        resp = await tenant_client.post("/api/tenants", json={
            "name": unique_name("invalid"),
            "type": "invalid_type",
            "url": "https://invalid.com",
        }, headers=auth_headers())
        assert resp.status_code == 422

    async def test_create_tenant_requires_auth(self, tenant_client):
        """POST /api/tenants should require authentication."""
        resp = await tenant_client.post("/api/tenants", json={
            "name": unique_name("noauth"),
            "type": "finance",
            "url": "https://test.com",
        })
        assert resp.status_code == 401

    async def test_list_tenants(self, tenant_client):
        """GET /api/tenants should return all tenants."""
        name = unique_name("list")
        await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "ecommerce",
            "url": "https://test-list.com",
        }, headers=auth_headers())
        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [t["name"] for t in data]
        assert name in names

    async def test_get_tenant_detail(self, tenant_client):
        """GET /api/tenants/{id} should return tenant detail with config."""
        name = unique_name("detail")
        create_resp = await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "finance",
            "url": "https://test-detail.sanaa.ug",
            "config": {"region": "East Africa"},
        }, headers=auth_headers())
        tenant_id = create_resp.json()["id"]
        resp = await tenant_client.get(f"/api/tenants/{tenant_id}", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == name
        assert data["config"]["region"] == "East Africa"

    async def test_get_tenant_not_found(self, tenant_client):
        """GET /api/tenants/{id} should return 404 for non-existent tenant."""
        resp = await tenant_client.get("/api/tenants/99999", headers=auth_headers())
        assert resp.status_code == 404

    async def test_update_tenant(self, tenant_client):
        """PUT /api/tenants/{id} should update tenant fields."""
        name = unique_name("update")
        create_resp = await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "finance",
            "url": "https://test-update.sanaa.ug",
        }, headers=auth_headers())
        tenant_id = create_resp.json()["id"]

        updated_name = unique_name("updated")
        resp = await tenant_client.put(f"/api/tenants/{tenant_id}", json={
            "name": updated_name,
            "health_score": 85.5,
            "status": "degraded",
        }, headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == updated_name
        assert data["health_score"] == 85.5
        assert data["status"] == "degraded"

    async def test_update_tenant_not_found(self, tenant_client):
        """PUT /api/tenants/{id} should return 404 for non-existent tenant."""
        resp = await tenant_client.put("/api/tenants/99999", json={"name": "nope"}, headers=auth_headers())
        assert resp.status_code == 404

    async def test_soft_delete_tenant(self, tenant_client):
        """DELETE /api/tenants/{id} should soft-delete (mark inactive)."""
        name = unique_name("delete")
        create_resp = await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "ecommerce",
            "url": "https://test-delete.com",
        }, headers=auth_headers())
        tenant_id = create_resp.json()["id"]

        resp = await tenant_client.delete(f"/api/tenants/{tenant_id}", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "inactive"

        # Verify it's still retrievable (not hard-deleted)
        get_resp = await tenant_client.get(f"/api/tenants/{tenant_id}", headers=auth_headers())
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "inactive"

    async def test_delete_tenant_not_found(self, tenant_client):
        """DELETE /api/tenants/{id} should return 404 for non-existent tenant."""
        resp = await tenant_client.delete("/api/tenants/99999", headers=auth_headers())
        assert resp.status_code == 404

    async def test_list_tenants_includes_health_and_status(self, tenant_client):
        """GET /api/tenants should include status and health_score in listing."""
        name = unique_name("hlth")
        await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "finance",
            "url": "https://test-health.sanaa.ug",
        }, headers=auth_headers())
        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        data = resp.json()
        tenant = next(t for t in data if t["name"] == name)
        assert "status" in tenant
        assert "health_score" in tenant

    async def test_create_duplicate_tenant(self, tenant_client):
        """POST /api/tenants should reject duplicate names."""
        name = unique_name("dup")
        await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "finance",
            "url": "https://test-dup.com",
        }, headers=auth_headers())
        resp = await tenant_client.post("/api/tenants", json={
            "name": name,
            "type": "finance",
            "url": "https://test-dup2.com",
        }, headers=auth_headers())
        assert resp.status_code == 409


# ==================== SEEDING TESTS ====================


@pytest.mark.asyncio(loop_scope="module")
class TestTenantSeeding:
    """Verify initial tenants are seeded on startup."""

    async def test_seeded_tenants_exist(self, tenant_client):
        """Initial tenants should be seeded: finance tenants, soko, mailcow."""
        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        names = [t["name"] for t in data]

        # Finance tenants
        assert "finance.sanaa.ug" in names
        assert "kalamba.sanaa.ug" in names
        assert "bukuya.sanaa.ug" in names
        # Ecommerce
        assert "soko" in names
        # Email
        assert "mailcow" in names

    async def test_seeded_finance_tenants_type(self, tenant_client):
        """Finance tenants should have type 'finance'."""
        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        data = resp.json()
        for name in ["finance.sanaa.ug", "kalamba.sanaa.ug", "bukuya.sanaa.ug"]:
            tenant = next((t for t in data if t["name"] == name), None)
            assert tenant is not None, f"Tenant {name} not found"
            assert tenant["type"] == "finance"

    async def test_seeded_soko_type(self, tenant_client):
        """Soko tenant should have type 'ecommerce'."""
        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        data = resp.json()
        soko = next((t for t in data if t["name"] == "soko"), None)
        assert soko is not None
        assert soko["type"] == "ecommerce"

    async def test_seeded_mailcow_type(self, tenant_client):
        """Mailcow tenant should have type 'email'."""
        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        data = resp.json()
        mailcow = next((t for t in data if t["name"] == "mailcow"), None)
        assert mailcow is not None
        assert mailcow["type"] == "email"

    async def test_seeded_tenants_active(self, tenant_client):
        """All seeded tenants should have active status."""
        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        data = resp.json()
        seeded_names = ["finance.sanaa.ug", "kalamba.sanaa.ug", "bukuya.sanaa.ug", "soko", "mailcow"]
        for name in seeded_names:
            tenant = next((t for t in data if t["name"] == name), None)
            assert tenant is not None, f"Tenant {name} not found"
            assert tenant["status"] == "active"

    async def test_seeding_is_idempotent(self, tenant_client):
        """Running seed multiple times should not duplicate tenants."""
        from core.routes.tenants import seed_initial_tenants
        await seed_initial_tenants()
        await seed_initial_tenants()

        resp = await tenant_client.get("/api/tenants", headers=auth_headers())
        data = resp.json()
        names = [t["name"] for t in data]
        assert names.count("finance.sanaa.ug") == 1
        assert names.count("soko") == 1
        assert names.count("mailcow") == 1
