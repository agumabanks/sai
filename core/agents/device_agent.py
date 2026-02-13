"""Device Agent — Handles device report processing"""


class DeviceAgent:
    def __init__(self):
        pass

    async def get_active_devices(self):
        """Get active devices from database.
        Device reports are received via POST /api/device/report
        and stored/queried via database.DeviceReport.
        """
        from database import DeviceReport
        return await DeviceReport.get_latest_all()
