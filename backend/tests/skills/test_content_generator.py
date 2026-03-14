"""
Tests for the content_generator skill — brand-aware content production.

Fulfills: VAL-SKILL-007, VAL-SKILL-008
  - content_generator skill has a valid manifest.yaml and handler.py, loads into
    the skill registry without errors.
  - blog_post generates structured post with title, introduction, body, conclusion.
  - social_copy produces platform-specific variants in one call.
  - email_copy generates subject line A/B variants + body.
  - brand_voice stores voice parameters in system_knowledge.
  - Content respects brand voice when configured.
"""

import json
import sys
import os
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

class TestContentGeneratorManifest:
    """Verify the content_generator skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(
            BACKEND_DIR, "skills", "content_generator", "manifest.yaml"
        )
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'content_generator'."""
        assert self.manifest.name == "content_generator"

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
        """Action parameter includes all four required actions."""
        action_param = next(
            p for p in self.manifest.parameters if p.name == "action"
        )
        assert "blog_post" in action_param.enum
        assert "social_copy" in action_param.enum
        assert "email_copy" in action_param.enum
        assert "brand_voice" in action_param.enum

    def test_manifest_has_topic_parameter(self):
        """Manifest defines a 'topic' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "topic" in param_names

    def test_manifest_has_length_parameter(self):
        """Manifest defines a 'length' parameter with valid enum values."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "length" in param_names
        length_param = next(p for p in self.manifest.parameters if p.name == "length")
        assert "short" in length_param.enum
        assert "medium" in length_param.enum
        assert "long" in length_param.enum

    def test_manifest_has_platforms_parameter(self):
        """Manifest defines a 'platforms' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "platforms" in param_names

    def test_manifest_has_voice_params_parameter(self):
        """Manifest defines a 'voice_params' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "voice_params" in param_names

    def test_manifest_category_is_marketing(self):
        """Manifest has category 'marketing'."""
        import yaml
        manifest_path = os.path.join(
            BACKEND_DIR, "skills", "content_generator", "manifest.yaml"
        )
        with open(manifest_path) as f:
            raw = yaml.safe_load(f)
        assert raw.get("category") == "marketing"


class TestContentGeneratorLoading:
    """Verify the content_generator skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """content_generator skill loads without errors."""
        assert "content_generator" in self.loaded, (
            f"content_generator not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'content_generator'."""
        skill = self.loaded.get("content_generator")
        assert skill is not None
        assert skill.name == "content_generator"

    @pytest.mark.asyncio
    async def test_loaded_skill_has_network_permission(self):
        """Loaded skill has network permission."""
        skill = self.loaded["content_generator"]
        assert "network" in skill.permissions


# ---------------------------------------------------------------------------
# Helper: build mock context
# ---------------------------------------------------------------------------

def _make_context(brain_response: str = "Generated content") -> MagicMock:
    """Create a SkillContext mock with a Brain that returns the given text."""
    from core.skills.base import SkillContext

    brain = AsyncMock()
    brain.think = AsyncMock(return_value=brain_response)

    ctx = SkillContext(
        session_id="test-session",
        channel="web",
        sender_id="tester",
        sender_name="Test User",
        brain=brain,
        memory=MagicMock(),
        sandbox=MagicMock(),
    )
    return ctx


# ---------------------------------------------------------------------------
# blog_post Action Tests
# ---------------------------------------------------------------------------

class TestBlogPost:
    """Tests for the blog_post action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.content_generator.handler import ContentGeneratorSkill
        self.skill = ContentGeneratorSkill()

    @pytest.mark.asyncio
    async def test_blog_post_generates_structured_content(self):
        """blog_post returns structured post with title, introduction, body, conclusion."""
        blog_content = (
            "# The Future of AI in Healthcare\n\n"
            "## Introduction\n"
            "Artificial intelligence is transforming healthcare in unprecedented ways.\n"
            "From diagnostics to treatment planning, AI is everywhere.\n\n"
            "## The Current Landscape\n"
            "Today, hospitals and clinics use AI for a variety of tasks.\n"
            "Machine learning models can detect diseases earlier.\n\n"
            "## Conclusion\n"
            "The future of AI in healthcare is bright and full of promise.\n"
            "Stay tuned for more developments in this exciting field."
        )
        ctx = _make_context(blog_content)

        result = await self.skill.execute(
            {"action": "blog_post", "topic": "AI in Healthcare", "length": "medium"},
            ctx,
        )

        assert result.success is True
        assert result.output  # Not empty
        assert result.data["topic"] == "AI in Healthcare"
        assert result.data["length"] == "medium"
        assert result.data["target_words"] == 1000
        assert result.data["actual_words"] > 0
        # Should have parsed sections
        assert "title" in result.data
        assert "introduction" in result.data
        assert "body" in result.data
        assert "conclusion" in result.data

    @pytest.mark.asyncio
    async def test_blog_post_requires_topic(self):
        """blog_post returns error when topic is missing."""
        ctx = _make_context()
        result = await self.skill.execute(
            {"action": "blog_post", "length": "short"},
            ctx,
        )
        assert result.success is False
        assert "topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blog_post_invalid_length(self):
        """blog_post returns error for invalid length value."""
        ctx = _make_context()
        result = await self.skill.execute(
            {"action": "blog_post", "topic": "Testing", "length": "enormous"},
            ctx,
        )
        assert result.success is False
        assert "length" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blog_post_requires_brain(self):
        """blog_post returns error when brain is not available."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", brain=None)
        result = await self.skill.execute(
            {"action": "blog_post", "topic": "Testing"},
            ctx,
        )
        assert result.success is False
        assert "brain" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blog_post_with_keywords(self):
        """blog_post includes SEO keywords in the prompt."""
        blog_content = "# SEO Blog\n\n## Introduction\nGreat content.\n\n## Body\nMore content.\n\n## Conclusion\nEnd."
        ctx = _make_context(blog_content)

        result = await self.skill.execute(
            {
                "action": "blog_post",
                "topic": "Cloud Computing",
                "keywords": ["AWS", "serverless", "microservices"],
            },
            ctx,
        )

        assert result.success is True
        assert result.data["keywords"] == ["AWS", "serverless", "microservices"]
        # Verify keywords were passed to the brain prompt
        call_args = ctx.brain.think.call_args
        prompt = call_args[0][0]
        assert "AWS" in prompt
        assert "serverless" in prompt

    @pytest.mark.asyncio
    async def test_blog_post_handles_llm_failure(self):
        """blog_post returns error when LLM call fails."""
        ctx = _make_context()
        ctx.brain.think = AsyncMock(side_effect=Exception("LLM connection timeout"))

        result = await self.skill.execute(
            {"action": "blog_post", "topic": "Testing"},
            ctx,
        )
        assert result.success is False
        assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blog_post_handles_empty_llm_response(self):
        """blog_post returns error when LLM returns empty content."""
        ctx = _make_context("")

        result = await self.skill.execute(
            {"action": "blog_post", "topic": "Testing"},
            ctx,
        )
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    @patch("skills.content_generator.handler._load_brand_voice")
    async def test_blog_post_uses_brand_voice(self, mock_load_voice):
        """blog_post incorporates brand voice into the prompt when configured."""
        mock_load_voice.return_value = {
            "tone": "authoritative and professional",
            "vocabulary": "technical but accessible",
            "values": "innovation, reliability",
        }

        blog_content = "# Test Title\n\n## Introduction\nIntro.\n\n## Body\nBody.\n\n## Conclusion\nEnd."
        ctx = _make_context(blog_content)

        result = await self.skill.execute(
            {"action": "blog_post", "topic": "DevOps Best Practices"},
            ctx,
        )

        assert result.success is True
        assert result.data["brand_voice_applied"] is True
        # Verify brand voice was included in the prompt
        call_args = ctx.brain.think.call_args
        prompt = call_args[0][0]
        assert "authoritative and professional" in prompt


# ---------------------------------------------------------------------------
# social_copy Action Tests
# ---------------------------------------------------------------------------

class TestSocialCopy:
    """Tests for the social_copy action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.content_generator.handler import ContentGeneratorSkill
        self.skill = ContentGeneratorSkill()

    @pytest.mark.asyncio
    async def test_social_copy_generates_multi_platform(self):
        """social_copy produces content for multiple platforms at once."""
        multi_content = (
            "[TWITTER]\n"
            "Excited about the future of AI! 🤖 #AI #Innovation\n\n"
            "[LINKEDIN]\n"
            "I'm thrilled to share insights about how artificial intelligence "
            "is transforming industries. Key takeaways from our latest research.\n\n"
            "[FACEBOOK]\n"
            "Have you tried AI tools yet? Let us know your experience! 🚀"
        )
        ctx = _make_context(multi_content)

        result = await self.skill.execute(
            {
                "action": "social_copy",
                "topic": "AI Innovation",
                "platforms": ["twitter", "linkedin", "facebook"],
            },
            ctx,
        )

        assert result.success is True
        assert "content" in result.data
        assert "twitter" in result.data["content"]
        assert "linkedin" in result.data["content"]
        assert "facebook" in result.data["content"]
        # Each platform should have content
        for platform in ["twitter", "linkedin", "facebook"]:
            assert len(result.data["content"][platform]) > 0

    @pytest.mark.asyncio
    async def test_social_copy_requires_topic(self):
        """social_copy returns error when topic is missing."""
        ctx = _make_context()
        result = await self.skill.execute(
            {"action": "social_copy", "platforms": ["twitter"]},
            ctx,
        )
        assert result.success is False
        assert "topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_social_copy_invalid_platform(self):
        """social_copy returns error for invalid platform name."""
        ctx = _make_context()
        result = await self.skill.execute(
            {
                "action": "social_copy",
                "topic": "Testing",
                "platforms": ["myspace"],
            },
            ctx,
        )
        assert result.success is False
        assert "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_social_copy_defaults_all_platforms(self):
        """social_copy defaults to all platforms when platforms not specified."""
        multi_content = (
            "[TWITTER]\nTweet content\n\n"
            "[LINKEDIN]\nLinkedIn post\n\n"
            "[FACEBOOK]\nFB post\n\n"
            "[INSTAGRAM]\nInsta post"
        )
        ctx = _make_context(multi_content)

        result = await self.skill.execute(
            {"action": "social_copy", "topic": "Test Topic"},
            ctx,
        )

        assert result.success is True
        assert result.data["platforms"] == ["twitter", "linkedin", "facebook", "instagram"]

    @pytest.mark.asyncio
    async def test_social_copy_platform_details(self):
        """social_copy returns platform details with character counts and limits."""
        multi_content = (
            "[TWITTER]\nShort tweet\n\n"
            "[LINKEDIN]\nLonger LinkedIn content here"
        )
        ctx = _make_context(multi_content)

        result = await self.skill.execute(
            {
                "action": "social_copy",
                "topic": "Test",
                "platforms": ["twitter", "linkedin"],
            },
            ctx,
        )

        assert result.success is True
        details = result.data["platform_details"]
        assert "twitter" in details
        assert "linkedin" in details
        assert "character_count" in details["twitter"]
        assert "max_chars" in details["twitter"]
        assert "within_limit" in details["twitter"]

    @pytest.mark.asyncio
    async def test_social_copy_requires_brain(self):
        """social_copy returns error when brain is not available."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", brain=None)
        result = await self.skill.execute(
            {"action": "social_copy", "topic": "Test"},
            ctx,
        )
        assert result.success is False
        assert "brain" in result.error.lower()


# ---------------------------------------------------------------------------
# email_copy Action Tests
# ---------------------------------------------------------------------------

class TestEmailCopy:
    """Tests for the email_copy action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.content_generator.handler import ContentGeneratorSkill
        self.skill = ContentGeneratorSkill()

    @pytest.mark.asyncio
    async def test_email_copy_generates_subject_variants(self):
        """email_copy generates multiple subject line A/B variants and body."""
        email_content = (
            "SUBJECT_1: Discover the Future of AI Today\n"
            "SUBJECT_2: How AI Is Changing Everything\n"
            "SUBJECT_3: You Won't Believe What AI Can Do Now\n\n"
            "EMAIL_BODY:\n"
            "Dear {{name}},\n\n"
            "We're excited to share our latest insights on artificial intelligence.\n"
            "Check out our newest report to learn more.\n\n"
            "Best regards,\nThe Team"
        )
        ctx = _make_context(email_content)

        result = await self.skill.execute(
            {
                "action": "email_copy",
                "topic": "AI Innovation",
                "subject_variants": 3,
            },
            ctx,
        )

        assert result.success is True
        assert len(result.data["subject_lines"]) == 3
        assert result.data["body"]  # Body is not empty
        assert "name" in result.data["body"] or "{{name}}" in result.data["body"]

    @pytest.mark.asyncio
    async def test_email_copy_requires_topic(self):
        """email_copy returns error when topic is missing."""
        ctx = _make_context()
        result = await self.skill.execute(
            {"action": "email_copy"},
            ctx,
        )
        assert result.success is False
        assert "topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_email_copy_clamps_variant_count(self):
        """email_copy clamps subject_variants to range [1, 5]."""
        email_content = (
            "SUBJECT_1: Subject One\n\n"
            "EMAIL_BODY:\nBody text here."
        )
        ctx = _make_context(email_content)

        # Request 10 variants — should clamp to 5
        result = await self.skill.execute(
            {"action": "email_copy", "topic": "Test", "subject_variants": 10},
            ctx,
        )
        assert result.success is True
        # The prompt should have asked for 5 variants (clamped)
        call_args = ctx.brain.think.call_args
        prompt = call_args[0][0]
        assert "5" in prompt

    @pytest.mark.asyncio
    async def test_email_copy_requires_brain(self):
        """email_copy returns error when brain is not available."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", brain=None)
        result = await self.skill.execute(
            {"action": "email_copy", "topic": "Test"},
            ctx,
        )
        assert result.success is False
        assert "brain" in result.error.lower()

    @pytest.mark.asyncio
    async def test_email_copy_handles_llm_failure(self):
        """email_copy returns error when LLM call fails."""
        ctx = _make_context()
        ctx.brain.think = AsyncMock(side_effect=Exception("Network error"))

        result = await self.skill.execute(
            {"action": "email_copy", "topic": "Testing"},
            ctx,
        )
        assert result.success is False
        assert "failed" in result.error.lower()


# ---------------------------------------------------------------------------
# brand_voice Action Tests
# ---------------------------------------------------------------------------

class TestBrandVoice:
    """Tests for the brand_voice action."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.content_generator.handler import ContentGeneratorSkill
        self.skill = ContentGeneratorSkill()

    @pytest.mark.asyncio
    @patch("skills.content_generator.handler.SystemKnowledge")
    async def test_brand_voice_stores_parameters(self, mock_sk):
        """brand_voice stores voice parameters in system_knowledge."""
        mock_sk.upsert = AsyncMock()

        ctx = _make_context()
        result = await self.skill.execute(
            {
                "action": "brand_voice",
                "brand_name": "Sanaa",
                "voice_params": {
                    "tone": "authoritative yet friendly",
                    "vocabulary": "technical but accessible",
                    "style_guide": "Use short sentences. Avoid jargon.",
                    "values": "innovation, reliability, community",
                    "audience": "tech-savvy professionals",
                },
            },
            ctx,
        )

        assert result.success is True
        assert result.data["brand_name"] == "Sanaa"
        assert result.data["stored_in"] == "system_knowledge"
        assert result.data["domain"] == "brand_voice"

        # Verify upsert was called
        mock_sk.upsert.assert_called_once()
        call_kwargs = mock_sk.upsert.call_args[1]
        assert call_kwargs["domain"] == "brand_voice"
        assert call_kwargs["key"] == "Sanaa"
        stored_value = json.loads(call_kwargs["value"])
        assert stored_value["tone"] == "authoritative yet friendly"
        assert stored_value["vocabulary"] == "technical but accessible"

    @pytest.mark.asyncio
    async def test_brand_voice_requires_brand_name(self):
        """brand_voice returns error when brand_name is missing."""
        ctx = _make_context()
        result = await self.skill.execute(
            {
                "action": "brand_voice",
                "voice_params": {"tone": "casual"},
            },
            ctx,
        )
        assert result.success is False
        assert "brand_name" in result.error.lower()

    @pytest.mark.asyncio
    async def test_brand_voice_requires_voice_params(self):
        """brand_voice returns error when voice_params is missing."""
        ctx = _make_context()
        result = await self.skill.execute(
            {"action": "brand_voice", "brand_name": "TestBrand"},
            ctx,
        )
        assert result.success is False
        assert "voice_params" in result.error.lower()

    @pytest.mark.asyncio
    async def test_brand_voice_requires_valid_voice_params(self):
        """brand_voice returns error when voice_params has no valid keys."""
        ctx = _make_context()
        result = await self.skill.execute(
            {
                "action": "brand_voice",
                "brand_name": "TestBrand",
                "voice_params": {"random_key": "random_value"},
            },
            ctx,
        )
        assert result.success is False
        assert "voice_params must include" in result.error.lower()

    @pytest.mark.asyncio
    async def test_brand_voice_rejects_non_dict_params(self):
        """brand_voice returns error when voice_params is not a dict."""
        ctx = _make_context()
        result = await self.skill.execute(
            {
                "action": "brand_voice",
                "brand_name": "TestBrand",
                "voice_params": "just a string",
            },
            ctx,
        )
        assert result.success is False
        assert "object" in result.error.lower()


# ---------------------------------------------------------------------------
# Unknown Action Test
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test error handling for unknown actions."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.content_generator.handler import ContentGeneratorSkill
        self.skill = ContentGeneratorSkill()

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        """Unknown action returns descriptive error."""
        ctx = _make_context()
        result = await self.skill.execute(
            {"action": "nonexistent_action"},
            ctx,
        )
        assert result.success is False
        assert "unknown action" in result.error.lower()
        assert "blog_post" in result.error


# ---------------------------------------------------------------------------
# Section Parser Tests
# ---------------------------------------------------------------------------

class TestSectionParsers:
    """Test internal parsing helpers."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from skills.content_generator.handler import ContentGeneratorSkill
        self.skill = ContentGeneratorSkill()

    def test_parse_blog_sections_with_headers(self):
        """Blog section parser extracts title, intro, body, conclusion."""
        content = (
            "# The Big Title\n\n"
            "## Introduction\n"
            "This is the introduction paragraph.\n\n"
            "## Main Points\n"
            "Here is the body content.\nMore body content.\n\n"
            "## Conclusion\n"
            "This is the conclusion."
        )
        sections = self.skill._parse_blog_sections(content)
        assert "Big Title" in sections["title"]
        assert "introduction" in sections["introduction"].lower()
        assert "body" in sections["body"].lower() or "main" in sections["body"].lower()
        assert "conclusion" in sections["conclusion"].lower()

    def test_parse_social_platforms(self):
        """Social platform parser extracts per-platform content."""
        content = (
            "[TWITTER]\n"
            "Short tweet #hashtag\n\n"
            "[LINKEDIN]\n"
            "Professional post here.\n\n"
            "[FACEBOOK]\n"
            "Casual fb post!"
        )
        result = self.skill._parse_social_platforms(
            content, ["twitter", "linkedin", "facebook"]
        )
        assert "tweet" in result["twitter"].lower()
        assert "professional" in result["linkedin"].lower()
        assert "casual" in result["facebook"].lower()

    def test_parse_email_content(self):
        """Email content parser extracts subject lines and body."""
        content = (
            "SUBJECT_1: First Subject Line\n"
            "SUBJECT_2: Second Subject Line\n"
            "SUBJECT_3: Third Subject Line\n\n"
            "EMAIL_BODY:\n"
            "Dear {{name}},\n\n"
            "This is the email body.\n"
            "Thanks!"
        )
        subjects, body = self.skill._parse_email_content(content, 3)
        assert len(subjects) == 3
        assert "First Subject" in subjects[0]
        assert "Second Subject" in subjects[1]
        assert "Third Subject" in subjects[2]
        assert "email body" in body.lower()


# ---------------------------------------------------------------------------
# Brand Voice Context Builder Tests
# ---------------------------------------------------------------------------

class TestBrandVoiceContext:
    """Test the brand voice context builder function."""

    def test_build_context_with_full_voice(self):
        """Brand voice context includes all parameters."""
        from skills.content_generator.handler import _build_brand_voice_context

        voice = {
            "tone": "professional",
            "vocabulary": "technical",
            "style_guide": "Use short sentences",
            "values": "innovation",
            "audience": "developers",
        }
        ctx = _build_brand_voice_context(voice)
        assert "professional" in ctx
        assert "technical" in ctx
        assert "short sentences" in ctx
        assert "innovation" in ctx
        assert "developers" in ctx

    def test_build_context_with_none(self):
        """Brand voice context returns empty string for None."""
        from skills.content_generator.handler import _build_brand_voice_context

        assert _build_brand_voice_context(None) == ""

    def test_build_context_with_empty_dict(self):
        """Brand voice context returns empty string for empty dict."""
        from skills.content_generator.handler import _build_brand_voice_context

        assert _build_brand_voice_context({}) == ""
