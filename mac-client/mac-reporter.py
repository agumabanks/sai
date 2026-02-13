#!/usr/bin/env python3
"""
Sanaa AI Mac Client — Reports device health to ai.sanaa.co
Install: Save to ~/antigravity/mac-reporter.py
Run: python3 ~/antigravity/mac-reporter.py
Auto-start: Add to Login Items or use launchd (see plist below)
"""

import subprocess
import json
import time
import socket
import platform
import requests
from datetime import datetime

# ============ CONFIGURATION ============
API_URL = "https://ai.sanaa.co/api/device/report"
API_KEY = "ag_mac_client_z8x9c7v6b5n4m3a2s1d0"
REPORT_INTERVAL = 300  # seconds (5 minutes)
DEVICE_ID = f"mac-{socket.gethostname()}"
DEVICE_NAME = f"{platform.node()} (MacBook Pro)"
# =======================================

def get_battery_info():
    """Get battery percentage and charging status"""
    try:
        result = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True
        )
        output = result.stdout
        if "InternalBattery" not in output and "BatteryPower" not in output:
             # Desktop macs might not have battery
             return -1, True, True
        
        percent = int(output.split("\t")[1].split("%")[0])
        charging = "charging" in output.lower() or "ac power" in output.lower()
        power_connected = "ac power" in output.lower()
        return percent, charging, power_connected
    except:
        return -1, False, False

def get_storage_info():
    """Get disk storage info"""
    try:
        result = subprocess.run(
            ["df", "-g", "/"], capture_output=True, text=True
        )
        lines = result.stdout.strip().split("\n")
        parts = lines[1].split()
        total = float(parts[1])
        available = float(parts[3])
        return total, available
    except:
        return 0, 0

def get_cpu_percent():
    """Get CPU usage percentage"""
    try:
        result = subprocess.run(
            ["top", "-l", "1", "-n", "0"], capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if "CPU usage" in line:
                idle = float(line.split("idle")[0].split()[-1].replace("%", ""))
                return round(100 - idle, 1)
        return 0
    except:
        return 0

def get_memory_percent():
    """Get memory pressure percentage"""
    try:
        result = subprocess.run(
            ["memory_pressure"], capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if "System-wide memory free percentage" in line:
                free = float(line.split(":")[-1].strip().replace("%", ""))
                return round(100 - free, 1)
        return 0
    except:
        return 0

def get_wifi_info():
    """Get current WiFi network"""
    try:
        result = subprocess.run(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
            capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if " SSID" in line and "BSSID" not in line:
                return line.split(":")[-1].strip()
        return None
    except:
        return None

def get_active_apps():
    """Get list of running applications"""
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of every process whose background only is false'],
            capture_output=True, text=True
        )
        apps = [a.strip() for a in result.stdout.strip().split(",")]
        return apps[:20]  # Limit to 20
    except:
        return []

def send_report():
    """Collect and send device report"""
    battery_pct, charging, power = get_battery_info()
    storage_total, storage_avail = get_storage_info()

    report = {
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "battery_percent": battery_pct,
        "battery_charging": charging,
        "power_connected": power,
        "storage_total_gb": storage_total,
        "storage_available_gb": storage_avail,
        "cpu_percent": get_cpu_percent(),
        "memory_percent": get_memory_percent(),
        "network_ssid": get_wifi_info(),
        "active_apps": get_active_apps(),
        "timestamp": datetime.now().isoformat(),
    }

    try:
        resp = requests.post(
            API_URL,
            json=report,
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("alerts_triggered", 0) > 0:
                # Show macOS notification for triggered alerts
                subprocess.run([
                    "osascript", "-e",
                    f'display notification "Sanaa AI triggered {data["alerts_triggered"]} alert(s)" with title "🛸 Sanaa AI"'
                ])
        else:
            print(f"Report failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Connection error: {e}")

def main():
    print(f"🛸 Sanaa AI Mac Client started")
    print(f"   Reporting to: {API_URL}")
    print(f"   Device: {DEVICE_NAME}")
    print(f"   Interval: {REPORT_INTERVAL}s")

    while True:
        send_report()
        time.sleep(REPORT_INTERVAL)

if __name__ == "__main__":
    main()
