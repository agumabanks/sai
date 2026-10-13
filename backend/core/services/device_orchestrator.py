"""
Sanaa Device Army — Device Orchestrator Service.

Handles intelligent task assignment, load balancing, workload migration,
device health evaluation, and failover for the distributed workforce.
"""

import logging
import random
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.database import (
    Device, DeviceTask, DeviceCommand, DeviceLog, DevicePairing,
    AsyncSessionLocal, utcnow,
)

logger = logging.getLogger(__name__)


class DeviceOrchestrator:
    """
    Central orchestrator for the device army.

    Responsibilities:
    - Assign pending tasks to the best available device
    - Load-balance across devices of the same role
    - Handle device failover (SOS → reassign tasks)
    - Schedule recurring device tasks
    - Track device health and reliability scores
    - Coordinate workload migration
    """

    def __init__(self):
        self._scheduler_task: Optional[asyncio.Task] = None
        self._health_purge_task: Optional[asyncio.Task] = None

    # ─── TASK ASSIGNMENT ──────────────────────────────────────────────

    async def assign_task(self, task_id: str) -> bool:
        """
        Attempt to assign a pending task to the best available device.

        Returns True if assigned, False if no suitable device available.
        """
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DeviceTask).where(DeviceTask.task_id == task_id)
            )
            task = result.scalars().first()

            if not task or task.status != "pending":
                return False

            # If already targeted at a specific device
            if task.device_id:
                device_result = await session.execute(
                    select(Device).where(
                        Device.device_id == task.device_id,
                        Device.is_revoked == False,
                    )
                )
                device = device_result.scalars().first()
                if device and device.status in ("online", "idle"):
                    task.status = "assigned"
                    task.assigned_at = utcnow()
                    await session.commit()
                    return True

                # Targeted device unavailable — find another with same role
                if device:
                    candidates = await self._find_candidates_by_capability(
                        task.task_type, exclude=device.device_id
                    )
                else:
                    return False
            else:
                # No target device — find one
                candidates = await self._find_candidates_by_capability(task.task_type)

            if not candidates:
                return False

            # Pick best candidate (least tasks currently assigned)
            chosen = candidates[0]
            task.device_id = chosen.device_id
            task.status = "assigned"
            task.assigned_at = utcnow()
            await session.commit()

        logger.info(f"Task {task.task_id} ({task.task_type}) assigned to device {task.device_id}")
        return True

    async def _find_candidates_by_capability(
        self, task_type: str, exclude: Optional[str] = None, limit: int = 5
    ) -> list[Device]:
        """
        Find online devices that can handle a given task type.
        Ordered by least-loaded first (fewest pending tasks).
        """
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            # Get online devices
            query = select(Device).where(
                Device.status.in_(["online", "idle"]),
                Device.is_revoked == False,
            )
            if exclude:
                query = query.where(Device.device_id != exclude)
            query = query.order_by(Device.last_heartbeat.desc().nullslast()).limit(limit * 2)

            result = await session.execute(query)
            devices = result.scalars().all()

            if not devices:
                return []

            # For each device, count pending tasks
            candidates = []
            for d in devices:
                task_count = await self._count_pending_tasks(d.device_id)
                candidates.append((d, task_count))

            # Sort by task count ascending
            candidates.sort(key=lambda x: x[1])
            return [c[0] for c in candidates[:limit]]

    async def _count_pending_tasks(self, device_id: str) -> int:
        """Count how many active (pending/in_progress) tasks a device has."""
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select, func
            result = await session.execute(
                select(func.count(DeviceTask.id)).where(
                    DeviceTask.device_id == device_id,
                    DeviceTask.status.in_(["pending", "assigned", "in_progress"]),
                )
            )
            return result.scalar() or 0

    # ─── FAILOVER HANDLING ────────────────────────────────────────────

    async def handle_device_failure(self, failed_device_id: str):
        """
        Called when a device goes offline or sends SOS.
        Reassigns its active tasks to other healthy devices.
        """
        logger.warning(f"Handling failover for device {failed_device_id}")

        # Get active tasks
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DeviceTask).where(
                    DeviceTask.device_id == failed_device_id,
                    DeviceTask.status.in_(["pending", "assigned", "in_progress"]),
                )
            )
            active_tasks = result.scalars().all()

        if not active_tasks:
            return {"failed_device": failed_device_id, "tasks_reassigned": 0}

        # Find replacement device (same role, online)
        target_role = None
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            dev_result = await session.execute(
                select(Device).where(Device.device_id == failed_device_id)
            )
            failed_dev = dev_result.scalars().first()
            if failed_dev:
                target_role = failed_dev.worker_role

        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            candidates = await session.execute(
                select(Device).where(
                    Device.status.in_(["online", "idle"]),
                    Device.is_revoked == False,
                    Device.device_id != failed_device_id,
                )
            )
            # Prefer same role
            all_candidates = candidates.scalars().all()
            same_role = [d for d in all_candidates if d.worker_role == target_role] if target_role else []
            replacements = same_role or all_candidates

        reassigned = 0
        for task in active_tasks:
            if not replacements:
                # Leave task pending — will be picked up when a device comes online
                async with AsyncSessionLocal() as session:
                    task.status = "pending"
                    task.device_id = None
                    await session.merge(task)
                    await session.commit()
                continue

            # Assign to the least loaded replacement (round-robin)
            replacement = replacements[reassigned % len(replacements)]
            async with AsyncSessionLocal() as session:
                task.device_id = replacement.device_id
                task.status = "assigned"
                task.assigned_at = utcnow()
                task.retry_count = (task.retry_count or 0) + 1
                await session.merge(task)
                await session.commit()
            reassigned += 1

        # Log the failover
        used_replacements = replacements[:min(len(replacements), reassigned)] if reassigned else []
        await DeviceLog.create(
            device_id=failed_device_id,
            log_type="state_change",
            source="orchestrator",
            message=f"Failover: {reassigned}/{len(active_tasks)} tasks reassigned from {failed_device_id}",
            log_metadata={
                "target_devices": [d.device_id for d in used_replacements],
                "target_role": target_role,
            },
            severity="high",
        )

        logger.info(
            f"Failover complete: {reassigned}/{len(active_tasks)} tasks reassigned "
            f"from {failed_device_id}"
        )
        return {
            "failed_device": failed_device_id,
            "tasks_found": len(active_tasks),
            "tasks_reassigned": reassigned,
        }

    # ─── SCHEDULED BACKGROUND WORK ────────────────────────────────────

    async def start_scheduler(self):
        """Start background task scheduler."""
        if self._scheduler_task is None or self._scheduler_task.done():
            self._scheduler_task = asyncio.create_task(self._run_scheduler())
            logger.info("Device orchestrator scheduler started")

    async def _run_scheduler(self):
        """Every 30s: try to assign unassigned pending tasks."""
        while True:
            try:
                await self._process_pending_assignments()
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)

    async def _process_pending_assignments(self):
        """Find unassigned pending tasks and assign them."""
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select, func
            result = await session.execute(
                select(DeviceTask).where(
                    DeviceTask.status == "pending",
                    DeviceTask.device_id.is_(None),  # Not yet assigned
                ).order_by(DeviceTask.priority.desc(), DeviceTask.created_at.asc()).limit(20)
            )
            tasks = result.scalars().all()

        assigned = 0
        for task in tasks:
            success = await self.assign_task(task.task_id)
            if success:
                assigned += 1

        if assigned:
            logger.debug(f"Scheduler assigned {assigned} pending task(s)")

    # ─── DEVICE HEALTH & SCORING ─────────────────────────────────────

    async def calculate_device_score(self, device_id: str) -> dict:
        """
        Calculate a health/reliability score for a device (0-100).
        Factors: uptime, task completion rate, response time, battery, errors.
        """
        score = 100
        reasons = []

        async with AsyncSessionLocal() as session:
            from sqlalchemy import select, func

            device_result = await session.execute(
                select(Device).where(Device.device_id == device_id)
            )
            device = device_result.scalars().first()
            if not device:
                return {"score": 0, "reasons": ["Device not found"]}

            # Battery penalty
            if device.battery_health:
                try:
                    battery = int(device.battery_health.replace("%", ""))
                    if battery < 20:
                        score -= 25
                        reasons.append("Low battery")
                    elif battery < 50:
                        score -= 10
                        reasons.append("Moderate battery")
                except (ValueError, AttributeError):
                    pass

            # Task completion rate
            tasks_result = await session.execute(
                select(
                    func.count(DeviceTask.id).filter(DeviceTask.status == "completed"),
                    func.count(DeviceTask.id).filter(DeviceTask.status == "failed"),
                ).where(DeviceTask.device_id == device_id)
            )
            completed_count, failed_count = tasks_result.one()
            total_done = (completed_count or 0) + (failed_count or 0)
            if total_done > 5:
                failure_rate = (failed_count or 0) / total_done
                if failure_rate > 0.3:
                    score -= 20
                    reasons.append(f"High failure rate ({failure_rate:.0%})")
                elif failure_rate > 0.1:
                    score -= 5
                    reasons.append(f"Moderate failure rate ({failure_rate:.0%})")

            # Stale heartbeat penalty
            if device.last_heartbeat:
                hours_since_hb = (utcnow() - device.last_heartbeat).total_seconds() / 3600
                if hours_since_hb > 1:
                    score -= 15
                    reasons.append(f"Stale heartbeat ({hours_since_hb:.1f}h ago)")

            # Uptime bonus
            if device.total_uptime_seconds and device.total_uptime_seconds > 86400:
                score += 5
                reasons.append("Good uptime")

            # Revoked penalty
            if device.is_revoked:
                score = 0
                reasons.append("Device revoked")

        return {
            "score": max(0, min(100, score)),
            "reasons": reasons,
            "device_id": device_id,
        }

    # ─── WORKLOAD BALANCING ───────────────────────────────────────────

    async def balance_workload(self, role: Optional[str] = None):
        """
        Redistribute tasks across devices of the same role to balance load.
        Moves tasks from overloaded devices to idle ones.
        """
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select, func

            # Find devices by role
            query = select(Device).where(
                Device.status.in_(["online", "idle", "busy"]),
                Device.is_revoked == False,
            )
            if role:
                query = query.where(Device.worker_role == role)

            result = await session.execute(query.order_by(Device.last_heartbeat.desc()))
            devices = result.scalars().all()

        if len(devices) < 2:
            return {"balanced": False, "reason": "Need at least 2 devices"}

        # Count tasks per device
        device_loads = []
        for d in devices:
            count = await self._count_pending_tasks(d.device_id)
            device_loads.append((d, count))

        device_loads.sort(key=lambda x: x[1], reverse=True)
        avg_load = sum(load for _, load in device_loads) / len(device_loads)

        overloaded = [(d, load) for d, load in device_loads if load > avg_load + 2]
        underloaded = [(d, load) for d, load in device_loads if load < avg_load - 1]

        moved = 0
        for src, _ in overloaded:
            if not underloaded:
                break
            # Move one task from src to dst
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                task_result = await session.execute(
                    select(DeviceTask).where(
                        DeviceTask.device_id == src.device_id,
                        DeviceTask.status.in_(["pending", "assigned"]),
                    ).order_by(DeviceTask.priority.asc()).limit(1)
                )
                task = task_result.scalars().first()
                if task:
                    dst = underloaded[0][0]
                    task.device_id = dst.device_id
                    await session.commit()
                    moved += 1
                    # Recalculate underloaded list
                    new_count = await self._count_pending_tasks(dst.device_id)
                    underloaded[0] = (dst, new_count)
                    if new_count >= avg_load:
                        underloaded.pop(0)

        if moved:
            logger.info(f"Workload balanced: moved {moved} task(s)")
        return {"balanced": True, "tasks_moved": moved}

    # ─── STATUS ───────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "orchestrator": "active",
            "scheduler_running": self._scheduler_task is not None and not self._scheduler_task.done(),
        }


# Singleton
orchestrator = DeviceOrchestrator()
