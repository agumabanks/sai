"""
Sanaa AI — Device routes: device reports and listing.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks

from core.database import DeviceReport
from core.routes import deps
from core.routes.deps import require_auth, verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/device/report")
async def receive_device_report(
    request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
):
    try:
        report = await request.json()
        device_id = report.get("device_id")
        device_name = report.get("device_name")

        await DeviceReport.create(
            device_id=device_id,
            device_name=device_name,
            data=report,
        )

        return {"status": "received", "device_id": device_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/api/devices")
async def list_devices(user: dict = Depends(require_auth)):
    devices = await DeviceReport.get_latest_all()
    return [
        {
            "device_id": d.device_id,
            "device_name": d.device_name,
            "last_report": d.created_at.isoformat() if d.created_at else None,
        }
        for d in devices
    ]
