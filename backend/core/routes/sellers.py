"""
Sanaa AI — Seller provisioning routes: create, query seller accounts.
"""

import logging
import secrets

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select as sa_select

from core.config import get_settings
from core.database import SellerAccount, AuditLog, AsyncSessionLocal
from core.routes import deps
from core.routes.deps import verify_soko_provision_key

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


class SellerProvisionRequest(BaseModel):
    seller_uuid: str
    soko_user_id: Optional[int] = None
    name: str
    shop_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsjet_vendor_uid: Optional[str] = None


@router.post("/api/sellers/provision")
async def provision_seller(
    payload: SellerProvisionRequest,
    token: str = Depends(verify_soko_provision_key),
):
    """Create a Sanaa Intelligence account for a Soko seller. Idempotent."""
    existing = await SellerAccount.get_by_uuid(payload.seller_uuid)
    if existing:
        return {
            "success": True,
            "already_existed": True,
            "seller_uuid": existing.seller_uuid,
            "api_key": existing.api_key,
            "dashboard_url": f"{settings.app_url}/seller/{existing.seller_uuid}",
        }

    api_key = "sa_" + secrets.token_urlsafe(32)

    account = await SellerAccount.create(
        seller_uuid=payload.seller_uuid,
        soko_user_id=payload.soko_user_id,
        name=payload.name,
        shop_name=payload.shop_name,
        phone=payload.phone,
        email=payload.email,
        whatsjet_vendor_uid=payload.whatsjet_vendor_uid,
        api_key=api_key,
        status="active",
    )

    await AuditLog.log(
        actor="soko_provisioning",
        action="seller_account_created",
        resource=f"seller:{payload.seller_uuid}",
        details={"soko_user_id": payload.soko_user_id, "name": payload.name},
    )

    return {
        "success": True,
        "already_existed": False,
        "seller_uuid": account.seller_uuid,
        "api_key": account.api_key,
        "dashboard_url": f"{settings.app_url}/seller/{account.seller_uuid}",
    }


@router.get("/api/sellers/{seller_uuid}")
async def get_seller(
    seller_uuid: str,
    token: str = Depends(verify_soko_provision_key),
):
    """Get a seller account by UUID."""
    account = await SellerAccount.get_by_uuid(seller_uuid)
    if not account:
        raise HTTPException(404, "Seller account not found")

    return {
        "success": True,
        "seller": {
            "seller_uuid": account.seller_uuid,
            "soko_user_id": account.soko_user_id,
            "name": account.name,
            "shop_name": account.shop_name,
            "phone": account.phone,
            "email": account.email,
            "whatsjet_vendor_uid": account.whatsjet_vendor_uid,
            "api_key": account.api_key,
            "status": account.status,
            "created_at": account.created_at.isoformat() if account.created_at else None,
        },
    }


@router.get("/api/sellers")
async def list_sellers(
    token: str = Depends(verify_soko_provision_key),
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List all seller accounts."""
    async with AsyncSessionLocal() as session:
        query = sa_select(SellerAccount).order_by(SellerAccount.created_at.desc())
        if status:
            query = query.where(SellerAccount.status == status)
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        accounts = result.scalars().all()

    return {
        "success": True,
        "count": len(accounts),
        "sellers": [
            {
                "seller_uuid": a.seller_uuid,
                "name": a.name,
                "shop_name": a.shop_name,
                "status": a.status,
                "whatsjet_vendor_uid": a.whatsjet_vendor_uid,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in accounts
        ],
    }
