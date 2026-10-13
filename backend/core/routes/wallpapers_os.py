"""
Sanaa OS — Wallpaper Catalog & Uploads

Provides categorized desktop wallpapers. Built-in wallpapers reference CSS
classes rendered by the OS shell. Custom wallpapers are uploaded to the user's
OS data directory and served as static files.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.routes import deps
from core.routes.deps import RateLimit

logger = logging.getLogger(__name__)
router = APIRouter()

OS_DATA_DIR = Path(os.environ.get("SANAA_OS_DATA_DIR", "/data/os"))
WALLPAPER_DIR = OS_DATA_DIR / "users"

ALLOWED_WP_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_WP_BYTES = 10 * 1024 * 1024  # 10 MB
THUMBNAIL_SIZE = (400, 400)

# Categories exposed to clients. Order matches the desired UI order.
BUILTIN_CATEGORIES = [
    "sanaa",
    "gradients",
    "abstract",
    "nature",
    "space",
    "dynamic",
    "custom",
]

# Built-in wallpapers. Gradients carry their CSS background value so the
# backend owns the catalog and the OS shell can render previews from it.
BUILTIN_WALLPAPERS: list[dict] = [
    {
        "id": "default",
        "name": "Sanaa Dark",
        "category": "sanaa",
        "type": "gradient",
        "is_uploadable": False,
        "style": "radial-gradient(ellipse 80% 60% at 15% 10%, rgba(47, 129, 247, 0.14) 0%, transparent 55%), radial-gradient(ellipse 70% 50% at 85% 75%, rgba(56, 139, 253, 0.1) 0%, transparent 50%), radial-gradient(ellipse 50% 40% at 50% 100%, rgba(163, 113, 247, 0.06) 0%, transparent 45%), linear-gradient(165deg, #0e1219 0%, #0d1117 42%, #080b10 100%)",
    },
    {
        "id": "ventura",
        "name": "Ventura",
        "category": "gradients",
        "type": "gradient",
        "is_uploadable": False,
        "style": "radial-gradient(ellipse at 10% 30%, rgba(255, 100, 50, 0.25) 0%, transparent 60%), radial-gradient(ellipse at 90% 70%, rgba(255, 60, 80, 0.2) 0%, transparent 60%), radial-gradient(ellipse at 50% 50%, rgba(255, 140, 0, 0.15) 0%, transparent 70%), linear-gradient(135deg, #1a0a00 0%, #2d1010 30%, #1a1020 60%, #0d1117 100%)",
    },
    {
        "id": "monterey",
        "name": "Monterey",
        "category": "gradients",
        "type": "gradient",
        "is_uploadable": False,
        "style": "radial-gradient(ellipse at 20% 80%, rgba(80, 60, 255, 0.2) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(100, 80, 255, 0.15) 0%, transparent 60%), radial-gradient(ellipse at 50% 50%, rgba(60, 100, 255, 0.1) 0%, transparent 70%), linear-gradient(180deg, #0a0e1a 0%, #0d1220 50%, #0a0e14 100%)",
    },
    {
        "id": "aurora",
        "name": "Aurora",
        "category": "abstract",
        "type": "gradient",
        "is_uploadable": False,
        "style": "radial-gradient(ellipse at 30% 20%, rgba(0, 255, 150, 0.12) 0%, transparent 50%), radial-gradient(ellipse at 70% 60%, rgba(0, 200, 255, 0.1) 0%, transparent 50%), radial-gradient(ellipse at 50% 80%, rgba(100, 0, 255, 0.08) 0%, transparent 50%), linear-gradient(180deg, #0a1410 0%, #0d1a14 50%, #0a0e14 100%)",
    },
    {
        "id": "space",
        "name": "Deep Space",
        "category": "space",
        "type": "gradient",
        "is_uploadable": False,
        "style": "radial-gradient(circle at 30% 40%, rgba(100, 80, 200, 0.15) 0%, transparent 40%), radial-gradient(circle at 70% 60%, rgba(200, 80, 150, 0.1) 0%, transparent 40%), radial-gradient(circle at 50% 20%, rgba(80, 150, 255, 0.08) 0%, transparent 40%), linear-gradient(180deg, #080a14 0%, #0d0a1a 50%, #0a0814 100%)",
    },
    {
        "id": "light",
        "name": "Minimal Light",
        "category": "abstract",
        "type": "gradient",
        "is_uploadable": False,
        "style": "radial-gradient(ellipse at 20% 20%, rgba(200, 210, 230, 0.3) 0%, transparent 50%), radial-gradient(ellipse at 80% 80%, rgba(220, 230, 240, 0.2) 0%, transparent 50%), linear-gradient(180deg, #e8ecf1 0%, #dce2ea 100%)",
    },
    {
        "id": "cyber",
        "name": "Cyberpunk",
        "category": "abstract",
        "type": "gradient",
        "is_uploadable": False,
        "style": "radial-gradient(ellipse at 10% 50%, rgba(255, 0, 200, 0.1) 0%, transparent 40%), radial-gradient(ellipse at 90% 50%, rgba(0, 255, 255, 0.08) 0%, transparent 40%), linear-gradient(180deg, #0a0a1a 0%, #1a0a1a 50%, #0a0a14 100%)",
    },
    {
        "id": "dynamic-coast",
        "name": "Coastline",
        "category": "dynamic",
        "type": "dynamic",
        "is_uploadable": False,
    },
]


class WallpaperUploadResponse(BaseModel):
    status: str
    wallpaper: dict


class WallpaperListResponse(BaseModel):
    categories: list[str]
    wallpapers: list[dict]


def _email_slug(email: str) -> str:
    """Create a filesystem-safe slug from an email address."""
    return re.sub(r"[^a-z0-9_-]+", "_", email.lower().strip()).strip("_")[:128] or "unknown"


def _user_wallpaper_dir(email: str) -> Path:
    slug = _email_slug(email)
    user_dir = WALLPAPER_DIR / slug / "Wallpapers"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _safe_filename(name: str) -> str:
    """Sanitize a filename while preserving the extension."""
    name = os.path.basename(name or "upload")
    base, ext = os.path.splitext(name)
    base = re.sub(r"[^\w\-]+", "_", base).strip("_")[:64] or "wallpaper"
    ext = re.sub(r"[^a-zA-Z0-9.]", "", ext).lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        ext = ".jpg"
    return f"{base}{ext}"


def _build_custom_wallpaper(email: str, filename: str, uploaded_at: str) -> dict:
    slug = _email_slug(email)
    base = f"/api/wallpapers/serve/{slug}/{filename}"
    return {
        "id": f"custom:{filename}",
        "name": Path(filename).stem.replace("_", " ").title(),
        "category": "custom",
        "thumbnail_url": base,
        "preview_url": base,
        "type": "image",
        "is_uploadable": True,
        "uploaded_at": uploaded_at,
    }


async def _generate_thumbnail_async(src: Path, dst: Path) -> None:
    """Generate a thumbnail if Pillow is installed; otherwise copy the original."""
    try:
        from PIL import Image

        def _make():
            with Image.open(src) as im:
                im.thumbnail(THUMBNAIL_SIZE)
                im.save(dst, format="JPEG", quality=85)

        await asyncio.to_thread(_make)
    except Exception:
        # Fallback: use the original file as the thumbnail.
        shutil.copy2(src, dst)


def _scan_custom_wallpapers(email: str) -> list[dict]:
    user_dir = _user_wallpaper_dir(email)
    wallpapers = []
    for entry in sorted(user_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.startswith("thumb_"):
            continue
        uploaded_at = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc).isoformat()
        wallpapers.append(_build_custom_wallpaper(email, entry.name, uploaded_at))
    return wallpapers


@router.get("/api/wallpapers")
async def list_wallpapers(request: Request, _rate: None = Depends(RateLimit(limit=120))):
    """Return the full categorized wallpaper catalog plus user's custom uploads."""
    user = deps.require_auth(request)
    email = user["email"]

    custom = await asyncio.to_thread(_scan_custom_wallpapers, email)

    # Merge built-ins with custom uploads. Custom uploads always appear in the
    # "custom" category, even if their name duplicates a built-in id.
    wallpapers = []
    for wp in BUILTIN_WALLPAPERS:
        wp_copy = dict(wp)
        wp_copy["thumbnail_url"] = None
        wp_copy["preview_url"] = None
        wallpapers.append(wp_copy)
    wallpapers.extend(custom)

    return {
        "categories": BUILTIN_CATEGORIES,
        "wallpapers": wallpapers,
    }


@router.get("/api/wallpapers/custom")
async def list_custom_wallpapers(request: Request, _rate: None = Depends(RateLimit(limit=120))):
    """List only the current user's uploaded wallpapers."""
    user = deps.require_auth(request)
    custom = await asyncio.to_thread(_scan_custom_wallpapers, user["email"])
    return {"wallpapers": custom}


@router.post("/api/wallpapers/upload")
async def upload_wallpaper(
    request: Request,
    file: UploadFile = File(...),
    name: Optional[str] = None,
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Upload an image to use as a custom wallpaper."""
    user = deps.require_auth(request)
    email = user["email"]

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_WP_TYPES:
        raise HTTPException(
            400,
            f"Invalid file type. Allowed: {', '.join(sorted(ALLOWED_WP_TYPES))}",
        )

    user_dir = _user_wallpaper_dir(email)
    ext = mimetypes.guess_extension(content_type) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"

    filename = _safe_filename(file.filename or "wallpaper")
    if not any(filename.lower().endswith(e) for e in {".jpg", ".jpeg", ".png", ".gif", ".webp"}):
        filename = f"{Path(filename).stem}{ext}"

    target_path = user_dir / filename

    # Read limited bytes to avoid memory blow-out
    contents = await file.read(MAX_WP_BYTES + 1)
    if len(contents) > MAX_WP_BYTES:
        raise HTTPException(413, f"Wallpaper must be under {MAX_WP_BYTES // (1024 * 1024)} MB")

    target_path.write_bytes(contents)

    # Best-effort thumbnail generation; if PIL is unavailable the original is kept.
    thumb_path = user_dir / f"thumb_{filename}"
    try:
        await _generate_thumbnail_async(target_path, thumb_path)
    except Exception as exc:
        logger.warning(f"Thumbnail generation failed for {target_path}: {exc}")

    uploaded_at = datetime.now(timezone.utc).isoformat()
    wallpaper = _build_custom_wallpaper(email, filename, uploaded_at)

    return {"status": "uploaded", "wallpaper": wallpaper}


@router.get("/api/wallpapers/serve/{email_slug}/{filename}")
async def serve_wallpaper(
    email_slug: str,
    filename: str,
    request: Request,
    thumb: bool = False,
    _rate: None = Depends(RateLimit(limit=240)),
):
    """Serve a user's custom wallpaper (or its thumbnail) by slug and filename."""
    deps.require_auth(request)

    user_dir = WALLPAPER_DIR / email_slug / "Wallpapers"
    if not user_dir.exists():
        raise HTTPException(404, "Wallpaper not found")

    target = user_dir / filename
    if thumb:
        thumb_candidate = user_dir / f"thumb_{filename}"
        if thumb_candidate.exists():
            target = thumb_candidate

    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Wallpaper not found")

    return FileResponse(target)
