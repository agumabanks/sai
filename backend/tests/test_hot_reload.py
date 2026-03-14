"""
Tests for skill hot-reload — verifies the SkillFileWatcher detects file changes,
re-validates manifests, reloads handler modules, and updates the skill registry.

Fulfills: VAL-SKILL-014, VAL-CROSS-009
"""

import os
import sys
import time
import shutil
import tempfile
from pathlib import Path

import pytest

# Ensure backend is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.skills.hot_reload import SkillFileWatcher
from core.skills.registry import SkillRegistry
from core.skills.base import SkillContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_MANIFEST_V1 = """\
name: hot_test_skill
version: "1.0.0"
description: "A skill for hot-reload testing"
parameters:
  - name: action
    type: string
    required: false
    default: greet
    description: "Action to perform"
"""

VALID_MANIFEST_V2 = """\
name: hot_test_skill
version: "2.0.0"
description: "A skill for hot-reload testing (v2)"
parameters:
  - name: action
    type: string
    required: false
    default: greet
    description: "Action to perform"
"""

INVALID_MANIFEST = """\
# Missing required 'name' field
version: "1.0.0"
description: "broken"
"""

HANDLER_V1 = """\
from core.skills.base import BaseSkill, SkillResult

class HotTestSkill(BaseSkill):
    async def execute(self, args: dict, context=None) -> SkillResult:
        return SkillResult(success=True, output="v1-output", data={"version": "1.0.0"})
"""

HANDLER_V2 = """\
from core.skills.base import BaseSkill, SkillResult

class HotTestSkill(BaseSkill):
    async def execute(self, args: dict, context=None) -> SkillResult:
        return SkillResult(success=True, output="v2-output", data={"version": "2.0.0"})
"""

HANDLER_BROKEN = """\
raise ImportError("intentionally broken handler")
"""


@pytest.fixture
def tmp_skills_dir(tmp_path):
    """Create a temporary skills directory with a test skill."""
    skill_dir = tmp_path / "hot_test_skill"
    skill_dir.mkdir()
    (skill_dir / "manifest.yaml").write_text(VALID_MANIFEST_V1)
    (skill_dir / "handler.py").write_text(HANDLER_V1)
    return tmp_path


@pytest.fixture
def registry():
    """Fresh skill registry."""
    return SkillRegistry()


@pytest.fixture
def watcher(tmp_skills_dir, registry):
    """SkillFileWatcher pointed at the temp dir with short debounce."""
    w = SkillFileWatcher(
        skills_dir=str(tmp_skills_dir),
        skill_registry=registry,
        debounce_seconds=0.1,  # fast for tests
    )
    return w


# ---------------------------------------------------------------------------
# VAL-SKILL-014: Skill hot-reload
# ---------------------------------------------------------------------------

class TestSkillFileWatcherInit:
    """Test SkillFileWatcher initialisation and state."""

    def test_watcher_not_running_initially(self, watcher):
        """Watcher is not running before start() is called."""
        assert not watcher.is_running

    def test_start_sets_running(self, watcher):
        """start() marks watcher as running."""
        watcher.start()
        try:
            assert watcher.is_running
        finally:
            watcher.stop()

    def test_stop_clears_running(self, watcher):
        """stop() marks watcher as not running."""
        watcher.start()
        watcher.stop()
        assert not watcher.is_running

    def test_double_start_is_safe(self, watcher):
        """Calling start() twice does not crash."""
        watcher.start()
        try:
            watcher.start()  # should log warning but not crash
            assert watcher.is_running
        finally:
            watcher.stop()

    def test_stop_without_start_is_safe(self, watcher):
        """Calling stop() when not started does not crash."""
        watcher.stop()  # no-op
        assert not watcher.is_running

    def test_nonexistent_dir_does_not_crash(self, registry):
        """Creating a watcher for a nonexistent directory does not crash."""
        w = SkillFileWatcher(
            skills_dir="/nonexistent/path/12345",
            skill_registry=registry,
        )
        w.start()  # should log error but not crash
        assert not w.is_running


class TestManifestReload:
    """Test that modified manifest.yaml triggers re-validation + registry update."""

    @pytest.mark.asyncio
    async def test_manifest_change_triggers_reload(self, watcher, tmp_skills_dir, registry):
        """Modifying manifest.yaml triggers skill reload with new version."""
        # First, do an initial load to populate registry
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )
        skill = registry.get("hot_test_skill")
        assert skill is not None
        assert skill.version == "1.0.0"

        # Update manifest to v2
        (tmp_skills_dir / "hot_test_skill" / "manifest.yaml").write_text(VALID_MANIFEST_V2)

        # Trigger reload
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )

        # Registry should have the updated skill
        skill = registry.get("hot_test_skill")
        assert skill is not None
        assert skill.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_invalid_manifest_rejected(self, watcher, tmp_skills_dir, registry):
        """Invalid manifest.yaml is rejected; registry not updated."""
        # Initial load
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )
        assert registry.get("hot_test_skill") is not None

        # Overwrite with invalid manifest
        (tmp_skills_dir / "hot_test_skill" / "manifest.yaml").write_text(INVALID_MANIFEST)

        # Attempt reload — should fail gracefully
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )

        # The last reload event should be a failure
        events = watcher.reload_history
        last = events[-1]
        assert last["success"] is False
        assert "Manifest validation failed" in last["error"]

    @pytest.mark.asyncio
    async def test_missing_manifest_rejected(self, watcher, tmp_skills_dir, registry):
        """A skill directory with no manifest.yaml is rejected."""
        # Remove manifest
        (tmp_skills_dir / "hot_test_skill" / "manifest.yaml").unlink()

        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        events = watcher.reload_history
        last = events[-1]
        assert last["success"] is False
        assert "not found" in last["error"].lower()


class TestHandlerReload:
    """Test that modified handler.py triggers module reload + registry update."""

    @pytest.mark.asyncio
    async def test_handler_change_updates_skill_behaviour(self, watcher, tmp_skills_dir, registry):
        """Modifying handler.py changes the skill's execute() output."""
        # Initial load
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )
        skill = registry.get("hot_test_skill")
        assert skill is not None
        result = await skill.execute({}, SkillContext())
        assert result.output == "v1-output"

        # Update handler to v2
        (tmp_skills_dir / "hot_test_skill" / "handler.py").write_text(HANDLER_V2)

        # Reload
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        skill = registry.get("hot_test_skill")
        result = await skill.execute({}, SkillContext())
        assert result.output == "v2-output"
        assert result.data["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_broken_handler_rejected(self, watcher, tmp_skills_dir, registry):
        """A broken handler.py is rejected; watcher does not crash."""
        # Initial successful load
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )
        assert registry.get("hot_test_skill") is not None

        # Break the handler
        (tmp_skills_dir / "hot_test_skill" / "handler.py").write_text(HANDLER_BROKEN)

        # Attempt reload — should fail gracefully
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        events = watcher.reload_history
        last = events[-1]
        assert last["success"] is False

    @pytest.mark.asyncio
    async def test_missing_handler_rejected(self, watcher, tmp_skills_dir, registry):
        """A skill with missing handler.py is rejected."""
        (tmp_skills_dir / "hot_test_skill" / "handler.py").unlink()

        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )

        events = watcher.reload_history
        last = events[-1]
        assert last["success"] is False
        assert "not found" in last["error"].lower()


class TestFileWatcherDetection:
    """Test that the filesystem watcher detects actual file changes."""

    def test_file_change_detected(self, watcher, tmp_skills_dir, registry):
        """Writing to a watched file triggers reload within a reasonable time."""
        watcher.start()
        try:
            # Wait for observer to be ready
            time.sleep(0.3)

            # Modify the manifest
            manifest_path = tmp_skills_dir / "hot_test_skill" / "manifest.yaml"
            manifest_path.write_text(VALID_MANIFEST_V2)

            # Wait for the watcher to pick up the change + debounce + reload
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if len(watcher.reload_history) > 0:
                    break
                time.sleep(0.2)

            assert len(watcher.reload_history) > 0, "No reload events detected"
            event = watcher.reload_history[-1]
            assert event["skill_name"] == "hot_test_skill"
        finally:
            watcher.stop()

    def test_handler_change_detected(self, watcher, tmp_skills_dir, registry):
        """Writing to handler.py triggers reload."""
        watcher.start()
        try:
            time.sleep(0.3)

            handler_path = tmp_skills_dir / "hot_test_skill" / "handler.py"
            handler_path.write_text(HANDLER_V2)

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if len(watcher.reload_history) > 0:
                    break
                time.sleep(0.2)

            assert len(watcher.reload_history) > 0, "No reload events detected"
            event = watcher.reload_history[-1]
            assert event["skill_name"] == "hot_test_skill"
        finally:
            watcher.stop()

    def test_unrelated_file_ignored(self, watcher, tmp_skills_dir, registry):
        """Changes to files other than manifest.yaml or handler.py are ignored."""
        watcher.start()
        try:
            time.sleep(0.3)

            # Write a random file
            (tmp_skills_dir / "hot_test_skill" / "README.md").write_text("# notes")

            time.sleep(1.5)
            assert len(watcher.reload_history) == 0, "Unexpected reload event"
        finally:
            watcher.stop()


class TestReloadHistory:
    """Test the reload event log / observability."""

    @pytest.mark.asyncio
    async def test_successful_reload_logged(self, watcher, tmp_skills_dir, registry):
        """Successful reloads are recorded in reload_history."""
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )

        history = watcher.reload_history
        assert len(history) >= 1
        last = history[-1]
        assert last["skill_name"] == "hot_test_skill"
        assert last["success"] is True
        assert last["version"] == "1.0.0"
        assert last["changed_file"] == "manifest.yaml"
        assert last["timestamp"] > 0

    @pytest.mark.asyncio
    async def test_failed_reload_logged(self, watcher, tmp_skills_dir, registry):
        """Failed reloads are recorded with error details."""
        # Break the manifest
        (tmp_skills_dir / "hot_test_skill" / "manifest.yaml").write_text(INVALID_MANIFEST)

        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )

        history = watcher.reload_history
        assert len(history) >= 1
        last = history[-1]
        assert last["success"] is False
        assert last["error"] != ""

    @pytest.mark.asyncio
    async def test_history_capped_at_100(self, watcher, tmp_skills_dir, registry):
        """Reload history is capped at 100 entries."""
        for i in range(110):
            watcher._record_event("test", "handler.py", success=True, version=f"1.0.{i}")
        assert len(watcher.reload_history) == 100


class TestRegistryIntegration:
    """Test that reloaded skills are properly accessible from the registry."""

    @pytest.mark.asyncio
    async def test_registry_get_returns_reloaded_skill(self, watcher, tmp_skills_dir, registry):
        """After reload, registry.get() returns the updated skill."""
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        skill = registry.get("hot_test_skill")
        assert skill is not None
        assert skill.name == "hot_test_skill"

    @pytest.mark.asyncio
    async def test_registry_list_includes_reloaded(self, watcher, tmp_skills_dir, registry):
        """After reload, skill appears in registry.list_skills()."""
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        skill_list = registry.list_skills()
        names = [s["name"] for s in skill_list]
        assert "hot_test_skill" in names

    @pytest.mark.asyncio
    async def test_no_registry_does_not_crash(self, tmp_skills_dir):
        """If no registry is attached, reload still succeeds (just logs warning)."""
        w = SkillFileWatcher(
            skills_dir=str(tmp_skills_dir),
            skill_registry=None,
            debounce_seconds=0.1,
        )
        # Should not crash
        await w._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )
        # Event logged
        assert len(w.reload_history) >= 1


# ---------------------------------------------------------------------------
# VAL-CROSS-009: Hot-reloaded skills work in brain tool loop
# ---------------------------------------------------------------------------

class TestBrainToolLoopIntegration:
    """Verify that hot-reloaded skills are used by the Brain's skill registry."""

    @pytest.mark.asyncio
    async def test_brain_registry_sees_reloaded_skill(self, tmp_skills_dir):
        """After hot-reloading into Brain's registry, execute_skill picks up new code."""
        from core.skills.registry import SkillRegistry

        # Use a fresh registry that mimics the Brain's skill_registry
        brain_registry = SkillRegistry()

        watcher = SkillFileWatcher(
            skills_dir=str(tmp_skills_dir),
            skill_registry=brain_registry,
            debounce_seconds=0.1,
        )

        # Load v1
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        skill = brain_registry.get("hot_test_skill")
        assert skill is not None
        result = await skill.execute({}, SkillContext())
        assert result.output == "v1-output"

        # Update to v2
        (tmp_skills_dir / "hot_test_skill" / "handler.py").write_text(HANDLER_V2)
        (tmp_skills_dir / "hot_test_skill" / "manifest.yaml").write_text(VALID_MANIFEST_V2)

        # Hot-reload
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        # Brain registry should now use the v2 skill
        skill = brain_registry.get("hot_test_skill")
        assert skill is not None
        result = await skill.execute({}, SkillContext())
        assert result.output == "v2-output"
        assert skill.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_tools_export_reflects_reload(self, tmp_skills_dir):
        """Brain's list_tools() reflects the latest version of reloaded skills."""
        from core.skills.registry import SkillRegistry

        brain_registry = SkillRegistry()
        watcher = SkillFileWatcher(
            skills_dir=str(tmp_skills_dir),
            skill_registry=brain_registry,
            debounce_seconds=0.1,
        )

        # Load v1
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )

        tools_v1 = brain_registry.list_tools()
        assert any(t["function"]["name"] == "hot_test_skill" for t in tools_v1)

        # Update manifest description
        (tmp_skills_dir / "hot_test_skill" / "manifest.yaml").write_text(VALID_MANIFEST_V2)

        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )

        tools_v2 = brain_registry.list_tools()
        tool = next(t for t in tools_v2 if t["function"]["name"] == "hot_test_skill")
        assert "v2" in tool["function"]["description"]


class TestDebounce:
    """Test the debounce mechanism."""

    @pytest.mark.asyncio
    async def test_rapid_changes_debounced(self, watcher, tmp_skills_dir, registry):
        """Multiple rapid changes to the same skill are debounced."""
        # Set very short debounce
        watcher.debounce_seconds = 0.5

        # Simulate rapid fire
        watcher._schedule_reload(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )
        time.sleep(0.1)
        watcher._schedule_reload(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )
        time.sleep(0.1)
        watcher._schedule_reload(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "manifest.yaml",
        )

        # Wait for first thread to finish
        time.sleep(2.0)

        # Should only have 1 event (others debounced)
        events = [e for e in watcher.reload_history if e["skill_name"] == "hot_test_skill"]
        assert len(events) == 1, f"Expected 1 event (debounced), got {len(events)}"


class TestSetRegistry:
    """Test the set_registry() method."""

    @pytest.mark.asyncio
    async def test_set_registry_updates_target(self, tmp_skills_dir):
        """set_registry() changes where reloaded skills are registered."""
        registry_a = SkillRegistry()
        registry_b = SkillRegistry()

        watcher = SkillFileWatcher(
            skills_dir=str(tmp_skills_dir),
            skill_registry=registry_a,
            debounce_seconds=0.1,
        )

        # Load into registry A
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )
        assert registry_a.get("hot_test_skill") is not None
        assert registry_b.get("hot_test_skill") is None

        # Switch to registry B
        watcher.set_registry(registry_b)
        await watcher._reload_skill(
            "hot_test_skill",
            str(tmp_skills_dir / "hot_test_skill"),
            "handler.py",
        )
        assert registry_b.get("hot_test_skill") is not None
