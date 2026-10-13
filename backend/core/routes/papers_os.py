"""
Sanaa OS — Papers Proxy (paperless-ngx integration)
Proxies authenticated OS requests to paperless-ngx API with service token.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response

from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

# paperless-ngx internal endpoint
PAPERLESS_BASE = "http://127.0.0.1:8105"
PAPERLESS_API = f"{PAPERLESS_BASE}/papers/api"
PAPERLESS_HOST = "ai.sanaa.co"
PAPERLESS_ADMIN_USER = "admin@sanaa.co"
PAPERLESS_ADMIN_PASS = "SanaaPapers2024!"

_service_token: Optional[str] = None


async def _get_paperless_token() -> str:
    """Authenticate with paperless-ngx and cache the token."""
    global _service_token
    if _service_token:
        return _service_token

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{PAPERLESS_BASE}/papers/api/token/",
                json={"username": PAPERLESS_ADMIN_USER, "password": PAPERLESS_ADMIN_PASS},
                headers={"Host": PAPERLESS_HOST},
            )
            resp.raise_for_status()
            data = resp.json()
            _service_token = data.get("token")
            if not _service_token:
                raise ValueError("No token in response")
            logger.info("Paperless-ngx service token acquired")
            return _service_token
        except Exception as e:
            logger.error(f"Failed to get paperless token: {e}")
            raise HTTPException(503, f"Papers backend unavailable: {e}")


def _paperless_headers() -> dict:
    """Build headers with service token."""
    return {
        "Authorization": f"Token {_service_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _proxy_request(
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    content: Optional[bytes] = None,
    headers: Optional[dict] = None,
    stream: bool = False,
):
    """Proxy a request to paperless-ngx API."""
    await _get_paperless_token()
    url = f"{PAPERLESS_API}/{path.lstrip('/')}"
    req_headers = _paperless_headers()
    req_headers["Host"] = PAPERLESS_HOST
    if headers:
        req_headers.update(headers)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                content=content,
                headers=req_headers,
                follow_redirects=True,
            )
            if stream:
                return StreamingResponse(
                    response.aiter_raw(),
                    status_code=response.status_code,
                    headers={k: v for k, v in response.headers.items() if k.lower() in ["content-type", "content-disposition"]},
                )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers={k: v for k, v in response.headers.items() if k.lower() in ["content-type", "content-disposition"]},
            )
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to paperless-ngx: {e}")
            raise HTTPException(503, "Papers backend is not running")
        except Exception as e:
            logger.error(f"Paperless proxy error: {e}")
            raise HTTPException(502, f"Papers backend error: {e}")


# ========== PROXY ENDPOINTS ==========

@router.get("/api/papers/{path:path}")
async def papers_get(path: str, request: Request, user: dict = Depends(require_auth)):
    """Proxy GET requests to paperless-ngx API."""
    return await _proxy_request("GET", path, params=dict(request.query_params))


@router.post("/api/papers/{path:path}")
async def papers_post(path: str, request: Request, user: dict = Depends(require_auth)):
    """Proxy POST requests to paperless-ngx API."""
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        # For file uploads, forward raw body with original content-type
        return await _proxy_request(
            "POST", path,
            content=body,
            headers={"Content-Type": content_type},
        )
    try:
        json_body = await request.json()
    except Exception:
        json_body = None
    return await _proxy_request("POST", path, json_body=json_body)


@router.put("/api/papers/{path:path}")
async def papers_put(path: str, request: Request, user: dict = Depends(require_auth)):
    """Proxy PUT requests to paperless-ngx API."""
    try:
        json_body = await request.json()
    except Exception:
        json_body = None
    return await _proxy_request("PUT", path, json_body=json_body)


@router.patch("/api/papers/{path:path}")
async def papers_patch(path: str, request: Request, user: dict = Depends(require_auth)):
    """Proxy PATCH requests to paperless-ngx API."""
    try:
        json_body = await request.json()
    except Exception:
        json_body = None
    return await _proxy_request("PATCH", path, json_body=json_body)


@router.delete("/api/papers/{path:path}")
async def papers_delete(path: str, request: Request, user: dict = Depends(require_auth)):
    """Proxy DELETE requests to paperless-ngx API."""
    return await _proxy_request("DELETE", path, params=dict(request.query_params))


# ========== STREAMING DOWNLOADS ==========

@router.get("/api/papers/documents/{doc_id}/download")
async def papers_download(doc_id: int, request: Request, user: dict = Depends(require_auth)):
    """Stream document download from paperless-ngx."""
    return await _proxy_request("GET", f"/documents/{doc_id}/download/", stream=True)


@router.get("/api/papers/documents/{doc_id}/preview")
async def papers_preview(doc_id: int, request: Request, user: dict = Depends(require_auth)):
    """Stream document preview from paperless-ngx."""
    return await _proxy_request("GET", f"/documents/{doc_id}/preview/", stream=True)


@router.get("/api/papers/documents/{doc_id}/thumb")
async def papers_thumb(doc_id: int, request: Request, user: dict = Depends(require_auth)):
    """Stream document thumbnail from paperless-ngx."""
    return await _proxy_request("GET", f"/documents/{doc_id}/thumb/", stream=True)
