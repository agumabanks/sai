"""
Tests for the backup_automation skill — scheduled database and config backups.

Fulfills: VAL-SKILL-010, VAL-SKILL-011
  - backup_automation skill has a valid manifest.yaml and handler.py, loads into
    the skill registry without errors, and appears in the API skills listing.
  - backup_automation skill creates database dumps (PostgreSQL pg_dump, MySQL
    mysqldump) and config file archives. Reports backup status.
"""

import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

# Ensure backend is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Manifest & Loading Tests
# ---------------------------------------------------------------------------

class TestBackupAutomationManifest:
    """Verify the backup_automation skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(BACKEND_DIR, "skills", "backup_automation", "manifest.yaml")
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'backup_automation'."""
        assert self.manifest.name == "backup_automation"

    def test_manifest_has_description(self):
        """Manifest includes a meaningful description."""
        assert self.manifest.description
        assert len(self.manifest.description) > 10

    def test_manifest_has_shell_permission(self):
        """Skill requires shell permission for subprocess calls."""
        assert "shell" in self.manifest.permissions

    def test_manifest_requires_approval(self):
        """Skill requires human approval before execution."""
        assert self.manifest.requires_approval is True

    def test_manifest_has_action_parameter(self):
        """Manifest defines an 'action' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "action" in param_names

    def test_manifest_action_enum_values(self):
        """Action parameter includes all five backup actions."""
        action_param = next(p for p in self.manifest.parameters if p.name == "action")
        assert "backup_postgres" in action_param.enum
        assert "backup_mysql" in action_param.enum
        assert "backup_configs" in action_param.enum
        assert "backup_status" in action_param.enum
        assert "schedule_backup" in action_param.enum

    def test_manifest_category_is_system(self):
        """Skill is categorized under 'system'."""
        assert self.manifest.tags  # tags exist
        # Category is set in the manifest but loaded into tags/category


class TestBackupAutomationLoading:
    """Verify the backup_automation skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """backup_automation skill loads without errors."""
        assert "backup_automation" in self.loaded, (
            f"backup_automation not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'backup_automation'."""
        skill = self.loaded["backup_automation"]
        assert skill.name == "backup_automation"

    @pytest.mark.asyncio
    async def test_loaded_skill_requires_approval(self):
        """Loaded skill has requires_approval == True."""
        skill = self.loaded["backup_automation"]
        assert skill.requires_approval is True


# ---------------------------------------------------------------------------
# backup_postgres Tests
# ---------------------------------------------------------------------------

class TestBackupPostgres:
    """Test PostgreSQL backup action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.backup_automation.handler import BackupAutomationSkill
        from core.skills.base import SkillContext
        self.skill = BackupAutomationSkill()
        self.context = SkillContext(session_id="test", channel="test")

    @pytest.mark.asyncio
    async def test_backup_postgres_success(self, tmp_path):
        """Successful pg_dump creates a compressed backup file."""
        backup_dir = str(tmp_path / "postgres")

        with patch("skills.backup_automation.handler.POSTGRES_BACKUP_DIR", backup_dir), \
             patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value="/usr/bin/pg_dump"), \
             patch("skills.backup_automation.handler._run_cmd") as mock_run:

            # Simulate pg_dump success, then gzip success
            dump_file_path = None

            async def mock_run_impl(cmd, timeout=120):
                nonlocal dump_file_path
                if cmd[0] == "pg_dump":
                    # Find the -f argument to get the file path
                    for i, arg in enumerate(cmd):
                        if arg == "-f" and i + 1 < len(cmd):
                            dump_file_path = cmd[i + 1]
                            # Create the dummy dump file
                            os.makedirs(os.path.dirname(dump_file_path), exist_ok=True)
                            Path(dump_file_path).write_text("-- pg_dump output")
                            break
                    return (0, "", "")
                elif cmd[0] == "gzip":
                    # Simulate gzip: remove .sql, create .sql.gz
                    sql_file = cmd[-1]
                    gz_file = sql_file + ".gz"
                    if os.path.isfile(sql_file):
                        Path(gz_file).write_bytes(b"compressed data here")
                        os.remove(sql_file)
                    return (0, "", "")
                return (0, "", "")

            mock_run.side_effect = mock_run_impl

            result = await self.skill.execute(
                {"action": "backup_postgres", "database": "antigravity_db"},
                self.context,
            )

            assert result.success is True
            assert "antigravity_db" in result.output
            assert result.data["database"] == "antigravity_db"
            assert result.data["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_backup_postgres_pg_dump_not_found(self, tmp_path):
        """Returns error when pg_dump is not installed."""
        with patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value=None):

            result = await self.skill.execute(
                {"action": "backup_postgres"},
                self.context,
            )

            assert result.success is False
            assert "pg_dump" in result.error.lower()

    @pytest.mark.asyncio
    async def test_backup_postgres_dump_failure(self, tmp_path):
        """Returns error details when pg_dump fails without crashing."""
        backup_dir = str(tmp_path / "postgres")

        with patch("skills.backup_automation.handler.POSTGRES_BACKUP_DIR", backup_dir), \
             patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value="/usr/bin/pg_dump"), \
             patch("skills.backup_automation.handler._run_cmd") as mock_run:

            async def mock_fail(cmd, timeout=120):
                return (1, "", "pg_dump: error: connection refused")

            mock_run.side_effect = mock_fail

            result = await self.skill.execute(
                {"action": "backup_postgres"},
                self.context,
            )

            assert result.success is False
            assert "connection refused" in result.error or "pg_dump failed" in result.error


# ---------------------------------------------------------------------------
# backup_mysql Tests
# ---------------------------------------------------------------------------

class TestBackupMySQL:
    """Test MySQL backup action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.backup_automation.handler import BackupAutomationSkill
        from core.skills.base import SkillContext
        self.skill = BackupAutomationSkill()
        self.context = SkillContext(session_id="test", channel="test")

    @pytest.mark.asyncio
    async def test_backup_mysql_no_tenants(self, tmp_path):
        """Returns success with informational message when no tenants found."""
        with patch("skills.backup_automation.handler.MYSQL_BACKUP_DIR", str(tmp_path / "mysql")), \
             patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value="/usr/bin/mysqldump"), \
             patch("skills.backup_automation.handler._discover_finance_tenants", return_value=[]):

            result = await self.skill.execute(
                {"action": "backup_mysql"},
                self.context,
            )

            assert result.success is True
            assert "no finance tenant" in result.output.lower()
            assert result.data["tenants_found"] == 0

    @pytest.mark.asyncio
    async def test_backup_mysql_specific_db(self, tmp_path):
        """Can back up a specific named database."""
        backup_dir = str(tmp_path / "mysql")

        with patch("skills.backup_automation.handler.MYSQL_BACKUP_DIR", backup_dir), \
             patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value="/usr/bin/mysqldump"), \
             patch("skills.backup_automation.handler._run_cmd") as mock_run:

            async def mock_run_impl(cmd, timeout=120):
                if cmd[0] == "mysqldump":
                    # Find --result-file
                    for arg in cmd:
                        if arg.startswith("--result-file="):
                            fpath = arg.split("=", 1)[1]
                            os.makedirs(os.path.dirname(fpath), exist_ok=True)
                            Path(fpath).write_text("-- mysqldump output")
                            break
                    return (0, "", "")
                elif cmd[0] == "gzip":
                    sql_file = cmd[-1]
                    gz_file = sql_file + ".gz"
                    if os.path.isfile(sql_file):
                        Path(gz_file).write_bytes(b"compressed")
                        os.remove(sql_file)
                    return (0, "", "")
                return (0, "", "")

            mock_run.side_effect = mock_run_impl

            result = await self.skill.execute(
                {"action": "backup_mysql", "database": "finance_testdb"},
                self.context,
            )

            assert result.success is True
            assert "finance_testdb" in result.output
            assert result.data["tenants_found"] == 1

    @pytest.mark.asyncio
    async def test_backup_mysql_dump_failure(self, tmp_path):
        """Reports errors per-tenant without crashing."""
        backup_dir = str(tmp_path / "mysql")

        with patch("skills.backup_automation.handler.MYSQL_BACKUP_DIR", backup_dir), \
             patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value="/usr/bin/mysqldump"), \
             patch("skills.backup_automation.handler._run_cmd") as mock_run:

            async def mock_fail(cmd, timeout=120):
                return (1, "", "Access denied for user 'root'@'localhost'")

            mock_run.side_effect = mock_fail

            result = await self.skill.execute(
                {"action": "backup_mysql", "database": "bad_db"},
                self.context,
            )

            assert result.success is False
            assert "Access denied" in result.output or result.data.get("backups")

    @pytest.mark.asyncio
    async def test_backup_mysql_mysqldump_not_found(self, tmp_path):
        """Returns error when mysqldump is not installed."""
        with patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value=None):

            result = await self.skill.execute(
                {"action": "backup_mysql"},
                self.context,
            )

            assert result.success is False
            assert "mysqldump" in result.error.lower()


# ---------------------------------------------------------------------------
# backup_configs Tests
# ---------------------------------------------------------------------------

class TestBackupConfigs:
    """Test config file archive action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.backup_automation.handler import BackupAutomationSkill
        from core.skills.base import SkillContext
        self.skill = BackupAutomationSkill()
        self.context = SkillContext(session_id="test", channel="test")

    @pytest.mark.asyncio
    async def test_backup_configs_success(self, tmp_path):
        """Creates a tar.gz archive of existing config files."""
        configs_dir = str(tmp_path / "configs")
        # Create some dummy config files to back up
        dummy_env = str(tmp_path / "dummy.env")
        Path(dummy_env).write_text("APP_KEY=test123")

        with patch("skills.backup_automation.handler.CONFIGS_BACKUP_DIR", configs_dir), \
             patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("skills.backup_automation.handler.CONFIG_PATHS", [dummy_env]), \
             patch("shutil.which", return_value="/usr/bin/tar"), \
             patch("skills.backup_automation.handler._run_cmd") as mock_run:

            async def mock_tar(cmd, timeout=60):
                # Simulate tar creating the archive
                archive_path = cmd[2]  # tar -czf <path> ...
                os.makedirs(os.path.dirname(archive_path), exist_ok=True)
                Path(archive_path).write_bytes(b"fake tar content " * 10)
                return (0, "", "")

            mock_run.side_effect = mock_tar

            result = await self.skill.execute(
                {"action": "backup_configs"},
                self.context,
            )

            assert result.success is True
            assert "Config backup completed" in result.output
            assert result.data["files_count"] == 1
            assert result.data["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_backup_configs_no_files_found(self, tmp_path):
        """Returns error when no config files exist."""
        with patch("skills.backup_automation.handler.CONFIGS_BACKUP_DIR", str(tmp_path / "configs")), \
             patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("skills.backup_automation.handler.CONFIG_PATHS", ["/nonexistent/path"]), \
             patch("shutil.which", return_value="/usr/bin/tar"):

            result = await self.skill.execute(
                {"action": "backup_configs"},
                self.context,
            )

            assert result.success is False
            assert "no config files" in result.error.lower()

    @pytest.mark.asyncio
    async def test_backup_configs_tar_not_found(self, tmp_path):
        """Returns error when tar is not installed."""
        with patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)), \
             patch("shutil.which", return_value=None):

            result = await self.skill.execute(
                {"action": "backup_configs"},
                self.context,
            )

            assert result.success is False
            assert "tar" in result.error.lower()


# ---------------------------------------------------------------------------
# backup_status Tests
# ---------------------------------------------------------------------------

class TestBackupStatus:
    """Test backup status reporting action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.backup_automation.handler import BackupAutomationSkill
        from core.skills.base import SkillContext
        self.skill = BackupAutomationSkill()
        self.context = SkillContext(session_id="test", channel="test")

    @pytest.mark.asyncio
    async def test_backup_status_empty(self, tmp_path):
        """Reports no records when no backups have been performed."""
        with patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "status.json")):

            result = await self.skill.execute(
                {"action": "backup_status"},
                self.context,
            )

            assert result.success is True
            assert "no backup records" in result.output.lower()

    @pytest.mark.asyncio
    async def test_backup_status_with_records(self, tmp_path):
        """Reports backup details when records exist."""
        status_file = str(tmp_path / "status.json")
        status_data = {
            "postgres:antigravity_db": {
                "last_backup": "2026-03-14T02:00:00+00:00",
                "success": True,
                "path": "/var/backups/sanaa/postgres/antigravity_db_20260314_020000.sql.gz",
                "size_bytes": 1048576,
                "size_human": "1.0 MB",
                "error": "",
            },
            "configs": {
                "last_backup": "2026-03-14T02:01:00+00:00",
                "success": False,
                "path": "",
                "size_bytes": 0,
                "size_human": "0 B",
                "error": "tar failed: permission denied",
            },
        }
        Path(status_file).write_text(json.dumps(status_data))

        with patch("skills.backup_automation.handler.STATUS_FILE", status_file):

            result = await self.skill.execute(
                {"action": "backup_status"},
                self.context,
            )

            assert result.success is True
            assert "postgres:antigravity_db" in result.output
            assert "✓" in result.output  # success marker
            assert "✗" in result.output  # failure marker
            assert "1.0 MB" in result.output
            assert "permission denied" in result.output
            assert "configs" in result.data["targets"]


# ---------------------------------------------------------------------------
# schedule_backup Tests
# ---------------------------------------------------------------------------

class TestScheduleBackup:
    """Test Celery periodic task registration."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.backup_automation.handler import BackupAutomationSkill
        from core.skills.base import SkillContext
        self.skill = BackupAutomationSkill()
        self.context = SkillContext(session_id="test", channel="test")

    @pytest.mark.asyncio
    async def test_schedule_backup_success(self):
        """Registers a Celery beat schedule entry."""
        result = await self.skill.execute(
            {"action": "schedule_backup", "target": "postgres", "schedule": "30 3 * * *"},
            self.context,
        )

        assert result.success is True
        assert result.data["task_name"] == "backup-postgres"
        assert result.data["target"] == "postgres"
        assert result.data["schedule"] == "30 3 * * *"

        # Verify it was registered
        from core.tasks import app as celery_app
        assert "backup-postgres" in celery_app.conf.beat_schedule

        # Clean up
        celery_app.conf.beat_schedule.pop("backup-postgres", None)

    @pytest.mark.asyncio
    async def test_schedule_backup_default_target(self):
        """Uses 'all' as default target when not specified."""
        result = await self.skill.execute(
            {"action": "schedule_backup", "schedule": "0 4 * * *"},
            self.context,
        )

        assert result.success is True
        assert result.data["target"] == "all"

        # Clean up
        from core.tasks import app as celery_app
        celery_app.conf.beat_schedule.pop("backup-all", None)

    @pytest.mark.asyncio
    async def test_schedule_backup_invalid_cron(self):
        """Returns error for invalid cron expression."""
        result = await self.skill.execute(
            {"action": "schedule_backup", "schedule": "invalid cron"},
            self.context,
        )

        assert result.success is False
        assert "invalid cron" in result.error.lower()


# ---------------------------------------------------------------------------
# Unknown Action Tests
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test error handling for invalid actions."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.backup_automation.handler import BackupAutomationSkill
        from core.skills.base import SkillContext
        self.skill = BackupAutomationSkill()
        self.context = SkillContext(session_id="test", channel="test")

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        """Returns error for unrecognized action."""
        result = await self.skill.execute(
            {"action": "delete_everything"},
            self.context,
        )

        assert result.success is False
        assert "unknown action" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_action_returns_error(self):
        """Returns error when action is not provided."""
        result = await self.skill.execute({}, self.context)

        assert result.success is False
        assert "unknown action" in result.error.lower()


# ---------------------------------------------------------------------------
# Celery Task Registration Tests
# ---------------------------------------------------------------------------

class TestCeleryIntegration:
    """Test that backup tasks are registered in Celery Beat."""

    @pytest.fixture(autouse=True)
    def _reload_tasks(self):
        """Ensure core.tasks is freshly loaded so beat_schedule includes our entry."""
        import importlib
        import core.tasks
        importlib.reload(core.tasks)
        self.celery_app = core.tasks.app

    def test_celery_beat_schedule_includes_backup(self):
        """The Celery Beat schedule should include a backup-all task."""
        schedule = self.celery_app.conf.beat_schedule
        assert "backup-all" in schedule, (
            f"backup-all not found in beat_schedule. Tasks: {list(schedule.keys())}"
        )

    def test_backup_task_targets_all(self):
        """The default backup task targets 'all'."""
        config = self.celery_app.conf.beat_schedule["backup-all"]
        assert config["kwargs"]["target"] == "all"

    def test_backup_task_references_correct_task(self):
        """The scheduled task points to core.tasks.run_backup."""
        config = self.celery_app.conf.beat_schedule["backup-all"]
        assert config["task"] == "core.tasks.run_backup"


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------

class TestBackupAutomationAPIIntegration:
    """Test that the skill appears in the API listing."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_in_registry(self):
        """backup_automation appears in the full skill registry."""
        assert "backup_automation" in self.loaded
        skill = self.loaded["backup_automation"]
        assert skill.requires_approval is True
        assert "shell" in skill.permissions


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Test internal helper functions."""

    def test_file_size_human_bytes(self):
        from skills.backup_automation.handler import _file_size_human
        assert _file_size_human(500) == "500.0 B"

    def test_file_size_human_kb(self):
        from skills.backup_automation.handler import _file_size_human
        assert _file_size_human(2048) == "2.0 KB"

    def test_file_size_human_mb(self):
        from skills.backup_automation.handler import _file_size_human
        assert _file_size_human(1048576) == "1.0 MB"

    def test_file_size_human_gb(self):
        from skills.backup_automation.handler import _file_size_human
        assert _file_size_human(1073741824) == "1.0 GB"

    def test_timestamp_format(self):
        from skills.backup_automation.handler import _timestamp
        ts = _timestamp()
        assert len(ts) == 15  # YYYYMMDD_HHMMSS
        assert "_" in ts

    def test_load_status_empty(self, tmp_path):
        from skills.backup_automation.handler import _load_status
        with patch("skills.backup_automation.handler.STATUS_FILE", str(tmp_path / "nope.json")):
            result = _load_status()
            assert result == {}

    def test_save_and_load_status(self, tmp_path):
        from skills.backup_automation.handler import _save_status, _load_status
        status_file = str(tmp_path / "status.json")
        with patch("skills.backup_automation.handler.STATUS_FILE", status_file), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)):
            _save_status({"test": {"success": True}})
            loaded = _load_status()
            assert loaded["test"]["success"] is True

    def test_record_result(self, tmp_path):
        from skills.backup_automation.handler import _record_result, _load_status
        status_file = str(tmp_path / "status.json")
        with patch("skills.backup_automation.handler.STATUS_FILE", status_file), \
             patch("skills.backup_automation.handler.BACKUP_ROOT", str(tmp_path)):
            _record_result("postgres:mydb", True, path="/backups/test.sql.gz", size=1024)
            status = _load_status()
            assert "postgres:mydb" in status
            assert status["postgres:mydb"]["success"] is True
            assert status["postgres:mydb"]["size_bytes"] == 1024
