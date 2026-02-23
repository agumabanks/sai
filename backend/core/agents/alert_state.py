"""
AlertStateManager — Persistent alert deduplication, cooldown, and lifecycle.

Sits between ServerWatchdog (raw events) and notification (emails).
Ensures the same alert is never emailed twice within a cooldown window,
tracks resolution, and escalates backoff for persistent issues.

Backoff tiers (default): immediate → 30min → 2hr → 6hr → 24hr
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, and_

from core.config import get_settings
from core.database import AsyncSessionLocal, WatchdogAlertState

logger = logging.getLogger(__name__)
settings = get_settings()


class AlertDecision:
    """Result of processing a single event through the state manager."""

    def __init__(self, fingerprint: str, action: str, event, state=None):
        self.fingerprint = fingerprint
        self.action = action  # notify_new, notify_escalation, suppress, skip_acknowledged
        self.event = event
        self.state = state


class AlertStateManager:
    """
    Processes watchdog events against persistent state to determine
    which alerts need notification, which are suppressed, and which resolved.
    """

    def __init__(self):
        self.backoff_tiers = settings.watchdog_cooldown_tier_list or [0, 1800, 7200, 21600, 86400]

    @staticmethod
    def compute_fingerprint(category: str, metric: str, severity: str) -> str:
        """
        Stable fingerprint for an alert condition.

        Uses category + metric (NOT the full message, which contains volatile
        values like "CPU at 87%"). This means "CPU at 87%" and "CPU at 92%"
        collapse to the same fingerprint since they represent the same condition.
        """
        raw = f"{category}:{metric}:{severity}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def process_events(self, events) -> dict:
        """
        Main entry point. Takes raw WatchdogEvents, returns categorized decisions.

        Returns:
            {
                "to_notify": [AlertDecision, ...],   # New or escalation-ready
                "suppressed": [AlertDecision, ...],   # Within cooldown
                "resolved": [WatchdogAlertState, ...], # Was open, now gone
                "acknowledged": [AlertDecision, ...],  # User-suppressed
            }
        """
        now = datetime.now(timezone.utc)
        current_fingerprints = set()
        results = {
            "to_notify": [],
            "suppressed": [],
            "resolved": [],
            "acknowledged": [],
        }

        for event in events:
            if event.severity not in ("critical", "high"):
                continue

            fp = self.compute_fingerprint(event.category, event.metric, event.severity)
            current_fingerprints.add(fp)

            state = await self._get_state(fp)

            if state is None:
                # NEW alert — create state, notify immediately
                state = await self._create_state(event, fp, now)
                await self._mark_notified(state, now)
                results["to_notify"].append(
                    AlertDecision(fp, "notify_new", event, state)
                )
            elif state.status == "acknowledged":
                # User suppressed — update seen but don't notify
                await self._update_seen(state, event, now)
                results["acknowledged"].append(
                    AlertDecision(fp, "skip_acknowledged", event, state)
                )
            elif state.status == "resolved":
                # Was resolved, now it's back — re-open and notify
                await self._reopen_state(state, event, now)
                results["to_notify"].append(
                    AlertDecision(fp, "notify_new", event, state)
                )
            else:
                # ONGOING — check cooldown backoff
                await self._update_seen(state, event, now)
                if self._cooldown_expired(state, now):
                    await self._advance_backoff(state, now)
                    results["to_notify"].append(
                        AlertDecision(fp, "notify_escalation", event, state)
                    )
                else:
                    results["suppressed"].append(
                        AlertDecision(fp, "suppress", event, state)
                    )

        # Check for RESOLVED alerts: open states not seen this cycle
        stale_threshold = timedelta(seconds=settings.watchdog_stale_threshold)
        resolved = await self._find_resolved(current_fingerprints, now, stale_threshold)
        results["resolved"] = resolved

        return results

    async def _get_state(self, fingerprint: str):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(WatchdogAlertState).where(
                    WatchdogAlertState.fingerprint == fingerprint
                )
            )
            return result.scalars().first()

    async def _create_state(self, event, fingerprint: str, now) -> WatchdogAlertState:
        return await WatchdogAlertState.create(
            fingerprint=fingerprint,
            category=event.category,
            metric=event.metric,
            status="open",
            severity=event.severity,
            latest_message=event.message,
            latest_value=event.value,
            first_seen_at=now,
            last_seen_at=now,
            notification_count=0,
            backoff_tier=0,
            occurrence_count=1,
        )

    async def _update_seen(self, state, event, now):
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(WatchdogAlertState)
                .where(WatchdogAlertState.id == state.id)
                .values(
                    last_seen_at=now,
                    latest_message=event.message,
                    latest_value=event.value,
                    severity=event.severity,
                    occurrence_count=state.occurrence_count + 1,
                )
            )
            await session.commit()
            state.occurrence_count += 1
            state.latest_message = event.message

    async def _reopen_state(self, state, event, now):
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(WatchdogAlertState)
                .where(WatchdogAlertState.id == state.id)
                .values(
                    status="open",
                    resolved_at=None,
                    last_seen_at=now,
                    latest_message=event.message,
                    latest_value=event.value,
                    severity=event.severity,
                    backoff_tier=0,
                    notification_count=0,
                    last_notified_at=now,
                    next_notify_at=now + timedelta(seconds=self.backoff_tiers[min(1, len(self.backoff_tiers) - 1)]),
                    occurrence_count=state.occurrence_count + 1,
                )
            )
            await session.commit()

    def _cooldown_expired(self, state, now) -> bool:
        if state.last_notified_at is None:
            return True
        if state.next_notify_at is None:
            return True
        return now >= state.next_notify_at

    async def _mark_notified(self, state, now):
        """Mark initial notification on a new alert."""
        next_tier = min(1, len(self.backoff_tiers) - 1)
        cooldown_seconds = self.backoff_tiers[next_tier]
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(WatchdogAlertState)
                .where(WatchdogAlertState.id == state.id)
                .values(
                    notification_count=1,
                    last_notified_at=now,
                    next_notify_at=now + timedelta(seconds=cooldown_seconds),
                    backoff_tier=1,
                )
            )
            await session.commit()

    async def _advance_backoff(self, state, now):
        new_tier = min(state.backoff_tier + 1, len(self.backoff_tiers) - 1)
        cooldown_seconds = self.backoff_tiers[new_tier]
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(WatchdogAlertState)
                .where(WatchdogAlertState.id == state.id)
                .values(
                    backoff_tier=new_tier,
                    notification_count=state.notification_count + 1,
                    last_notified_at=now,
                    next_notify_at=now + timedelta(seconds=cooldown_seconds),
                )
            )
            await session.commit()

    async def _find_resolved(self, current_fps: set, now, stale_threshold: timedelta):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(WatchdogAlertState).where(
                    and_(
                        WatchdogAlertState.status == "open",
                        WatchdogAlertState.last_seen_at < now - stale_threshold,
                    )
                )
            )
            stale_states = result.scalars().all()

        resolved = []
        for state in stale_states:
            if state.fingerprint not in current_fps:
                await self._mark_resolved(state, now)
                resolved.append(state)

        return resolved

    async def _mark_resolved(self, state, now):
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(WatchdogAlertState)
                .where(WatchdogAlertState.id == state.id)
                .values(status="resolved", resolved_at=now)
            )
            await session.commit()

    async def record_healing(self, fingerprint: str, action_name: str, success: bool):
        """Record a healing attempt against an alert state."""
        now = datetime.now(timezone.utc)
        state = await self._get_state(fingerprint)
        if not state:
            return
        async with AsyncSessionLocal() as session:
            values = {
                "heal_attempts": state.heal_attempts + 1,
                "last_heal_action": action_name,
                "last_heal_at": now,
            }
            if success:
                values["heal_successes"] = state.heal_successes + 1

            await session.execute(
                update(WatchdogAlertState)
                .where(WatchdogAlertState.fingerprint == fingerprint)
                .values(**values)
            )
            await session.commit()

    async def acknowledge(self, fingerprint: str, user: str):
        """Acknowledge an alert — stop notifications until it resolves and re-opens."""
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(WatchdogAlertState)
                .where(WatchdogAlertState.fingerprint == fingerprint)
                .values(
                    status="acknowledged",
                    acknowledged_at=datetime.now(timezone.utc),
                    acknowledged_by=user,
                )
            )
            await session.commit()

    async def get_active_alerts(self) -> list:
        """Get all currently open or acknowledged alerts for dashboard."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(WatchdogAlertState)
                .where(WatchdogAlertState.status.in_(["open", "acknowledged"]))
                .order_by(WatchdogAlertState.last_seen_at.desc())
            )
            return result.scalars().all()
