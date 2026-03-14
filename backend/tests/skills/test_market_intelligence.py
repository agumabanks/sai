"""
Tests for the market_intelligence skill — competitor monitoring and market analysis.

Fulfills: VAL-SKILL-005, VAL-SKILL-006
  - market_intelligence skill has a valid manifest.yaml and handler.py, loads
    into the skill registry without errors, and appears in the API skills listing.
  - market_intelligence skill gathers signals from configured RSS feeds and web
    sources, analyzes trends via LLM, and returns structured market intelligence.
"""

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

class TestMarketIntelligenceManifest:
    """Verify the market_intelligence skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(
            BACKEND_DIR, "skills", "market_intelligence", "manifest.yaml",
        )
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'market_intelligence'."""
        assert self.manifest.name == "market_intelligence"

    def test_manifest_has_description(self):
        """Manifest includes a meaningful description."""
        assert self.manifest.description
        assert len(self.manifest.description) > 20

    def test_manifest_has_network_permission(self):
        """Skill requires network permission for HTTP fetches and LLM calls."""
        assert "network" in self.manifest.permissions

    def test_manifest_has_action_parameter(self):
        """Manifest defines an 'action' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "action" in param_names

    def test_manifest_action_enum_values(self):
        """Action parameter lists all four actions."""
        action_param = next(p for p in self.manifest.parameters if p.name == "action")
        assert "scan_market" in action_param.enum
        assert "analyze_trends" in action_param.enum
        assert "competitor_watch" in action_param.enum
        assert "report" in action_param.enum

    def test_manifest_has_feeds_parameter(self):
        """Manifest defines a 'feeds' parameter for scan_market."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "feeds" in param_names

    def test_manifest_has_urls_parameter(self):
        """Manifest defines a 'urls' parameter for competitor_watch."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "urls" in param_names


class TestMarketIntelligenceLoading:
    """Verify the market_intelligence skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """market_intelligence skill loads without errors."""
        assert "market_intelligence" in self.loaded, (
            f"market_intelligence not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'market_intelligence'."""
        skill = self.loaded["market_intelligence"]
        assert skill.name == "market_intelligence"


# ---------------------------------------------------------------------------
# scan_market Action Tests
# ---------------------------------------------------------------------------

class TestScanMarket:
    """Test the scan_market action — aggregate signals from RSS feeds."""

    @pytest.fixture
    def skill(self):
        from skills.market_intelligence.handler import MarketIntelligenceSkill
        return MarketIntelligenceSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_scan_market_parses_rss_feeds(self, skill, context):
        """scan_market fetches and parses RSS feeds, returns signal data."""
        sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Test Feed</title>
            <item>
              <title>AI Market Growth in 2026</title>
              <link>https://example.com/ai-growth</link>
              <description>The AI market is projected to grow 40% this year.</description>
            </item>
            <item>
              <title>Cloud Computing Trends</title>
              <link>https://example.com/cloud</link>
              <description>Multi-cloud strategies dominate enterprise adoption.</description>
            </item>
          </channel>
        </rss>"""

        # Mock the fetch and DB
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.market_intelligence.handler._fetch_url",
            new=AsyncMock(return_value=sample_rss),
        ), patch(
            "skills.market_intelligence.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await skill.execute(
                {"action": "scan_market", "feeds": ["https://example.com/rss"]},
                context,
            )

        assert result.success is True
        assert result.data["total_signals"] == 2
        assert result.data["stored"] == 2
        assert result.data["feeds_processed"] == 1
        assert "AI Market Growth" in result.output

    @pytest.mark.asyncio
    async def test_scan_market_handles_failed_feeds(self, skill, context):
        """scan_market gracefully handles feeds that fail to fetch."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.market_intelligence.handler._fetch_url",
            new=AsyncMock(return_value=None),
        ), patch(
            "skills.market_intelligence.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await skill.execute(
                {"action": "scan_market", "feeds": ["https://bad-feed.example.com/rss"]},
                context,
            )

        assert result.success is True
        assert result.data["total_signals"] == 0
        assert result.data["feed_errors"] == ["https://bad-feed.example.com/rss"]

    @pytest.mark.asyncio
    async def test_scan_market_invalid_feeds_param(self, skill, context):
        """scan_market returns error when feeds is not a list."""
        result = await skill.execute(
            {"action": "scan_market", "feeds": "not-a-list"},
            context,
        )
        assert result.success is False
        assert "list" in result.error.lower()


# ---------------------------------------------------------------------------
# analyze_trends Action Tests
# ---------------------------------------------------------------------------

class TestAnalyzeTrends:
    """Test the analyze_trends action — LLM-driven trend analysis."""

    @pytest.fixture
    def skill(self):
        from skills.market_intelligence.handler import MarketIntelligenceSkill
        return MarketIntelligenceSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="test")
        ctx.brain = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_analyze_trends_returns_structured_analysis(self, skill, context):
        """analyze_trends uses LLM to produce trend analysis."""
        analysis_text = (
            "## Key Trends\n- AI adoption accelerating\n"
            "## Opportunities\n- East African fintech expansion\n"
            "## Threats\n- Regulatory uncertainty\n"
            "## Recommended Actions\n- Invest in compliance infrastructure"
        )
        context.brain.think = AsyncMock(return_value=analysis_text)

        # Mock DB for fetching signals and storing the analysis signal
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"title": "AI Growth", "summary": "Market growing fast", "source": "rss",
             "classification": "market_signal", "score": 50},
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.market_intelligence.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await skill.execute(
                {"action": "analyze_trends", "topic": "fintech"},
                context,
            )

        assert result.success is True
        assert "Key Trends" in result.output
        assert "Opportunities" in result.output
        assert result.data["topic"] == "fintech"
        assert result.data["signals_analysed"] == 1

    @pytest.mark.asyncio
    async def test_analyze_trends_no_brain(self, skill):
        """analyze_trends returns error if brain is unavailable."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", channel="test")
        ctx.brain = None
        result = await skill.execute(
            {"action": "analyze_trends", "topic": "test"},
            ctx,
        )
        assert result.success is False
        assert "brain" in result.error.lower()


# ---------------------------------------------------------------------------
# competitor_watch Action Tests
# ---------------------------------------------------------------------------

class TestCompetitorWatch:
    """Test the competitor_watch action — content change detection."""

    @pytest.fixture
    def skill(self):
        from skills.market_intelligence.handler import MarketIntelligenceSkill
        return MarketIntelligenceSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_competitor_watch_detects_new_url(self, skill, context):
        """competitor_watch marks a new URL as 'new' when no previous hash exists."""
        html_content = "<html><body><h1>Competitor Page</h1><p>Latest product info</p></body></html>"

        # Mock fetch
        fetch_mock = AsyncMock(return_value=html_content)

        # Mock DB: no existing hash, then store new hash
        mock_session = AsyncMock()
        mock_select_result = MagicMock()
        mock_select_result.mappings.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_select_result)
        mock_session.commit = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.market_intelligence.handler._fetch_url", fetch_mock,
        ), patch(
            "skills.market_intelligence.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await skill.execute(
                {"action": "competitor_watch", "urls": ["https://competitor.example.com"]},
                context,
            )

        assert result.success is True
        assert result.data["urls_monitored"] == 1
        assert result.data["new_entries"] == 1
        assert result.data["results"][0]["status"] == "new"

    @pytest.mark.asyncio
    async def test_competitor_watch_detects_change(self, skill, context):
        """competitor_watch detects content change when hash differs from stored."""
        html_content = "<html><body><h1>Updated Page</h1><p>New info</p></body></html>"
        fetch_mock = AsyncMock(return_value=html_content)

        # Mock DB: return a different hash from the current page
        mock_session = AsyncMock()
        mock_select_result = MagicMock()
        mock_select_result.mappings.return_value.first.return_value = {
            "business_impact": "old_hash_that_does_not_match",
        }
        mock_session.execute = AsyncMock(return_value=mock_select_result)
        mock_session.commit = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.market_intelligence.handler._fetch_url", fetch_mock,
        ), patch(
            "skills.market_intelligence.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await skill.execute(
                {"action": "competitor_watch", "urls": ["https://competitor.example.com"]},
                context,
            )

        assert result.success is True
        assert result.data["changes_detected"] == 1
        assert result.data["results"][0]["changed"] is True

    @pytest.mark.asyncio
    async def test_competitor_watch_missing_urls(self, skill, context):
        """competitor_watch returns error when urls not provided."""
        result = await skill.execute(
            {"action": "competitor_watch"},
            context,
        )
        assert result.success is False
        assert "urls" in result.error.lower()

    @pytest.mark.asyncio
    async def test_competitor_watch_empty_urls(self, skill, context):
        """competitor_watch returns error for empty list."""
        result = await skill.execute(
            {"action": "competitor_watch", "urls": []},
            context,
        )
        assert result.success is False
        assert "urls" in result.error.lower()


# ---------------------------------------------------------------------------
# report Action Tests
# ---------------------------------------------------------------------------

class TestReport:
    """Test the report action — structured market intelligence report."""

    @pytest.fixture
    def skill(self):
        from skills.market_intelligence.handler import MarketIntelligenceSkill
        return MarketIntelligenceSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test-session", channel="test")
        ctx.brain = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_report_generates_comprehensive_output(self, skill, context):
        """report action produces structured market intelligence report."""
        report_text = (
            "# Market Intelligence Report\n"
            "**Period:** weekly\n**Focus:** East African e-commerce\n\n"
            "## Executive Summary\nStrong growth across the region.\n"
            "## Market Signals Overview\n3 major signals detected.\n"
            "## Competitor Activity\nCompetitor X launched new features.\n"
            "## Trend Analysis\nMobile-first strategies dominating.\n"
            "## Opportunities\nCross-border trade expansion.\n"
            "## Threats & Risks\nRegulatory fragmentation.\n"
            "## Recommendations\nInvest in compliance tooling."
        )
        context.brain.think = AsyncMock(return_value=report_text)

        # Mock DB
        mock_session = AsyncMock()
        mock_select_result = MagicMock()
        mock_select_result.mappings.return_value.all.return_value = [
            {
                "title": "E-commerce growth in East Africa",
                "link": "https://example.com/article",
                "source": "rss",
                "summary": "Rapid growth reported",
                "classification": "market_signal",
                "score": 60,
                "business_impact": "",
                "created_at": datetime.now(timezone.utc),
            },
        ]
        mock_session.execute = AsyncMock(return_value=mock_select_result)
        mock_session.commit = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.market_intelligence.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await skill.execute(
                {"action": "report", "topic": "East African e-commerce", "timeframe": "weekly"},
                context,
            )

        assert result.success is True
        assert "Market Intelligence Report" in result.output
        assert result.data["topic"] == "East African e-commerce"
        assert result.data["timeframe"] == "weekly"
        assert result.data["signals_used"] == 1

    @pytest.mark.asyncio
    async def test_report_no_brain(self, skill):
        """report returns error if brain is unavailable."""
        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", channel="test")
        ctx.brain = None
        result = await skill.execute(
            {"action": "report", "topic": "test"},
            ctx,
        )
        assert result.success is False
        assert "brain" in result.error.lower()


# ---------------------------------------------------------------------------
# Unknown / Invalid Action Tests
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test handling of invalid actions."""

    @pytest.fixture
    def skill(self):
        from skills.market_intelligence.handler import MarketIntelligenceSkill
        return MarketIntelligenceSkill()

    @pytest.fixture
    def context(self):
        from core.skills.base import SkillContext
        return SkillContext(session_id="test-session", channel="test")

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, skill, context):
        """Unknown action returns descriptive error."""
        result = await skill.execute({"action": "destroy"}, context)
        assert result.success is False
        assert "unknown action" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_action_returns_error(self, skill, context):
        """Missing action parameter returns an error."""
        result = await skill.execute({}, context)
        assert result.success is False
        assert "unknown action" in result.error.lower()


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------

class TestHelpers:
    """Test helper functions directly."""

    def test_parse_rss_extracts_items(self):
        """_parse_rss extracts title, link, summary from RSS XML."""
        from skills.market_intelligence.handler import _parse_rss
        xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Test Article</title>
              <link>https://example.com/test</link>
              <description>A test article description.</description>
            </item>
          </channel>
        </rss>"""
        items = _parse_rss(xml)
        assert len(items) == 1
        assert items[0]["title"] == "Test Article"
        assert items[0]["link"] == "https://example.com/test"
        assert "test article description" in items[0]["summary"].lower()

    def test_parse_rss_handles_empty_feed(self):
        """_parse_rss returns empty list for feed with no items."""
        from skills.market_intelligence.handler import _parse_rss
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Empty</title></channel></rss>"""
        items = _parse_rss(xml)
        assert items == []

    def test_hash_content_deterministic(self):
        """_hash_content produces the same hash for the same content."""
        from skills.market_intelligence.handler import _hash_content
        h1 = _hash_content("Hello World")
        h2 = _hash_content("Hello World")
        assert h1 == h2

    def test_hash_content_different_for_different_input(self):
        """_hash_content produces different hashes for different content."""
        from skills.market_intelligence.handler import _hash_content
        h1 = _hash_content("Page version 1")
        h2 = _hash_content("Page version 2")
        assert h1 != h2

    def test_extract_page_text_strips_scripts(self):
        """_extract_page_text removes script and style tags."""
        from skills.market_intelligence.handler import _extract_page_text
        html = """<html>
        <head><style>body{color:red}</style></head>
        <body>
          <script>alert('x')</script>
          <h1>Visible Title</h1>
          <p>Visible paragraph.</p>
          <nav>Navigation</nav>
        </body></html>"""
        text = _extract_page_text(html)
        assert "Visible Title" in text
        assert "Visible paragraph" in text
        assert "alert" not in text
        assert "color:red" not in text
        assert "Navigation" not in text


# ---------------------------------------------------------------------------
# API Integration Test
# ---------------------------------------------------------------------------

class TestMarketIntelligenceAPIIntegration:
    """Verify skill appears in the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_in_registry(self):
        """market_intelligence skill appears in loaded skills registry."""
        assert "market_intelligence" in self.loaded
        skill = self.loaded["market_intelligence"]
        assert skill.name == "market_intelligence"
        assert "network" in skill.permissions
