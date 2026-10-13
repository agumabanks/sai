"""
Sanaa OS — Unified Contacts API
Aggregates people from Soko, Cards, Furzone, Finance tenants, OS users, WhatsApp, devices.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from core.routes import deps
from core.services import contacts_sources as src

logger = logging.getLogger(__name__)
router = APIRouter()

PLATFORM_SOURCES = [
    {"id": "os_users", "label": "Sanaa OS", "platform": "Sanaa OS"},
    {"id": "whatsapp", "label": "WhatsApp", "platform": "Sanaa Chat"},
    {"id": "soko", "label": "Soko 24", "platform": "Soko 24"},
    {"id": "cards", "label": "Cards Sanaa", "platform": "Cards Sanaa"},
    {"id": "farzone", "label": "Furzone", "platform": "Furzone"},
    {"id": "finance_bweyale", "label": "Bweyale SACCO", "platform": "Sanaa Finance"},
    {"id": "finance_kalamba", "label": "Kalamba SACCO", "platform": "Sanaa Finance"},
    {"id": "finance_bukuya", "label": "Bukuya SACCO", "platform": "Sanaa Finance"},
    {"id": "finance_mafubira", "label": "Mafubira SACCO", "platform": "Sanaa Finance"},
    {"id": "tenants", "label": "Tenants", "platform": "Sanaa Tenants"},
    {"id": "devices", "label": "Device Army", "platform": "Sanaa Devices"},
]


async def _fetch_whatsapp() -> tuple[list[dict], Optional[str]]:
    from core.config import get_settings

    settings = get_settings()
    if not settings.whatsapp_saas_enabled or not deps.whatsapp_saas:
        return [], "WhatsApp service unavailable"

    contacts: list[dict] = []
    page = 1
    try:
        while page <= 5:
            payload = await deps.whatsapp_saas.get_contacts(page=page, per_page=100)
            items = payload.get("data") or payload.get("contacts") or payload.get("result", {}).get("data") or []
            if isinstance(items, dict):
                items = items.get("data", [])
            if not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                first = (item.get("first_name") or item.get("firstName") or "").strip()
                last = (item.get("last_name") or item.get("lastName") or "").strip()
                name = (
                    item.get("name")
                    or f"{first} {last}".strip()
                    or item.get("phone_number")
                    or item.get("phone")
                    or "WhatsApp Contact"
                ).strip()
                phone = str(item.get("phone_number") or item.get("phone") or item.get("wa_id") or "")
                contacts.append(
                    src.contact_row(
                        source="whatsapp",
                        platform="Sanaa Chat",
                        name=name,
                        email=item.get("email") or "",
                        phone=phone,
                        organization=item.get("groups") or item.get("group") or "",
                        role=item.get("status") or "contact",
                        external_id=phone or name,
                    )
                )
            if len(items) < 100:
                break
            page += 1
        return contacts, None
    except Exception as exc:
        logger.warning("contacts whatsapp: %s", exc)
        return contacts, str(exc)


async def _fetch_tenants() -> tuple[list[dict], Optional[str]]:
    from sqlalchemy import select

    from core.database import AsyncSessionLocal, Tenant

    contacts: list[dict] = []
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Tenant).order_by(Tenant.name))
            tenants = result.scalars().all()
        for tenant in tenants:
            cfg = tenant.config if isinstance(tenant.config, dict) else {}
            contacts.append(
                src.contact_row(
                    source="tenants",
                    platform="Sanaa Tenants",
                    name=tenant.name,
                    email=cfg.get("contact_email") or cfg.get("email") or "",
                    phone=cfg.get("contact_phone") or cfg.get("phone") or "",
                    organization=tenant.type or "",
                    role=tenant.status or "tenant",
                    external_id=str(tenant.id),
                    meta={"url": tenant.url, "health_score": tenant.health_score, "type": tenant.type},
                )
            )
        return contacts, None
    except Exception as exc:
        logger.warning("contacts tenants: %s", exc)
        return [], str(exc)


async def _fetch_devices() -> tuple[list[dict], Optional[str]]:
    from sqlalchemy import select

    from core.database import AsyncSessionLocal, Device

    contacts: list[dict] = []
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Device).order_by(Device.display_name))
            devices = result.scalars().all()
        for device in devices:
            contacts.append(
                src.contact_row(
                    source="devices",
                    platform="Sanaa Devices",
                    name=device.display_name or device.codename or device.device_id,
                    organization=device.device_model or "",
                    role=device.worker_role or device.status or "worker",
                    external_id=device.device_id,
                    meta={
                        "codename": device.codename,
                        "status": device.status,
                        "android_version": device.android_version,
                    },
                )
            )
        return contacts, None
    except Exception as exc:
        logger.warning("contacts devices: %s", exc)
        return [], str(exc)


def _filter_contacts(contacts: list[dict], q: str = "", source: str = "") -> list[dict]:
    filtered = contacts
    if source:
        filtered = [c for c in filtered if c["source"] == source]
    if q:
        needle = q.lower()
        filtered = [
            c
            for c in filtered
            if needle in c["name"].lower()
            or needle in c["email"].lower()
            or needle in c["phone"].lower()
            or needle in c["organization"].lower()
            or needle in c["platform"].lower()
        ]
    return filtered


@router.get("/api/contacts/sources")
async def list_contact_sources(user: dict = Depends(deps.require_auth)):
    return {"sources": PLATFORM_SOURCES}


@router.get("/api/contacts")
async def list_unified_contacts(
    q: str = Query("", max_length=120),
    source: str = Query("", max_length=40),
    limit: int = Query(500, ge=1, le=5000),
    user: dict = Depends(deps.require_auth),
):
    aggregated: list[dict] = []
    source_stats: dict[str, dict] = {}

    fetchers: list[tuple[str, Any]] = [
        ("os_users", src.fetch_os_users),
        ("whatsapp", _fetch_whatsapp),
        ("soko", src.fetch_soko_users),
        ("cards", src.fetch_cards_users),
        ("farzone", src.fetch_farzone_users),
        ("tenants", _fetch_tenants),
        ("devices", _fetch_devices),
    ]

    for tenant in src.FINANCE_TENANTS:
        fetchers.append((tenant["id"], lambda t=tenant: src.fetch_finance_tenant(t)))

    for source_id, fetcher in fetchers:
        items, error = await fetcher()
        source_stats[source_id] = {"count": len(items), "error": error}
        aggregated.extend(items)

    deduped: dict[str, dict] = {}
    for contact in aggregated:
        deduped[contact["id"]] = contact

    contacts = src.attach_links(list(deduped.values()))
    contacts = _filter_contacts(contacts, q=q, source=source)
    contacts.sort(key=lambda c: (c["name"].lower(), c["platform"].lower()))
    total = len(contacts)
    contacts = contacts[:limit]

    return {
        "total": total,
        "count": len(contacts),
        "query": q,
        "source_filter": source or None,
        "sources": source_stats,
        "contacts": contacts,
        "viewer": {
            "email": user.get("email"),
            "role": user.get("role"),
            "is_admin": deps.is_admin(user),
        },
    }