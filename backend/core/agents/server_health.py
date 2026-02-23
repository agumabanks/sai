import psutil
import subprocess
import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from core.brain import Brain
from core.config import get_settings
from core.intelligence.memory import IntelligenceMemory

logger = logging.getLogger(__name__)

class HealthEvent:
    """Structured health event logging."""
    def __init__(self, category: str, severity: str, message: str, metric: str = "", value: str = ""):
        self.id = hashlib.md5(f"health:{metric}:{message}".encode()).hexdigest()[:8]
        self.category = category # resource, service, security
        self.severity = severity # info, warning, error, critical
        self.message = message
        self.metric = metric
        self.value = value
        self.timestamp = datetime.now()

    def log(self):
        log_msg = f"[HEALTH][{self.category.upper()}][{self.severity.upper()}] {self.message}"
        if self.metric:
            log_msg += f" | Metric: {self.metric}={self.value}"
        if self.severity in ("error", "critical"):
            logger.error(log_msg)
        elif self.severity == "warning":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

class ServerHealthAgent:
    def __init__(self):
        self.settings = get_settings()
        self.brain = Brain()
        self.memory = IntelligenceMemory()
        self.thresholds = {
            "cpu": int(os.getenv("CPU_ALERT_THRESHOLD", 85)),
            "ram": int(os.getenv("RAM_ALERT_THRESHOLD", 85)),
            "disk": int(os.getenv("DISK_ALERT_THRESHOLD", 90)),
            "load": float(os.getenv("LOAD_ALERT_THRESHOLD", 4.0)),
        }

    async def get_snapshot(self) -> dict:
        """Complete server health snapshot with event tracking."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load_1, load_5, load_15 = psutil.getloadavg()
        net = psutil.net_io_counters()
        boot_time = datetime.fromtimestamp(psutil.boot_time())

        # Check critical services
        services = {}
        for svc in ["nginx", "php8.4-fpm", "redis-server", "postgresql", "supervisor"]:
            try:
                result = subprocess.run(
                    f"systemctl is-active {svc}", shell=True,
                    capture_output=True, text=True, timeout=5
                )
                status = result.stdout.strip()
                services[svc] = status
                if status != "active":
                    HealthEvent("service", "critical", f"Service {svc} is {status}", f"service.{svc}", status).log()
            except:
                services[svc] = "unknown"

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": cpu_percent,
                "cores": psutil.cpu_count(),
                "load_1m": round(load_1, 2),
                "status": "critical" if cpu_percent > self.thresholds["cpu"] else "ok"
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "percent": memory.percent,
                "status": "critical" if memory.percent > self.thresholds["ram"] else "ok"
            },
            "disk": {
                "percent": round(disk.percent, 1),
                "free_gb": round(disk.free / (1024**3), 2),
                "status": "critical" if disk.percent > self.thresholds["disk"] else "ok"
            },
            "services": services,
            "uptime_since": boot_time.isoformat(),
            "overall_status": "ok"
        }

        # Log resource issues
        if snapshot["cpu"]["status"] == "critical":
            HealthEvent("resource", "critical", f"CPU usage critical: {cpu_percent}%", "cpu", str(cpu_percent)).log()
        if snapshot["memory"]["status"] == "critical":
            HealthEvent("resource", "critical", f"RAM usage critical: {memory.percent}%", "ram", str(memory.percent)).log()

        if any(v.get("status") == "critical" for v in [snapshot["cpu"], snapshot["memory"], snapshot["disk"]]):
            snapshot["overall_status"] = "critical"
        elif any(v != "active" for v in services.values()):
            snapshot["overall_status"] = "degraded"

        return snapshot

    async def get_metric(self, metric: str) -> dict:
        """Return a specific metric from the current snapshot."""
        snapshot = await self.get_snapshot()
        metric = (metric or "all").lower()
        if metric == "all":
            return snapshot
        if metric == "services":
            return {"services": snapshot.get("services", {}), "overall_status": snapshot.get("overall_status")}
        if metric in snapshot:
            return {metric: snapshot.get(metric), "overall_status": snapshot.get("overall_status")}
        return {"error": f"Unknown metric: {metric}", "available": list(snapshot.keys())}

    async def get_alerts(self) -> list:
        """Analyze alerts using tiered Brain for root cause analysis."""
        snapshot = await self.get_snapshot()
        alerts = []
        
        # Static alerts
        if snapshot["cpu"]["status"] == "critical":
            alerts.append({"severity": "high", "message": f"CPU at {snapshot['cpu']['percent']}%", "metric": "cpu"})
        if snapshot["memory"]["status"] == "critical":
            alerts.append({"severity": "high", "message": f"RAM at {snapshot['memory']['percent']}%", "metric": "memory"})
        for svc, status in snapshot["services"].items():
            if status != "active":
                alerts.append({"severity": "critical", "message": f"Service {svc} is {status}", "metric": "service"})

        if alerts:
            # Brain analysis for critical states
            context = await self.memory.get_all_context()
            prompt = f"""Analyze these server alerts. Is there a likely root cause or correlation?
            DOMAIN CONTEXT: {context}
            ALERTS: {json.dumps(alerts)}
            SNAPSHOT: {json.dumps(snapshot)}
            """
            analysis = await self.brain.think(prompt, complexity="medium")
            HealthEvent("analysis", "info", f"Brain analysis completed for {len(alerts)} alerts").log()
            # Wrap alerts with analysis
            for a in alerts:
                a["analysis"] = analysis

        return alerts
