"""
Sanaa AI — Channel routes: WhatsApp bridge, webhook, integrations.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from core.config import get_settings
from core.routes import deps
from core.routes.deps import require_auth, verify_whatsapp_api_key

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


@router.get("/api/channels")
async def list_channels(request: Request, user: dict = Depends(require_auth)):
    """Get status of all registered channels."""
    from core.routes import deps

    status = deps.router_instance.get_channel_status()

    if deps.whatsapp_adapter:
        status["whatsapp"]["detail"] = deps.whatsapp_adapter.get_status()
    if deps.telegram_adapter:
        status["telegram"]["detail"] = deps.telegram_adapter.get_status()

    return status


@router.post("/api/channels/whatsapp/pair")
async def whatsapp_pair(request: Request, user: dict = Depends(require_auth)):
    """Initiate WhatsApp QR pairing."""
    from core.routes import deps

    if not deps.whatsapp_adapter:
        raise HTTPException(400, "WhatsApp channel not enabled")
    if deps.whatsapp_adapter.is_connected():
        return {"status": "already_connected", "phone": deps.whatsapp_adapter.phone_number}
    await deps.whatsapp_adapter._send({"type": "connect"})
    return {
        "status": "pairing",
        "qr": deps.whatsapp_adapter.current_qr,
        "message": "Scan QR code with WhatsApp",
    }


@router.get("/api/channels/whatsapp/qr")
async def whatsapp_qr(request: Request, user: dict = Depends(require_auth)):
    """Get current WhatsApp QR code for dashboard display."""
    from core.routes import deps

    if not deps.whatsapp_adapter:
        raise HTTPException(400, "WhatsApp channel not enabled")
    return {
        "qr": deps.whatsapp_adapter.current_qr,
        "connected": deps.whatsapp_adapter.is_connected(),
        "phone": deps.whatsapp_adapter.phone_number,
    }


# ==================== INTEGRATIONS API ====================

@router.get("/api/integrations/whatsapp-saas/status")
async def whatsapp_saas_status(user: dict = Depends(require_auth)):
    if not settings.whatsapp_saas_enabled:
        raise HTTPException(400, "WhatsApp SaaS integration is disabled")
    return await deps.whatsapp_saas.status()


@router.get("/api/integrations/whatsapp-saas/routes")
async def whatsapp_saas_routes(user: dict = Depends(require_auth)):
    if not settings.whatsapp_saas_enabled:
        raise HTTPException(400, "WhatsApp SaaS integration is disabled")
    routes = deps.whatsapp_saas.discover_api_routes()
    return {"count": len(routes), "routes": routes}


# ==================== WHATSAPP API BRIDGE ====================

@router.get("/api/whatsapp/status")
async def wa_bridge_status(token: str = Depends(verify_whatsapp_api_key)):
    """Health status of WhatsJet."""
    return await deps.whatsapp_saas.status()


@router.post("/api/whatsapp/send-message")
async def wa_bridge_send_message(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send a text message."""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    message = body.get("message")
    if not phone or not message:
        raise HTTPException(400, "phone and message are required")
    return await deps.whatsapp_saas.send_message(phone, message)


@router.post("/api/whatsapp/send-media")
async def wa_bridge_send_media(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send media."""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    media_url = body.get("media_url") or body.get("media_link")
    media_type = body.get("type", "image")
    caption = body.get("caption", "")
    if not phone or not media_url:
        raise HTTPException(400, "phone and media_url are required")
    return await deps.whatsapp_saas.send_media_message(phone, media_url, media_type, caption)


@router.post("/api/whatsapp/send-template")
async def wa_bridge_send_template(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send a template."""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    template_name = body.get("template_name")
    if not phone or not template_name:
        raise HTTPException(400, "phone and template_name are required")
    return await deps.whatsapp_saas.send_template_message(
        phone, template_name,
        language=body.get("language", "en"),
        components=body.get("components"),
    )


@router.post("/api/whatsapp/send-interactive")
async def wa_bridge_send_interactive(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send interactive message (buttons/lists)."""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    if not phone:
        raise HTTPException(400, "phone is required")
    return await deps.whatsapp_saas.send_interactive_message(phone, body)


@router.post("/api/whatsapp/send-carousel")
async def wa_bridge_send_carousel(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send carousel template."""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    template_name = body.get("template_name")
    if not phone or not template_name:
        raise HTTPException(400, "phone and template_name are required")
    return await deps.whatsapp_saas.send_carousel_template(
        phone, template_name,
        language=body.get("language", "en"),
        components=body.get("components"),
    )


@router.post("/api/whatsapp/contacts")
async def wa_bridge_create_contact(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Create a contact."""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    if not phone:
        raise HTTPException(400, "phone is required")
    return await deps.whatsapp_saas.create_contact(
        phone,
        first_name=body.get("first_name", ""),
        last_name=body.get("last_name", ""),
        email=body.get("email", ""),
        groups=body.get("groups", ""),
    )


@router.put("/api/whatsapp/contacts/{phone}")
async def wa_bridge_update_contact(phone: str, request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Update a contact by phone number."""
    body = await request.json()
    return await deps.whatsapp_saas.update_contact(phone, **body)


@router.get("/api/whatsapp/contacts")
async def wa_bridge_list_contacts(
    page: int = 1, per_page: int = 50,
    token: str = Depends(verify_whatsapp_api_key),
):
    """List contacts with pagination."""
    return await deps.whatsapp_saas.get_contacts(page=page, per_page=per_page)


@router.get("/api/whatsapp/contacts/{phone}")
async def wa_bridge_get_contact(phone: str, token: str = Depends(verify_whatsapp_api_key)):
    """Get a single contact by phone number or email."""
    return await deps.whatsapp_saas.get_contact(phone)


@router.post("/api/whatsapp/contacts/assign")
async def wa_bridge_assign_member(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Assign a team member."""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    user_id = body.get("user_id")
    if not phone or not user_id:
        raise HTTPException(400, "phone and user_id are required")
    return await deps.whatsapp_saas.assign_team_member(phone, int(user_id))


# ==================== WHATSAPP WEBHOOK (AI BOT) ====================

@router.post("/api/whatsapp/webhook/incoming")
async def wa_webhook_incoming(request: Request, background_tasks: BackgroundTasks):
    """
    Receive forwarded webhooks from WhatsJet.
    Processes incoming messages through Sanaa AI Brain for auto-replies.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not await deps.rate_limiter.check(f"webhook:{client_ip}", limit=60):
        return JSONResponse(status_code=429, content={"status": "rate_limited"})

    webhook_token = request.headers.get("X-Webhook-Token") or request.query_params.get("verify_token")
    if settings.whatsapp_webhook_secret and webhook_token != settings.whatsapp_webhook_secret:
        logger.warning(f"WhatsApp webhook: invalid token from {request.client.host if request.client else 'unknown'}")
        return JSONResponse(status_code=403, content={"status": "forbidden", "reason": "invalid webhook token"})

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid json"}

    entry = (payload.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value", {})
    messages = value.get("messages", [])

    if not messages:
        return {"status": "ok", "reason": "no messages"}

    for msg in messages:
        phone = msg.get("from", "")
        msg_type = msg.get("type", "")
        text = ""
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            text = (interactive.get("button_reply") or interactive.get("list_reply") or {}).get("title", "")

        if text and phone:
            background_tasks.add_task(_process_ai_reply, phone, text)

    return {"status": "ok", "processed": len(messages)}


async def _process_ai_reply(phone: str, text: str):
    """Background task: run incoming WhatsApp message through AI Brain and reply."""
    try:
        session_id = f"whatsapp:{phone}"
        response = await deps.brain.think(
            prompt=text,
            complexity="auto",
            session_id=session_id,
            channel="whatsapp",
        )
        if response and deps.whatsapp_saas.vendor_uid:
            result = await deps.whatsapp_saas.send_message(phone, response)
            logger.info(f"AI reply sent to {phone}: {result.get('status', 'unknown')}")
        else:
            logger.warning(f"Cannot reply to {phone}: no vendor_uid configured or empty response")
    except Exception as e:
        logger.error(f"AI reply to {phone} failed: {e}")
