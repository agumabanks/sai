"""
Sanaa Contacts — platform source connectors (local DB + HTTP fallback).
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from typing import Any, Callable, Optional

import asyncpg
import httpx
import pymysql

logger = logging.getLogger(__name__)

LARAVEL_DB = "/var/www/ai.sanaa.co/frontend/database/database.sqlite"

# Local DB connectors (same host). Credentials match deployed platform .env files.
SOKO_DB = {
    "host": "127.0.0.1",
    "user": "soko24",
    "password": "SUPER_STRONG_PASSWORDX",
    "database": "soko",
}

CARDS_DB = {
    "host": "127.0.0.1",
    "user": "sanaa",
    "password": "sanaa_secret",
    "database": "sanaa_cards",
}

FARZONE_DB = {
    "host": "127.0.0.1",
    "user": "farzone_user",
    "password": "FarzoneDB2026!",
    "database": "farzone_db",
}

FINANCE_TENANTS: list[dict[str, str]] = [
    {"id": "finance_bweyale", "label": "Bweyale SACCO", "database": "bweyale", "user": "root", "password": "root"},
    {"id": "finance_kalamba", "label": "Kalamba SACCO", "database": "kalamba", "user": "kalamba_user", "password": "K@l@mb@Secure2026!"},
    {"id": "finance_bukuya", "label": "Bukuya SACCO", "database": "bukuya", "user": "kalamba_user", "password": "K@l@mb@Secure2026!"},
    {"id": "finance_mafubira", "label": "Mafubira SACCO", "database": "mafubira", "user": "root", "password": "root"},
]

HTTP_SOURCES: list[dict[str, str]] = [
    {"id": "soko", "url": "https://soko24.co/api/sanaa/contacts", "platform": "Soko 24"},
    {"id": "cards", "url": "https://cards.sanaa.co/api/sanaa/contacts", "platform": "Cards Sanaa"},
    {"id": "farzone", "url": "https://furzone.sanaa.co/api/sanaa/contacts", "platform": "Furzone"},
]


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _norm_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def contact_row(
    *,
    source: str,
    platform: str,
    name: str,
    email: str = "",
    phone: str = "",
    organization: str = "",
    role: str = "",
    external_id: str = "",
    meta: Optional[dict] = None,
) -> dict[str, Any]:
    key = external_id or _norm_email(email) or _norm_phone(phone) or name
    cid = f"{source}:{key}".lower().replace(" ", "_")
    return {
        "id": cid,
        "source": source,
        "platform": platform,
        "name": name or "Unknown",
        "email": email or "",
        "phone": phone or "",
        "organization": organization or "",
        "role": role or "",
        "avatar_initials": _initials(name or email or phone),
        "meta": meta or {},
        "links": [],
    }


async def _run_sync(fn: Callable[[], list[dict]]) -> list[dict]:
    return await asyncio.to_thread(fn)


def _mysql_query(cfg: dict, sql: str) -> list[dict]:
    conn = pymysql.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg.get("password") or "",
        database=cfg["database"],
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall())
    finally:
        conn.close()


async def _pg_query(cfg: dict, sql: str, *args) -> list[dict]:
    conn = await asyncpg.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        timeout=8,
    )
    try:
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def fetch_os_users() -> tuple[list[dict], Optional[str]]:
    def run() -> list[dict]:
        conn = sqlite3.connect(LARAVEL_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, email, role FROM users WHERE deleted_at IS NULL ORDER BY name"
        ).fetchall()
        conn.close()
        return [
            contact_row(
                source="os_users",
                platform="Sanaa OS",
                name=row["name"],
                email=row["email"],
                role=row["role"] or "operator",
                external_id=str(row["id"]),
                meta={"user_id": row["id"]},
            )
            for row in rows
        ]

    try:
        return await _run_sync(run), None
    except Exception as exc:
        logger.warning("contacts os_users: %s", exc)
        return [], str(exc)


async def fetch_soko_users() -> tuple[list[dict], Optional[str]]:
    try:
        rows = await _run_sync(
            lambda: _mysql_query(
                SOKO_DB,
                """
                SELECT id, name, email, phone, user_type
                FROM users
                WHERE name IS NOT NULL AND name != ''
                ORDER BY name
                LIMIT 3000
                """,
            )
        )
        contacts = [
            contact_row(
                source="soko",
                platform="Soko 24",
                name=row.get("name") or "Soko User",
                email=row.get("email") or "",
                phone=str(row.get("phone") or ""),
                organization="",
                role=row.get("user_type") or "user",
                external_id=str(row.get("id")),
                meta={"soko_user_id": row.get("id")},
            )
            for row in rows
        ]
        return contacts, None
    except Exception as exc:
        logger.warning("contacts soko: %s", exc)
        return [], str(exc)


async def fetch_cards_users() -> tuple[list[dict], Optional[str]]:
    try:
        rows = await _pg_query(
            CARDS_DB,
            """
            SELECT id, first_name, last_name, email, phone, status
            FROM users
            WHERE deleted_at IS NULL
            ORDER BY first_name, last_name
            LIMIT 2000
            """,
        )
        contacts = []
        for row in rows:
            name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or "Cards User"
            contacts.append(
                contact_row(
                    source="cards",
                    platform="Cards Sanaa",
                    name=name,
                    email=row.get("email") or "",
                    phone=str(row.get("phone") or ""),
                    role=str(row.get("status") or "user"),
                    external_id=str(row.get("id")),
                    meta={"cards_user_id": row.get("id")},
                )
            )
        return contacts, None
    except Exception as exc:
        logger.warning("contacts cards: %s", exc)
        return [], str(exc)


async def fetch_farzone_users() -> tuple[list[dict], Optional[str]]:
    try:
        rows = await _pg_query(
            FARZONE_DB,
            """
            SELECT id, name, email, phone, plan_tier, emergency_contacts, is_active
            FROM users
            WHERE deleted_at IS NULL
            ORDER BY name
            LIMIT 2000
            """,
        )
        contacts = []
        for row in rows:
            contacts.append(
                contact_row(
                    source="farzone",
                    platform="Furzone",
                    name=row.get("name") or "Furzone User",
                    email=row.get("email") or "",
                    phone=str(row.get("phone") or ""),
                    role="active" if row.get("is_active") else "inactive",
                    organization=str(row.get("plan_tier") or ""),
                    external_id=str(row.get("id")),
                    meta={
                        "plan_tier": row.get("plan_tier"),
                        "emergency_contacts": row.get("emergency_contacts"),
                    },
                )
            )
        return contacts, None
    except Exception as exc:
        logger.warning("contacts farzone: %s", exc)
        return [], str(exc)


async def fetch_finance_tenant(tenant: dict) -> tuple[list[dict], Optional[str]]:
    cfg = {
        "host": "127.0.0.1",
        "user": tenant["user"],
        "password": tenant.get("password") or "",
        "database": tenant["database"],
    }
    try:
        rows = await _run_sync(
            lambda: _mysql_query(
                cfg,
                """
                SELECT id, name, email, phone, business_name, status, branch_id
                FROM clients
                WHERE deleted_at IS NULL
                  AND name IS NOT NULL AND name != ''
                ORDER BY name
                LIMIT 5000
                """,
            )
        )
        source_id = tenant["id"]
        contacts = [
            contact_row(
                source=source_id,
                platform="Sanaa Finance",
                name=row.get("name") or "Client",
                email=row.get("email") or "",
                phone=str(row.get("phone") or ""),
                organization=row.get("business_name") or tenant["label"],
                role=str(row.get("status") or "client"),
                external_id=str(row.get("id")),
                meta={"tenant": tenant["label"], "branch_id": row.get("branch_id")},
            )
            for row in rows
        ]
        return contacts, None
    except Exception as exc:
        logger.warning("contacts %s: %s", tenant["id"], exc)
        return [], str(exc)


async def fetch_http_source(url: str, source: str, platform: str) -> tuple[list[dict], Optional[str]]:
    contacts: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(url, headers={"Accept": "application/json", "User-Agent": "SanaaContacts/1.0"})
            if res.status_code >= 400:
                return [], f"HTTP {res.status_code}"
            data = res.json()
    except Exception as exc:
        return [], str(exc)

    items = data.get("contacts") or data.get("data") or []
    if isinstance(items, dict):
        items = items.get("data", [])
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("full_name") or "Contact"
        contacts.append(
            contact_row(
                source=source,
                platform=platform,
                name=str(name),
                email=item.get("email") or "",
                phone=str(item.get("phone") or item.get("phone_number") or ""),
                organization=item.get("organization") or item.get("company") or "",
                role=item.get("role") or item.get("type") or "",
                external_id=str(item.get("id") or item.get("uuid") or name),
                meta={"remote": True},
            )
        )
    return contacts, None


def attach_links(contacts: list[dict]) -> list[dict]:
    by_email: dict[str, list[str]] = {}
    by_phone: dict[str, list[str]] = {}

    for c in contacts:
        email = _norm_email(c.get("email", ""))
        phone = _norm_phone(c.get("phone", ""))
        if email:
            by_email.setdefault(email, []).append(c["id"])
        if phone and len(phone) >= 9:
            by_phone.setdefault(phone, []).append(c["id"])

    for c in contacts:
        linked: set[str] = set()
        email = _norm_email(c.get("email", ""))
        phone = _norm_phone(c.get("phone", ""))
        if email:
            linked.update(by_email.get(email, []))
        if phone:
            linked.update(by_phone.get(phone, []))
        linked.discard(c["id"])
        c["links"] = sorted(linked)[:12]

    return contacts