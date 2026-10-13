"""
Sanaa AI OS — Behavioral Analytics & Audit Engine
Tracks user patterns, surfaces insights, logs compliance events.
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.routes.deps import require_auth

router = APIRouter()

DB_PATH = "/var/www/ai.sanaa.co/data/os/analytics.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            session_id TEXT,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_email, created_at);
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, created_at);

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            user_email TEXT NOT NULL,
            user_agent TEXT,
            ip_address TEXT,
            started_at REAL NOT NULL,
            last_active_at REAL NOT NULL,
            ended_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_email, last_active_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(ended_at);

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            details TEXT,
            ip_address TEXT,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_email, created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created_at);
    """)
    conn.commit()
    conn.close()


_init_db()


class EventCreate(BaseModel):
    event_type: str
    event_data: Optional[dict] = None
    session_id: Optional[str] = None


class AuditEntry(BaseModel):
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[dict] = None


@router.post("/api/analytics/events")
async def log_event(data: EventCreate, user: dict = Depends(require_auth)):
    """Log a behavioral event."""
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO events (user_email, event_type, event_data, session_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (user.get("email", "unknown"), data.event_type, json.dumps(data.event_data or {}),
             data.session_id or "", time.time())
        )
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.get("/api/analytics/patterns")
async def get_patterns(
    user: dict = Depends(require_auth),
    days: int = Query(30, ge=1, le=90),
):
    """Get learned behavioral patterns for the current user."""
    email = user.get("email", "unknown")
    since = time.time() - (days * 86400)
    conn = _get_db()
    try:
        # App open frequency
        app_rows = conn.execute(
            "SELECT event_data FROM events WHERE user_email = ? AND event_type = 'app_open' AND created_at > ?",
            (email, since)
        ).fetchall()
        app_counts = {}
        for row in app_rows:
            try:
                data = json.loads(row["event_data"])
                app_id = data.get("app_id", "unknown")
                app_counts[app_id] = app_counts.get(app_id, 0) + 1
            except:
                pass

        # App sequences (what follows what)
        sequence_rows = conn.execute(
            "SELECT event_data, created_at FROM events WHERE user_email = ? AND event_type = 'app_open' AND created_at > ? ORDER BY created_at",
            (email, since)
        ).fetchall()
        sequences = {}
        prev_app = None
        for row in sequence_rows:
            try:
                data = json.loads(row["event_data"])
                app_id = data.get("app_id", "unknown")
                if prev_app and prev_app != app_id:
                    key = f"{prev_app} → {app_id}"
                    sequences[key] = sequences.get(key, 0) + 1
                prev_app = app_id
            except:
                pass

        # Hourly activity pattern
        hour_rows = conn.execute(
            "SELECT created_at FROM events WHERE user_email = ? AND created_at > ?",
            (email, since)
        ).fetchall()
        hourly = [0] * 24
        for row in hour_rows:
            dt = datetime.fromtimestamp(row["created_at"])
            hourly[dt.hour] += 1

        # Search patterns
        search_rows = conn.execute(
            "SELECT event_data FROM events WHERE user_email = ? AND event_type = 'search' AND created_at > ?",
            (email, since)
        ).fetchall()
        search_counts = {}
        for row in search_rows:
            try:
                data = json.loads(row["event_data"])
                q = data.get("query", "").lower().strip()
                if q:
                    search_counts[q] = search_counts.get(q, 0) + 1
            except:
                pass

        # Workspace usage
        ws_rows = conn.execute(
            "SELECT event_data FROM events WHERE user_email = ? AND event_type = 'workspace_switch' AND created_at > ?",
            (email, since)
        ).fetchall()
        ws_counts = {}
        for row in ws_rows:
            try:
                data = json.loads(row["event_data"])
                ws = data.get("workspace", "1")
                ws_counts[ws] = ws_counts.get(ws, 0) + 1
            except:
                pass

        return {
            "apps": sorted(app_counts.items(), key=lambda x: -x[1])[:10],
            "sequences": sorted(sequences.items(), key=lambda x: -x[1])[:8],
            "hourly_activity": hourly,
            "searches": sorted(search_counts.items(), key=lambda x: -x[1])[:10],
            "workspaces": ws_counts,
            "total_events": len(app_rows) + len(search_rows) + len(ws_rows),
        }
    finally:
        conn.close()


@router.get("/api/analytics/suggestions")
async def get_suggestions(user: dict = Depends(require_auth)):
    """Get AI-generated suggestions based on user patterns."""
    email = user.get("email", "unknown")
    since = time.time() - (7 * 86400)
    conn = _get_db()
    suggestions = []
    try:
        # Suggest pinning frequently used apps
        app_rows = conn.execute(
            "SELECT event_data FROM events WHERE user_email = ? AND event_type = 'app_open' AND created_at > ?",
            (email, since)
        ).fetchall()
        app_counts = {}
        for row in app_rows:
            try:
                data = json.loads(row["event_data"])
                app_id = data.get("app_id")
                if app_id:
                    app_counts[app_id] = app_counts.get(app_id, 0) + 1
            except:
                pass
        for app_id, count in app_counts.items():
            if count >= 5:
                suggestions.append({
                    "type": "pin_app",
                    "app_id": app_id,
                    "message": f"You opened {app_id} {count} times this week. Pin it?",
                    "priority": min(count / 10, 1.0)
                })

        # Suggest workspace organization
        ws_rows = conn.execute(
            "SELECT event_data FROM events WHERE user_email = ? AND event_type = 'workspace_switch' AND created_at > ?",
            (email, since)
        ).fetchall()
        if len(ws_rows) < 3:
            suggestions.append({
                "type": "use_workspaces",
                "message": "Try using workspaces to organize different tasks. Press Ctrl+1-4 to switch.",
                "priority": 0.5
            })

        # Suggest spotlight for repeated searches
        search_rows = conn.execute(
            "SELECT event_data FROM events WHERE user_email = ? AND event_type = 'search' AND created_at > ?",
            (email, since)
        ).fetchall()
        search_counts = {}
        for row in search_rows:
            try:
                data = json.loads(row["event_data"])
                q = data.get("query", "").lower().strip()
                if q:
                    search_counts[q] = search_counts.get(q, 0) + 1
            except:
                pass
        for query, count in search_counts.items():
            if count >= 3:
                suggestions.append({
                    "type": "shortcut",
                    "query": query,
                    "message": f"You searched '{query}' {count} times. Want a shortcut?",
                    "priority": min(count / 5, 1.0)
                })

        return {"suggestions": sorted(suggestions, key=lambda x: -x["priority"])[:6]}
    finally:
        conn.close()


@router.post("/api/audit/log")
async def log_audit(data: AuditEntry, user: dict = Depends(require_auth)):
    """Log an audit event."""
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO audit_log (user_email, action, resource_type, resource_id, details, ip_address, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user.get("email", "unknown"), data.action, data.resource_type, data.resource_id,
             json.dumps(data.details or {}), user.get("ip", ""), time.time())
        )
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.get("/api/audit/logs")
async def get_audit_logs(
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = None,
    since: Optional[int] = None,
):
    """Get audit log entries. Admin sees all, users see own."""
    email = user.get("email", "unknown")
    is_admin = user.get("role") == "admin"
    conn = _get_db()
    try:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if not is_admin:
            query += " AND user_email = ?"
            params.append(email)
        if action:
            query += " AND action = ?"
            params.append(action)
        if since:
            query += " AND created_at > ?"
            params.append(since)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return {
            "logs": [
                {
                    "id": r["id"],
                    "user_email": r["user_email"],
                    "action": r["action"],
                    "resource_type": r["resource_type"],
                    "resource_id": r["resource_id"],
                    "details": json.loads(r["details"] or "{}"),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@router.get("/api/sessions/active")
async def get_active_sessions(user: dict = Depends(require_auth)):
    """Get active sessions. Admin sees all."""
    is_admin = user.get("role") == "admin"
    conn = _get_db()
    try:
        cutoff = time.time() - 3600  # Active within last hour
        if is_admin:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE ended_at IS NULL AND last_active_at > ? ORDER BY last_active_at DESC",
                (cutoff,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE user_email = ? AND ended_at IS NULL AND last_active_at > ? ORDER BY last_active_at DESC",
                (user.get("email"), cutoff)
            ).fetchall()

        return {
            "sessions": [
                {
                    "session_id": r["session_id"],
                    "user_email": r["user_email"],
                    "started_at": r["started_at"],
                    "last_active_at": r["last_active_at"],
                    "user_agent": r["user_agent"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@router.post("/api/sessions/heartbeat")
async def session_heartbeat(user: dict = Depends(require_auth)):
    """Update session activity."""
    email = user.get("email", "unknown")
    session_id = user.get("session_id", "default")
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO sessions (session_id, user_email, started_at, last_active_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET last_active_at = ?",
            (session_id, email, time.time(), time.time(), time.time())
        )
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()
