import os
import re
import glob
import json
import hashlib
import logging
import asyncio
from datetime import datetime
from core.brain import Brain
from core.config import get_settings
from core.intelligence.memory import IntelligenceMemory
from core.intelligence.persistence import archive_knowledge

logger = logging.getLogger(__name__)

class AppEvent:
    """Structured application event logging."""
    def __init__(self, category: str, severity: str, message: str, app: str = "", metadata: dict = None):
        self.id = hashlib.md5(f"app:{app}:{message}".encode()).hexdigest()[:8]
        self.category = category  # error, exception, performance
        self.severity = severity  # info, warning, error, critical
        self.message = message
        self.app = app
        self.metadata = metadata or {}
        self.timestamp = datetime.now()

    def log(self):
        log_msg = f"[APP][{self.app.upper()}][{self.category.upper()}][{self.severity.upper()}] {self.message}"
        if self.severity in ("error", "critical"):
            logger.error(log_msg)
        elif self.severity == "warning":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

class AppMonitorAgent:
    def __init__(self):
        self.settings = get_settings()
        self.brain = Brain()
        self.memory = IntelligenceMemory()
        self.log_pattern = "/var/www/*/storage/logs/laravel.log"
        self.known_errors_file = "/opt/antigravity/data/known_errors.json"
        
    async def get_logs(self, app=None, level=None, limit=100):
        """Read logs from file system with structured mapping."""
        logs = []
        files = glob.glob(self.log_pattern)
        
        for f in files:
            app_name = f.split('/')[-4]
            if app and app != app_name:
                continue
                
            try:
                with open(f, 'r') as log_file:
                    lines = log_file.readlines()[-limit:] 
                    for line in lines:
                        if level and level.upper() not in line:
                            continue
                        logs.append({
                            "app": app_name,
                            "raw": line.strip(),
                            "timestamp": datetime.now().isoformat()
                        })
            except Exception as e:
                logger.error(f"Error reading log {f}: {e}")
                
        return logs

    async def analyze_errors(self, errors: list):
        """Deep analysis of error patterns using Tier 3 Brain."""
        if not errors: return None
        
        context = await self.memory.get_all_context()
        prompt = f"""Perform a deep root-cause analysis on these application errors.
        Identify patterns, potential bug locations, and remediation steps.
        DOMAIN CONTEXT: {context}
        ERRORS: {json.dumps(errors[:10])}
        """
        analysis = await self.brain.think(prompt, complexity="high")
        AppEvent("analysis", "info", f"Analyzed {len(errors)} errors for {errors[0].get('app')}", errors[0].get("app")).log()
        return analysis

    async def scan_for_new_errors(self):
        """Scan logs and perform deep analysis if errors found."""
        errors = await self.get_logs(level="ERROR", limit=5)
        if errors:
            for err in errors:
                AppEvent("error", "high", err["raw"][:200], err["app"]).log()
            
            analysis = await self.analyze_errors(errors)
            await archive_knowledge(
                title=f"Application Error Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                content=analysis,
                metadata={"error_count": len(errors), "apps": list(set(e["app"] for e in errors))}
            )
        return errors
