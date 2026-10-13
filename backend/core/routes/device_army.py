"""
Sanaa Device Army — Route handlers for device registration, pairing, tasking, and telemetry.

All device-facing endpoints use bearer token auth (worker_token), not session auth.
Dashboard/admin endpoints use session auth (require_auth).
"""

import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, Query

from core.database import (
    Device, DevicePairing, DeviceTask, DeviceCommand, DeviceLog,
    AsyncSessionLocal, utcnow,
)
from core.routes import deps
from core.routes.deps import require_auth, verify_api_key
from core.utils.crypto import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── HELPERS ──────────────────────────────────────────────────────────

def _generate_id() -> str:
    return uuid.uuid4().hex[:16]


def _generate_token() -> str:
    return "da_" + secrets.token_hex(32)


def _generate_pairing_key() -> str:
    return "pk_" + secrets.token_hex(32)


async def _get_device_by_token(request: Request) -> Device:
    """Extract worker_token from Authorization header and return Device."""
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing worker token")
    device = await Device.find_by_token(token)
    if not device:
        raise HTTPException(401, "Invalid worker token")
    if device.is_revoked:
        raise HTTPException(403, "Device is revoked")
    return device


# ─── REGISTRATION & PAIRING ────────────────────────────────────────────

@router.post("/api/device-army/register")
async def register_device(request: Request):
    """Step 1: Device submits fingerprint + hardware info, receives pairing key."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    fingerprint = body.get("fingerprint")
    if not fingerprint:
        raise HTTPException(400, "Missing 'fingerprint' field")

    # Optional account linkage supplied by authenticated device app
    owner_email = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.replace("Bearer ", "").strip()
        device = await Device.find_by_token(token)
        if device and device.owner_email:
            owner_email = device.owner_email
    if not owner_email:
        owner_email = (body.get("owner_email") or "").strip().lower() or None

    # Check if already registered
    existing = await Device.find_by_fingerprint(fingerprint)
    if existing:
        raise HTTPException(409, "Device already registered — use /pair to complete pairing")

    # Generate pairing key (valid 15 minutes)
    pairing_key = _generate_pairing_key()
    await DevicePairing.create(
        pairing_key=pairing_key,
        device_fingerprint=fingerprint,
        owner_email=owner_email,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )

    return {
        "status": "pairing_key_generated",
        "pairing_key": pairing_key,
        "expires_in_seconds": 900,
        "message": "Use this key within 15 minutes to complete pairing via /api/device-army/pair",
    }


@router.post("/api/device-army/pair")
async def pair_device(request: Request):
    """Step 2: Device submits pairing key + device info, receives worker credentials."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    pairing_key = body.get("pairing_key")
    display_name = body.get("display_name", "").strip()
    codename = body.get("codename", "").strip()
    worker_role = body.get("worker_role", "worker").strip()
    public_key = body.get("public_key", "")
    device_info = body.get("device_info", {})

    if not pairing_key:
        raise HTTPException(400, "Missing 'pairing_key'")

    # Validate pairing key
    pairing = await DevicePairing.find_valid(pairing_key)
    if not pairing:
        raise HTTPException(401, "Invalid or expired pairing key")

    # Generate permanent credentials
    device_id = f"da-{_generate_id()}"
    worker_token = _generate_token()
    encryption_key = secrets.token_hex(32)

    # Create device record, linking to the account that initiated pairing
    device = await Device.create(
        device_id=device_id,
        device_fingerprint=pairing.device_fingerprint,
        owner_email=pairing.owner_email,
        display_name=display_name or f"Device-{device_id[:8]}",
        codename=codename,
        worker_role=worker_role,
        device_model=device_info.get("model", ""),
        android_version=device_info.get("android_version", ""),
        cpu_info=device_info.get("cpu"),
        ram_mb=device_info.get("ram_mb"),
        storage_mb=device_info.get("storage_mb"),
        battery_health=device_info.get("battery_health"),
        sensors=device_info.get("sensors"),
        connectivity_capabilities=device_info.get("connectivity"),
        worker_token=worker_token,  # TODO: encrypt at rest
        encryption_key=encryption_key,
        public_key=public_key,
        status="online",
        last_heartbeat=utcnow(),
        ip_address=request.client.host if request.client else None,
        app_version=device_info.get("app_version", ""),
    )

    # Mark pairing as used
    async with AsyncSessionLocal() as session:
        pairing.status = "paired"
        pairing.paired_at = utcnow()
        pairing.device_id = device_id
        await session.merge(pairing)
        await session.commit()

    logger.info(f"Device paired: {device_id} ({display_name}) as {worker_role}")

    return {
        "status": "paired",
        "device_id": device_id,
        "worker_token": worker_token,
        "encryption_key": encryption_key,
        "ws_endpoint": "/ws/device/{device_id}",
    }


# ─── HEARTBEAT ──────────────────────────────────────────────────────────

@router.post("/api/device-army/heartbeat")
async def device_heartbeat(request: Request):
    """Receive heartbeat/telemetry from a paired device. Returns pending tasks + commands."""
    device = await _get_device_by_token(request)

    try:
        body = await request.json()
    except Exception:
        body = {}

    # Update device state
    device.status = body.get("status", "online")
    device.last_heartbeat = utcnow()
    device.ip_address = request.client.host if request.client else device.ip_address
    device.app_version = body.get("app_version", device.app_version)
    device.battery_health = body.get("battery_level", device.battery_health)
    device.total_uptime_seconds = body.get("uptime_seconds", device.total_uptime_seconds)

    async with AsyncSessionLocal() as session:
        await session.merge(device)
        await session.commit()

    # Fetch pending tasks
    pending_tasks = await DeviceTask.get_pending_for_device(device.device_id, limit=5)
    pending_commands = await DeviceCommand.get_pending_for_device(device.device_id)

    return {
        "status": "ok",
        "device_id": device.device_id,
        "server_time": utcnow().isoformat(),
        "pending_tasks": [
            {"task_id": t.task_id, "task_type": t.task_type, "payload": t.task_payload, "priority": t.priority}
            for t in pending_tasks
        ],
        "commands": [
            {"command_id": c.command_id, "command_type": c.command_type, "payload": c.command_payload}
            for c in pending_commands
        ],
    }


# ─── DEVICE TASKS ────────────────────────────────────────────────────────

@router.get("/api/device-army/tasks/{device_id}")
async def get_device_tasks(device_id: str, request: Request):
    """Get pending tasks for a device."""
    device = await _get_device_by_token(request)
    if device.device_id != device_id:
        raise HTTPException(403, "Token does not match this device")

    tasks = await DeviceTask.get_pending_for_device(device_id, limit=10)
    return {
        "device_id": device_id,
        "tasks": [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "payload": t.task_payload,
                "priority": t.priority,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
    }


@router.post("/api/device-army/tasks/{task_id}/status")
async def update_task_status(task_id: str, request: Request):
    """Device reports task progress/completion."""
    device = await _get_device_by_token(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    status = body.get("status")
    if status not in ("in_progress", "completed", "failed", "cancelled"):
        raise HTTPException(400, "Invalid status — use: in_progress, completed, failed, cancelled")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            __import__("sqlalchemy").select(DeviceTask).where(
                DeviceTask.task_id == task_id,
                DeviceTask.device_id == device.device_id,
            )
        )
        task = result.scalars().first()
        if not task:
            raise HTTPException(404, "Task not found for this device")

        task.status = status
        if status == "in_progress":
            task.started_at = utcnow()
        elif status in ("completed", "failed"):
            task.completed_at = utcnow()
            task.result = body.get("result")
            task.error_message = body.get("error_message")
            if status == "completed":
                device.total_tasks_completed = (device.total_tasks_completed or 0) + 1

        await session.merge(device)
        await session.commit()

    logger.info(f"Task {task_id} updated to {status} for device {device.device_id}")
    return {"status": "received", "task_id": task_id, "new_status": status}


@router.post("/api/device-army/tasks")
async def create_task(request: Request, user: dict = Depends(require_auth)):
    """Admin: Create a task for a device. Requires dashboard auth."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    device_id = body.get("device_id")
    task_type = body.get("task_type")
    payload = body.get("payload", {})
    priority = body.get("priority", 0)

    if not device_id or not task_type:
        raise HTTPException(400, "Missing 'device_id' or 'task_type'")

    # Verify device exists
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(Device).where(Device.device_id == device_id))
        device = result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")

    task_id = f"t-{_generate_id()}"
    await DeviceTask.create(
        task_id=task_id,
        device_id=device_id,
        task_type=task_type,
        task_payload=payload,
        priority=priority,
        status="pending",
        assigned_by=user.get("email", "admin"),
    )

    logger.info(f"Task {task_id} ({task_type}) created for device {device_id}")
    return {
        "status": "created",
        "task_id": task_id,
        "task_type": task_type,
        "device_id": device_id,
    }


# ─── COMMANDS ──────────────────────────────────────────────────────────

@router.post("/api/device-army/command")
async def send_command(request: Request, user: dict = Depends(require_auth)):
    """Admin: Send a remote command to a device. Requires dashboard auth."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    device_id = body.get("device_id")
    command_type = body.get("command_type")
    payload = body.get("payload", {})

    if not device_id or not command_type:
        raise HTTPException(400, "Missing 'device_id' or 'command_type'")

    if command_type not in ("restart", "update", "shutdown", "run_task", "cancel_task", "sync", "debug", "screenshot"):
        raise HTTPException(400, f"Invalid command_type: {command_type}")

    command_id = f"cmd-{_generate_id()}"
    await DeviceCommand.create(
        command_id=command_id,
        device_id=device_id,
        command_type=command_type,
        command_payload=payload,
        status="pending",
    )

    logger.info(f"Command {command_id} ({command_type}) sent to device {device_id}")
    return {"status": "sent", "command_id": command_id}


# ─── SOS / FAILSAFE ──────────────────────────────────────────────────────

@router.post("/api/device-army/sos")
async def device_sos(request: Request):
    """Device sends emergency SOS signal."""
    device = await _get_device_by_token(request)

    try:
        body = await request.json()
    except Exception:
        body = {}

    error_type = body.get("error_type", "unknown")
    message = body.get("message", "No details")
    device_state = body.get("device_state", {})
    context = body.get("context", {})

    # Log the SOS
    await DeviceLog.create(
        device_id=device.device_id,
        log_type="crash",
        source="sos",
        message=f"SOS: {error_type} — {message}",
        log_metadata={"device_state": device_state, "context": context},
        severity="critical",
    )

    # Mark device status
    device.status = "error"
    async with AsyncSessionLocal() as session:
        await session.merge(device)
        await session.commit()

    # Find failover candidates (same role, online)
    online_devices = await Device.get_online()
    failover_candidates = [
        d for d in online_devices
        if d.device_id != device.device_id and d.worker_role == device.worker_role
    ]

    logger.warning(f"SOS from device {device.device_id}: {error_type} — {message}")

    return {
        "status": "acknowledged",
        "device_id": device.device_id,
        "acknowledged_at": utcnow().isoformat(),
        "failover_available": len(failover_candidates) > 0,
        "failover_device_id": failover_candidates[0].device_id if failover_candidates else None,
    }


# ─── LOGS ────────────────────────────────────────────────────────────────

@router.post("/api/device-army/logs")
async def submit_logs(request: Request, background_tasks: BackgroundTasks):
    """Device submits batch of log entries."""
    device = await _get_device_by_token(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    entries = body.get("logs", [])
    if not isinstance(entries, list):
        raise HTTPException(400, "'logs' must be an array")

    count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        await DeviceLog.create(
            device_id=device.device_id,
            log_type=entry.get("log_type", "info"),
            source=entry.get("source", "unknown"),
            message=entry.get("message", ""),
            log_metadata=entry.get("metadata"),
            severity=entry.get("severity", "info"),
        )
        count += 1

    logger.debug(f"Stored {count} log entries from device {device.device_id}")
    return {"status": "received", "count": count, "device_id": device.device_id}


# ─── DASHBOARD ADMIN ROUTES ────────────────────────────────────────────

@router.get("/api/device-army/devices")
async def list_devices(
    request: Request,
    user: dict = Depends(require_auth),
    status: str = Query(None, description="Filter by status"),
    role: str = Query(None, description="Filter by worker role"),
):
    """List registered devices. Admins see all; non-admins see their own."""
    actor_email = user.get("email", "").lower().strip()
    is_admin = deps.is_user_admin(user)

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        query = select(Device).order_by(Device.last_heartbeat.desc().nullslast())
        if not is_admin:
            query = query.where(Device.owner_email == actor_email)
        if status:
            query = query.where(Device.status == status)
        if role:
            query = query.where(Device.worker_role == role)

        result = await session.execute(query)
        devices = result.scalars().all()

    return {
        "total": len(devices),
        "devices": [
            {
                "device_id": d.device_id,
                "display_name": d.display_name,
                "codename": d.codename,
                "worker_role": d.worker_role,
                "owner_email": d.owner_email,
                "status": d.status,
                "device_model": d.device_model,
                "android_version": d.android_version,
                "ram_mb": d.ram_mb,
                "storage_mb": d.storage_mb,
                "battery_health": d.battery_health,
                "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None,
                "total_tasks_completed": d.total_tasks_completed,
                "is_revoked": d.is_revoked,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "app_version": d.app_version,
                "ip_address": d.ip_address,
            }
            for d in devices
        ],
    }


@router.get("/api/device-army/account-devices")
async def list_device_army_account_devices(user: dict = Depends(require_auth)):
    """List devices linked to the authenticated user's account."""
    email = user.get("email", "").lower().strip()
    devices = await Device.get_by_owner(email)

    return {
        "total": len(devices),
        "devices": [
            {
                "device_id": d.device_id,
                "display_name": d.display_name,
                "codename": d.codename,
                "worker_role": d.worker_role,
                "status": d.status,
                "device_model": d.device_model,
                "android_version": d.android_version,
                "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None,
                "total_tasks_completed": d.total_tasks_completed,
                "is_revoked": d.is_revoked,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in devices
        ],
    }


@router.get("/api/device-army/devices/{device_id}")
async def get_device_detail(device_id: str, user: dict = Depends(require_auth)):
    """Get detailed info about a specific device."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(Device).where(Device.device_id == device_id))
        device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    actor_email = user.get("email", "").lower().strip()
    if not deps.is_user_admin(user) and device.owner_email != actor_email:
        raise HTTPException(403, "You do not own this device")

    # Get recent logs
    recent_logs = await DeviceLog.get_recent_for_device(device_id, limit=20)
    task_history = await DeviceTask.get_device_history(device_id, limit=10)

    return {
        "device": {
            "device_id": device.device_id,
            "display_name": device.display_name,
            "codename": device.codename,
            "worker_role": device.worker_role,
            "owner_email": device.owner_email,
            "device_model": device.device_model,
            "android_version": device.android_version,
            "cpu_info": device.cpu_info,
            "ram_mb": device.ram_mb,
            "storage_mb": device.storage_mb,
            "battery_health": device.battery_health,
            "sensors": device.sensors,
            "connectivity_capabilities": device.connectivity_capabilities,
            "status": device.status,
            "last_heartbeat": device.last_heartbeat.isoformat() if device.last_heartbeat else None,
            "ip_address": device.ip_address,
            "app_version": device.app_version,
            "total_tasks_completed": device.total_tasks_completed,
            "total_uptime_seconds": device.total_uptime_seconds,
            "is_revoked": device.is_revoked,
            "created_at": device.created_at.isoformat() if device.created_at else None,
        },
        "recent_logs": [
            {
                "log_type": l.log_type,
                "source": l.source,
                "message": l.message[:200],
                "severity": l.severity,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in recent_logs
        ],
        "recent_tasks": [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in task_history
        ],
    }


@router.post("/api/device-army/devices/{device_id}/revoke")
async def revoke_device(device_id: str, user: dict = Depends(require_auth)):
    """Revoke a device's access. Requires dashboard auth."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(Device).where(Device.device_id == device_id))
        device = result.scalars().first()

        if not device:
            raise HTTPException(404, "Device not found")

        device.is_revoked = True
        device.status = "offline"
        device.worker_token = None
        await session.commit()

    logger.warning(f"Device {device_id} revoked by {user.get('email', 'admin')}")
    return {"status": "revoked", "device_id": device_id}


@router.get("/api/device-army/stats")
async def device_army_stats(user: dict = Depends(require_auth)):
    """Get aggregate statistics about the device army."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, func

        total = await session.execute(select(func.count(Device.id)))
        total_count = total.scalar()

        online_result = await session.execute(
            select(func.count(Device.id)).where(Device.status.in_(["online", "idle", "busy"]))
        )
        online_count = online_result.scalar()

        by_role_result = await session.execute(
            select(Device.worker_role, func.count(Device.id)).group_by(Device.worker_role)
        )
        by_role = dict(by_role_result.all())

        tasks_result = await session.execute(
            select(DeviceTask.status, func.count(DeviceTask.id)).group_by(DeviceTask.status)
        )
        task_counts = dict(tasks_result.all())

        logs_result = await session.execute(
            select(DeviceLog.severity, func.count(DeviceLog.id)).group_by(DeviceLog.severity)
        )
        log_counts = dict(logs_result.all())

    return {
        "total_devices": total_count,
        "online_devices": online_count,
        "offline_devices": total_count - online_count,
        "by_role": by_role,
        "task_counts": task_counts,
        "log_counts": log_counts,
    }
