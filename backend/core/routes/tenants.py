"""
Sanaa AI — Tenant CRUD routes.
Provides endpoints for managing tenants (finance, ecommerce, email, other).
"""

import logging
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.database import Tenant, Alert, AsyncSessionLocal, utcnow
from core.routes.deps import require_auth
from core.tenant_health import TenantHealthChecker

logger = logging.getLogger(__name__)
router = APIRouter()
LEGACY_HEALTH_STATUSES = {"healthy", "degraded", "down"}


# ==================== SCHEMAS ====================

class TenantType(str, Enum):
    finance = "finance"
    ecommerce = "ecommerce"
    email = "email"
    other = "other"


class TenantStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    degraded = "degraded"
    down = "down"


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: TenantType
    url: Optional[str] = None
    config: Optional[dict] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    type: Optional[TenantType] = None
    url: Optional[str] = None
    status: Optional[TenantStatus] = None
    health_score: Optional[float] = Field(default=None, ge=0, le=100)
    config: Optional[dict] = None


def _alert_to_dict(alert: Alert) -> dict:
    """Serialize an Alert model instance to a dict."""
    return {
        "id": alert.id,
        "severity": alert.severity,
        "source": alert.source,
        "title": alert.title,
        "message": alert.message,
        "metric": alert.metric,
        "tenant_id": alert.tenant_id,
        "acknowledged": alert.acknowledged,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


def _tenant_to_dict(tenant: Tenant, recent_alerts: list | None = None) -> dict:
    """Serialize a Tenant model instance to a dict."""
    checker = TenantHealthChecker()
    lifecycle_status = tenant.status

    # Backward compatibility for rows written before lifecycle and health
    # state were separated. Health-derived statuses are treated as active
    # lifecycle state and exposed via health_status instead.
    if lifecycle_status in LEGACY_HEALTH_STATUSES and tenant.last_checked is not None:
        health_status = lifecycle_status
        lifecycle_status = "active"
    else:
        health_status = checker.compute_tenant_health_status(
            tenant.health_score,
            lifecycle_status=lifecycle_status,
            last_checked=tenant.last_checked,
        )

    result = {
        "id": tenant.id,
        "name": tenant.name,
        "type": tenant.type,
        "url": tenant.url,
        "status": lifecycle_status,
        "health_status": health_status,
        "health_score": tenant.health_score,
        "last_checked": tenant.last_checked.isoformat() if tenant.last_checked else None,
        "config": tenant.config,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
    }
    if recent_alerts is not None:
        result["recent_alerts"] = [_alert_to_dict(a) for a in recent_alerts]
    return result


# ==================== ENDPOINTS ====================

@router.post("/api/tenants", status_code=201)
async def create_tenant(payload: TenantCreate, user: dict = Depends(require_auth)):
    """Create a new tenant."""
    async with AsyncSessionLocal() as session:
        # Check for duplicate name
        result = await session.execute(
            select(Tenant).where(Tenant.name == payload.name)
        )
        if result.scalars().first():
            raise HTTPException(status_code=409, detail=f"Tenant '{payload.name}' already exists")

        tenant = Tenant(
            name=payload.name,
            type=payload.type.value,
            url=payload.url,
            config=payload.config,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        return _tenant_to_dict(tenant)


@router.get("/api/tenants")
async def list_tenants(user: dict = Depends(require_auth)):
    """List all tenants with status and health_score."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).order_by(Tenant.name)
        )
        tenants = result.scalars().all()
        return [_tenant_to_dict(t) for t in tenants]


# ==================== HEALTH MONITORING ====================
# NOTE: Health routes MUST be registered before /api/tenants/{tenant_id}
# to prevent FastAPI from matching "health" as a tenant_id path parameter.


@router.get("/api/tenants/health")
async def aggregated_tenant_health(user: dict = Depends(require_auth)):
    """Return aggregated health scores across all registered tenants.

    Returns overall_score, overall_status, per-tenant breakdown, and checked_at.
    """
    checker = TenantHealthChecker()
    health_data = await checker.check_all_tenants()
    return health_data


@router.get("/api/tenants/{tenant_id}/health")
async def individual_tenant_health(tenant_id: int, user: dict = Depends(require_auth)):
    """Perform a live health check on a specific tenant.

    Checks the tenant's service (HTTP for web, Docker for email) and returns
    current status. Also updates health_score and last_checked in the database.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        tenant_data = {
            "id": tenant.id,
            "name": tenant.name,
            "type": tenant.type,
            "url": tenant.url,
            "status": tenant.status,
        }

    checker = TenantHealthChecker()
    check_result = await checker.check_single_tenant(tenant_data)

    # Persist health check result to DB
    await checker.update_tenant_health_in_db(check_result)

    return check_result


# ==================== LIFECYCLE MANAGEMENT ====================


@router.post("/api/tenants/{tenant_id}/enable")
async def enable_tenant(tenant_id: int, user: dict = Depends(require_auth)):
    """Enable a tenant: set status to 'active' and resume health check polling."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        tenant.status = "active"
        tenant.updated_at = utcnow()
        await session.commit()
        await session.refresh(tenant)
        logger.info(f"Tenant '{tenant.name}' (id={tenant.id}) enabled")
        return _tenant_to_dict(tenant)


@router.post("/api/tenants/{tenant_id}/disable")
async def disable_tenant(tenant_id: int, user: dict = Depends(require_auth)):
    """Disable a tenant: set status to 'inactive' and stop health check polling."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        tenant.status = "inactive"
        tenant.updated_at = utcnow()
        await session.commit()
        await session.refresh(tenant)
        logger.info(f"Tenant '{tenant.name}' (id={tenant.id}) disabled")
        return _tenant_to_dict(tenant)


@router.post("/api/tenants/{tenant_id}/check")
async def check_tenant(tenant_id: int, user: dict = Depends(require_auth)):
    """Trigger an immediate health check for a specific tenant.

    Unlike GET /api/tenants/{id}/health, this endpoint forces a check even
    for inactive tenants and always persists the result.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        tenant_data = {
            "id": tenant.id,
            "name": tenant.name,
            "type": tenant.type,
            "url": tenant.url,
            "status": tenant.status,
        }

    checker = TenantHealthChecker()
    # Force check regardless of tenant status
    check_result = await checker.check_single_tenant_forced(tenant_data)

    # Persist health check result
    await checker.update_tenant_health_in_db(check_result)

    return check_result


# ==================== CRUD (DETAIL) ====================


@router.get("/api/tenants/{tenant_id}")
async def get_tenant(tenant_id: int, user: dict = Depends(require_auth)):
    """Get tenant detail with config and recent alerts."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Include recent alerts for this tenant
        recent_alerts = await Alert.get_by_tenant(tenant_id, limit=10)
        return _tenant_to_dict(tenant, recent_alerts=recent_alerts)


@router.get("/api/tenants/{tenant_id}/alerts")
async def get_tenant_alerts(tenant_id: int, limit: int = 20, user: dict = Depends(require_auth)):
    """Get alerts associated with a specific tenant."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

    alerts = await Alert.get_by_tenant(tenant_id, limit=min(limit, 100))
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "alerts": [_alert_to_dict(a) for a in alerts],
        "total": len(alerts),
    }


@router.put("/api/tenants/{tenant_id}")
async def update_tenant(tenant_id: int, payload: TenantUpdate, user: dict = Depends(require_auth)):
    """Update tenant fields."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if isinstance(value, Enum):
                value = value.value
            setattr(tenant, key, value)
        tenant.updated_at = utcnow()

        await session.commit()
        await session.refresh(tenant)
        return _tenant_to_dict(tenant)


@router.delete("/api/tenants/{tenant_id}")
async def delete_tenant(tenant_id: int, user: dict = Depends(require_auth)):
    """Soft-delete a tenant by marking it inactive."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        tenant.status = "inactive"
        tenant.updated_at = utcnow()
        await session.commit()
        await session.refresh(tenant)
        return _tenant_to_dict(tenant)


# ==================== SEEDING ====================

# Initial tenants to seed on startup
INITIAL_TENANTS = [
    {
        "name": "finance.sanaa.ug",
        "type": "finance",
        "url": "https://finance.sanaa.ug",
        "config": {"description": "Sanaa Finance Platform"},
    },
    {
        "name": "kalamba.sanaa.ug",
        "type": "finance",
        "url": "https://kalamba.sanaa.ug",
        "config": {"description": "Kalamba Finance Platform"},
    },
    {
        "name": "bukuya.sanaa.ug",
        "type": "finance",
        "url": "https://bukuya.sanaa.ug",
        "config": {"description": "Bukuya Finance Platform"},
    },
    {
        "name": "soko",
        "type": "ecommerce",
        "url": "https://soko.sanaa.ug",
        "config": {"description": "Soko 24 Marketplace"},
    },
    {
        "name": "mailcow",
        "type": "email",
        "url": "https://mail.sanaa.ug",
        "config": {"description": "Mailcow Email Server"},
    },
]


async def seed_initial_tenants():
    """Seed initial tenants if they don't already exist. Idempotent.

    Also repairs legacy tenant rows whose status was overwritten with health
    values before lifecycle and health state were split.
    """
    async with AsyncSessionLocal() as session:
        for tenant_data in INITIAL_TENANTS:
            result = await session.execute(
                select(Tenant).where(Tenant.name == tenant_data["name"])
            )
            existing = result.scalars().first()
            if not existing:
                tenant = Tenant(**tenant_data)
                session.add(tenant)
                logger.info(f"Seeded tenant: {tenant_data['name']}")
            elif existing.status in LEGACY_HEALTH_STATUSES:
                existing.status = "active"
                existing.updated_at = utcnow()
                logger.info(f"Normalized legacy tenant status for: {tenant_data['name']}")
        await session.commit()
