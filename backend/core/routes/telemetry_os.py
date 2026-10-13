"""
Sanaa OS — Telemetry & Crash Logger
Receives, stores, and analyses frontend crash reports.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.routes import deps

logger = logging.getLogger(__name__)
router = APIRouter()

DATA_DIR = "/var/www/ai.sanaa.co/data/telemetry"
CRASHES_FILE = os.path.join(DATA_DIR, "crashes.jsonl")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Ensure directory exists once at import time; log warning on failure.
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError as exc:
    logger.warning("Cannot create telemetry data directory %s: %s", DATA_DIR, exc)


# ── Pydantic schemas ─────────────────────────────────────────────────────

class CrashReportIn(BaseModel):
    message: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    line: int = Field(..., ge=0)
    column: int = Field(..., ge=0)
    stack: Optional[str] = Field(default=None)
    userAgent: str = Field(..., min_length=1)
    timestamp: str = Field(..., min_length=1)
    sessionId: Optional[str] = Field(default=None)
    appId: Optional[str] = Field(default=None)
    winId: Optional[str] = Field(default=None)


class CrashAckOut(BaseModel):
    ok: bool
    id: str


# ── Helpers ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rotate_if_needed(path: str, max_size: int = MAX_FILE_SIZE):
    """If path exceeds max_size, rename it to path.1 and start fresh."""
    if os.path.exists(path) and os.path.getsize(path) >= max_size:
        rotated = path + ".1"
        try:
            os.replace(path, rotated)
        except OSError:
            # Fallback: try remove then rename
            if os.path.exists(rotated):
                os.remove(rotated)
            os.rename(path, rotated)


def _append_crash_line(record: dict) -> str:
    """Append a crash record to the JSONL file using advisory locking."""
    _rotate_if_needed(CRASHES_FILE)
    line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
    with open(CRASHES_FILE, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return record["id"]


def _read_all_crashes() -> list[dict]:
    """Read every crash record from the JSONL file."""
    if not os.path.exists(CRASHES_FILE):
        return []
    records = []
    with open(CRASHES_FILE, "r", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return records


def _write_all_crashes(records: list[dict]):
    """Atomically overwrite the JSONL file with the given records."""
    tmp = CRASHES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            for rec in records:
                f.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    os.replace(tmp, CRASHES_FILE)


def _suggested_fix(message: str) -> str:
    msg = message.lower()
    if "typeerror" in msg and "undefined" in msg:
        return "Check for null/undefined before accessing property"
    if "networkerror" in msg or "fetch" in msg:
        return "Check network connectivity and API endpoint availability"
    if "404" in message:
        return "Verify the API endpoint or resource exists"
    if "401" in message or "403" in message:
        return "Check authentication status and session validity"
    if "iframe" in msg or "sandbox" in msg:
        return "Review iframe sandbox permissions"
    return "Review application logs and stack trace"


def _signature(msg: str) -> str:
    return msg[:60]


# ── Routes ───────────────────────────────────────────────────────────────

@router.post("/api/telemetry/crash")
async def post_crash(body: CrashReportIn, user: dict = Depends(deps.require_auth)):
    """Receive a crash report from the frontend and persist it."""
    crash_id = str(uuid.uuid4())
    record = {
        "id": crash_id,
        "message": body.message,
        "source": body.source,
        "line": body.line,
        "column": body.column,
        "stack": body.stack,
        "userAgent": body.userAgent,
        "timestamp": body.timestamp,
        "sessionId": body.sessionId,
        "appId": body.appId,
        "winId": body.winId,
        "received_at": _now_iso(),
        "acknowledged": False,
        "acknowledged_at": None,
    }
    try:
        _append_crash_line(record)
    except OSError as exc:
        logger.error("Failed to write crash report: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to store crash report")
    return {"ok": True, "id": crash_id}


@router.get("/api/telemetry/crashes")
async def list_crashes(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(deps.require_auth),
):
    """List recent crashes with pagination and pattern analysis."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    records = _read_all_crashes()
    total = len(records)

    # Reverse chronological order (newest first)
    records.sort(key=lambda r: r.get("received_at") or "", reverse=True)
    page = records[offset : offset + limit]

    # Pattern analysis
    sig_counter: Counter = Counter()
    sig_last: dict[str, str] = {}
    for rec in records:
        sig = _signature(rec.get("message", ""))
        sig_counter[sig] += 1
        ts = rec.get("received_at", "")
        if ts and (sig not in sig_last or ts > sig_last[sig]):
            sig_last[sig] = ts

    patterns = []
    for sig, count in sig_counter.most_common(10):
        patterns.append(
            {
                "signature": sig,
                "count": count,
                "last_seen": sig_last.get(sig, ""),
                "suggested_fix": _suggested_fix(sig),
            }
        )

    return {"crashes": page, "total": total, "patterns": patterns}


@router.post("/api/telemetry/crashes/{crash_id}/ack")
async def ack_crash(crash_id: str, user: dict = Depends(deps.require_auth)):
    """Mark a crash as acknowledged / reviewed."""
    records = _read_all_crashes()
    for rec in records:
        if rec.get("id") == crash_id:
            rec["acknowledged"] = True
            rec["acknowledged_at"] = _now_iso()
            try:
                _write_all_crashes(records)
            except OSError as exc:
                logger.error("Failed to acknowledge crash %s: %s", crash_id, exc)
                raise HTTPException(status_code=500, detail="Unable to update crash record")
            return {"ok": True, "id": crash_id, "acknowledged_at": rec["acknowledged_at"]}
    raise HTTPException(status_code=404, detail="Crash not found")


@router.get("/api/telemetry/crashes/stats")
async def crash_stats(user: dict = Depends(deps.require_auth)):
    """Return aggregate crash statistics."""
    records = _read_all_crashes()
    total = len(records)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    last_24h = sum(
        1
        for r in records
        if r.get("received_at")
        and datetime.fromisoformat(r["received_at"].replace("Z", "+00:00")) >= cutoff
    )

    source_counter: Counter = Counter(r.get("source", "unknown") for r in records)
    message_counter: Counter = Counter(r.get("message", "unknown") for r in records)

    top_sources = [
        {"source": src, "count": cnt} for src, cnt in source_counter.most_common(3)
    ]
    top_messages = [
        {"message": msg, "count": cnt} for msg, cnt in message_counter.most_common(3)
    ]

    return {
        "total": total,
        "last_24h": last_24h,
        "top_sources": top_sources,
        "top_messages": top_messages,
    }
