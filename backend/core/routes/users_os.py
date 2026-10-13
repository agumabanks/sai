"""
Sanaa OS — User & Role Management
Reads/writes Laravel's users table directly via SQLite.
"""

import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import get_settings
from core.routes import deps
from core.routes.deps import RateLimit

router = APIRouter()
settings = get_settings()

LARAVEL_DB = "/var/www/ai.sanaa.co/frontend/database/database.sqlite"

VALID_ROLES = ["admin", "operator", "viewer", "seller"]
SANAA_EMAIL_DOMAIN = "@sanaa.co"
ROOT_ADMIN_EMAIL = (settings.root_admin_email or "banks@sanaa.co").lower()


def _get_db():
    conn = sqlite3.connect(LARAVEL_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _is_sanaa_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@sanaa\.co$", (email or "").strip(), re.IGNORECASE))


def _serialize_user(row: sqlite3.Row) -> dict:
    data = dict(row)
    email = (data.get("email") or "").lower()
    data["is_root"] = email == ROOT_ADMIN_EMAIL
    return data


def _require_admin(actor: dict = Depends(deps.require_auth)) -> dict:
    return deps.require_user_admin(actor)


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)
    role: str = Field(default="viewer")


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = Field(default=None)


def _validate_create(body: UserCreate, actor: dict):
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    if not _is_sanaa_email(body.email):
        raise HTTPException(400, f"New users must use a {SANAA_EMAIL_DOMAIN} email address")
    if body.role == "admin" and not deps.is_root_admin(actor):
        raise HTTPException(403, "Only the root administrator can create admin accounts")


def _validate_update(body: UserUpdate, actor: dict, target_email: str):
    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    if body.email is not None and not _is_sanaa_email(body.email):
        raise HTTPException(400, f"Users must use a {SANAA_EMAIL_DOMAIN} email address")
    if body.role == "admin" and not deps.is_root_admin(actor):
        raise HTTPException(403, "Only the root administrator can assign the admin role")
    if target_email.lower() == ROOT_ADMIN_EMAIL and not deps.is_root_admin(actor):
        raise HTTPException(403, "The root administrator account cannot be modified by others")
    if target_email.lower() == ROOT_ADMIN_EMAIL and body.role and body.role != "admin":
        raise HTTPException(400, "The root administrator must remain an admin")


@router.get("/api/admin/users")
async def list_users(
    include_deleted: bool = False,
    user: dict = Depends(_require_admin),
    _rate: None = Depends(RateLimit(limit=60)),
):
    conn = _get_db()
    try:
        if include_deleted:
            rows = conn.execute(
                "SELECT id, name, email, role, created_at, updated_at, deleted_at FROM users ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, email, role, created_at, updated_at, deleted_at FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC"
            ).fetchall()
        return {
            "users": [_serialize_user(r) for r in rows],
            "root_admin": ROOT_ADMIN_EMAIL,
            "domain_rule": SANAA_EMAIL_DOMAIN,
        }
    finally:
        conn.close()


@router.post("/api/admin/users")
async def create_user(
    body: UserCreate,
    user: dict = Depends(_require_admin),
    _rate: None = Depends(RateLimit(limit=30)),
):
    _validate_create(body, user)

    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? AND deleted_at IS NULL",
            (body.email.strip().lower(),),
        ).fetchone()
        if existing:
            raise HTTPException(409, "Email already in use")

        now = datetime.now(timezone.utc).isoformat()
        import bcrypt
        hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(rounds=10)).decode()

        cur = conn.execute(
            "INSERT INTO users (name, email, password, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (body.name, body.email.strip().lower(), hashed, body.role, now, now),
        )
        conn.commit()
        return {"id": cur.lastrowid, "status": "created"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.put("/api/admin/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    user: dict = Depends(_require_admin),
    _rate: None = Depends(RateLimit(limit=30)),
):
    conn = _get_db()
    try:
        existing = conn.execute("SELECT id, email FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "User not found")

        _validate_update(body, user, existing["email"])

        updates = []
        args = []
        if body.name is not None:
            updates.append("name = ?")
            args.append(body.name)
        if body.email is not None:
            updates.append("email = ?")
            args.append(body.email.strip().lower())
        if body.role is not None:
            updates.append("role = ?")
            args.append(body.role)
        if body.password is not None:
            import bcrypt
            hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(rounds=10)).decode()
            updates.append("password = ?")
            args.append(hashed)

        if len(updates) == 0:
            raise HTTPException(400, "No fields to update")

        now = datetime.now(timezone.utc).isoformat()
        updates.append("updated_at = ?")
        args.append(now)
        args.append(user_id)

        conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", args)
        conn.commit()
        return {"status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    user: dict = Depends(_require_admin),
    _rate: None = Depends(RateLimit(limit=30)),
):
    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT id, email FROM users WHERE id = ? AND deleted_at IS NULL",
            (user_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "User not found")
        if existing["email"].lower() == ROOT_ADMIN_EMAIL:
            raise HTTPException(403, "The root administrator cannot be deleted")

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE users SET deleted_at = ? WHERE id = ?", (now, user_id))
        conn.commit()
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.post("/api/admin/users/{user_id}/restore")
async def restore_user(
    user_id: int,
    user: dict = Depends(_require_admin),
    _rate: None = Depends(RateLimit(limit=30)),
):
    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE id = ? AND deleted_at IS NOT NULL",
            (user_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "User not found or not deleted")

        conn.execute("UPDATE users SET deleted_at = NULL WHERE id = ?", (user_id,))
        conn.commit()
        return {"status": "restored"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.post("/api/admin/users/ensure-root")
async def ensure_root_admin(
    user: dict = Depends(deps.require_auth),
    _rate: None = Depends(RateLimit(limit=10)),
):
    """Idempotently ensure the root administrator exists."""
    if not deps.is_root_admin(user) and not deps.is_admin(user):
        raise HTTPException(403, "Administrator access required")

    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (ROOT_ADMIN_EMAIL,),
        ).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        if row:
            conn.execute(
                "UPDATE users SET role = 'admin', deleted_at = NULL, updated_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            conn.commit()
            return {"status": "exists", "email": ROOT_ADMIN_EMAIL, "id": row["id"]}

        import bcrypt
        import secrets
        temp_password = secrets.token_urlsafe(16)
        hashed = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt(rounds=10)).decode()
        cur = conn.execute(
            "INSERT INTO users (name, email, password, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("Banks Admin", ROOT_ADMIN_EMAIL, hashed, "admin", now, now),
        )
        conn.commit()
        return {
            "status": "created",
            "email": ROOT_ADMIN_EMAIL,
            "id": cur.lastrowid,
            "note": "Use OTP login or reset password via admin panel",
        }
    finally:
        conn.close()