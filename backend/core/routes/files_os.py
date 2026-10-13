"""
Sanaa OS — Kabati Filesystem API
User-scoped workspaces (Desktop, Downloads, …) with root-admin server access.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.routes import deps

router = APIRouter()
logger = logging.getLogger(__name__)

USER_DATA_ROOT = "/var/www/ai.sanaa.co/data/os/users"
SEED_DESKTOP = "/var/www/ai.sanaa.co/data/os/seed/Desktop"
STANDARD_FOLDERS = ["Desktop", "Downloads", "Documents", "Pictures", "Music", "Movies", "Shared"]

_BLOCKED_PREFIXES = ["/proc", "/sys", "/dev"]
_ROOT_ALLOWED_BASES = [
    "/var/www/ai.sanaa.co",
    "/home",
    "/tmp",
    "/opt",
    "/var/log",
    "/etc",
    "/",
]

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"}
_DOC_EXT = {".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".csv", ".xlsx", ".xls"}
_CODE_EXT = {".js", ".ts", ".jsx", ".tsx", ".py", ".php", ".json", ".html", ".css", ".yaml", ".yml", ".sh", ".sql"}
_AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
_VIDEO_EXT = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
_ARCHIVE_EXT = {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"}


def _user_slug(email: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (email or "guest").lower()).strip("_") or "guest"


def _user_home(user: dict) -> str:
    return os.path.join(USER_DATA_ROOT, _user_slug(user.get("email", "guest")))


def _tags_path(user: dict) -> str:
    meta_dir = os.path.join(_user_home(user), ".kabati")
    os.makedirs(meta_dir, exist_ok=True)
    return os.path.join(meta_dir, "tags.json")


def _load_tags(user: dict) -> dict:
    path = _tags_path(user)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_tags(user: dict, tags: dict) -> None:
    path = _tags_path(user)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tags, f, indent=2)


def _seed_desktop(home: str) -> None:
    """Copy seed files to user Desktop once (e.g. audit prompts, guides)."""
    if not os.path.isdir(SEED_DESKTOP):
        return
    desktop = os.path.join(home, "Desktop")
    os.makedirs(desktop, exist_ok=True)
    for name in os.listdir(SEED_DESKTOP):
        src = os.path.join(SEED_DESKTOP, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(desktop, name)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)


def _ensure_user_home(user: dict) -> str:
    home = _user_home(user)
    os.makedirs(home, exist_ok=True)
    for folder in STANDARD_FOLDERS:
        os.makedirs(os.path.join(home, folder), exist_ok=True)
    _seed_desktop(home)
    return home


def _normalize(path: str) -> str:
    if ".." in path:
        raise HTTPException(400, "Path cannot contain '..'")
    path = os.path.normpath(path)
    for prefix in _BLOCKED_PREFIXES:
        if path.startswith(prefix):
            raise HTTPException(400, f"Access to {prefix} is not allowed")
    return path


def _is_within(path: str, base: str) -> bool:
    base = os.path.normpath(base)
    path = os.path.normpath(path)
    return path == base or path.startswith(base + os.sep)


def _validate_path(path: str, user: dict) -> str:
    path = _normalize(path)
    if deps.is_root_admin(user):
        if path == "/":
            return path
        for base in _ROOT_ALLOWED_BASES:
            if _is_within(path, base) or path.startswith(base):
                return path
        raise HTTPException(403, "Path outside server access policy")

    home = _ensure_user_home(user)
    if _is_within(path, home):
        return path
    raise HTTPException(403, "Access denied — user workspace only")


def _file_kind(name: str, is_dir: bool) -> str:
    if is_dir:
        return "folder"
    ext = os.path.splitext(name)[1].lower()
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _DOC_EXT:
        return "document"
    if ext in _CODE_EXT:
        return "code"
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _ARCHIVE_EXT:
        return "archive"
    return "file"


def _serialize_item(full: str, name: str, tags_map: dict) -> dict:
    is_dir = os.path.isdir(full)
    stat = os.stat(full)
    mime_type, _ = mimetypes.guess_type(full)
    return {
        "name": name,
        "path": full,
        "type": "dir" if is_dir else "file",
        "kind": _file_kind(name, is_dir),
        "size": stat.st_size if not is_dir else None,
        "modified": stat.st_mtime,
        "permissions": oct(stat.st_mode)[-3:],
        "mime": mime_type or ("inode/directory" if is_dir else "application/octet-stream"),
        "tags": tags_map.get(full, []),
    }


class FileCreateRequest(BaseModel):
    path: str
    type: str = "file"
    content: Optional[str] = None


class FileRenameRequest(BaseModel):
    source: str
    destination: str


class FileWriteRequest(BaseModel):
    path: str
    content: str


class FileCopyRequest(BaseModel):
    source: str
    destination: str


class FileTagsRequest(BaseModel):
    path: str
    tags: list[str] = Field(default_factory=list)


class FileCompressRequest(BaseModel):
    paths: list[str] = Field(..., min_length=1)
    destination: Optional[str] = Field(default=None)


class FileDuplicateRequest(BaseModel):
    path: str


@router.get("/api/files/volumes")
async def list_volumes(user: dict = Depends(deps.require_auth)):
    """Sidebar locations — user favorites + system roots for root admin."""
    home = _ensure_user_home(user)
    is_root = deps.is_root_admin(user)

    favorites = [
        {"id": "desktop", "label": "Desktop", "icon": "desktop", "path": os.path.join(home, "Desktop"), "section": "favorites"},
        {"id": "downloads", "label": "Downloads", "icon": "download", "path": os.path.join(home, "Downloads"), "section": "favorites"},
        {"id": "documents", "label": "Documents", "icon": "document", "path": os.path.join(home, "Documents"), "section": "favorites"},
        {"id": "pictures", "label": "Pictures", "icon": "image", "path": os.path.join(home, "Pictures"), "section": "favorites"},
        {"id": "music", "label": "Music", "icon": "music", "path": os.path.join(home, "Music"), "section": "favorites"},
        {"id": "movies", "label": "Movies", "icon": "video", "path": os.path.join(home, "Movies"), "section": "favorites"},
        {"id": "shared", "label": "Shared", "icon": "share", "path": os.path.join(home, "Shared"), "section": "favorites"},
        {"id": "home", "label": "Kabati", "icon": "home", "path": home, "section": "favorites"},
    ]

    system = []
    if is_root:
        system = [
            {"id": "sanaa_project", "label": "Sanaa Project", "icon": "server", "path": "/var/www/ai.sanaa.co", "section": "system"},
            {"id": "sanaa_data", "label": "Sanaa Data", "icon": "database", "path": "/var/www/ai.sanaa.co/data", "section": "system"},
            {"id": "server_home", "label": "Server /home", "icon": "folder", "path": "/home", "section": "system"},
            {"id": "server_logs", "label": "System Logs", "icon": "log", "path": "/var/log", "section": "system"},
            {"id": "server_root", "label": "Macintosh HD", "icon": "disk", "path": "/", "section": "system", "root_only": True},
        ]

    return {
        "home": home,
        "is_root": is_root,
        "email": user.get("email"),
        "favorites": favorites,
        "system": system,
        "app": {"name": "Kabati", "tagline": "Sanduku lako la Sanaa"},
    }


@router.get("/api/files")
async def list_files(
    path: Optional[str] = None,
    sort: str = Query("name", pattern="^(name|date|size|kind)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    kind: str = Query("", max_length=20),
    user: dict = Depends(deps.require_auth),
):
    """List directory contents with metadata, tags, and sorting."""
    home = _ensure_user_home(user)
    target = _validate_path(path or os.path.join(home, "Desktop"), user)

    if not os.path.isdir(target):
        raise HTTPException(404, "Directory not found")

    tags_map = _load_tags(user)
    items = []
    try:
        for name in os.listdir(target):
            if name == ".kabati":
                continue
            full = os.path.join(target, name)
            try:
                item = _serialize_item(full, name, tags_map)
                if kind and item["kind"] != kind and not (kind == "folder" and item["type"] == "dir"):
                    continue
                items.append(item)
            except OSError:
                continue
    except PermissionError:
        raise HTTPException(403, "Permission denied")

    reverse = order == "desc"

    def sort_key(item: dict):
        if sort == "date":
            return item.get("modified") or 0
        if sort == "size":
            return item.get("size") or 0
        if sort == "kind":
            return (item.get("kind") or "", item.get("name", "").lower())
        return item.get("name", "").lower()

    items.sort(key=sort_key, reverse=reverse)
    if sort == "name":
        items.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()), reverse=False)

    parent = os.path.dirname(target) if target != "/" else None
    return {
        "path": target,
        "parent": parent,
        "home": home,
        "is_root": deps.is_root_admin(user),
        "items": items,
        "count": len(items),
    }


@router.get("/api/files/search")
async def search_files(
    q: str = Query(..., min_length=1, max_length=120),
    path: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(deps.require_auth),
):
    """Search files within user workspace or root scope."""
    home = _ensure_user_home(user)
    root_path = _validate_path(path or home, user)
    if not os.path.isdir(root_path):
        raise HTTPException(404, "Search root not found")

    needle = q.lower()
    tags_map = _load_tags(user)
    results = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d != ".kabati"]
        if len(results) >= limit:
            break
        for name in dirnames + filenames:
            if needle in name.lower():
                full = os.path.join(dirpath, name)
                try:
                    results.append(_serialize_item(full, name, tags_map))
                except OSError:
                    continue
                if len(results) >= limit:
                    break

    return {"query": q, "root": root_path, "count": len(results), "items": results}


@router.get("/api/files/tags")
async def get_all_tags(user: dict = Depends(deps.require_auth)):
    tags_map = _load_tags(user)
    unique = sorted({tag for tags in tags_map.values() for tag in tags})
    return {"tags": unique, "count": len(unique)}


@router.post("/api/files/tags")
async def set_file_tags(body: FileTagsRequest, user: dict = Depends(deps.require_auth)):
    path = _validate_path(body.path, user)
    if not os.path.exists(path):
        raise HTTPException(404, "Path not found")
    tags_map = _load_tags(user)
    cleaned = sorted({t.strip().lower() for t in body.tags if t.strip()})
    if cleaned:
        tags_map[path] = cleaned
    else:
        tags_map.pop(path, None)
    _save_tags(user, tags_map)
    return {"path": path, "tags": cleaned}


@router.post("/api/files/share")
async def share_file(path: str, user: dict = Depends(deps.require_auth)):
    path = _validate_path(path, user)
    if not os.path.exists(path):
        raise HTTPException(404, "Path not found")
    return {
        "path": path,
        "name": os.path.basename(path),
        "download_url": f"/api/files/download?path={path}",
        "view_url": f"/api/files/view?path={path}" if os.path.isfile(path) else None,
        "shared_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/files")
async def create_file(body: FileCreateRequest, user: dict = Depends(deps.require_auth)):
    path = _validate_path(body.path, user)
    if os.path.exists(path):
        raise HTTPException(409, "Path already exists")
    try:
        if body.type == "dir":
            os.makedirs(path, exist_ok=False)
            logger.info("Kabati: %s created directory %s", user.get("email"), path)
            return {"status": "created", "type": "dir", "path": path}
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body.content or "")
        logger.info("Kabati: %s created file %s", user.get("email"), path)
        return {"status": "created", "type": "file", "path": path}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/api/files/copy")
async def copy_file(body: FileCopyRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.source, user)
    dst = _validate_path(body.destination, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Source not found")
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
        logger.info("Kabati: %s copied %s -> %s", user.get("email"), src, dst)
        return {"status": "copied", "source": src, "destination": dst}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/api/files")
async def delete_file(path: str, user: dict = Depends(deps.require_auth)):
    path = _validate_path(path, user)
    if not os.path.exists(path):
        raise HTTPException(404, "Path not found")
    home = _user_home(user)
    if _is_within(path, home) and path == home:
        raise HTTPException(400, "Cannot delete home directory")
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        tags_map = _load_tags(user)
        tags_map.pop(path, None)
        _save_tags(user, tags_map)
        logger.info("Kabati: %s deleted %s", user.get("email"), path)
        return {"status": "deleted", "path": path}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/api/files/rename")
async def rename_file(body: FileRenameRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.source, user)
    dst = _validate_path(body.destination, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Source not found")
    if os.path.exists(dst):
        raise HTTPException(409, "Destination already exists")
    try:
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.move(src, dst)
        tags_map = _load_tags(user)
        if src in tags_map:
            tags_map[dst] = tags_map.pop(src)
            _save_tags(user, tags_map)
        logger.info("Kabati: %s moved %s -> %s", user.get("email"), src, dst)
        return {"status": "renamed", "source": src, "destination": dst}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/api/files/read")
async def read_file(path: str, user: dict = Depends(deps.require_auth)):
    path = _validate_path(path, user)
    if not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    try:
        size = os.path.getsize(path)
        if size > 1024 * 1024:
            raise HTTPException(413, "File too large to read (>1MB)")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": path, "size": size, "content": content}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/api/files/write")
async def write_file(body: FileWriteRequest, user: dict = Depends(deps.require_auth)):
    path = _validate_path(body.path, user)
    if not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(body.content)
        return {"status": "written", "path": path, "size": len(body.content)}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/api/files/upload")
async def upload_file(
    path: str = Form(""),
    file: UploadFile = File(...),
    user: dict = Depends(deps.require_auth),
):
    home = _ensure_user_home(user)
    dest_dir = _validate_path(path or os.path.join(home, "Downloads"), user)
    if not os.path.isdir(dest_dir):
        raise HTTPException(404, "Destination directory not found")
    safe_name = os.path.basename(file.filename or "upload.bin")
    dest_path = _validate_path(os.path.join(dest_dir, safe_name), user)
    try:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"status": "uploaded", "path": dest_path, "filename": safe_name}
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        file.file.close()


@router.get("/api/files/info")
async def file_info(path: str, user: dict = Depends(deps.require_auth)):
    path = _validate_path(path, user)
    if not os.path.exists(path):
        raise HTTPException(404, "Path not found")
    tags_map = _load_tags(user)
    name = os.path.basename(path)
    item = _serialize_item(path, name, tags_map)
    is_dir = os.path.isdir(path)
    children = None
    if is_dir:
        try:
            children = len([n for n in os.listdir(path) if n != ".kabati"])
        except OSError:
            children = 0
    return {
        **item,
        "created": os.path.getctime(path),
        "children": children,
        "parent": os.path.dirname(path),
        "download_url": f"/api/files/download?path={path}" if not is_dir else None,
        "view_url": f"/api/files/view?path={path}" if not is_dir else None,
    }


@router.post("/api/files/duplicate")
async def duplicate_file(body: FileDuplicateRequest, user: dict = Depends(deps.require_auth)):
    src = _validate_path(body.path, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Source not found")
    parent = os.path.dirname(src)
    base = os.path.basename(src)
    stem, ext = os.path.splitext(base) if not os.path.isdir(src) else (base, "")
    candidate = f"{stem} copy{ext}" if ext or not os.path.isdir(src) else f"{base} copy"
    dest = os.path.join(parent, candidate)
    n = 2
    while os.path.exists(dest):
        candidate = f"{stem} copy {n}{ext}" if ext or not os.path.isdir(src) else f"{base} copy {n}"
        dest = os.path.join(parent, candidate)
        n += 1
    dest = _validate_path(dest, user)
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        logger.info("Kabati: %s duplicated %s -> %s", user.get("email"), src, dest)
        return {"status": "duplicated", "source": src, "destination": dest, "name": os.path.basename(dest)}
    except OSError as e:
        raise HTTPException(500, str(e))


@router.post("/api/files/alias")
async def make_alias(path: str, user: dict = Depends(deps.require_auth)):
    src = _validate_path(path, user)
    if not os.path.exists(src):
        raise HTTPException(404, "Source not found")
    parent = os.path.dirname(src)
    base = os.path.basename(src)
    alias_name = f"{base} alias"
    dest = os.path.join(parent, alias_name)
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(parent, f"{base} alias {n}")
        n += 1
    dest = _validate_path(dest, user)
    try:
        os.symlink(src, dest)
        logger.info("Kabati: %s alias %s -> %s", user.get("email"), dest, src)
        return {"status": "aliased", "source": src, "destination": dest, "name": os.path.basename(dest)}
    except OSError as e:
        raise HTTPException(500, str(e))


@router.post("/api/files/compress")
async def compress_files(body: FileCompressRequest, user: dict = Depends(deps.require_auth)):
    paths = [_validate_path(p, user) for p in body.paths]
    for p in paths:
        if not os.path.exists(p):
            raise HTTPException(404, f"Path not found: {p}")

    first = os.path.basename(paths[0])
    stem = os.path.splitext(first)[0] or first
    parent = os.path.dirname(paths[0])
    if body.destination:
        dest = _validate_path(body.destination, user)
    else:
        dest = _validate_path(os.path.join(parent, f"{stem}.zip"), user)

    if os.path.isdir(dest):
        dest = os.path.join(dest, f"{stem}.zip")

    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                if os.path.isfile(p):
                    zf.write(p, os.path.basename(p))
                elif os.path.isdir(p):
                    for dirpath, _, filenames in os.walk(p):
                        for fname in filenames:
                            full = os.path.join(dirpath, fname)
                            arc = os.path.join(os.path.basename(p), os.path.relpath(full, p))
                            zf.write(full, arc)
        logger.info("Kabati: %s compressed %d item(s) -> %s", user.get("email"), len(paths), dest)
        return {"status": "compressed", "destination": dest, "name": os.path.basename(dest), "count": len(paths)}
    except OSError as e:
        raise HTTPException(500, str(e))


@router.get("/api/files/download")
async def download_file(path: str, user: dict = Depends(deps.require_auth)):
    path = _validate_path(path, user)
    if not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=os.path.basename(path), media_type="application/octet-stream")


@router.get("/api/files/view")
async def view_file(path: str, user: dict = Depends(deps.require_auth)):
    path = _validate_path(path, user)
    if not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    mime_type, _ = mimetypes.guess_type(path)
    return FileResponse(path, filename=os.path.basename(path), media_type=mime_type or "application/octet-stream")