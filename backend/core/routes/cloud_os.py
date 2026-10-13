"""
Sanaa OS — Sanaa Cloud API
iCloud-style storage layer: quota, recent files, starred, trash, shares, activity.
Built on user workspaces from files_os (Kabati).
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import shutil
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.database import AsyncSessionLocal, UserCloudMeta
from core.routes import deps

router = APIRouter()

USER_DATA_ROOT = "/var/www/ai.sanaa.co/data/os/users"
DEFAULT_QUOTA_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB
TRASH_DIRNAME = ".Trash"
META_DIRNAME = ".kabati"
META_FILE = "cloud.json"


def _user_slug(email: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (email or "guest").lower()).strip("_") or "guest"


def _user_home(user: dict) -> str:
    return os.path.join(USER_DATA_ROOT, _user_slug(user.get("email", "guest")))


def _ensure_user_home(user: dict) -> str:
    home = _user_home(user)
    os.makedirs(home, exist_ok=True)
    os.makedirs(os.path.join(home, TRASH_DIRNAME), exist_ok=True)
    return home


def _meta_path(user: dict) -> str:
    meta_dir = os.path.join(_ensure_user_home(user), META_DIRNAME)
    os.makedirs(meta_dir, exist_ok=True)
    return os.path.join(meta_dir, META_FILE)


async def _load_meta(user: dict) -> dict:
    email = (user.get("email") or "guest").lower().strip()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserCloudMeta).where(UserCloudMeta.email == email))
        row = result.scalars().first()
        if row:
            return {
                "starred": list(row.starred or []),
                "activity": list(row.activity or []),
                "shares": list(row.shares or []),
                "sync_status": row.sync_status or "synced",
                "last_sync": row.last_sync_at.isoformat() if row.last_sync_at else datetime.now(timezone.utc).isoformat(),
                "pending_count": row.pending_count or 0,
            }

    # One-time migration from legacy JSON file
    path = _meta_path(user)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            row = UserCloudMeta(
                email=email,
                starred=list(data.get("starred") or []),
                activity=list(data.get("activity") or []),
                shares=list(data.get("shares") or []),
            )
            async with AsyncSessionLocal() as session:
                session.add(row)
                await session.commit()
            return {
                "starred": row.starred,
                "activity": row.activity,
                "shares": row.shares,
                "sync_status": row.sync_status,
                "last_sync": row.last_sync_at.isoformat() if row.last_sync_at else datetime.now(timezone.utc).isoformat(),
                "pending_count": row.pending_count or 0,
            }
        except Exception:
            pass

    return {
        "starred": [],
        "activity": [],
        "shares": [],
        "sync_status": "synced",
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "pending_count": 0,
    }


async def _save_meta(user: dict, meta: dict) -> None:
    email = (user.get("email") or "guest").lower().strip()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserCloudMeta).where(UserCloudMeta.email == email))
        row = result.scalars().first()
        now = datetime.now(timezone.utc)
        if row:
            row.starred = list(meta.get("starred") or [])
            row.activity = list(meta.get("activity") or [])
            row.shares = list(meta.get("shares") or [])
            row.sync_status = meta.get("sync_status") or "synced"
            row.pending_count = int(meta.get("pending_count") or 0)
            row.last_sync_at = now
            row.updated_at = now
        else:
            row = UserCloudMeta(
                email=email,
                starred=list(meta.get("starred") or []),
                activity=list(meta.get("activity") or []),
                shares=list(meta.get("shares") or []),
                sync_status=meta.get("sync_status") or "synced",
                pending_count=int(meta.get("pending_count") or 0),
                last_sync_at=now,
                updated_at=now,
            )
            session.add(row)
        await session.commit()


def _normalize(path: str) -> str:
    if ".." in path:
        raise HTTPException(400, "Path cannot contain '..'")
    return os.path.normpath(path)


def _is_within(path: str, base: str) -> bool:
    base = os.path.normpath(base)
    path = os.path.normpath(path)
    return path == base or path.startswith(base + os.sep)


def _validate_path(path: str, user: dict) -> str:
    path = _normalize(path)
    home = _ensure_user_home(user)
    if _is_within(path, home):
        return path
    raise HTTPException(403, "Access denied — user workspace only")


def _file_kind(name: str, is_dir: bool) -> str:
    if is_dir:
        return "folder"
    ext = os.path.splitext(name)[1].lower()
    image = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
    doc = {".txt", ".md", ".pdf", ".doc", ".docx", ".csv", ".xlsx"}
    if ext in image:
        return "image"
    if ext in doc:
        return "document"
    return "file"


def _serialize(path: str, starred: set[str]) -> dict:
    is_dir = os.path.isdir(path)
    stat = os.stat(path)
    mime_type, _ = mimetypes.guess_type(path)
    name = os.path.basename(path)
    return {
        "name": name,
        "path": path,
        "type": "dir" if is_dir else "file",
        "kind": _file_kind(name, is_dir),
        "size": stat.st_size if not is_dir else None,
        "modified": stat.st_mtime,
        "mime": mime_type or ("inode/directory" if is_dir else "application/octet-stream"),
        "starred": path in starred,
        "download_url": f"/api/files/download?path={path}" if not is_dir else None,
        "view_url": f"/api/files/view?path={path}" if not is_dir else None,
    }


async def _log_activity(user: dict, action: str, path: str, detail: str = "") -> None:
    meta = await _load_meta(user)
    entry = {
        "action": action,
        "path": path,
        "detail": detail,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    meta["activity"] = ([entry] + meta["activity"])[:100]
    await _save_meta(user, meta)


async def _update_meta_paths(user: dict, old_path: str, new_path: str) -> None:
    """Keep starred paths and shares in sync after rename/move operations."""
    meta = await _load_meta(user)
    starred = list(meta.get("starred") or [])
    new_starred = []
    updated = False
    for p in starred:
        if p == old_path:
            new_starred.append(new_path)
            updated = True
        elif p.startswith(old_path + os.sep):
            new_starred.append(new_path + p[len(old_path):])
            updated = True
        else:
            new_starred.append(p)
    if updated:
        meta["starred"] = new_starred

    shares = list(meta.get("shares") or [])
    new_shares = []
    share_updated = False
    for share in shares:
        spath = share.get("path")
        if spath == old_path:
            share["path"] = new_path
            share["name"] = os.path.basename(new_path)
            share["url"] = f"/api/files/download?path={new_path}"
            share_updated = True
        elif spath and spath.startswith(old_path + os.sep):
            share["path"] = new_path + spath[len(old_path):]
            share["name"] = os.path.basename(share["path"])
            share["url"] = f"/api/files/download?path={share['path']}"
            share_updated = True
        new_shares.append(share)
    if share_updated:
        meta["shares"] = new_shares

    if updated or share_updated:
        await _save_meta(user, meta)


def _disk_usage(root: str) -> tuple[int, int]:
    total = 0
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        if TRASH_DIRNAME in dirnames:
            dirnames.remove(TRASH_DIRNAME)
        if META_DIRNAME in dirnames:
            dirnames.remove(META_DIRNAME)
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
                count += 1
            except OSError:
                continue
    return total, count


def _recent_files(home: str, starred: set[str], limit: int = 24) -> list[dict]:
    entries = []
    for dirpath, dirnames, filenames in os.walk(home):
        if TRASH_DIRNAME in dirnames:
            dirnames.remove(TRASH_DIRNAME)
        if META_DIRNAME in dirnames:
            dirnames.remove(META_DIRNAME)
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                entries.append((os.path.getmtime(full), full))
            except OSError:
                continue
    entries.sort(key=lambda x: x[0], reverse=True)
    return [_serialize(p, starred) for _, p in entries[:limit]]


def _trash_dir(user: dict) -> str:
    return os.path.join(_ensure_user_home(user), TRASH_DIRNAME)


class StarRequest(BaseModel):
    path: str
    starred: bool = True


class TrashRequest(BaseModel):
    path: str


class ShareRequest(BaseModel):
    path: str
    expires_days: Optional[int] = Field(default=7, ge=1, le=90)


class ShareUpdateRequest(BaseModel):
    expires_days: Optional[int] = Field(default=None, ge=1, le=90)


class FolderCreateRequest(BaseModel):
    path: str


class RenameRequest(BaseModel):
    source: str
    destination: str


class MoveRequest(BaseModel):
    source: str
    destination: str


class CopyRequest(BaseModel):
    source: str
    destination: str


@router.get("/api/cloud/overview")
async def cloud_overview(user: dict = Depends(deps.require_auth)):
    home = _ensure_user_home(user)
    meta = await _load_meta(user)
    starred_set = set(meta["starred"])
    used, file_count = _disk_usage(home)
    trash_path = _trash_dir(user)
    trash_count = 0
    trash_size = 0
    if os.path.isdir(trash_path):
        for name in os.listdir(trash_path):
            full = os.path.join(trash_path, name)
            try:
                if os.path.isfile(full):
                    trash_size += os.path.getsize(full)
                    trash_count += 1
                elif os.path.isdir(full):
                    trash_count += 1
            except OSError:
                continue

    quota = DEFAULT_QUOTA_BYTES
    pct = round((used / quota) * 100, 1) if quota else 0

    return {
        "email": user.get("email"),
        "home": home,
        "quota_bytes": quota,
        "used_bytes": used,
        "available_bytes": max(0, quota - used),
        "usage_percent": min(pct, 100),
        "file_count": file_count,
        "starred_count": len(starred_set),
        "trash_count": trash_count,
        "trash_bytes": trash_size,
        "shares_count": len(meta.get("shares") or []),
        "sync_status": meta.get("sync_status", "synced"),
        "last_sync": meta.get("last_sync") or datetime.now(timezone.utc).isoformat(),
        "app": {"name": "Sanaa Cloud", "tagline": "Your files, everywhere on Sanaa"},
    }


@router.get("/api/cloud/recent")
async def cloud_recent(
    limit: int = Query(24, ge=1, le=100),
    user: dict = Depends(deps.require_auth),
):
    home = _ensure_user_home(user)
    meta = await _load_meta(user)
    starred_set = set(meta["starred"])
    items = _recent_files(home, starred_set, limit)
    return {"items": items, "count": len(items)}


@router.get("/api/cloud/starred")
async def cloud_starred(user: dict = Depends(deps.require_auth)):
    meta = await _load_meta(user)
    starred_set = set(meta["starred"])
    items = []
    for path in meta["starred"]:
        if os.path.exists(path):
            try:
                items.append(_serialize(path, starred_set))
            except OSError:
                continue
    items.sort(key=lambda x: x.get("modified") or 0, reverse=True)
    return {"items": items, "count": len(items)}


@router.post("/api/cloud/star")
async def cloud_star(body: StarRequest, user: dict = Depends(deps.require_auth)):
    path = _validate_path(body.path, user)
    if not os.path.exists(path):
        raise HTTPException(404, "Path not found")
    meta = await _load_meta(user)
    starred = list(meta["starred"])
    if body.starred and path not in starred:
        starred.append(path)
        await _log_activity(user, "star", path)
    elif not body.starred and path in starred:
        starred = [p for p in starred if p != path]
        await _log_activity(user, "unstar", path)
    meta["starred"] = starred
    await _save_meta(user, meta)
    return {"path": path, "starred": body.starred}


@router.get("/api/cloud/trash")
async def cloud_trash(user: dict = Depends(deps.require_auth)):
    trash = _trash_dir(user)
    items = []
    if os.path.isdir(trash):
        for name in sorted(os.listdir(trash)):
            full = os.path.join(trash, name)
            try:
                is_dir = os.path.isdir(full)
                stat = os.stat(full)
                items.append({
                    "name": name,
                    "path": full,
                    "type": "dir" if is_dir else "file",
                    "kind": _file_kind(name, is_dir),
                    "size": stat.st_size if not is_dir else None,
                    "modified": stat.st_mtime,
                    "deleted_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
            except OSError:
                continue
    return {"items": items, "count": len(items), "trash_dir": trash}


@router.post("/api/cloud/trash")
async def cloud_move_to_trash(body: TrashRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.path, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Path not found")
    home = _ensure_user_home(user)
    if src == home or src == _trash_dir(user):
        raise HTTPException(400, "Cannot trash this path")

    trash = _trash_dir(user)
    base = os.path.basename(src)
    dest = os.path.join(trash, base)
    if os.path.exists(dest):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(trash, f"{stamp}_{base}")

    try:
        shutil.move(src, dest)
        meta = await _load_meta(user)
        meta["starred"] = [p for p in meta["starred"] if p != src and not p.startswith(src + os.sep)]
        await _save_meta(user, meta)
        await _log_activity(user, "trash", src, dest)
        return {"status": "trashed", "source": src, "destination": dest}
    except OSError as e:
        raise HTTPException(500, str(e))


@router.post("/api/cloud/restore")
async def cloud_restore(body: TrashRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.path, user)
    trash = _trash_dir(user)
    if not _is_within(src, trash):
        raise HTTPException(400, "Path is not in trash")
    if not os.path.exists(src):
        raise HTTPException(404, "Item not found in trash")

    home = _ensure_user_home(user)
    name = os.path.basename(src)
    if name and "_" in name[:20]:
        parts = name.split("_", 2)
        if len(parts) >= 3 and parts[0].isdigit():
            name = parts[2]

    dest = os.path.join(home, "Documents", name)
    if os.path.exists(dest):
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        stem, ext = os.path.splitext(name)
        dest = os.path.join(home, "Documents", f"{stem}_{stamp}{ext}")

    try:
        shutil.move(src, dest)
        await _log_activity(user, "restore", dest)
        return {"status": "restored", "path": dest}
    except OSError as e:
        raise HTTPException(500, str(e))


@router.delete("/api/cloud/trash")
async def cloud_empty_trash(
    path: Optional[str] = None,
    user: dict = Depends(deps.require_auth),
):
    trash = _trash_dir(user)
    if path:
        target = _validate_path(path, user)
        if not _is_within(target, trash):
            raise HTTPException(400, "Path is not in trash")
        if not os.path.exists(target):
            raise HTTPException(404, "Item not found")
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        await _log_activity(user, "delete_permanent", target)
        return {"status": "deleted", "path": target}

    count = 0
    if os.path.isdir(trash):
        for name in os.listdir(trash):
            full = os.path.join(trash, name)
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full)
                else:
                    os.remove(full)
                count += 1
            except OSError:
                continue
    await _log_activity(user, "empty_trash", trash, str(count))
    return {"status": "emptied", "count": count}


@router.get("/api/cloud/activity")
async def cloud_activity(
    limit: int = Query(30, ge=1, le=100),
    user: dict = Depends(deps.require_auth),
):
    meta = await _load_meta(user)
    items = (meta.get("activity") or [])[:limit]
    return {"items": items, "count": len(items)}


@router.get("/api/cloud/shares")
async def cloud_shares(user: dict = Depends(deps.require_auth)):
    meta = await _load_meta(user)
    shares = []
    for share in meta.get("shares") or []:
        path = share.get("path")
        if path and os.path.exists(path):
            shares.append(share)
    meta["shares"] = shares
    await _save_meta(user, meta)
    return {"shares": shares, "count": len(shares)}


@router.post("/api/cloud/share")
async def cloud_create_share(body: ShareRequest, user: dict = Depends(deps.require_auth)):
    path = _validate_path(body.path, user)
    if not os.path.exists(path):
        raise HTTPException(404, "Path not found")

    meta = await _load_meta(user)
    token = secrets.token_urlsafe(16)
    share = {
        "path": path,
        "name": os.path.basename(path),
        "token": token,
        "url": f"/api/files/download?path={path}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_days": body.expires_days,
    }
    shares = [s for s in meta.get("shares") or [] if s.get("path") != path]
    shares.insert(0, share)
    meta["shares"] = shares[:50]
    await _save_meta(user, meta)
    await _log_activity(user, "share", path)
    return share


@router.post("/api/cloud/share/{token}/revoke")
async def cloud_revoke_share(token: str, user: dict = Depends(deps.require_auth)):
    meta = await _load_meta(user)
    shares = list(meta.get("shares") or [])
    before = len(shares)
    shares = [s for s in shares if s.get("token") != token]
    if len(shares) == before:
        raise HTTPException(404, "Share not found")
    meta["shares"] = shares
    await _save_meta(user, meta)
    await _log_activity(user, "revoke_share", token)
    return {"status": "revoked", "token": token}


@router.put("/api/cloud/share/{token}")
async def cloud_update_share(
    token: str,
    body: ShareUpdateRequest,
    user: dict = Depends(deps.require_auth),
):
    meta = await _load_meta(user)
    share = next((s for s in meta.get("shares") or [] if s.get("token") == token), None)
    if not share:
        raise HTTPException(404, "Share not found")
    if body.expires_days is not None:
        share["expires_days"] = body.expires_days
    await _save_meta(user, meta)
    return share


@router.get("/api/cloud/sync-status")
async def cloud_sync_status(user: dict = Depends(deps.require_auth)):
    meta = await _load_meta(user)
    return {
        "email": user.get("email"),
        "status": meta.get("sync_status", "synced"),
        "last_sync": meta.get("last_sync") or datetime.now(timezone.utc).isoformat(),
        "pending_count": meta.get("pending_count", 0),
    }


@router.get("/api/cloud/search")
async def cloud_search(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(deps.require_auth),
):
    home = _ensure_user_home(user)
    meta = await _load_meta(user)
    starred = set(meta["starred"])
    needle = q.lower()
    results = []

    for dirpath, dirnames, filenames in os.walk(home):
        if META_DIRNAME in dirnames:
            dirnames.remove(META_DIRNAME)
        if TRASH_DIRNAME in dirnames:
            dirnames.remove(TRASH_DIRNAME)
        if len(results) >= limit:
            break
        for name in dirnames + filenames:
            if needle in name.lower():
                full = os.path.join(dirpath, name)
                try:
                    results.append(_serialize(full, starred))
                except OSError:
                    continue
                if len(results) >= limit:
                    break

    return {"query": q, "count": len(results), "items": results}


@router.post("/api/cloud/folder")
async def cloud_create_folder(body: FolderCreateRequest, user: dict = Depends(deps.require_auth)):
    path = _validate_path(body.path, user)
    home = _ensure_user_home(user)
    if path == home or path == _trash_dir(user) or _is_within(path, _trash_dir(user)):
        raise HTTPException(400, "Cannot create folder here")
    if os.path.exists(path):
        raise HTTPException(409, "Folder already exists")
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.makedirs(path, exist_ok=True)
        await _log_activity(user, "create_folder", path)
        meta = await _load_meta(user)
        return {"status": "created", "path": path, "item": _serialize(path, set(meta["starred"]))}
    except OSError as e:
        raise HTTPException(500, str(e))


@router.post("/api/cloud/rename")
async def cloud_rename(body: RenameRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.source, user)
    dst = _validate_path(body.destination, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Source not found")
    home = _ensure_user_home(user)
    if src == home or src == _trash_dir(user):
        raise HTTPException(400, "Cannot rename this path")
    if os.path.exists(dst):
        raise HTTPException(409, "Destination already exists")

    try:
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.move(src, dst)
        await _update_meta_paths(user, src, dst)
        await _log_activity(user, "rename", src, dst)
        meta = await _load_meta(user)
        return {"status": "renamed", "source": src, "destination": dst, "item": _serialize(dst, set(meta["starred"]))}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except OSError as e:
        raise HTTPException(500, str(e))


@router.post("/api/cloud/move")
async def cloud_move(body: MoveRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.source, user)
    dst = _validate_path(body.destination, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Source not found")
    home = _ensure_user_home(user)
    if src == home or src == _trash_dir(user):
        raise HTTPException(400, "Cannot move this path")
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    if os.path.exists(dst):
        raise HTTPException(409, "Destination already exists")

    try:
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.move(src, dst)
        await _update_meta_paths(user, src, dst)
        await _log_activity(user, "move", src, dst)
        meta = await _load_meta(user)
        return {"status": "moved", "source": src, "destination": dst, "item": _serialize(dst, set(meta["starred"]))}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except OSError as e:
        raise HTTPException(500, str(e))


@router.post("/api/cloud/copy")
async def cloud_copy(body: CopyRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.source, user)
    dst = _validate_path(body.destination, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Source not found")
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    if os.path.exists(dst):
        raise HTTPException(409, "Destination already exists")

    try:
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        await _log_activity(user, "copy", src, dst)
        meta = await _load_meta(user)
        return {"status": "copied", "source": src, "destination": dst, "item": _serialize(dst, set(meta["starred"]))}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except OSError as e:
        raise HTTPException(500, str(e))
