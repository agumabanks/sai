"""
Sanaa Device Army — WebSocket Manager for real-time device communication.

Handles device connections, heartbeat monitoring, task streaming,
command relay, and live log streaming to dashboard listeners.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends

from core.database import Device, DeviceTask, DeviceCommand, DeviceLog, AsyncSessionLocal, utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


class DeviceWebSocketManager:
    """
    Manages persistent WebSocket connections to worker devices.

    - Devices connect with device_id + worker_token auth
    - Dashboard admins connect as listeners for live monitoring
    - Heartbeats flow over WS for real-time status
    - Tasks and commands pushed to devices immediately
    """

    def __init__(self):
        # device_id -> WebSocket
        self._device_connections: dict[str, WebSocket] = {}
        # listener_id -> WebSocket (dashboard sessions)
        self._listeners: dict[str, WebSocket] = {}
        # device_id -> last heartbeat timestamp
        self._heartbeats: dict[str, datetime] = {}
        # Background tasks
        self._watchdog_task: Optional[asyncio.Task] = None

    async def start_watchdog(self):
        """Start the heartbeat watchdog that detects stale connections."""
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._heartbeat_watchdog())
            logger.info("Device WS heartbeat watchdog started")

    async def _heartbeat_watchdog(self):
        """Check every 60s for devices that missed heartbeats."""
        while True:
            try:
                now = datetime.now(timezone.utc)
                stale = []
                for device_id, last_hb in self._heartbeats.items():
                    if (now - last_hb).total_seconds() > 120:
                        stale.append(device_id)

                for device_id in stale:
                    logger.warning(f"Device {device_id} heartbeat timeout — marking offline")
                    del self._heartbeats[device_id]
                    # Remove from connections if still there
                    if device_id in self._device_connections:
                        try:
                            await self._device_connections[device_id].close(code=1000)
                        except Exception:
                            pass
                        del self._device_connections[device_id]

                    # Update DB status
                    async with AsyncSessionLocal() as session:
                        from sqlalchemy import select
                        result = await session.execute(
                            select(Device).where(Device.device_id == device_id)
                        )
                        device = result.scalars().first()
                        if device:
                            device.status = "offline"
                            await session.commit()

                    # Notify listeners
                    await self._broadcast_to_listeners({
                        "type": "device_offline",
                        "device_id": device_id,
                        "timestamp": utcnow().isoformat(),
                    })

                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat watchdog error: {e}")
                await asyncio.sleep(60)

    async def connect_device(self, device_id: str, websocket: WebSocket):
        """Register a device WebSocket connection."""
        await websocket.accept()
        self._device_connections[device_id] = websocket
        self._heartbeats[device_id] = datetime.now(timezone.utc)

        # Update device status in DB
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(select(Device).where(Device.device_id == device_id))
            device = result.scalars().first()
            if device:
                device.status = "online"
                device.last_heartbeat = utcnow()
                await session.commit()

        await self._broadcast_to_listeners({
            "type": "device_online",
            "device_id": device_id,
            "timestamp": utcnow().isoformat(),
        })
        logger.info(f"Device connected via WS: {device_id}")

    async def disconnect_device(self, device_id: str):
        """Remove a device WebSocket connection."""
        if device_id in self._device_connections:
            try:
                del self._device_connections[device_id]
            except Exception:
                pass
        self._heartbeats.pop(device_id, None)

        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(select(Device).where(Device.device_id == device_id))
            device = result.scalars().first()
            if device:
                device.status = "offline"
                await session.commit()

        await self._broadcast_to_listeners({
            "type": "device_offline",
            "device_id": device_id,
            "timestamp": utcnow().isoformat(),
        })
        logger.info(f"Device disconnected: {device_id}")

    async def handle_device_message(self, device_id: str, data: dict):
        """Process incoming message from a device."""
        msg_type = data.get("type", "")

        if msg_type == "heartbeat":
            self._heartbeats[device_id] = datetime.now(timezone.utc)
            # Update device in DB
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                result = await session.execute(select(Device).where(Device.device_id == device_id))
                device = result.scalars().first()
                if device:
                    device.status = data.get("status", "online")
                    device.last_heartbeat = utcnow()
                    device.battery_health = data.get("battery_level", device.battery_health)
                    await session.commit()

            # Reply with pending tasks
            pending_tasks = await DeviceTask.get_pending_for_device(device_id, limit=5)
            pending_commands = await DeviceCommand.get_pending_for_device(device_id)
            await self.send_to_device(device_id, {
                "type": "heartbeat_ack",
                "server_time": utcnow().isoformat(),
                "pending_tasks": [
                    {"task_id": t.task_id, "task_type": t.task_type, "payload": t.task_payload}
                    for t in pending_tasks
                ],
                "commands": [
                    {"command_id": c.command_id, "command_type": c.command_type, "payload": c.command_payload}
                    for c in pending_commands
                ],
            })
            # Relay to dashboard listeners
            await self._broadcast_to_listeners({
                "type": "heartbeat",
                "device_id": device_id,
                "data": data,
                "timestamp": utcnow().isoformat(),
            })

        elif msg_type == "task_update":
            task_id = data.get("task_id")
            task_status = data.get("status")
            if task_id and task_status:
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import select
                    result = await session.execute(
                        select(DeviceTask).where(DeviceTask.task_id == task_id)
                    )
                    task = result.scalars().first()
                    if task:
                        task.status = task_status
                        if task_status == "in_progress":
                            task.started_at = utcnow()
                        elif task_status in ("completed", "failed"):
                            task.completed_at = utcnow()
                            task.result = data.get("result")
                            task.error_message = data.get("error_message")
                        await session.commit()

            await self._broadcast_to_listeners({
                "type": "task_update",
                "device_id": device_id,
                "task_id": task_id,
                "status": task_status,
                "timestamp": utcnow().isoformat(),
            })

        elif msg_type == "log":
            entries = data.get("entries", [])
            for entry in entries:
                await DeviceLog.create(
                    device_id=device_id,
                    log_type=entry.get("log_type", "info"),
                    source=entry.get("source", "unknown"),
                    message=entry.get("message", ""),
                    log_metadata=entry.get("metadata"),
                    severity=entry.get("severity", "info"),
                )

        elif msg_type == "state_change":
            new_state = data.get("state", "unknown")
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                result = await session.execute(select(Device).where(Device.device_id == device_id))
                device = result.scalars().first()
                if device:
                    device.status = new_state
                    await session.commit()

            await self._broadcast_to_listeners({
                "type": "state_change",
                "device_id": device_id,
                "state": new_state,
                "timestamp": utcnow().isoformat(),
            })

        elif msg_type == "sos":
            # Relay SOS to listeners
            await self._broadcast_to_listeners({
                "type": "sos",
                "device_id": device_id,
                "data": data,
                "timestamp": utcnow().isoformat(),
            })

        elif msg_type == "pong":
            self._heartbeats[device_id] = datetime.now(timezone.utc)

    async def send_to_device(self, device_id: str, message: dict):
        """Send a JSON message to a specific device."""
        ws = self._device_connections.get(device_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception as e:
                logger.warning(f"Failed to send to device {device_id}: {e}")
                await self.disconnect_device(device_id)
        return False

    async def send_command_to_device(self, device_id: str, command: dict):
        """Push a command to a device immediately."""
        success = await self.send_to_device(device_id, {
            "type": "command",
            "command": command,
        })
        if success:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(DeviceCommand).where(DeviceCommand.command_id == command["command_id"])
                )
                cmd = result.scalars().first()
                if cmd:
                    cmd.status = "sent"
                    cmd.delivered_at = utcnow()
                    await session.commit()
        return success

    async def push_task_to_device(self, device_id: str, task: dict):
        """Push a new task to a device immediately."""
        return await self.send_to_device(device_id, {
            "type": "task_assigned",
            "task": task,
        })

    def is_device_connected(self, device_id: str) -> bool:
        return device_id in self._device_connections

    def get_connected_devices(self) -> list[str]:
        return list(self._device_connections.keys())

    # ─── LISTENER MANAGEMENT (Dashboard) ────────────────────────────

    async def register_listener(self, listener_id: str, websocket: WebSocket):
        """Register a dashboard listener for live device events."""
        await websocket.accept()
        self._listeners[listener_id] = websocket
        # Send current device state
        await websocket.send_json({
            "type": "connected",
            "listener_id": listener_id,
            "connected_devices": list(self._device_connections.keys()),
            "timestamp": utcnow().isoformat(),
        })
        logger.info(f"Dashboard listener connected: {listener_id}")

    async def remove_listener(self, listener_id: str):
        self._listeners.pop(listener_id, None)
        logger.info(f"Dashboard listener disconnected: {listener_id}")

    async def _broadcast_to_listeners(self, message: dict):
        """Send event to all connected dashboard listeners."""
        stale = []
        for lid, ws in self._listeners.items():
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(lid)
        for lid in stale:
            await self.remove_listener(lid)

    def get_status(self) -> dict:
        return {
            "connected_devices": len(self._device_connections),
            "devices": list(self._device_connections.keys()),
            "listeners": len(self._listeners),
            "watchdog_running": self._watchdog_task is not None and not self._watchdog_task.done(),
        }


# Singleton instance
ws_manager = DeviceWebSocketManager()


# ─── WEBSOCKET ENDPOINTS ──────────────────────────────────────────────────

@router.websocket("/ws/device/{device_id}")
async def device_websocket_endpoint(websocket: WebSocket, device_id: str, token: str = Query("")):
    """WebSocket endpoint for device connections."""
    # Authenticate device via token query param
    device = await Device.find_by_token(token)
    if not device or device.device_id != device_id:
        await websocket.close(code=4001)
        return
    if device.is_revoked:
        await websocket.close(code=4003)
        return

    await ws_manager.connect_device(device_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                await ws_manager.handle_device_message(device_id, data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from device {device_id}: {raw[:100]}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error for device {device_id}: {e}")
    finally:
        await ws_manager.disconnect_device(device_id)


@router.websocket("/ws/device/listener")
async def listener_websocket_endpoint(websocket: WebSocket, listener_id: str = Query("default")):
    """WebSocket endpoint for dashboard listeners."""
    await ws_manager.register_listener(listener_id, websocket)
    try:
        while True:
            # Keep-alive ping every 30s
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if raw == "ping":
                await websocket.send_json({"type": "pong"})
    except asyncio.TimeoutError:
        # Send keepalive ping
        try:
            await websocket.send_json({"type": "ping"})
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Listener WS error: {e}")
    finally:
        await ws_manager.remove_listener(listener_id)


# ─── REST HELPERS ────────────────────────────────────────────────────────

async def ensure_watchdog_running():
    """Called at app startup to start the WS watchdog."""
    await ws_manager.start_watchdog()
