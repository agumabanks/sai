"""
Tests for the calendar skill — task management and scheduling.

Fulfills: VAL-SKILL-012, VAL-SKILL-013
  - The calendar skill has a valid manifest.yaml and handler.py. It loads into
    the skill registry without errors and appears in the API skills listing.
  - The calendar skill creates, lists, and manages tasks with due dates,
    priorities, and reminders. Overdue tasks are flagged.
"""

import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

import pytest

# Ensure backend is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Manifest & Loading Tests
# ---------------------------------------------------------------------------

class TestCalendarManifest:
    """Verify the calendar skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(BACKEND_DIR, "skills", "calendar", "manifest.yaml")
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'calendar'."""
        assert self.manifest.name == "calendar"

    def test_manifest_has_description(self):
        """Manifest includes a meaningful description."""
        assert self.manifest.description
        assert len(self.manifest.description) > 10

    def test_manifest_has_no_special_permissions(self):
        """Calendar skill does not require shell or network permissions."""
        assert "shell" not in self.manifest.permissions
        assert "network" not in self.manifest.permissions

    def test_manifest_has_action_parameter(self):
        """Manifest defines an 'action' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "action" in param_names

    def test_manifest_action_enum_values(self):
        """Action parameter includes all six expected actions."""
        action_param = next(p for p in self.manifest.parameters if p.name == "action")
        for expected in ["create_task", "list_tasks", "update_task",
                         "complete_task", "overdue_check", "set_reminder"]:
            assert expected in action_param.enum, f"Missing action: {expected}"

    def test_manifest_has_priority_parameter(self):
        """Manifest defines a 'priority' parameter with enum."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "priority" in param_names
        priority_param = next(p for p in self.manifest.parameters if p.name == "priority")
        for level in ["low", "medium", "high", "urgent"]:
            assert level in priority_param.enum

    def test_manifest_has_task_id_parameter(self):
        """Manifest defines a 'task_id' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "task_id" in param_names

    def test_manifest_category_is_productivity(self):
        """Skill category should be 'productivity'."""
        assert "productivity" in self.manifest.tags


class TestCalendarLoading:
    """Verify the calendar skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """calendar skill loads without errors."""
        assert "calendar" in self.loaded, (
            f"calendar not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'calendar'."""
        skill = self.loaded["calendar"]
        assert skill.name == "calendar"


# ---------------------------------------------------------------------------
# Helper: mock DB session context manager
# ---------------------------------------------------------------------------

def _mock_session_ctx(mock_session):
    """Create an AsyncMock context manager wrapping *mock_session*."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# create_task Action Tests
# ---------------------------------------------------------------------------

class TestCreateTask:
    """Test the create_task action."""

    @pytest.fixture
    def skill(self):
        from skills.calendar.handler import CalendarSkill
        return CalendarSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_create_task_success(self, skill, context):
        """create_task stores a task with title, priority, and due_date."""
        due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        # Build a mock TaskCalendar row returned after commit+refresh
        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.title = "Write report"
        mock_task.description = "Annual report draft"
        mock_task.due_date = datetime.fromisoformat(due)
        mock_task.priority = "high"
        mock_task.status = "pending"
        mock_task.completed_at = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # After flush, the task should have an id
        async def set_id(*a, **kw):
            pass
        mock_session.flush.side_effect = set_id

        # After refresh, return mock_task attributes
        async def refresh_task(obj):
            obj.id = mock_task.id
            obj.title = mock_task.title
            obj.description = mock_task.description
            obj.due_date = mock_task.due_date
            obj.priority = mock_task.priority
            obj.status = mock_task.status
            obj.completed_at = mock_task.completed_at
            obj.created_at = mock_task.created_at
            obj.updated_at = mock_task.updated_at
        mock_session.refresh.side_effect = refresh_task

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {
                    "action": "create_task",
                    "title": "Write report",
                    "description": "Annual report draft",
                    "due_date": due,
                    "priority": "high",
                },
                context,
            )

        assert result.success is True
        assert result.data["title"] == "Write report"
        assert result.data["priority"] == "high"
        assert result.data["status"] == "pending"
        assert "42" in result.output or "Write report" in result.output

    @pytest.mark.asyncio
    async def test_create_task_missing_title(self, skill, context):
        """create_task without title returns error."""
        result = await skill.execute({"action": "create_task"}, context)
        assert result.success is False
        assert "title" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_task_invalid_priority(self, skill, context):
        """create_task with invalid priority returns error."""
        result = await skill.execute(
            {"action": "create_task", "title": "Test", "priority": "critical"},
            context,
        )
        assert result.success is False
        assert "priority" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_task_invalid_due_date(self, skill, context):
        """create_task with bad due_date format returns error."""
        result = await skill.execute(
            {"action": "create_task", "title": "Test", "due_date": "not-a-date"},
            context,
        )
        assert result.success is False
        assert "due_date" in result.error.lower() or "iso" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_task_with_reminders(self, skill, context):
        """create_task with reminders list creates reminder entries."""
        due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        reminder_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

        mock_task = MagicMock()
        mock_task.id = 99
        mock_task.title = "Meeting prep"
        mock_task.description = ""
        mock_task.due_date = datetime.fromisoformat(due)
        mock_task.priority = "medium"
        mock_task.status = "pending"
        mock_task.completed_at = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        async def refresh_task(obj):
            if hasattr(obj, 'title'):
                obj.id = mock_task.id
                obj.title = mock_task.title
                obj.description = mock_task.description
                obj.due_date = mock_task.due_date
                obj.priority = mock_task.priority
                obj.status = mock_task.status
                obj.completed_at = mock_task.completed_at
                obj.created_at = mock_task.created_at
                obj.updated_at = mock_task.updated_at
        mock_session.refresh.side_effect = refresh_task

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {
                    "action": "create_task",
                    "title": "Meeting prep",
                    "due_date": due,
                    "reminders": [reminder_time],
                },
                context,
            )

        assert result.success is True
        assert len(result.data.get("reminders_created", [])) == 1
        # session.add called at least twice: task + reminder
        assert mock_session.add.call_count >= 2


# ---------------------------------------------------------------------------
# list_tasks Action Tests
# ---------------------------------------------------------------------------

class TestListTasks:
    """Test the list_tasks action with filtering."""

    @pytest.fixture
    def skill(self):
        from skills.calendar.handler import CalendarSkill
        return CalendarSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    def _make_task_row(self, id, title, priority="medium", status="pending", due_date=None):
        row = MagicMock()
        row.id = id
        row.title = title
        row.description = ""
        row.due_date = due_date
        row.priority = priority
        row.status = status
        row.completed_at = None
        row.created_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
        return row

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, skill, context):
        """list_tasks with no results returns informative message."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute({"action": "list_tasks"}, context)

        assert result.success is True
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_tasks_returns_tasks(self, skill, context):
        """list_tasks returns task data when tasks exist."""
        rows = [
            self._make_task_row(1, "Task A", "high", "pending"),
            self._make_task_row(2, "Task B", "low", "done"),
        ]
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute({"action": "list_tasks"}, context)

        assert result.success is True
        assert result.data["count"] == 2
        assert result.data["tasks"][0]["title"] == "Task A"

    @pytest.mark.asyncio
    async def test_list_tasks_with_status_filter(self, skill, context):
        """list_tasks with status filter builds correct query."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "list_tasks", "status": "pending"},
                context,
            )

        assert result.success is True
        # The query was executed (we just check it didn't error)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tasks_with_priority_filter(self, skill, context):
        """list_tasks with priority filter works."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "list_tasks", "priority": "high"},
                context,
            )

        assert result.success is True
        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# update_task Action Tests
# ---------------------------------------------------------------------------

class TestUpdateTask:
    """Test the update_task action."""

    @pytest.fixture
    def skill(self):
        from skills.calendar.handler import CalendarSkill
        return CalendarSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_update_task_success(self, skill, context):
        """update_task modifies the requested fields."""
        existing = MagicMock()
        existing.id = 10
        existing.title = "Old Title"
        existing.description = ""
        existing.due_date = None
        existing.priority = "medium"
        existing.status = "pending"
        existing.completed_at = None
        existing.created_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        async def refresh(obj):
            pass
        mock_session.refresh = AsyncMock(side_effect=refresh)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "update_task", "task_id": 10, "title": "New Title", "priority": "urgent"},
                context,
            )

        assert result.success is True
        assert "title" in result.output.lower() or "updated" in result.output.lower()
        assert existing.title == "New Title"
        assert existing.priority == "urgent"

    @pytest.mark.asyncio
    async def test_update_task_missing_id(self, skill, context):
        """update_task without task_id returns error."""
        result = await skill.execute(
            {"action": "update_task", "title": "Something"},
            context,
        )
        assert result.success is False
        assert "task_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, skill, context):
        """update_task for non-existent task returns error."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "update_task", "task_id": 999, "title": "Nope"},
                context,
            )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_update_task_invalid_priority(self, skill, context):
        """update_task with invalid priority returns error."""
        existing = MagicMock()
        existing.id = 10
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "update_task", "task_id": 10, "priority": "extreme"},
                context,
            )

        assert result.success is False
        assert "priority" in result.error.lower()


# ---------------------------------------------------------------------------
# complete_task Action Tests
# ---------------------------------------------------------------------------

class TestCompleteTask:
    """Test the complete_task action."""

    @pytest.fixture
    def skill(self):
        from skills.calendar.handler import CalendarSkill
        return CalendarSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_complete_task_success(self, skill, context):
        """complete_task sets status='done' and completed_at."""
        existing = MagicMock()
        existing.id = 5
        existing.title = "Finish docs"
        existing.description = ""
        existing.due_date = None
        existing.priority = "medium"
        existing.status = "pending"
        existing.completed_at = None
        existing.created_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "complete_task", "task_id": 5},
                context,
            )

        assert result.success is True
        assert existing.status == "done"
        assert existing.completed_at is not None
        assert "done" in result.output.lower()

    @pytest.mark.asyncio
    async def test_complete_task_already_done(self, skill, context):
        """complete_task on an already done task returns informational message."""
        existing = MagicMock()
        existing.id = 5
        existing.title = "Done task"
        existing.description = ""
        existing.due_date = None
        existing.priority = "low"
        existing.status = "done"
        existing.completed_at = datetime.now(timezone.utc)
        existing.created_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "complete_task", "task_id": 5},
                context,
            )

        assert result.success is True
        assert "already" in result.output.lower()

    @pytest.mark.asyncio
    async def test_complete_task_missing_id(self, skill, context):
        """complete_task without task_id returns error."""
        result = await skill.execute({"action": "complete_task"}, context)
        assert result.success is False
        assert "task_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self, skill, context):
        """complete_task for non-existent task returns error."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "complete_task", "task_id": 404},
                context,
            )

        assert result.success is False
        assert "not found" in result.error.lower()


# ---------------------------------------------------------------------------
# overdue_check Action Tests
# ---------------------------------------------------------------------------

class TestOverdueCheck:
    """Test the overdue_check action."""

    @pytest.fixture
    def skill(self):
        from skills.calendar.handler import CalendarSkill
        return CalendarSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    def _make_task_row(self, id, title, due_date, status="pending"):
        row = MagicMock()
        row.id = id
        row.title = title
        row.description = ""
        row.due_date = due_date
        row.priority = "high"
        row.status = status
        row.completed_at = None
        row.created_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
        return row

    @pytest.mark.asyncio
    async def test_overdue_check_finds_overdue_tasks(self, skill, context):
        """overdue_check returns tasks past their due_date with status != done."""
        past = datetime.now(timezone.utc) - timedelta(days=2)
        rows = [
            self._make_task_row(1, "Late task", past),
            self._make_task_row(2, "Another late", past - timedelta(hours=5)),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute({"action": "overdue_check"}, context)

        assert result.success is True
        assert result.data["count"] == 2
        assert result.data["overdue_tasks"][0]["title"] == "Late task"

    @pytest.mark.asyncio
    async def test_overdue_check_no_overdue(self, skill, context):
        """overdue_check with no overdue tasks returns positive message."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute({"action": "overdue_check"}, context)

        assert result.success is True
        assert result.data["count"] == 0
        assert "no overdue" in result.output.lower()


# ---------------------------------------------------------------------------
# set_reminder Action Tests
# ---------------------------------------------------------------------------

class TestSetReminder:
    """Test the set_reminder action."""

    @pytest.fixture
    def skill(self):
        from skills.calendar.handler import CalendarSkill
        return CalendarSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_set_reminder_success(self, skill, context):
        """set_reminder creates a reminder entry with trigger time."""
        trigger = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        task = MagicMock()
        task.id = 7
        task.title = "Deploy release"

        reminder_mock = MagicMock()
        reminder_mock.id = 1
        reminder_mock.task_id = 7
        reminder_mock.trigger_time = datetime.fromisoformat(trigger)
        reminder_mock.message = "Reminder for: Deploy release"
        reminder_mock.triggered = False
        reminder_mock.created_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        # First execute: select task
        mock_result_task = MagicMock()
        mock_result_task.scalars.return_value.first.return_value = task
        mock_session.execute = AsyncMock(return_value=mock_result_task)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        async def refresh_reminder(obj):
            obj.id = reminder_mock.id
            obj.task_id = reminder_mock.task_id
            obj.trigger_time = reminder_mock.trigger_time
            obj.message = reminder_mock.message
            obj.triggered = reminder_mock.triggered
            obj.created_at = reminder_mock.created_at
        mock_session.refresh = AsyncMock(side_effect=refresh_reminder)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {
                    "action": "set_reminder",
                    "task_id": 7,
                    "trigger_time": trigger,
                    "reminder_message": "Time to deploy!",
                },
                context,
            )

        assert result.success is True
        assert result.data["task_id"] == 7
        assert result.data["triggered"] is False
        assert "reminder" in result.output.lower()

    @pytest.mark.asyncio
    async def test_set_reminder_missing_task_id(self, skill, context):
        """set_reminder without task_id returns error."""
        trigger = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = await skill.execute(
            {"action": "set_reminder", "trigger_time": trigger},
            context,
        )
        assert result.success is False
        assert "task_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_set_reminder_missing_trigger_time(self, skill, context):
        """set_reminder without trigger_time returns error."""
        result = await skill.execute(
            {"action": "set_reminder", "task_id": 1},
            context,
        )
        assert result.success is False
        assert "trigger_time" in result.error.lower()

    @pytest.mark.asyncio
    async def test_set_reminder_invalid_trigger_time(self, skill, context):
        """set_reminder with bad datetime returns error."""
        result = await skill.execute(
            {"action": "set_reminder", "task_id": 1, "trigger_time": "yesterday"},
            context,
        )
        assert result.success is False
        assert "iso" in result.error.lower() or "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_set_reminder_task_not_found(self, skill, context):
        """set_reminder for non-existent task returns error."""
        trigger = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("skills.calendar.handler.AsyncSessionLocal", return_value=_mock_session_ctx(mock_session)):
            result = await skill.execute(
                {"action": "set_reminder", "task_id": 999, "trigger_time": trigger},
                context,
            )

        assert result.success is False
        assert "not found" in result.error.lower()


# ---------------------------------------------------------------------------
# Unknown Action Tests
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test handling of invalid actions."""

    @pytest.fixture
    def skill(self):
        from skills.calendar.handler import CalendarSkill
        return CalendarSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, skill, context):
        """Unknown action returns descriptive error."""
        result = await skill.execute({"action": "delete_all"}, context)
        assert result.success is False
        assert "unknown action" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_action_returns_error(self, skill, context):
        """Missing action parameter returns an error."""
        result = await skill.execute({}, context)
        assert result.success is False
        assert "unknown action" in result.error.lower()


# ---------------------------------------------------------------------------
# API Integration Test
# ---------------------------------------------------------------------------

class TestCalendarAPIIntegration:
    """Verify skill appears in the registry and API."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_in_registry(self):
        """calendar skill appears in loaded skills registry."""
        assert "calendar" in self.loaded
        skill = self.loaded["calendar"]
        assert skill.name == "calendar"
        assert skill.permissions == []
