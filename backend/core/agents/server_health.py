import psutil
import subprocess
import json
import hashlib
import logging
from datetime import datetime, timezone
from core.brain import get_shared_brain
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
        self.timestamp = datetime.now(timezone.utc)

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
    def __init__(self, brain=None):
        self.settings = get_settings()
        self.brain = brain or get_shared_brain()
        self.memory = IntelligenceMemory()
        self.thresholds = {
            "cpu": self.settings.cpu_alert_threshold,
            "ram": self.settings.ram_alert_threshold,
            "disk": self.settings.disk_alert_threshold,
            "load": self.settings.load_alert_threshold,
        }

    async def get_snapshot(self) -> dict:
        """Complete server health snapshot with event tracking."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load_1, load_5, load_15 = psutil.getloadavg()
        net = psutil.net_io_counters()
        boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)

        # Check critical services
        services = {}
        for svc in ["nginx", "php8.4-fpm", "redis-server", "postgresql", "supervisor"]:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", svc],
                    shell=False, capture_output=True, text=True, timeout=5
                )
                status = result.stdout.strip()
                services[svc] = status
                if status != "active":
                    HealthEvent("service", "critical", f"Service {svc} is {status}", f"service.{svc}", status).log()
            except Exception as exc:
                logger.warning("Failed to check service %s: %s", svc, exc)
                services[svc] = "unknown"

        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "uptime_seconds": int((datetime.now(timezone.utc) - boot_time).total_seconds()),
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
        """Return health alerts without spending Groq tokens by default."""
        snapshot = await self.get_snapshot()
        alerts = []
        
        # Static alerts
        if snapshot["cpu"]["status"] == "critical":
            alerts.append({"severity": "high", "message": f"CPU at {snapshot['cpu']['percent']}%", "metric": "cpu"})
        if snapshot["memory"]["status"] == "critical":
            alerts.append({"severity": "high", "message": f"RAM at {snapshot['memory']['percent']}%", "metric": "memory"})
        if snapshot["disk"]["percent"] >= 85:
            alerts.append({"severity": "warning", "message": f"Disk usage at {snapshot['disk']['percent']}%. Only {snapshot['disk']['free_gb']}GB remaining. Prediction: Risk of filling up within 7-14 days.", "metric": "disk_prediction"})
            
        for svc, status in snapshot["services"].items():
            if status != "active":
                alerts.append({"severity": "critical", "message": f"Service {svc} is {status}", "metric": "service"})

        if alerts:
            analysis = self._local_alert_analysis(alerts, snapshot)
            if self.settings.health_llm_analysis_enabled:
                try:
                    context = (await self.memory.get_all_context())[:1200]
                    prompt = f"""Analyze these server alerts in 3 short bullets.
                    DOMAIN CONTEXT: {context}
                    ALERTS: {json.dumps(alerts)}
                    SNAPSHOT: {json.dumps(snapshot)}
                    """
                    analysis = await self.brain.think(prompt, complexity="low")
                    HealthEvent("analysis", "info", f"Groq analysis completed for {len(alerts)} alerts").log()
                except Exception as exc:
                    logger.warning("Health Groq analysis skipped: %s", exc)
            for alert in alerts:
                alert["analysis"] = analysis

        return alerts

    def _local_alert_analysis(self, alerts: list, snapshot: dict) -> str:
        metrics = ", ".join(f"{a.get('metric')}: {a.get('message')}" for a in alerts)
        cpu = snapshot.get("cpu", {}).get("percent")
        memory = snapshot.get("memory", {}).get("percent")
        disk = snapshot.get("disk", {}).get("percent")
        return (
            f"Local health analysis: {metrics}. "
            f"Current resource snapshot is CPU {cpu}%, memory {memory}%, disk {disk}%. "
            "Reduce noisy background work first, then inspect service logs if the alert persists."
        )
