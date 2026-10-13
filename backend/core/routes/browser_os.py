"""
Sanaa OS — Authenticated web browser proxy
Loads external sites that block iframe embedding (Google, soko24.co, etc.)
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse, quote

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 SanaaOS/1.0"
)
MAX_BODY_BYTES = 2_500_000
TIMEOUT_SECONDS = 25
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _validate_target(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Only http and https URLs are allowed")
    if not parsed.netloc:
        raise HTTPException(400, "Invalid URL")

    host = parsed.hostname or ""
    if host.lower() in BLOCKED_HOSTS:
        raise HTTPException(403, "Target host is not allowed")

    try:
        addr = ipaddress.ip_address(host)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        ):
            raise HTTPException(403, "Private network targets are not allowed")
    except ValueError:
        if host.endswith(".local") or host.endswith(".internal"):
            raise HTTPException(403, "Internal hostnames are not allowed")

    return urlunparse(parsed)


def _proxy_url(request: Request, target: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/browser/proxy?url={quote(target, safe='')}"


def _rewrite_link(request: Request, base_url: str, href: str) -> str:
    if not href or href.startswith("#"):
        return href
    if href.startswith("javascript:") or href.startswith("data:"):
        return "#"
    if href.startswith("mailto:") or href.startswith("tel:"):
        return href

    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return href

    return _proxy_url(request, absolute)


def _rewrite_html(request: Request, body: str, final_url: str) -> str:
    soup = BeautifulSoup(body, "html.parser")

    if soup.head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    base_tag = soup.find("base")
    if base_tag is None:
        base_tag = soup.new_tag("base")
        soup.head.insert(0, base_tag)
    base_tag["href"] = final_url

    for tag_name, attr in (("a", "href"), ("form", "action"), ("area", "href")):
        for node in soup.find_all(tag_name):
            val = node.get(attr)
            if not val:
                continue
            node[attr] = _rewrite_link(request, final_url, val)

    banner = soup.new_tag("div")
    banner["style"] = (
        "position:sticky;top:0;z-index:2147483647;padding:6px 12px;"
        "background:#0d1117;color:#8b949e;font:12px/1.4 Inter,system-ui,sans-serif;"
        "border-bottom:1px solid #30363d;display:flex;gap:10px;align-items:center;"
    )
    banner.string = f"Sanaa Browser · {final_url}"
    if soup.body:
        soup.body.insert(0, banner)
    else:
        soup.insert(0, banner)

    return str(soup)


@router.get("/api/browser/proxy")
async def browser_proxy(
    request: Request,
    url: str = Query(..., min_length=4, max_length=4000),
    user: dict = Depends(require_auth),
):
    """Fetch and rewrite an external page for in-OS browsing."""
    target = _validate_target(url)
    email = user.get("email", "unknown")

    logger.info("Browser proxy %s -> %s", email, target)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=TIMEOUT_SECONDS,
            headers=headers,
        ) as client:
            response = await client.get(target)
    except httpx.TimeoutException:
        raise HTTPException(408, "Site took too long to respond")
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Could not reach site: {exc}")

    final_url = str(response.url)
    content_type = (response.headers.get("content-type") or "").lower()

    if response.status_code >= 400:
        raise HTTPException(response.status_code, f"Remote site returned HTTP {response.status_code}")

    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return RedirectResponse(final_url, status_code=302)

    raw = response.content[:MAX_BODY_BYTES]
    try:
        body = raw.decode(response.encoding or "utf-8", errors="replace")
    except Exception:
        body = raw.decode("utf-8", errors="replace")

    rewritten = _rewrite_html(request, body, final_url)
    return HTMLResponse(
        content=rewritten,
        headers={
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "frame-ancestors 'self'",
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/browser/resolve")
async def browser_resolve(
    q: str = Query(..., min_length=1, max_length=500),
    user: dict = Depends(require_auth),
):
    """Resolve user input to a URL or search engine query."""
    text = q.strip()
    if re.match(r"^https?://", text, re.I):
        url = _validate_target(text)
        mode = "url"
    elif re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", text):
        url = _validate_target(f"https://{text}")
        mode = "url"
    elif "." in text and " " not in text and not text.startswith("."):
        try:
            url = _validate_target(f"https://{text}")
            mode = "url"
        except HTTPException:
            url = f"https://www.google.com/search?q={quote(text)}"
            mode = "search"
    else:
        url = f"https://www.google.com/search?q={quote(text)}"
        mode = "search"

    return {
        "input": text,
        "url": url,
        "mode": mode,
        "proxy": f"/api/browser/proxy?url={quote(url, safe='')}",
    }