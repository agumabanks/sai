"""
Sanaa OS — Soko 24 command center API (proxies soko_agent skill).
"""

from fastapi import APIRouter, Depends, Query, HTTPException

from core.config import get_settings
from core.routes import deps
from core.routes.deps import require_auth
from core.services import soko_sso

router = APIRouter()


async def _run_soko(action: str, user: dict, **kwargs) -> dict:
    await deps.brain.ensure_skills_loaded()
    args = {"action": action, **kwargs}
    return await deps.brain.execute_skill(
        name="soko_agent",
        args=args,
        session_id=f"os:soko:{user.get('email', 'web')}",
        channel="web",
        sender_id=user.get("email", "web_user"),
        execution_mode="manual",
        sender_role=user.get("role", "operator"),
    )


def _admin_meta() -> dict:
    s = get_settings()
    base = f"{s.soko_site_url.rstrip('/')}{s.soko_admin_path}"
    return {
        "site_url": s.soko_site_url.rstrip("/"),
        "admin_base": base,
    }


def _admin_links() -> dict:
    s = get_settings()
    base = f"{s.soko_site_url.rstrip('/')}{s.soko_admin_path}"
    site = s.soko_site_url.rstrip("/")
    return {
        "dashboard": base,
        "all_orders": f"{base}/all_orders",
        "unpaid_orders": f"{base}/unpaid_orders",
        "seller_orders": f"{base}/seller_orders",
        "sellers": f"{base}/sellers",
        "products_all": f"{base}/products/all",
        "products_admin": f"{base}/products/admin",
        "customers": f"{base}/customers",
        "categories": f"{base}/categories",
        "crm_contacts": f"{base}/crm/contacts",
        "soko_studio": f"{base}/soko-studio",
        "storefront": site,
        "seller_os": f"{site}/seller/os",
        "seller_login": f"{site}/seller/login",
        "customer_dashboard": f"{site}/dashboard",
        "admin_login": f"{site}/admin/login",
    }


def _soko_persona(user: dict) -> dict:
    role = str(user.get("role", "operator")).lower()
    if role == "viewer":
        return {
            "role": role,
            "default_surface": "store",
            "default_tab": "pulse",
            "surfaces": ["command", "store"],
            "tabs": ["pulse"],
            "can_operate": False,
        }
    if role == "seller":
        return {
            "role": role,
            "default_surface": "seller",
            "default_tab": "pulse",
            "surfaces": ["seller", "store"],
            "tabs": [],
            "can_operate": False,
        }
    return {
        "role": role,
        "default_surface": "command",
        "default_tab": "pulse",
        "surfaces": ["command", "seller", "store"],
        "tabs": ["pulse", "orders", "sellers", "products", "distressed"],
        "can_operate": True,
    }


def _platform_surfaces() -> dict:
    links = _admin_links()
    site = get_settings().soko_site_url.rstrip("/")
    return {
        "command": {
            "id": "command",
            "label": "Command",
            "description": "Analytics, orders, alerts, and ops",
            "type": "native",
            "icon": "chart",
        },
        "admin": {
            "id": "admin",
            "label": "Admin",
            "description": "Full Laravel platform administration",
            "type": "embed",
            "url": links["dashboard"],
            "open_url": links["dashboard"],
            "login_url": links["admin_login"],
            "icon": "shield",
        },
        "seller": {
            "id": "seller",
            "label": "Seller OS",
            "description": "Seller business operating system",
            "type": "embed",
            "url": links["seller_os"],
            "open_url": links["seller_os"],
            "login_url": links["seller_login"],
            "icon": "store",
        },
        "store": {
            "id": "store",
            "label": "Store",
            "description": "Customer marketplace storefront",
            "type": "embed",
            "url": links["storefront"],
            "open_url": links["storefront"],
            "icon": "cart",
        },
        "customers": {
            "id": "customers",
            "label": "Buyers",
            "description": "Registered marketplace customers",
            "type": "native",
            "admin_url": links["customers"],
            "icon": "users",
        },
    }


@router.get("/api/soko/links")
async def soko_admin_links(user: dict = Depends(require_auth)):
    """Deep links into Soko 24 Laravel admin."""
    return {
        "success": True,
        **_admin_meta(),
        "links": _admin_links(),
    }


@router.get("/api/soko/platform")
async def soko_platform(user: dict = Depends(require_auth)):
    """Soko 24 platform surfaces: admin, seller OS, storefront, buyers."""
    result = await _run_soko("platform_surfaces", user)
    data = result.get("data") or {}
    return {
        "success": result.get("success", False),
        "surfaces": data.get("surfaces") or _platform_surfaces(),
        "admin_links": data.get("admin_links") or _admin_links(),
        "counts": data.get("counts") or {},
        "persona": _soko_persona(user),
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/pulse")
async def soko_pulse(
    user: dict = Depends(require_auth),
    limit: int = Query(12, ge=1, le=30),
):
    """Lightweight pulse: revenue, needs-you queue, dock badge count."""
    result = await _run_soko("pulse", user, limit=limit)
    data = result.get("data") or {}
    return {
        "success": result.get("success", False),
        "summary": data.get("summary") or {},
        "needs_you": data.get("needs_you") or [],
        "recent_orders": data.get("recent_orders") or [],
        "badge": int(data.get("badge") or 0),
        "admin_links": data.get("admin_links") or _admin_links(),
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/sso")
async def soko_sso_urls(
    user: dict = Depends(require_auth),
    surface: str = Query("admin"),
    seller_id: int | None = Query(None),
):
    """Signed SSO URLs for iframe embed (proxy-safe)."""
    email = user.get("email", "")
    sso_surface = surface
    if surface == "admin":
        sso_surface = "admin"
    elif surface not in ("seller", "store"):
        sso_surface = "admin"

    urls = soko_sso.sso_urls(email, surface=sso_surface, seller_id=seller_id)
    return {
        "success": urls.get("available", False),
        **urls,
        "seller_id": seller_id,
        **_admin_meta(),
    }


@router.get("/api/soko/bridge")
async def soko_bridge(
    user: dict = Depends(require_auth),
    surface: str = Query("admin"),
    seller_id: int | None = Query(None),
):
    """Embed bridge URLs (proxy-safe) for Admin / Seller / Store surfaces."""
    links = _admin_links()
    site = get_settings().soko_site_url.rstrip("/")
    base = f"{site}{get_settings().soko_admin_path}"

    embed = {
        "admin": links["dashboard"],
        "seller": links["seller_os"],
        "store": links["storefront"],
    }
    url = embed.get(surface, links["dashboard"])
    if surface == "seller" and seller_id:
        url = f"{base}/sellers/login/{seller_id}"

    sso = soko_sso.sso_urls(user.get("email", ""), surface=surface, seller_id=seller_id)
    embed_url = sso.get("proxy_embed_url") if sso.get("available") else url
    if sso.get("available") and embed_url:
        url = embed_url

    return {
        "success": True,
        "surface": surface,
        "embed_url": url,
        "open_url": sso.get("open_url") or url,
        "sso": sso,
        "login_url": links.get("admin_login") if surface == "admin" else links.get("seller_login"),
        "seller_id": seller_id,
        **_admin_meta(),
    }


@router.post("/api/soko/products/{product_id}/approve")
async def soko_approve_product(product_id: int, user: dict = Depends(require_auth)):
    """Approve a product in the moderation queue without opening Laravel admin."""
    role = str(user.get("role", "")).lower()
    if role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Operator access required")
    result = await _run_soko("approve_product", user, product_id=product_id)
    data = result.get("data") or {}
    return {
        "success": result.get("success", False),
        "product_id": product_id,
        "status": data.get("status"),
        "name": data.get("name"),
        "error": result.get("error"),
        "output": result.get("output"),
    }


@router.post("/api/soko/sellers/{seller_id}/verify")
async def soko_verify_seller(seller_id: int, user: dict = Depends(require_auth)):
    """Verify a pending seller without opening Laravel admin."""
    role = str(user.get("role", "")).lower()
    if role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Operator access required")
    result = await _run_soko("verify_seller", user, seller_id=seller_id)
    return {
        "success": result.get("success", False),
        "seller_id": seller_id,
        "status": (result.get("data") or {}).get("status"),
        "error": result.get("error"),
        "output": result.get("output"),
    }


@router.get("/api/soko/customers")
async def soko_customers(
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
):
    """Marketplace buyers (user_type=customer)."""
    result = await _run_soko("list_customers", user, limit=limit, search=search or "")
    customers = (result.get("data") or {}).get("customers") or []
    return {
        "success": result.get("success", False),
        "customers": customers,
        "count": len(customers),
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/dashboard")
async def soko_dashboard(
    user: dict = Depends(require_auth),
    limit: int = Query(20, ge=1, le=50),
):
    """Full command-center payload: KPIs, alerts, recent orders, queues."""
    result = await _run_soko("dashboard", user, limit=limit)
    data = result.get("data") or {}
    return {
        "success": result.get("success", False),
        "summary": data.get("summary") or {},
        "health": data.get("health") or {},
        "metrics": data.get("metrics") or {},
        "alerts": data.get("alerts") or [],
        "recent_orders": data.get("recent_orders") or [],
        "pending_sellers": data.get("pending_sellers") or [],
        "distressed_sellers": data.get("distressed_sellers") or [],
        "admin_links": data.get("admin_links") or {},
        "surfaces": data.get("surfaces") or _platform_surfaces(),
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/overview")
async def soko_overview(user: dict = Depends(require_auth)):
    """Platform health + order metrics for Soko Command OS app."""
    health = await _run_soko("platform_health", user)
    metrics = await _run_soko("order_metrics", user)
    health_data = health.get("data") or {}
    metrics_data = metrics.get("data") or {}
    recent = metrics_data.get("recent_orders") or []
    total_orders = sum(int(r.get("count") or 0) for r in recent)
    return {
        "success": health.get("success") and metrics.get("success"),
        "health": health_data,
        "metrics": metrics_data,
        "summary": {
            "active_sellers": health_data.get("active_sellers", 0),
            "active_products": health_data.get("active_products", 0),
            "total_users": health_data.get("total_users", 0),
            "pending_sellers": health_data.get("pending_sellers", 0),
            "product_queue": health_data.get("product_queue", 0),
            "total_orders_7d": total_orders,
            "daily_revenue": metrics_data.get("daily_revenue", 0),
        },
        **_admin_meta(),
        "errors": [e for e in [health.get("error"), metrics.get("error")] if e],
    }


@router.get("/api/soko/orders")
async def soko_orders(
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=100),
    payment: str | None = Query(None),
    delivery: str | None = Query(None),
    search: str | None = Query(None),
):
    """Recent orders with optional filters."""
    result = await _run_soko(
        "recent_orders",
        user,
        limit=limit,
        payment_status=payment,
        delivery_status=delivery,
        search=search or "",
    )
    orders = (result.get("data") or {}).get("orders") or []
    return {
        "success": result.get("success", False),
        "orders": orders,
        "count": len(orders),
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/sellers")
async def soko_sellers(
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=100),
    verification: int | None = Query(None, ge=0, le=1),
    search: str | None = Query(None),
):
    """Seller registry with verification status."""
    kwargs = {"limit": limit, "search": search or ""}
    if verification is not None:
        kwargs["verification"] = verification
    result = await _run_soko("list_sellers", user, **kwargs)
    sellers = (result.get("data") or {}).get("sellers") or []
    return {
        "success": result.get("success", False),
        "sellers": sellers,
        "count": len(sellers),
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/products")
async def soko_products(
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
):
    """Unpublished or unapproved products."""
    result = await _run_soko("product_queue", user, limit=limit, search=search or "")
    products = (result.get("data") or {}).get("products") or []
    return {
        "success": result.get("success", False),
        "products": products,
        "count": len(products),
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/alerts")
async def soko_alerts(user: dict = Depends(require_auth)):
    """Actionable admin alerts."""
    result = await _run_soko("admin_alerts", user)
    return {
        "success": result.get("success", False),
        "alerts": (result.get("data") or {}).get("alerts") or [],
        **_admin_meta(),
        "error": result.get("error"),
    }


@router.get("/api/soko/distressed")
async def soko_distressed(
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=100),
):
    """Sellers with delayed pending orders."""
    result = await _run_soko("distressed_sellers", user, limit=limit)
    sellers = (result.get("data") or {}).get("sellers") or []
    normalized = [
        {
            "seller_id": s.get("seller_id"),
            "name": s.get("shop_name") or s.get("name") or "Unknown",
            "phone": s.get("phone"),
            "orders": s.get("pending_orders", 0),
            "status": "distressed",
            "revenue": 0,
        }
        for s in sellers
    ]
    return {
        "success": result.get("success", False),
        "sellers": normalized,
        "count": len(normalized),
        "output": result.get("output"),
        **_admin_meta(),
        "error": result.get("error"),
    }