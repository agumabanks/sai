"""Project Manager — create and track tasks/tickets with priority, due dates, tags."""
import logging
import json
from datetime import datetime, timezone
from sqlalchemy import text
from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class ProjectManagerSkill(BaseSkill):
    name = "project_manager"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "create":
            return await self._create(args)
        elif action == "list":
            return await self._list(args)
        elif action == "complete":
            return await self._complete(args)
        elif action == "delete":
            return await self._delete(args)
        elif action == "filter":
            return await self._filter(args)
        elif action == "from_insight":
            return await self._from_insight(args, context)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ── create ───────────────────────────────────────────────────────────────
    async def _create(self, args: dict) -> SkillResult:
        title = args.get("title")
        priority = args.get("priority", "medium")
        description = args.get("description", "")
        due_date = args.get("due_date", "")
        tags = args.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        if not title:
            return SkillResult(success=False, error="'title' is required.")
        try:
            task = {
                "title": title,
                "description": description,
                "priority": priority,
                "status": "open",
                "due_date": due_date,
                "tags": tags,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            async with AsyncSessionLocal() as session:
                await session.execute(text("""
                    INSERT INTO system_knowledge (domain, key, value, last_verified)
                    VALUES ('tasks', :key, :value, :ts)
                """), {
                    "key": f"task.{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    "value": json.dumps(task),
                    "ts": datetime.now(timezone.utc),
                })
                await session.commit()
            due_str = f" (due: {due_date})" if due_date else ""
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            return SkillResult(
                success=True,
                output=f"Task created: [{priority.upper()}] {title}{due_str}{tag_str}",
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── list ─────────────────────────────────────────────────────────────────
    async def _list(self, args: dict) -> SkillResult:
        limit = int(args.get("limit", 20))
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT id, value FROM system_knowledge
                    WHERE domain = 'tasks'
                    ORDER BY last_verified DESC
                    LIMIT :limit
                """), {"limit": limit})
                rows = result.mappings().all()

            if not rows:
                return SkillResult(success=True, output="No tasks found.")

            lines = []
            for r in rows:
                try:
                    d = json.loads(r["value"])
                    status_icon = "✅" if d.get("status") == "done" else "⬜"
                    due = f" · due {d['due_date']}" if d.get("due_date") else ""
                    tags = f" [{', '.join(d['tags'])}]" if d.get("tags") else ""
                    lines.append(
                        f"{status_icon} [#{r['id']}] [{d.get('priority','med').upper()}] "
                        f"{d.get('title','Untitled')}{due}{tags}"
                    )
                    if d.get("description"):
                        lines.append(f"   {d['description'][:80]}")
                except Exception:
                    lines.append(f"⬜ [#{r['id']}] {r['value'][:80]}")

            return SkillResult(success=True, output="\n".join(lines))
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── complete ──────────────────────────────────────────────────────────────
    async def _complete(self, args: dict) -> SkillResult:
        task_id = args.get("task_id")
        if not task_id:
            return SkillResult(success=False, error="'task_id' required.")
        try:
            async with AsyncSessionLocal() as session:
                row = await session.execute(
                    text("SELECT value FROM system_knowledge WHERE id = :id AND domain = 'tasks'"),
                    {"id": task_id}
                )
                existing = row.scalar()
                if not existing:
                    return SkillResult(success=False, error=f"Task #{task_id} not found.")
                d = json.loads(existing)
                d["status"] = "done"
                d["completed_at"] = datetime.now(timezone.utc).isoformat()
                await session.execute(
                    text("UPDATE system_knowledge SET value = :val WHERE id = :id"),
                    {"val": json.dumps(d), "id": task_id}
                )
                await session.commit()
            return SkillResult(success=True, output=f"Task #{task_id} marked as complete.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── delete ────────────────────────────────────────────────────────────────
    async def _delete(self, args: dict) -> SkillResult:
        task_id = args.get("task_id")
        if not task_id:
            return SkillResult(success=False, error="'task_id' required.")
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("DELETE FROM system_knowledge WHERE id = :id AND domain = 'tasks'"),
                    {"id": task_id}
                )
                await session.commit()
            return SkillResult(success=True, output=f"Task #{task_id} deleted.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── filter ────────────────────────────────────────────────────────────────
    async def _filter(self, args: dict) -> SkillResult:
        """Filter tasks by priority or status."""
        priority = args.get("priority", "")
        status = args.get("status", "")
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text(
                    "SELECT id, value FROM system_knowledge WHERE domain = 'tasks' ORDER BY last_verified DESC LIMIT 100"
                ))
                rows = result.mappings().all()

            matched = []
            for r in rows:
                try:
                    d = json.loads(r["value"])
                    if priority and d.get("priority") != priority:
                        continue
                    if status and d.get("status") != status:
                        continue
                    matched.append((r["id"], d))
                except Exception:
                    pass

            if not matched:
                return SkillResult(success=True, output="No tasks match the filter.")

            lines = []
            for tid, d in matched:
                icon = "✅" if d.get("status") == "done" else "⬜"
                lines.append(f"{icon} [#{tid}] [{d.get('priority','med').upper()}] {d.get('title','?')}")

            return SkillResult(success=True, output="\n".join(lines), data={"count": len(matched)})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── from_insight ──────────────────────────────────────────────────────────
    async def _from_insight(self, args: dict, context: SkillContext) -> SkillResult:
        """Create a task from a news/strategic insight using the Brain."""
        insight = args.get("insight", "")
        if not insight:
            return SkillResult(success=False, error="'insight' is required.")
        try:
            brain = context.brain
            if not brain:
                from core.brain import Brain
                brain = Brain()
            prompt = (
                f"Given this strategic insight:\n\n{insight}\n\n"
                "Generate a concise actionable task title (max 80 chars) and priority (low/medium/high/critical). "
                "Respond ONLY as JSON: {\"title\": \"...\", \"priority\": \"...\"}"
            )
            resp = await brain.think(prompt, complexity="medium")
            import re
            match = re.search(r'\{[^}]+\}', resp)
            if match:
                import json as _json
                data = _json.loads(match.group())
                args["title"] = data.get("title", insight[:80])
                args["priority"] = data.get("priority", "medium")
            else:
                args["title"] = insight[:80]
                args["priority"] = "medium"

            args["description"] = insight[:200]
            args["tags"] = ["insight", "auto"]
            return await self._create(args)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
