"""Server Health Monitoring Agent"""

import psutil
import subprocess
import os
from datetime import datetime

class ServerHealthAgent:
    def __init__(self):
        self.thresholds = {
            "cpu": int(os.getenv("CPU_ALERT_THRESHOLD", 85)),
            "ram": int(os.getenv("RAM_ALERT_THRESHOLD", 85)),
            "disk": int(os.getenv("DISK_ALERT_THRESHOLD", 90)),
            "load": float(os.getenv("LOAD_ALERT_THRESHOLD", 4.0)),
        }

    async def get_snapshot(self) -> dict:
        """Complete server health snapshot"""
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
                services[svc] = result.stdout.strip()
            except:
                services[svc] = "unknown"

        # Check Ollama
        try:
            result = subprocess.run(
                "curl -s http://localhost:11434/api/tags", shell=True,
                capture_output=True, text=True, timeout=5
            )
            services["ollama"] = "active" if result.returncode == 0 else "inactive"
        except:
            services["ollama"] = "unknown"

        # Active connections
        connections = len(psutil.net_connections())

        # Docker containers
        try:
            result = subprocess.run(
                "docker ps --format '{{.Names}}: {{.Status}}'",
                shell=True, capture_output=True, text=True, timeout=5
            )
            docker_containers = result.stdout.strip().split('\n') if result.stdout.strip() else []
        except:
            docker_containers = []

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": cpu_percent,
                "cores": psutil.cpu_count(),
                "load_1m": round(load_1, 2),
                "load_5m": round(load_5, 2),
                "load_15m": round(load_15, 2),
                "status": "critical" if cpu_percent > self.thresholds["cpu"] else "ok"
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "percent": memory.percent,
                "status": "critical" if memory.percent > self.thresholds["ram"] else "ok"
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": round(disk.percent, 1),
                "status": "critical" if disk.percent > self.thresholds["disk"] else "ok"
            },
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
                "connections": connections,
            },
            "services": services,
            "docker": docker_containers,
            "uptime_since": boot_time.isoformat(),
            "overall_status": "ok"
        }

        # Determine overall status
        if any(v.get("status") == "critical" for v in [snapshot["cpu"], snapshot["memory"], snapshot["disk"]]):
            snapshot["overall_status"] = "critical"
        elif any(v == "inactive" for v in services.values()):
            snapshot["overall_status"] = "degraded"

        return snapshot

    async def get_alerts(self) -> list:
        """Check for any conditions that need alerting"""
        snapshot = await self.get_snapshot()
        alerts = []

        if snapshot["cpu"]["percent"] > self.thresholds["cpu"]:
            alerts.append({
                "severity": "high",
                "message": f"CPU usage at {snapshot['cpu']['percent']}%",
                "metric": "cpu"
            })

        if snapshot["memory"]["percent"] > self.thresholds["ram"]:
            alerts.append({
                "severity": "high",
                "message": f"Memory usage at {snapshot['memory']['percent']}%",
                "metric": "memory"
            })

        if snapshot["disk"]["percent"] > self.thresholds["disk"]:
            alerts.append({
                "severity": "critical",
                "message": f"Disk usage at {snapshot['disk']['percent']}%",
                "metric": "disk"
            })

        for svc, status in snapshot["services"].items():
            if status not in ["active", "unknown"]:
                alerts.append({
                    "severity": "critical",
                    "message": f"Service {svc} is {status}",
                    "metric": "service"
                })

        return alerts
