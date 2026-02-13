"""App Monitor Agent"""

import os
import re
import glob
import asyncio
from datetime import datetime

class AppMonitorAgent:
    def __init__(self):
        # Scan all laravel logs in /var/www
        self.log_pattern = "/var/www/*/storage/logs/laravel.log"
        self.known_errors_file = "/opt/antigravity/data/known_errors.json"
        
    async def get_logs(self, app=None, level=None, limit=100):
        """Read logs from file system"""
        logs = []
        files = glob.glob(self.log_pattern)
        
        for f in files:
            app_name = f.split('/')[-4] # /var/www/APP/storage/logs/...
            if app and app != app_name:
                continue
                
            try:
                with open(f, 'r') as log_file:
                    # Read last N lines efficiently-ish
                    lines = log_file.readlines()[-limit:] 
                    for line in lines:
                        if level and level.upper() not in line:
                            continue
                        logs.append({
                            "app": app_name,
                            "raw": line.strip(),
                            "timestamp": datetime.now().isoformat() # Placeholder timestamp if not parsed
                        })
            except Exception as e:
                print(f"Error reading log {f}: {e}")
                
        return logs

    async def get_recent_errors(self, limit=20):
        """Get recent error logs"""
        return await self.get_logs(level="ERROR", limit=limit)

    async def scan_for_new_errors(self):
        """Scan for new errors since last scan"""
        # In a real impl, we'd track file offsets.
        # For this MVP, we'll just return the last 5 errors as "new" for alerts
        # This is a simplification.
        return await self.get_recent_errors(limit=5)
