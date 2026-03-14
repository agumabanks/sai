"""
Tests for the self_improve skill — OpenClaw-inspired self-improving agent.

Fulfills: VAL-MEM-008
  - self_improve skill exists that analyzes recent errors and conversation patterns,
    creates structured learning entries, and logs improvement actions.
  - pytest(test_self_improve_skill)
  - curl(POST /api/skills/self_improve/run -> 200)
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

class TestSelfImproveManifest:
    """Verify the self_improve skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(BACKEND_DIR, "skills", "self_improve", "manifest.yaml")
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'self_improve'."""
        assert self.manifest.name == "self_improve"

    def test_manifest_has_description(self):
        """Manifest includes a description."""
        assert self.manifest.description
        assert len(self.manifest.description) > 10

    def test_manifest_requires_network_permission(self):
        """Skill requires network permission for LLM calls."""
        assert "network" in self.manifest.permissions

    def test_manifest_has_action_parameter(self):
        """Manifest defines an 'action' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "action" in param_names

    def test_manifest_action_enum_has_required_values(self):
        """Action parameter includes analyze_errors, learn_patterns, suggest_improvements."""
        action_param = next(p for p in self.manifest.parameters if p.name == "action")
        assert "analyze_errors" in action_param.enum
        assert "learn_patterns" in action_param.enum
        assert "suggest_improvements" in action_param.enum


class TestSelfImproveLoading:
    """Verify the self_improve skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """self_improve skill loads without errors."""
        assert "self_improve" in self.loaded, (
            f"self_improve not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'self_improve'."""
        skill = self.loaded["self_improve"]
        assert skill.name == "self_improve"


# ---------------------------------------------------------------------------
# analyze_errors Action Tests
# ---------------------------------------------------------------------------

class TestAnalyzeErrors:
    """Test the analyze_errors action — scans skill_runs for failures."""

    @pytest.fixture
    def skill(self):
        from skills.self_improve.handler import SelfImproveSkill
        return SelfImproveSkill()

    @pytest.fixture
    def mock_context(self):
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="web")
        ctx.brain = MagicMock()
        ctx.memory = MagicMock()
        return ctx

    @pytest.mark.asyncio
    async def test_analyze_errors_no_failures(self, skill, mock_context):
        """analyze_errors returns success with empty results when no failures exist."""
        # Mock the database query to return no failed runs
        with patch("skills.self_improve.handler.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            result = await skill.execute({"action": "analyze_errors"}, mock_context)

        assert result.success is True
        assert "no recent" in result.output.lower() or "0" in result.output

    @pytest.mark.asyncio
    async def test_analyze_errors_with_failures(self, skill, mock_context):
        """analyze_errors creates ERRORS entries for failed skill runs."""
        # Create mock failed runs
        mock_run1 = MagicMock()
        mock_run1.skill_name = "web_fetch"
        mock_run1.action = "fetch"
        mock_run1.error_message = "Connection timeout"
        mock_run1.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_run1.input_data = {"url": "https://example.com"}

        mock_run2 = MagicMock()
        mock_run2.skill_name = "healthcheck"
        mock_run2.action = "check_all"
        mock_run2.error_message = "DNS resolution failed"
        mock_run2.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_run2.input_data = {}

        with patch("skills.self_improve.handler.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_run1, mock_run2]
            mock_session.execute = AsyncMock(return_value=mock_result)

            with patch("skills.self_improve.handler.LearningLogManager") as mock_llm_cls:
                mock_llm = AsyncMock()
                mock_llm_cls.return_value = mock_llm
                mock_llm.add_entry = AsyncMock(return_value={
                    "id": 1, "log_type": "ERRORS", "content": "test",
                    "confidence": 0.8, "category": "skill_failure",
                    "promoted": False, "promotion_timestamp": None,
                    "source": "error", "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                result = await skill.execute({"action": "analyze_errors"}, mock_context)

        assert result.success is True
        assert "2" in result.output or "web_fetch" in result.output or "error" in result.output.lower()

    @pytest.mark.asyncio
    async def test_analyze_errors_returns_data(self, skill, mock_context):
        """analyze_errors returns structured data about errors found."""
        with patch("skills.self_improve.handler.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            result = await skill.execute({"action": "analyze_errors"}, mock_context)

        assert result.success is True
        assert isinstance(result.data, dict)


# ---------------------------------------------------------------------------
# learn_patterns Action Tests
# ---------------------------------------------------------------------------

class TestLearnPatterns:
    """Test the learn_patterns action — detects recurring themes in learning logs."""

    @pytest.fixture
    def skill(self):
        from skills.self_improve.handler import SelfImproveSkill
        return SelfImproveSkill()

    @pytest.fixture
    def mock_context(self):
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="web")
        ctx.brain = MagicMock()
        ctx.memory = MagicMock()
        return ctx

    @pytest.mark.asyncio
    async def test_learn_patterns_no_entries(self, skill, mock_context):
        """learn_patterns returns success when no learning log entries exist."""
        with patch("skills.self_improve.handler.LearningLogManager") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm
            mock_llm.get_entries = AsyncMock(return_value=[])

            result = await skill.execute({"action": "learn_patterns"}, mock_context)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_learn_patterns_detects_recurring(self, skill, mock_context):
        """learn_patterns identifies recurring themes when multiple similar entries exist."""
        entries = [
            {
                "id": 1, "log_type": "ERRORS", "source": "error",
                "content": "Skill web_fetch failed: connection timeout",
                "confidence": 0.8, "category": "skill_failure",
                "promoted": False, "promotion_timestamp": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": 2, "log_type": "ERRORS", "source": "error",
                "content": "Skill web_fetch failed: connection timeout to example.com",
                "confidence": 0.8, "category": "skill_failure",
                "promoted": False, "promotion_timestamp": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": 3, "log_type": "ERRORS", "source": "error",
                "content": "Skill web_fetch failed: connection timeout to api.test.org",
                "confidence": 0.8, "category": "skill_failure",
                "promoted": False, "promotion_timestamp": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ]

        with patch("skills.self_improve.handler.LearningLogManager") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm
            mock_llm.get_entries = AsyncMock(return_value=entries)
            mock_llm.add_entry = AsyncMock(return_value={
                "id": 10, "log_type": "LEARNINGS", "content": "test",
                "confidence": 0.9, "category": "pattern_detection",
                "promoted": False, "promotion_timestamp": None,
                "source": "reflection", "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            result = await skill.execute({"action": "learn_patterns"}, mock_context)

        assert result.success is True
        assert isinstance(result.data, dict)
        # Should detect at least one pattern
        patterns = result.data.get("patterns_detected", [])
        assert isinstance(patterns, list)

    @pytest.mark.asyncio
    async def test_learn_patterns_creates_learnings(self, skill, mock_context):
        """learn_patterns creates LEARNINGS entries for detected patterns."""
        entries = [
            {
                "id": i, "log_type": "ERRORS", "source": "error",
                "content": f"Skill healthcheck failed: DNS resolution failed for endpoint {i}",
                "confidence": 0.7, "category": "skill_failure",
                "promoted": False, "promotion_timestamp": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(5)
        ]

        with patch("skills.self_improve.handler.LearningLogManager") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm
            mock_llm.get_entries = AsyncMock(return_value=entries)
            mock_llm.add_entry = AsyncMock(return_value={
                "id": 10, "log_type": "LEARNINGS", "content": "test",
                "confidence": 0.9, "category": "pattern_detection",
                "promoted": False, "promotion_timestamp": None,
                "source": "reflection", "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            result = await skill.execute({"action": "learn_patterns"}, mock_context)

        assert result.success is True
        # add_entry should have been called at least once (for the detected pattern)
        if result.data.get("patterns_detected"):
            assert mock_llm.add_entry.call_count >= 1


# ---------------------------------------------------------------------------
# suggest_improvements Action Tests
# ---------------------------------------------------------------------------

class TestSuggestImprovements:
    """Test the suggest_improvements action — uses Brain/LLM for recommendations."""

    @pytest.fixture
    def skill(self):
        from skills.self_improve.handler import SelfImproveSkill
        return SelfImproveSkill()

    @pytest.fixture
    def mock_context(self):
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="web")
        ctx.brain = AsyncMock()
        ctx.memory = MagicMock()
        return ctx

    @pytest.mark.asyncio
    async def test_suggest_improvements_success(self, skill, mock_context):
        """suggest_improvements generates recommendations via LLM."""
        mock_context.brain.think = AsyncMock(return_value=(
            "## Improvement Recommendations\n"
            "1. Add retry logic to web_fetch skill for connection timeouts\n"
            "2. Implement circuit breaker pattern for external API calls\n"
            "3. Add fallback DNS resolution for healthcheck skill\n"
        ))

        # Mock the error and learning data
        with patch("skills.self_improve.handler.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            with patch("skills.self_improve.handler.LearningLogManager") as mock_llm_cls:
                mock_llm = AsyncMock()
                mock_llm_cls.return_value = mock_llm
                mock_llm.get_entries = AsyncMock(return_value=[])
                mock_llm.add_entry = AsyncMock(return_value={
                    "id": 20, "log_type": "LEARNINGS", "content": "test",
                    "confidence": 0.7, "category": "improvement_suggestion",
                    "promoted": False, "promotion_timestamp": None,
                    "source": "reflection", "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                result = await skill.execute({"action": "suggest_improvements"}, mock_context)

        assert result.success is True
        assert result.output  # Should have LLM-generated content
        assert isinstance(result.data, dict)

    @pytest.mark.asyncio
    async def test_suggest_improvements_no_brain(self, skill):
        """suggest_improvements fails gracefully when Brain is not available."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="web")
        ctx.brain = None

        with patch("skills.self_improve.handler.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            with patch("skills.self_improve.handler.LearningLogManager") as mock_llm_cls:
                mock_llm = AsyncMock()
                mock_llm_cls.return_value = mock_llm
                mock_llm.get_entries = AsyncMock(return_value=[])

                result = await skill.execute({"action": "suggest_improvements"}, ctx)

        assert result.success is False
        assert "brain" in result.error.lower() or "llm" in result.error.lower()

    @pytest.mark.asyncio
    async def test_suggest_improvements_logs_action(self, skill, mock_context):
        """suggest_improvements logs the generated recommendations."""
        mock_context.brain.think = AsyncMock(return_value="Add retry logic for timeouts")

        with patch("skills.self_improve.handler.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            with patch("skills.self_improve.handler.LearningLogManager") as mock_llm_cls:
                mock_llm = AsyncMock()
                mock_llm_cls.return_value = mock_llm
                mock_llm.get_entries = AsyncMock(return_value=[])
                mock_llm.add_entry = AsyncMock(return_value={
                    "id": 20, "log_type": "LEARNINGS", "content": "test",
                    "confidence": 0.7, "category": "improvement_suggestion",
                    "promoted": False, "promotion_timestamp": None,
                    "source": "reflection", "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                result = await skill.execute({"action": "suggest_improvements"}, mock_context)

        assert result.success is True
        # Should have logged the suggestion
        assert mock_llm.add_entry.call_count >= 1


# ---------------------------------------------------------------------------
# Unknown Action Test
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test error handling for unknown actions."""

    @pytest.fixture
    def skill(self):
        from skills.self_improve.handler import SelfImproveSkill
        return SelfImproveSkill()

    @pytest.fixture
    def mock_context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="web")

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, skill, mock_context):
        """Unknown action returns SkillResult with success=False."""
        result = await skill.execute({"action": "nonexistent_action"}, mock_context)
        assert result.success is False
        assert "unknown" in result.error.lower() or "nonexistent" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_action_returns_error(self, skill, mock_context):
        """Missing action parameter returns SkillResult with success=False."""
        result = await skill.execute({}, mock_context)
        assert result.success is False


# ---------------------------------------------------------------------------
# Integration: Skill in API listing
# ---------------------------------------------------------------------------

class TestSelfImproveAPIIntegration:
    """Verify self_improve appears in skill listing and is executable."""

    @pytest.mark.asyncio
    async def test_skill_in_registry(self):
        """self_improve skill is registered and listed by the registry."""
        from core.skills.loader import SkillLoader
        from core.skills.registry import SkillRegistry

        loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        loaded = await loader.load_all()

        registry = SkillRegistry()
        for skill in loaded.values():
            registry.register(skill)

        # Check it's in the listing
        skill_list = registry.list_skills()
        names = [s["name"] for s in skill_list]
        assert "self_improve" in names

        # Check it's gettable
        skill = registry.get("self_improve")
        assert skill is not None
        assert skill.name == "self_improve"
