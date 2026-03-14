"""
Calendar Skill — task management and scheduling.

Actions:
  - create_task: Create a new task with title, description, due_date, priority, reminders.
  - list_tasks: List tasks with optional filtering by status, priority, date range.
  - update_task: Modify fields of an existing task.
  - complete_task: Mark a task as done with a completion timestamp.
  - overdue_check: Find tasks past their due_date that are not done.
  - set_reminder: Create a reminder entry for a task with a trigger time.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text, select, desc, and_

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal, TaskCalendar, TaskReminder, utcnow

logger = logging.getLogger(__name__)

VALID_PRIORITIES = ("low", "medium", "high", "urgent")
VALID_STATUSES = ("pending", "in_progress", "done", "cancelled")


def _parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 datetime string, defaulting to UTC if tz-naive."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _task_to_dict(row) -> dict:
    """Convert a TaskCalendar ORM row to a plain dict."""
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description or "",
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "priority": row.priority,
        "status": row.status,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _reminder_to_dict(row) -> dict:
    """Convert a TaskReminder ORM row to a plain dict."""
    return {
        "id": row.id,
        "task_id": row.task_id,
        "trigger_time": row.trigger_time.isoformat() if row.trigger_time else None,
        "message": row.message or "",
        "triggered": row.triggered,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class CalendarSkill(BaseSkill):
    """Task management and scheduling skill."""

    name = "calendar"
    description = (
        "Task management and scheduling: create, list, update, and complete "
        "tasks with due dates, priorities, and reminders. Check for overdue "
        "tasks and set reminder notifications."
    )
    version = "1.0.0"
    permissions = []
    tags = ["calendar", "tasks", "scheduling", "reminders", "productivity"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "create_task":
            return await self._create_task(args)
        elif action == "list_tasks":
            return await self._list_tasks(args)
        elif action == "update_task":
            return await self._update_task(args)
        elif action == "complete_task":
            return await self._complete_task(args)
        elif action == "overdue_check":
            return await self._overdue_check(args)
        elif action == "set_reminder":
            return await self._set_reminder(args)

        return SkillResult(
            success=False,
            error=(
                f"Unknown action: {action}. Valid actions: create_task, "
                "list_tasks, update_task, complete_task, overdue_check, set_reminder"
            ),
        )

    # ------------------------------------------------------------------
    # create_task
    # ------------------------------------------------------------------
    async def _create_task(self, args: dict) -> SkillResult:
        title = args.get("title")
        if not title:
            return SkillResult(success=False, error="Parameter 'title' is required for create_task.")

        description = args.get("description", "")
        priority = args.get("priority", "medium").lower()
        if priority not in VALID_PRIORITIES:
            return SkillResult(
                success=False,
                error=f"Invalid priority: '{priority}'. Must be one of: {', '.join(VALID_PRIORITIES)}",
            )

        due_date = None
        due_date_str = args.get("due_date")
        if due_date_str:
            try:
                due_date = _parse_dt(due_date_str)
            except (ValueError, TypeError) as e:
                return SkillResult(
                    success=False,
                    error=f"Invalid due_date format. Use ISO 8601 (e.g. 2026-03-20T10:00:00Z): {e}",
                )

        try:
            async with AsyncSessionLocal() as session:
                task = TaskCalendar(
                    title=title,
                    description=description,
                    due_date=due_date,
                    priority=priority,
                    status="pending",
                )
                session.add(task)
                await session.flush()  # get the id
                task_id = task.id

                # Create reminders if provided
                reminders_raw = args.get("reminders", [])
                reminder_records = []
                for r in (reminders_raw or []):
                    try:
                        trigger = _parse_dt(r) if isinstance(r, str) else None
                        if trigger:
                            reminder = TaskReminder(
                                task_id=task_id,
                                trigger_time=trigger,
                                message=f"Reminder for: {title}",
                            )
                            session.add(reminder)
                            reminder_records.append(trigger.isoformat())
                    except (ValueError, TypeError):
                        pass  # skip invalid reminder times silently

                await session.commit()
                # Refresh to get server-set defaults
                await session.refresh(task)
                task_dict = _task_to_dict(task)
        except Exception as e:
            logger.error(f"[Calendar] Failed to create task: {e}")
            return SkillResult(success=False, error=f"Failed to create task: {e}")

        output_parts = [
            f"✅ Task created: {title}",
            f"   ID: {task_dict['id']}",
            f"   Priority: {priority}",
            f"   Status: pending",
        ]
        if due_date:
            output_parts.append(f"   Due: {due_date.isoformat()}")
        if reminder_records:
            output_parts.append(f"   Reminders: {len(reminder_records)} set")

        return SkillResult(
            success=True,
            output="\n".join(output_parts),
            data={**task_dict, "reminders_created": reminder_records},
        )

    # ------------------------------------------------------------------
    # list_tasks
    # ------------------------------------------------------------------
    async def _list_tasks(self, args: dict) -> SkillResult:
        status_filter = args.get("status")
        priority_filter = args.get("priority")
        date_from_str = args.get("date_from")
        date_to_str = args.get("date_to")

        try:
            async with AsyncSessionLocal() as session:
                q = select(TaskCalendar)

                conditions = []
                if status_filter:
                    conditions.append(TaskCalendar.status == status_filter.lower())
                if priority_filter:
                    conditions.append(TaskCalendar.priority == priority_filter.lower())
                if date_from_str:
                    try:
                        dt_from = _parse_dt(date_from_str)
                        conditions.append(TaskCalendar.due_date >= dt_from)
                    except (ValueError, TypeError):
                        pass
                if date_to_str:
                    try:
                        dt_to = _parse_dt(date_to_str)
                        conditions.append(TaskCalendar.due_date <= dt_to)
                    except (ValueError, TypeError):
                        pass

                if conditions:
                    q = q.where(and_(*conditions))

                q = q.order_by(desc(TaskCalendar.created_at)).limit(100)
                result = await session.execute(q)
                rows = result.scalars().all()

        except Exception as e:
            logger.error(f"[Calendar] Failed to list tasks: {e}")
            return SkillResult(success=False, error=f"Failed to list tasks: {e}")

        tasks = [_task_to_dict(r) for r in rows]

        if not tasks:
            return SkillResult(
                success=True,
                output="No tasks found matching the given filters.",
                data={"tasks": [], "count": 0},
            )

        output_lines = [f"📋 Tasks ({len(tasks)} found):", ""]
        for t in tasks:
            status_icon = {"pending": "⏳", "in_progress": "🔄", "done": "✅", "cancelled": "❌"}.get(
                t["status"], "❓"
            )
            due_str = f" | Due: {t['due_date']}" if t["due_date"] else ""
            output_lines.append(
                f"  {status_icon} [{t['id']}] {t['title']} "
                f"({t['priority']}{due_str}) — {t['status']}"
            )

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={"tasks": tasks, "count": len(tasks)},
        )

    # ------------------------------------------------------------------
    # update_task
    # ------------------------------------------------------------------
    async def _update_task(self, args: dict) -> SkillResult:
        task_id = args.get("task_id")
        if not task_id:
            return SkillResult(success=False, error="Parameter 'task_id' is required for update_task.")

        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            return SkillResult(success=False, error=f"Invalid task_id: {task_id}. Must be an integer.")

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TaskCalendar).where(TaskCalendar.id == task_id)
                )
                task = result.scalars().first()

                if not task:
                    return SkillResult(success=False, error=f"Task with ID {task_id} not found.")

                updated_fields = []

                if "title" in args and args["title"]:
                    task.title = args["title"]
                    updated_fields.append("title")
                if "description" in args:
                    task.description = args["description"]
                    updated_fields.append("description")
                if "priority" in args:
                    p = args["priority"].lower()
                    if p not in VALID_PRIORITIES:
                        return SkillResult(
                            success=False,
                            error=f"Invalid priority: '{p}'. Must be one of: {', '.join(VALID_PRIORITIES)}",
                        )
                    task.priority = p
                    updated_fields.append("priority")
                if "status" in args:
                    s = args["status"].lower()
                    if s not in VALID_STATUSES:
                        return SkillResult(
                            success=False,
                            error=f"Invalid status: '{s}'. Must be one of: {', '.join(VALID_STATUSES)}",
                        )
                    task.status = s
                    updated_fields.append("status")
                if "due_date" in args and args["due_date"]:
                    try:
                        task.due_date = _parse_dt(args["due_date"])
                        updated_fields.append("due_date")
                    except (ValueError, TypeError) as e:
                        return SkillResult(success=False, error=f"Invalid due_date: {e}")

                if not updated_fields:
                    return SkillResult(
                        success=False,
                        error="No fields to update. Provide at least one of: title, description, priority, status, due_date.",
                    )

                task.updated_at = utcnow()
                await session.commit()
                await session.refresh(task)
                task_dict = _task_to_dict(task)

        except Exception as e:
            logger.error(f"[Calendar] Failed to update task: {e}")
            return SkillResult(success=False, error=f"Failed to update task: {e}")

        return SkillResult(
            success=True,
            output=f"✏️ Task [{task_id}] updated: {', '.join(updated_fields)}",
            data=task_dict,
        )

    # ------------------------------------------------------------------
    # complete_task
    # ------------------------------------------------------------------
    async def _complete_task(self, args: dict) -> SkillResult:
        task_id = args.get("task_id")
        if not task_id:
            return SkillResult(success=False, error="Parameter 'task_id' is required for complete_task.")

        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            return SkillResult(success=False, error=f"Invalid task_id: {task_id}. Must be an integer.")

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TaskCalendar).where(TaskCalendar.id == task_id)
                )
                task = result.scalars().first()

                if not task:
                    return SkillResult(success=False, error=f"Task with ID {task_id} not found.")

                if task.status == "done":
                    return SkillResult(
                        success=True,
                        output=f"Task [{task_id}] is already marked as done.",
                        data=_task_to_dict(task),
                    )

                now = utcnow()
                task.status = "done"
                task.completed_at = now
                task.updated_at = now
                await session.commit()
                await session.refresh(task)
                task_dict = _task_to_dict(task)

        except Exception as e:
            logger.error(f"[Calendar] Failed to complete task: {e}")
            return SkillResult(success=False, error=f"Failed to complete task: {e}")

        return SkillResult(
            success=True,
            output=f"✅ Task [{task_id}] '{task_dict['title']}' marked as done.",
            data=task_dict,
        )

    # ------------------------------------------------------------------
    # overdue_check
    # ------------------------------------------------------------------
    async def _overdue_check(self, args: dict) -> SkillResult:
        try:
            now = utcnow()
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TaskCalendar).where(
                        and_(
                            TaskCalendar.due_date < now,
                            TaskCalendar.status.notin_(["done", "cancelled"]),
                            TaskCalendar.due_date.isnot(None),
                        )
                    ).order_by(TaskCalendar.due_date)
                )
                rows = result.scalars().all()

        except Exception as e:
            logger.error(f"[Calendar] Overdue check failed: {e}")
            return SkillResult(success=False, error=f"Overdue check failed: {e}")

        tasks = [_task_to_dict(r) for r in rows]

        if not tasks:
            return SkillResult(
                success=True,
                output="🎉 No overdue tasks! Everything is on track.",
                data={"overdue_tasks": [], "count": 0},
            )

        output_lines = [f"⚠️ Overdue Tasks ({len(tasks)}):", ""]
        for t in tasks:
            output_lines.append(
                f"  🔴 [{t['id']}] {t['title']} — Due: {t['due_date']} "
                f"({t['priority']})"
            )

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={"overdue_tasks": tasks, "count": len(tasks)},
        )

    # ------------------------------------------------------------------
    # set_reminder
    # ------------------------------------------------------------------
    async def _set_reminder(self, args: dict) -> SkillResult:
        task_id = args.get("task_id")
        if not task_id:
            return SkillResult(success=False, error="Parameter 'task_id' is required for set_reminder.")

        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            return SkillResult(success=False, error=f"Invalid task_id: {task_id}. Must be an integer.")

        trigger_time_str = args.get("trigger_time")
        if not trigger_time_str:
            return SkillResult(
                success=False,
                error="Parameter 'trigger_time' is required for set_reminder.",
            )

        try:
            trigger_time = _parse_dt(trigger_time_str)
        except (ValueError, TypeError) as e:
            return SkillResult(
                success=False,
                error=f"Invalid trigger_time format. Use ISO 8601 (e.g. 2026-03-20T09:00:00Z): {e}",
            )

        message = args.get("reminder_message", "")

        try:
            async with AsyncSessionLocal() as session:
                # Verify the task exists
                result = await session.execute(
                    select(TaskCalendar).where(TaskCalendar.id == task_id)
                )
                task = result.scalars().first()
                if not task:
                    return SkillResult(success=False, error=f"Task with ID {task_id} not found.")

                reminder = TaskReminder(
                    task_id=task_id,
                    trigger_time=trigger_time,
                    message=message or f"Reminder for: {task.title}",
                )
                session.add(reminder)
                await session.commit()
                await session.refresh(reminder)
                reminder_dict = _reminder_to_dict(reminder)

        except Exception as e:
            logger.error(f"[Calendar] Failed to set reminder: {e}")
            return SkillResult(success=False, error=f"Failed to set reminder: {e}")

        return SkillResult(
            success=True,
            output=(
                f"🔔 Reminder set for task [{task_id}] '{task.title}'\n"
                f"   Trigger: {trigger_time.isoformat()}\n"
                f"   Message: {reminder_dict['message']}"
            ),
            data=reminder_dict,
        )


# Register entry point
handler = CalendarSkill
