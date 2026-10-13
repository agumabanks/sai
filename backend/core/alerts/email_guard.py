"""Shared alert email rate limiting.

The monitoring stack has multiple email entry points. This module gives all of
them one cooldown policy so a single noisy check cannot send a mailbox-sized
burst of messages.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_subject(subject: str) -> str:
    """Normalize dynamic subjects so repeated variants share a fingerprint."""
    normalized = (subject or "alert").strip().lower()
    normalized = re.sub(r"\b[a-f0-9]{6,}\b", "#", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "#", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:300]


def subject_fingerprint(subject: str, category: str = "alert") -> str:
    raw = f"{category}:{normalize_subject(subject)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


async def reserve_alert_email(
    subject: str,
    *,
    category: str = "alert",
    cooldown_seconds=None,
    global_min_seconds=None,
):
    """Return (allowed, reason) and reserve the send slot when allowed."""
    from core.database import SystemKnowledge

    enabled = await SystemKnowledge.get_pref("alert.email_rate_limit_enabled", True)
    if not _as_bool(enabled, True):
        return True, "rate limit disabled"

    if global_min_seconds is None:
        global_min_seconds = await SystemKnowledge.get_pref(
            "alert.email_global_min_seconds",
            300,
        )
    if cooldown_seconds is None:
        cooldown_seconds = await SystemKnowledge.get_pref(
            "alert.email_cooldown_seconds",
            3600,
        )

    global_min_seconds = _as_int(global_min_seconds, 300)
    cooldown_seconds = _as_int(cooldown_seconds, 3600)

    now = datetime.now(timezone.utc)
    global_key = "alert.email.last_sent.global"
    fingerprint = subject_fingerprint(subject, category)
    subject_key = f"alert.email.last_sent.{category}.{fingerprint}"

    if global_min_seconds > 0:
        last_global = _parse_dt(await SystemKnowledge.get_pref(global_key, None))
        if last_global:
            elapsed = (now - last_global).total_seconds()
            if elapsed < global_min_seconds:
                remaining = int(global_min_seconds - elapsed)
                return False, f"global cooldown active for {remaining}s"

    if cooldown_seconds > 0:
        last_subject = _parse_dt(await SystemKnowledge.get_pref(subject_key, None))
        if last_subject:
            elapsed = (now - last_subject).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = int(cooldown_seconds - elapsed)
                return False, f"subject cooldown active for {remaining}s"

    now_value = now.isoformat()
    try:
        if global_min_seconds > 0:
            await SystemKnowledge.set_pref(
                global_key,
                now_value,
                source="alert_email_guard",
            )
        if cooldown_seconds > 0:
            await SystemKnowledge.set_pref(
                subject_key,
                now_value,
                source="alert_email_guard",
            )
    except Exception as exc:
        logger.warning("Could not persist alert email cooldown state: %s", exc)

    return True, "reserved"
