"""
Tests for the email_marketing skill — email campaign management.

Fulfills: VAL-SKILL-003, VAL-SKILL-004
  - email_marketing skill has a valid manifest.yaml and handler.py, loads into
    the skill registry without errors.
  - create_campaign stores campaign with subject, body_template, segment, status.
  - send_campaign queues emails via Celery for async delivery.
  - list_campaigns returns campaigns with status (draft/sending/sent).
  - audience_segment creates reusable segment definitions.
  - Email body supports template variables ({{name}}, {{company}}).
"""

import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime, timezone

import pytest

# Ensure backend is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Manifest & Loading Tests
# ---------------------------------------------------------------------------

class TestEmailMarketingManifest:
    """Verify the email_marketing skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(BACKEND_DIR, "skills", "email_marketing", "manifest.yaml")
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'email_marketing'."""
        assert self.manifest.name == "email_marketing"

    def test_manifest_has_description(self):
        """Manifest includes a meaningful description."""
        assert self.manifest.description
        assert len(self.manifest.description) > 10

    def test_manifest_has_network_permission(self):
        """Skill requires network permission for SMTP delivery."""
        assert "network" in self.manifest.permissions

    def test_manifest_has_action_parameter(self):
        """Manifest defines an 'action' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "action" in param_names

    def test_manifest_action_enum_values(self):
        """Action parameter includes all four required actions."""
        action_param = next(p for p in self.manifest.parameters if p.name == "action")
        assert "create_campaign" in action_param.enum
        assert "send_campaign" in action_param.enum
        assert "list_campaigns" in action_param.enum
        assert "audience_segment" in action_param.enum

    def test_manifest_has_subject_parameter(self):
        """Manifest defines a 'subject' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "subject" in param_names

    def test_manifest_has_body_template_parameter(self):
        """Manifest defines a 'body_template' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "body_template" in param_names

    def test_manifest_category_is_marketing(self):
        """Manifest has category 'marketing'."""
        # Category is in the tags or the raw YAML
        import yaml
        manifest_path = os.path.join(BACKEND_DIR, "skills", "email_marketing", "manifest.yaml")
        with open(manifest_path) as f:
            raw = yaml.safe_load(f)
        assert raw.get("category") == "marketing"


class TestEmailMarketingLoading:
    """Verify the email_marketing skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """email_marketing skill loads without errors."""
        assert "email_marketing" in self.loaded, (
            f"email_marketing not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'email_marketing'."""
        skill = self.loaded["email_marketing"]
        assert skill.name == "email_marketing"


# ---------------------------------------------------------------------------
# Template Rendering Tests
# ---------------------------------------------------------------------------

class TestTemplateRendering:
    """Test template variable rendering in email bodies."""

    def test_render_with_name_and_company(self):
        """Template variables {{name}} and {{company}} are replaced."""
        from skills.email_marketing.handler import render_template
        template = "Hello {{name}}, welcome to {{company}}!"
        result = render_template(template, {"name": "Alice", "company": "Sanaa"})
        assert result == "Hello Alice, welcome to Sanaa!"

    def test_render_with_missing_variable(self):
        """Unknown template variables are left as-is."""
        from skills.email_marketing.handler import render_template
        template = "Hello {{name}}, your code is {{code}}."
        result = render_template(template, {"name": "Bob"})
        assert result == "Hello Bob, your code is {{code}}."

    def test_render_with_no_variables(self):
        """Template with no variables is returned unchanged."""
        from skills.email_marketing.handler import render_template
        template = "Hello world, no variables here."
        result = render_template(template, {"name": "Test"})
        assert result == "Hello world, no variables here."

    def test_render_multiple_occurrences(self):
        """Same variable used multiple times is replaced everywhere."""
        from skills.email_marketing.handler import render_template
        template = "{{name}} from {{company}}, hi {{name}}!"
        result = render_template(template, {"name": "Eve", "company": "Acme"})
        assert result == "Eve from Acme, hi Eve!"


# ---------------------------------------------------------------------------
# create_campaign Action Tests
# ---------------------------------------------------------------------------

class TestCreateCampaign:
    """Test the create_campaign action — stores campaign in database."""

    @pytest.fixture
    def skill(self):
        from skills.email_marketing.handler import EmailMarketingSkill
        return EmailMarketingSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="test")
        ctx.brain = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_create_campaign_with_body_template(self, skill, context):
        """create_campaign stores campaign with subject, body_template, and status=draft."""
        # Mock database session
        mock_campaign = MagicMock()
        mock_campaign.id = 42

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'id', 42))

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {
                    "action": "create_campaign",
                    "name": "Spring Sale",
                    "subject": "Don't miss our spring sale!",
                    "body_template": "Hi {{name}}, check out our deals at {{company}}!",
                },
                context,
            )

        assert result.success is True
        assert result.data["name"] == "Spring Sale"
        assert result.data["subject"] == "Don't miss our spring sale!"
        assert result.data["status"] == "draft"
        assert "name" in result.data["template_variables"]
        assert "company" in result.data["template_variables"]
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_campaign_with_llm_generation(self, skill, context):
        """create_campaign uses Brain/LLM to generate email copy when topic is provided."""
        context.brain.think = AsyncMock(
            return_value="Dear {{name}},\n\nDiscover the latest in AI.\n\nBest,\n{{company}}"
        )

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'id', 99))

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {
                    "action": "create_campaign",
                    "name": "AI Newsletter",
                    "subject": "AI Trends This Week",
                    "topic": "Latest AI developments in East Africa",
                },
                context,
            )

        assert result.success is True
        assert result.data["name"] == "AI Newsletter"
        assert "name" in result.data["template_variables"]
        assert "company" in result.data["template_variables"]
        context.brain.think.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_campaign_missing_name(self, skill, context):
        """Missing name returns an error."""
        result = await skill.execute(
            {
                "action": "create_campaign",
                "subject": "Test",
                "body_template": "Test body",
            },
            context,
        )
        assert result.success is False
        assert "name" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_campaign_missing_subject(self, skill, context):
        """Missing subject returns an error."""
        result = await skill.execute(
            {
                "action": "create_campaign",
                "name": "Test Campaign",
                "body_template": "Test body",
            },
            context,
        )
        assert result.success is False
        assert "subject" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_campaign_missing_body_and_topic(self, skill, context):
        """Missing both body_template and topic returns an error."""
        result = await skill.execute(
            {
                "action": "create_campaign",
                "name": "Test Campaign",
                "subject": "Test Subject",
            },
            context,
        )
        assert result.success is False
        assert "body_template" in result.error.lower() or "topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_campaign_no_brain_with_topic(self, skill):
        """create_campaign with topic but no brain returns an error."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", channel="test")
        ctx.brain = None
        result = await skill.execute(
            {
                "action": "create_campaign",
                "name": "Test",
                "subject": "Test Subject",
                "topic": "AI in healthcare",
            },
            ctx,
        )
        assert result.success is False
        assert "brain" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_campaign_with_nonexistent_segment(self, skill, context):
        """create_campaign with a segment that doesn't exist returns an error."""
        # Mock segment lookup to return nothing
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {
                    "action": "create_campaign",
                    "name": "Test",
                    "subject": "Test Subject",
                    "body_template": "Hello {{name}}",
                    "segment": "nonexistent_segment",
                },
                context,
            )

        assert result.success is False
        assert "nonexistent_segment" in result.error


# ---------------------------------------------------------------------------
# send_campaign Action Tests
# ---------------------------------------------------------------------------

class TestSendCampaign:
    """Test the send_campaign action — queues emails for delivery."""

    @pytest.fixture
    def skill(self):
        from skills.email_marketing.handler import EmailMarketingSkill
        return EmailMarketingSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_send_campaign_queues_via_celery(self, skill, context):
        """send_campaign updates status to 'sending' and queues Celery task."""
        mock_campaign = MagicMock()
        mock_campaign.id = 1
        mock_campaign.name = "Test Campaign"
        mock_campaign.status = "draft"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_campaign

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_celery_task = MagicMock()

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx), \
             patch("core.tasks.send_email_campaign", mock_celery_task):
            result = await skill.execute(
                {"action": "send_campaign", "campaign_id": 1},
                context,
            )

        assert result.success is True
        assert result.data["status"] == "sending"
        assert result.data["campaign_id"] == 1
        mock_celery_task.delay.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_send_campaign_missing_id(self, skill, context):
        """Missing campaign_id returns an error."""
        result = await skill.execute(
            {"action": "send_campaign"},
            context,
        )
        assert result.success is False
        assert "campaign_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_campaign_not_found(self, skill, context):
        """Non-existent campaign returns an error."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {"action": "send_campaign", "campaign_id": 999},
                context,
            )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_campaign_already_sent(self, skill, context):
        """Sending an already-sent campaign returns an error."""
        mock_campaign = MagicMock()
        mock_campaign.id = 1
        mock_campaign.name = "Old Campaign"
        mock_campaign.status = "sent"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_campaign

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {"action": "send_campaign", "campaign_id": 1},
                context,
            )

        assert result.success is False
        assert "already been sent" in result.error.lower()


# ---------------------------------------------------------------------------
# list_campaigns Action Tests
# ---------------------------------------------------------------------------

class TestListCampaigns:
    """Test the list_campaigns action — lists campaigns by status."""

    @pytest.fixture
    def skill(self):
        from skills.email_marketing.handler import EmailMarketingSkill
        return EmailMarketingSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_list_campaigns_empty(self, skill, context):
        """Empty campaign list returns informative message."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {"action": "list_campaigns"},
                context,
            )

        assert result.success is True
        assert result.data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_campaigns_with_data(self, skill, context):
        """List campaigns returns campaign details with status."""
        mock_campaign = MagicMock()
        mock_campaign.id = 1
        mock_campaign.name = "Spring Sale"
        mock_campaign.subject = "Spring Sale!"
        mock_campaign.status = "draft"
        mock_campaign.recipients_count = 100
        mock_campaign.sent_count = 0
        mock_campaign.failed_count = 0
        mock_campaign.created_at = datetime(2026, 3, 14, tzinfo=timezone.utc)
        mock_campaign.sent_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_campaign]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {"action": "list_campaigns"},
                context,
            )

        assert result.success is True
        assert result.data["total"] == 1
        assert result.data["campaigns"][0]["name"] == "Spring Sale"
        assert result.data["campaigns"][0]["status"] == "draft"

    @pytest.mark.asyncio
    async def test_list_campaigns_with_status_filter(self, skill, context):
        """list_campaigns respects status_filter parameter."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {"action": "list_campaigns", "status_filter": "sent"},
                context,
            )

        assert result.success is True
        # Verify the query was filtered - the result itself is empty but the action succeeded
        assert "sent" in result.output.lower()


# ---------------------------------------------------------------------------
# audience_segment Action Tests
# ---------------------------------------------------------------------------

class TestAudienceSegment:
    """Test the audience_segment action — creates reusable audience segments."""

    @pytest.fixture
    def skill(self):
        from skills.email_marketing.handler import EmailMarketingSkill
        return EmailMarketingSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_create_new_segment(self, skill, context):
        """audience_segment creates a new segment with criteria."""
        # Mock: no existing segment found, then create succeeds
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'id', 10))

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {
                    "action": "audience_segment",
                    "name": "East Africa Admins",
                    "criteria": {"role": "admin", "region": "East Africa"},
                    "description": "Administrators in East Africa region",
                },
                context,
            )

        assert result.success is True
        assert result.data["name"] == "East Africa Admins"
        assert result.data["action"] == "created"
        assert result.data["criteria"] == {"role": "admin", "region": "East Africa"}
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing_segment(self, skill, context):
        """audience_segment updates existing segment when name matches."""
        mock_existing = MagicMock()
        mock_existing.id = 5
        mock_existing.name = "VIP Customers"
        mock_existing.description = "Old description"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_existing

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("skills.email_marketing.handler.AsyncSessionLocal", return_value=mock_ctx):
            result = await skill.execute(
                {
                    "action": "audience_segment",
                    "name": "VIP Customers",
                    "criteria": {"spend": ">1000", "status": "active"},
                    "description": "Updated description",
                },
                context,
            )

        assert result.success is True
        assert result.data["action"] == "updated"
        assert mock_existing.criteria == {"spend": ">1000", "status": "active"}

    @pytest.mark.asyncio
    async def test_segment_missing_name(self, skill, context):
        """Missing name returns an error."""
        result = await skill.execute(
            {
                "action": "audience_segment",
                "criteria": {"role": "admin"},
            },
            context,
        )
        assert result.success is False
        assert "name" in result.error.lower()

    @pytest.mark.asyncio
    async def test_segment_missing_criteria(self, skill, context):
        """Missing criteria returns an error."""
        result = await skill.execute(
            {
                "action": "audience_segment",
                "name": "Test Segment",
            },
            context,
        )
        assert result.success is False
        assert "criteria" in result.error.lower()

    @pytest.mark.asyncio
    async def test_segment_invalid_criteria_type(self, skill, context):
        """Non-dict criteria returns an error."""
        result = await skill.execute(
            {
                "action": "audience_segment",
                "name": "Test Segment",
                "criteria": "not a dict",
            },
            context,
        )
        assert result.success is False
        assert "criteria" in result.error.lower()


# ---------------------------------------------------------------------------
# Unknown Action Tests
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test handling of invalid actions."""

    @pytest.fixture
    def skill(self):
        from skills.email_marketing.handler import EmailMarketingSkill
        return EmailMarketingSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, skill, context):
        """Unknown action returns descriptive error."""
        result = await skill.execute({"action": "delete_all_emails"}, context)
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

class TestEmailMarketingAPIIntegration:
    """Verify skill appears in the registry and API."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_in_registry(self):
        """email_marketing skill appears in loaded skills registry."""
        assert "email_marketing" in self.loaded
        skill = self.loaded["email_marketing"]
        assert skill.name == "email_marketing"
        assert "network" in skill.permissions
