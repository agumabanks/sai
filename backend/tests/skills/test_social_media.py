"""
Tests for the social_media skill — social media content management.

Fulfills: VAL-SKILL-001, VAL-SKILL-002
  - social_media skill has a valid manifest.yaml and handler.py, loads into
    the skill registry without errors, and appears in the API skills listing.
  - create_content action generates platform-specific content (Twitter/X,
    LinkedIn, Facebook) given a topic and target platform.
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

class TestSocialMediaManifest:
    """Verify the social_media skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(BACKEND_DIR, "skills", "social_media", "manifest.yaml")
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'social_media'."""
        assert self.manifest.name == "social_media"

    def test_manifest_has_description(self):
        """Manifest includes a meaningful description."""
        assert self.manifest.description
        assert len(self.manifest.description) > 10

    def test_manifest_has_network_permission(self):
        """Skill requires network permission for LLM calls."""
        assert "network" in self.manifest.permissions

    def test_manifest_has_action_parameter(self):
        """Manifest defines an 'action' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "action" in param_names

    def test_manifest_action_enum_values(self):
        """Action parameter includes create_content, schedule_post, analytics_summary."""
        action_param = next(p for p in self.manifest.parameters if p.name == "action")
        assert "create_content" in action_param.enum
        assert "schedule_post" in action_param.enum
        assert "analytics_summary" in action_param.enum

    def test_manifest_has_platform_parameter(self):
        """Manifest defines a 'platform' parameter with valid enum values."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "platform" in param_names
        platform_param = next(p for p in self.manifest.parameters if p.name == "platform")
        assert "twitter" in platform_param.enum
        assert "linkedin" in platform_param.enum
        assert "facebook" in platform_param.enum

    def test_manifest_has_topic_parameter(self):
        """Manifest defines a 'topic' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "topic" in param_names


class TestSocialMediaLoading:
    """Verify the social_media skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """social_media skill loads without errors."""
        assert "social_media" in self.loaded, (
            f"social_media not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'social_media'."""
        skill = self.loaded["social_media"]
        assert skill.name == "social_media"


# ---------------------------------------------------------------------------
# create_content Action Tests
# ---------------------------------------------------------------------------

class TestCreateContent:
    """Test the create_content action — generates platform-specific content."""

    @pytest.fixture
    def skill(self):
        from skills.social_media.handler import SocialMediaSkill
        return SocialMediaSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="test")
        ctx.brain = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_create_twitter_content_under_280_chars(self, skill, context):
        """Twitter content should be under 280 characters."""
        context.brain.think = AsyncMock(
            return_value="AI is revolutionizing healthcare with faster diagnostics and personalized treatments. #AI #HealthTech #Innovation"
        )
        result = await skill.execute(
            {"action": "create_content", "topic": "AI in healthcare", "platform": "twitter"},
            context,
        )
        assert result.success is True
        assert len(result.data["content"]) <= 280
        assert result.data["platform"] == "twitter"
        assert result.data["character_count"] <= 280

    @pytest.mark.asyncio
    async def test_create_twitter_truncates_long_content(self, skill, context):
        """Twitter content longer than 280 chars is truncated."""
        long_text = "A" * 300  # Exceeds 280 chars
        context.brain.think = AsyncMock(return_value=long_text)
        result = await skill.execute(
            {"action": "create_content", "topic": "test topic", "platform": "twitter"},
            context,
        )
        assert result.success is True
        assert len(result.data["content"]) <= 280

    @pytest.mark.asyncio
    async def test_create_linkedin_content_professional(self, skill, context):
        """LinkedIn content should be generated with professional tone."""
        professional_content = (
            "The future of work is being reshaped by artificial intelligence. "
            "As leaders, we must embrace these changes while ensuring our teams "
            "are equipped with the right skills. Here are three strategies for "
            "AI adoption in the enterprise."
        )
        context.brain.think = AsyncMock(return_value=professional_content)
        result = await skill.execute(
            {"action": "create_content", "topic": "AI in the workplace", "platform": "linkedin"},
            context,
        )
        assert result.success is True
        assert result.data["platform"] == "linkedin"
        assert result.data["tone"] == "professional, insightful, thought-leadership"
        assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_create_facebook_content(self, skill, context):
        """Facebook content should be generated with casual tone."""
        casual_content = "Hey everyone! 🎉 Check out how AI is making our lives easier. What do you think?"
        context.brain.think = AsyncMock(return_value=casual_content)
        result = await skill.execute(
            {"action": "create_content", "topic": "AI benefits", "platform": "facebook"},
            context,
        )
        assert result.success is True
        assert result.data["platform"] == "facebook"
        assert result.data["tone"] == "casual, conversational, community-oriented"

    @pytest.mark.asyncio
    async def test_create_content_invalid_platform(self, skill, context):
        """Invalid platform returns a descriptive error."""
        result = await skill.execute(
            {"action": "create_content", "topic": "test", "platform": "tiktok"},
            context,
        )
        assert result.success is False
        assert "tiktok" in result.error.lower()
        assert "twitter" in result.error.lower()
        assert "linkedin" in result.error.lower()
        assert "facebook" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_content_missing_topic(self, skill, context):
        """Missing topic returns an error."""
        result = await skill.execute(
            {"action": "create_content", "platform": "twitter"},
            context,
        )
        assert result.success is False
        assert "topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_content_no_brain(self, skill):
        """If brain is not available, returns an error."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", channel="test")
        ctx.brain = None
        result = await skill.execute(
            {"action": "create_content", "topic": "test", "platform": "twitter"},
            ctx,
        )
        assert result.success is False
        assert "brain" in result.error.lower()


# ---------------------------------------------------------------------------
# schedule_post Action Tests
# ---------------------------------------------------------------------------

class TestSchedulePost:
    """Test the schedule_post action — creates scheduled post entries in DB."""

    @pytest.fixture
    def skill(self):
        from skills.social_media.handler import SocialMediaSkill
        return SocialMediaSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_schedule_post_success(self, skill, context):
        """schedule_post creates entry with platform, content, scheduled_time."""
        scheduled_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        # Mock the database session for insert
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock(return_value=None)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.social_media.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {
                    "action": "schedule_post",
                    "platform": "twitter",
                    "content": "Test scheduled tweet about AI trends #AI",
                    "scheduled_time": scheduled_time,
                },
                context,
            )
        assert result.success is True
        assert result.data["platform"] == "twitter"
        assert result.data["status"] == "scheduled"
        assert result.data["content"] == "Test scheduled tweet about AI trends #AI"
        # Verify DB was called
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_post_missing_content(self, skill, context):
        """Missing content returns an error."""
        result = await skill.execute(
            {
                "action": "schedule_post",
                "platform": "linkedin",
                "scheduled_time": datetime.now(timezone.utc).isoformat(),
            },
            context,
        )
        assert result.success is False
        assert "content" in result.error.lower()

    @pytest.mark.asyncio
    async def test_schedule_post_missing_scheduled_time(self, skill, context):
        """Missing scheduled_time returns an error."""
        result = await skill.execute(
            {
                "action": "schedule_post",
                "platform": "facebook",
                "content": "Test post content",
            },
            context,
        )
        assert result.success is False
        assert "scheduled_time" in result.error.lower()

    @pytest.mark.asyncio
    async def test_schedule_post_invalid_time_format(self, skill, context):
        """Invalid datetime format returns an error."""
        result = await skill.execute(
            {
                "action": "schedule_post",
                "platform": "twitter",
                "content": "Test",
                "scheduled_time": "not-a-date",
            },
            context,
        )
        assert result.success is False
        assert "iso 8601" in result.error.lower() or "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_schedule_post_invalid_platform(self, skill, context):
        """Invalid platform returns a descriptive error."""
        result = await skill.execute(
            {
                "action": "schedule_post",
                "platform": "instagram",
                "content": "Test",
                "scheduled_time": datetime.now(timezone.utc).isoformat(),
            },
            context,
        )
        assert result.success is False
        assert "instagram" in result.error.lower()


# ---------------------------------------------------------------------------
# analytics_summary Action Tests
# ---------------------------------------------------------------------------

class TestAnalyticsSummary:
    """Test the analytics_summary action — summarizes post metrics."""

    @pytest.fixture
    def skill(self):
        from skills.social_media.handler import SocialMediaSkill
        return SocialMediaSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_analytics_summary_empty(self, skill, context):
        """Analytics with no posts returns informative message."""
        # Mock the database session to return empty results
        mock_session = AsyncMock()
        mock_result_groups = MagicMock()
        mock_result_groups.mappings.return_value.all.return_value = []
        mock_result_recent = MagicMock()
        mock_result_recent.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[mock_result_groups, mock_result_recent])

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.social_media.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {"action": "analytics_summary"},
                context,
            )
        assert result.success is True
        assert result.data is not None
        assert result.data["total_posts"] == 0

    @pytest.mark.asyncio
    async def test_analytics_summary_with_posts(self, skill, context):
        """Analytics shows aggregated data when posts exist."""
        # Mock the database session to return some post data
        mock_session = AsyncMock()

        # Mock group-by result
        mock_result_groups = MagicMock()
        mock_result_groups.mappings.return_value.all.return_value = [
            {"platform": "twitter", "status": "scheduled", "count": 3},
            {"platform": "linkedin", "status": "scheduled", "count": 2},
            {"platform": "linkedin", "status": "published", "count": 1},
        ]

        # Mock recent posts result
        mock_result_recent = MagicMock()
        mock_result_recent.mappings.return_value.all.return_value = [
            {
                "platform": "twitter",
                "content": "Sample tweet about AI",
                "scheduled_time": datetime.now(timezone.utc),
                "status": "scheduled",
                "created_at": datetime.now(timezone.utc),
            },
        ]

        mock_session.execute = AsyncMock(side_effect=[mock_result_groups, mock_result_recent])

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.social_media.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {"action": "analytics_summary"},
                context,
            )
        assert result.success is True
        assert result.data["total_posts"] == 6
        assert "twitter" in result.data["platforms"]
        assert "linkedin" in result.data["platforms"]


# ---------------------------------------------------------------------------
# Unknown Action Tests
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test handling of invalid actions."""

    @pytest.fixture
    def skill(self):
        from skills.social_media.handler import SocialMediaSkill
        return SocialMediaSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, skill, context):
        """Unknown action returns descriptive error."""
        result = await skill.execute({"action": "delete_everything"}, context)
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

class TestSocialMediaAPIIntegration:
    """Verify skill appears in the registry and API."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_in_registry(self):
        """social_media skill appears in loaded skills registry."""
        assert "social_media" in self.loaded
        skill = self.loaded["social_media"]
        assert skill.name == "social_media"
        assert "network" in skill.permissions
