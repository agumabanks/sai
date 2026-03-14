"""
Tests for the research_agent skill — multi-step web research with deeper analysis.

Fulfills: VAL-SKILL-009
  - The research_agent skill performs multi-step web research: formulates queries,
    fetches results, synthesizes findings, and produces a structured research report.
  - Research results are stored in memory for future context.
  - Handles network errors gracefully (timeouts, 404s).
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

class TestResearchAgentManifest:
    """Verify the research_agent skill manifest is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        manifest_path = os.path.join(
            BACKEND_DIR, "skills", "research_agent", "manifest.yaml",
        )
        self.manifest = parse_manifest(manifest_path)

    def test_manifest_parses_successfully(self):
        """Manifest YAML parses without errors."""
        assert self.manifest is not None

    def test_manifest_has_correct_name(self):
        """Skill name is 'research_agent'."""
        assert self.manifest.name == "research_agent"

    def test_manifest_has_description(self):
        """Manifest includes a meaningful description."""
        assert self.manifest.description
        assert len(self.manifest.description) > 20

    def test_manifest_version_is_2(self):
        """Manifest version is 2.0.0 (upgraded)."""
        assert self.manifest.version == "2.0.0"

    def test_manifest_has_network_permission(self):
        """Skill requires network permission for HTTP fetches and LLM calls."""
        assert "network" in self.manifest.permissions

    def test_manifest_has_action_parameter(self):
        """Manifest defines an 'action' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "action" in param_names

    def test_manifest_action_enum_values(self):
        """Action parameter lists all three actions."""
        action_param = next(p for p in self.manifest.parameters if p.name == "action")
        assert "research" in action_param.enum
        assert "quick_search" in action_param.enum
        assert "extract_url" in action_param.enum

    def test_manifest_has_topic_parameter(self):
        """Manifest defines a 'topic' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "topic" in param_names

    def test_manifest_has_num_queries_parameter(self):
        """Manifest defines a 'num_queries' parameter."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "num_queries" in param_names

    def test_manifest_has_url_parameter(self):
        """Manifest defines a 'url' parameter for extract_url."""
        param_names = [p.name for p in self.manifest.parameters]
        assert "url" in param_names

    def test_manifest_category_is_research(self):
        """Manifest has category 'research'."""
        import yaml
        manifest_path = os.path.join(
            BACKEND_DIR, "skills", "research_agent", "manifest.yaml",
        )
        with open(manifest_path) as f:
            raw = yaml.safe_load(f)
        assert raw.get("category") == "research"


class TestResearchAgentLoading:
    """Verify the research_agent skill loads into the registry."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_loads_successfully(self):
        """research_agent skill loads without errors."""
        assert "research_agent" in self.loaded, (
            f"research_agent not in loaded skills: {list(self.loaded.keys())}"
        )

    @pytest.mark.asyncio
    async def test_loaded_skill_has_correct_name(self):
        """Loaded skill has name == 'research_agent'."""
        skill = self.loaded["research_agent"]
        assert skill.name == "research_agent"

    @pytest.mark.asyncio
    async def test_loaded_skill_has_network_permission(self):
        """Loaded skill has network permission."""
        skill = self.loaded["research_agent"]
        assert "network" in skill.permissions


# ---------------------------------------------------------------------------
# Helper: build context
# ---------------------------------------------------------------------------

def _make_context(brain_response: str = "Generated report") -> MagicMock:
    """Create a SkillContext mock with a Brain that returns the given text."""
    from core.skills.base import SkillContext

    brain = AsyncMock()
    brain.think = AsyncMock(return_value=brain_response)

    ctx = SkillContext(
        session_id="test-session",
        channel="test",
        sender_id="tester",
        sender_name="Test User",
        brain=brain,
        memory=MagicMock(),
    )
    return ctx


def _make_context_no_brain() -> MagicMock:
    """Create a SkillContext mock without a Brain."""
    from core.skills.base import SkillContext
    return SkillContext(session_id="test", channel="test", brain=None)


# ---------------------------------------------------------------------------
# Query Formulation Tests
# ---------------------------------------------------------------------------

class TestQueryFormulation:
    """Test query formulation from research topic."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    @pytest.mark.asyncio
    async def test_formulate_queries_with_brain(self, skill):
        """LLM generates diverse search queries from topic."""
        ctx = _make_context(
            "AI in healthcare diagnostics\n"
            "artificial intelligence medical imaging 2026\n"
            "machine learning clinical trials analysis"
        )
        queries = await skill._formulate_queries(
            "AI in healthcare", 3, ctx
        )
        assert len(queries) == 3
        assert all(isinstance(q, str) for q in queries)
        assert all(len(q) > 3 for q in queries)

    @pytest.mark.asyncio
    async def test_formulate_queries_without_brain(self, skill):
        """Falls back to basic query variants when Brain not available."""
        ctx = _make_context_no_brain()
        queries = await skill._formulate_queries(
            "AI in healthcare", 3, ctx
        )
        assert len(queries) == 3
        assert queries[0] == "AI in healthcare"
        assert "2026" in queries[1]

    @pytest.mark.asyncio
    async def test_formulate_queries_limits_count(self, skill):
        """Never returns more queries than requested."""
        ctx = _make_context(
            "query 1\nquery 2\nquery 3\nquery 4\nquery 5\nquery 6"
        )
        queries = await skill._formulate_queries("test topic", 2, ctx)
        assert len(queries) <= 2

    @pytest.mark.asyncio
    async def test_formulate_queries_brain_failure(self, skill):
        """Falls back to basic queries when Brain throws."""
        ctx = _make_context()
        ctx.brain.think = AsyncMock(side_effect=Exception("LLM down"))
        queries = await skill._formulate_queries("test topic", 3, ctx)
        assert len(queries) == 3
        assert queries[0] == "test topic"

    def test_fallback_queries(self, skill):
        """Fallback queries cover the topic from multiple angles."""
        queries = skill._fallback_queries("blockchain technology", 3)
        assert len(queries) == 3
        assert "blockchain technology" in queries[0]
        assert "2026" in queries[1]
        assert "analysis" in queries[2] or "overview" in queries[2]


# ---------------------------------------------------------------------------
# Full Research Action Tests
# ---------------------------------------------------------------------------

class TestFullResearch:
    """Test the full multi-step research flow."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    @pytest.mark.asyncio
    async def test_research_full_flow(self, skill):
        """Full research pipeline: queries -> search -> extract -> synthesize -> memory."""
        # LLM returns queries first, then a synthesis report
        synthesis_report = (
            "## Key Findings\n"
            "- AI is transforming healthcare diagnostics\n"
            "- Machine learning improves imaging accuracy by 40%\n"
            "- Clinical trial analysis accelerated\n\n"
            "## Detailed Analysis\n"
            "Comprehensive analysis of AI in healthcare.\n\n"
            "## Sources\n"
            "- Source 1 (https://example.com/1)\n\n"
            "## Confidence Assessment\n"
            "HIGH - multiple reliable sources\n\n"
            "## Knowledge Gaps\n"
            "- Long-term impact on patient outcomes\n"
            "- Regulatory frameworks still evolving"
        )

        brain = AsyncMock()
        # First call: query formulation, second call: synthesis
        brain.think = AsyncMock(side_effect=[
            "AI healthcare diagnostics\nAI medical imaging latest research\nAI clinical trials 2026",
            synthesis_report,
        ])

        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", channel="test", brain=brain)

        sample_html = (
            "<html><head><title>AI in Healthcare</title></head>"
            "<body><h1>AI in Healthcare</h1>"
            "<p>Artificial intelligence is revolutionizing healthcare. "
            "Machine learning algorithms are being used for diagnostics, "
            "treatment planning, drug discovery, and patient monitoring. "
            "Research shows significant improvements in diagnostic accuracy. "
            "The field continues to grow rapidly with new applications emerging daily.</p>"
            "</body></html>"
        )

        ddg_results = [
            {"title": "AI Healthcare Article", "href": "https://example.com/ai-health", "body": "AI healthcare snippet"},
            {"title": "ML in Medicine", "href": "https://example.com/ml-med", "body": "ML medicine snippet"},
        ]

        mock_memory = AsyncMock()
        mock_memory.store = AsyncMock(return_value=42)

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=sample_html),
        ), patch(
            "skills.research_agent.handler.MemoryManager",
            return_value=mock_memory,
        ):
            result = await skill.execute(
                {"action": "research", "topic": "AI in healthcare", "num_queries": 3},
                ctx,
            )

        assert result.success is True
        assert "Research Report" in result.output
        assert result.data["topic"] == "AI in healthcare"
        assert len(result.data["queries_used"]) == 3
        assert result.data["sources_count"] > 0
        assert result.data["confidence"] == 0.85  # HIGH confidence
        assert len(result.data["key_findings"]) >= 3
        assert len(result.data["knowledge_gaps"]) >= 1
        assert result.data["memory_id"] == 42

    @pytest.mark.asyncio
    async def test_research_requires_topic(self, skill):
        """Research returns error when topic is missing."""
        ctx = _make_context()
        result = await skill.execute({"action": "research"}, ctx)
        assert result.success is False
        assert "topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_research_no_search_results(self, skill):
        """Research handles case when no search results are found."""
        ctx = _make_context("query1\nquery2\nquery3")

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=[],
        ):
            result = await skill.execute(
                {"action": "research", "topic": "extremely obscure topic xyz"},
                ctx,
            )

        assert result.success is False
        assert "failed" in result.error.lower() or "extract" in result.error.lower()

    @pytest.mark.asyncio
    async def test_research_all_fetches_fail(self, skill):
        """Research handles case when all URL fetches fail (timeouts, 404s)."""
        ctx = _make_context("query1\nquery2")

        ddg_results = [
            {"title": "Bad Page", "href": "https://example.com/bad", "body": "snippet"},
        ]

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=None),
        ):
            result = await skill.execute(
                {"action": "research", "topic": "test topic"},
                ctx,
            )

        assert result.success is False
        assert "failed" in result.error.lower()
        assert len(result.data.get("errors", [])) > 0

    @pytest.mark.asyncio
    async def test_research_stores_in_memory(self, skill):
        """Research stores results in memory system."""
        synthesis_report = (
            "## Key Findings\n"
            "- Finding one\n\n"
            "## Detailed Analysis\nAnalysis text.\n\n"
            "## Sources\n- Source\n\n"
            "## Confidence Assessment\nMEDIUM\n\n"
            "## Knowledge Gaps\n- Gap one"
        )

        brain = AsyncMock()
        brain.think = AsyncMock(side_effect=[
            "search query 1\nsearch query 2",
            synthesis_report,
        ])

        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", channel="test", brain=brain)

        sample_html = (
            "<html><head><title>Research Page</title></head>"
            "<body><h1>Research Results</h1>"
            "<p>This page contains substantial content about the research topic. "
            "It has detailed information about the subject matter with multiple paragraphs "
            "and sufficient text content to pass the minimum extraction threshold of 100 characters "
            "that the research agent requires for valid page extraction.</p></body></html>"
        )
        ddg_results = [
            {"title": "Result", "href": "https://example.com/page", "body": "snippet"},
        ]

        mock_memory = AsyncMock()
        mock_memory.store = AsyncMock(return_value=99)

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=sample_html),
        ), patch(
            "skills.research_agent.handler.MemoryManager",
            return_value=mock_memory,
        ):
            result = await skill.execute(
                {"action": "research", "topic": "test storage"},
                ctx,
            )

        assert result.success is True
        # Verify memory store was called
        mock_memory.store.assert_called_once()
        call_kwargs = mock_memory.store.call_args[1]
        assert call_kwargs["category"] == "research"
        assert call_kwargs["source"] == "research_agent"
        assert "test storage" in call_kwargs["content"]
        assert result.data["memory_id"] == 99

    @pytest.mark.asyncio
    async def test_research_memory_failure_doesnt_crash(self, skill):
        """Research continues even if memory storage fails."""
        synthesis_report = (
            "## Key Findings\n- Finding\n\n"
            "## Detailed Analysis\nText.\n\n"
            "## Sources\n- S\n\n"
            "## Confidence Assessment\nLOW\n\n"
            "## Knowledge Gaps\n- G"
        )

        brain = AsyncMock()
        brain.think = AsyncMock(side_effect=[
            "query1\nquery2",
            synthesis_report,
        ])

        from core.skills.base import SkillContext
        ctx = SkillContext(session_id="test", channel="test", brain=brain)

        html = (
            "<html><head><title>Test Page</title></head>"
            "<body><h1>Test Content</h1>"
            "<p>This is a test page with substantial content for the research agent "
            "to extract and process. It contains enough text to surpass the minimum "
            "threshold of 100 characters needed for valid content extraction in the "
            "multi-step research pipeline.</p></body></html>"
        )
        ddg_results = [
            {"title": "R", "href": "https://example.com/p", "body": "s"},
        ]

        mock_memory = AsyncMock()
        mock_memory.store = AsyncMock(side_effect=Exception("DB connection failed"))

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=html),
        ), patch(
            "skills.research_agent.handler.MemoryManager",
            return_value=mock_memory,
        ):
            result = await skill.execute(
                {"action": "research", "topic": "test memory failure"},
                ctx,
            )

        # Should still succeed (memory storage is best-effort)
        assert result.success is True
        assert result.data["memory_id"] is None

    @pytest.mark.asyncio
    async def test_research_max_queries_clamped(self, skill):
        """num_queries parameter is clamped to max 5."""
        ctx = _make_context("q1\nq2\nq3\nq4\nq5\nq6\nq7")

        ddg_results = [
            {"title": "R", "href": "https://example.com/page", "body": "s"},
        ]
        html = (
            "<html><head><title>Test Page</title></head>"
            "<body><h1>Clamping Test</h1>"
            "<p>This page has enough content for the research agent to extract properly. "
            "It includes detailed text about the topic being researched, with multiple sentences "
            "that provide sufficient length to surpass the minimum content threshold requirement "
            "of 100 characters for valid page extraction.</p></body></html>"
        )

        synthesis = (
            "## Key Findings\n- F\n\n"
            "## Detailed Analysis\nA.\n\n"
            "## Sources\n- S\n\n"
            "## Confidence Assessment\nMEDIUM\n\n"
            "## Knowledge Gaps\n"
        )

        brain = AsyncMock()
        brain.think = AsyncMock(side_effect=[
            "\n".join([f"query {i}" for i in range(10)]),
            synthesis,
        ])

        from core.skills.base import SkillContext
        ctx2 = SkillContext(session_id="test", channel="test", brain=brain)

        mock_memory = AsyncMock()
        mock_memory.store = AsyncMock(return_value=1)

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=html),
        ), patch(
            "skills.research_agent.handler.MemoryManager",
            return_value=mock_memory,
        ):
            result = await skill.execute(
                {"action": "research", "topic": "test clamping", "num_queries": 10},
                ctx2,
            )

        assert result.success is True
        # Should have at most 5 queries
        assert len(result.data["queries_used"]) <= 5


# ---------------------------------------------------------------------------
# Quick Search Tests
# ---------------------------------------------------------------------------

class TestQuickSearch:
    """Test the quick_search action."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    @pytest.mark.asyncio
    async def test_quick_search_returns_results(self, skill):
        """quick_search returns DuckDuckGo search results."""
        ctx = _make_context()

        ddg_results = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "First result"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Second result"},
        ]

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ):
            result = await skill.execute(
                {"action": "quick_search", "topic": "test search"},
                ctx,
            )

        assert result.success is True
        assert "Quick Search" in result.output
        assert result.data["results_count"] == 2
        assert result.data["results"][0]["title"] == "Result 1"
        assert result.data["results"][0]["url"] == "https://example.com/1"

    @pytest.mark.asyncio
    async def test_quick_search_requires_topic(self, skill):
        """quick_search returns error when topic is missing."""
        ctx = _make_context()
        result = await skill.execute({"action": "quick_search"}, ctx)
        assert result.success is False
        assert "topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_quick_search_no_results(self, skill):
        """quick_search returns error when no results found."""
        ctx = _make_context()

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=[],
        ):
            result = await skill.execute(
                {"action": "quick_search", "topic": "xyznonexistent"},
                ctx,
            )

        assert result.success is False
        assert "no search results" in result.error.lower()

    @pytest.mark.asyncio
    async def test_quick_search_max_results_clamped(self, skill):
        """quick_search clamps max_results to 10."""
        ctx = _make_context()

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=[{"title": "R", "href": "https://e.com", "body": "s"}],
        ) as mock_search:
            await skill.execute(
                {"action": "quick_search", "topic": "test", "max_results": 50},
                ctx,
            )
            # Should have been clamped to 10
            mock_search.assert_called_once_with("test", max_results=10)


# ---------------------------------------------------------------------------
# Extract URL Tests
# ---------------------------------------------------------------------------

class TestExtractUrl:
    """Test the extract_url action."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    @pytest.mark.asyncio
    async def test_extract_url_returns_content(self, skill):
        """extract_url fetches and extracts text from a URL."""
        ctx = _make_context()

        html = (
            "<html><head><title>Test Page</title></head>"
            "<body><h1>Welcome</h1><p>This is the main content of the page.</p></body></html>"
        )

        with patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=html),
        ):
            result = await skill.execute(
                {"action": "extract_url", "url": "https://example.com/page"},
                ctx,
            )

        assert result.success is True
        assert "Test Page" in result.output
        assert result.data["title"] == "Test Page"
        assert "main content" in result.data["content"]
        assert result.data["content_length"] > 0

    @pytest.mark.asyncio
    async def test_extract_url_requires_url(self, skill):
        """extract_url returns error when URL is missing."""
        ctx = _make_context()
        result = await skill.execute({"action": "extract_url"}, ctx)
        assert result.success is False
        assert "url" in result.error.lower()

    @pytest.mark.asyncio
    async def test_extract_url_fetch_failure(self, skill):
        """extract_url returns error when fetch fails."""
        ctx = _make_context()

        with patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=None),
        ):
            result = await skill.execute(
                {"action": "extract_url", "url": "https://example.com/404"},
                ctx,
            )

        assert result.success is False
        assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_extract_url_empty_content(self, skill):
        """extract_url returns error when page has no visible text content."""
        ctx = _make_context()

        # Page with only script tags, no visible text in body
        html = "<html><head></head><body><script>console.log('x')</script><style>.a{color:red}</style></body></html>"

        with patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=html),
        ):
            result = await skill.execute(
                {"action": "extract_url", "url": "https://example.com/empty"},
                ctx,
            )

        assert result.success is False
        assert "no text" in result.error.lower()


# ---------------------------------------------------------------------------
# Unknown Action Tests
# ---------------------------------------------------------------------------

class TestUnknownAction:
    """Test handling of invalid actions."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, skill):
        """Unknown action returns descriptive error."""
        ctx = _make_context()
        result = await skill.execute({"action": "destroy"}, ctx)
        assert result.success is False
        assert "unknown action" in result.error.lower()


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------

class TestHelpers:
    """Test helper functions directly."""

    def test_extract_page_text_strips_scripts(self):
        """_extract_page_text removes script, style, nav, footer, header, aside tags."""
        from skills.research_agent.handler import _extract_page_text
        html = """<html>
        <head><style>body{color:red}</style></head>
        <body>
            <script>alert('x')</script>
            <header>Site Header</header>
            <nav>Navigation Links</nav>
            <h1>Visible Title</h1>
            <p>Visible paragraph with useful content.</p>
            <aside>Sidebar content</aside>
            <footer>Footer text</footer>
        </body></html>"""
        text_content = _extract_page_text(html)
        assert "Visible Title" in text_content
        assert "Visible paragraph" in text_content
        assert "alert" not in text_content
        assert "color:red" not in text_content
        assert "Navigation Links" not in text_content
        assert "Site Header" not in text_content
        assert "Footer text" not in text_content
        assert "Sidebar content" not in text_content

    def test_extract_page_text_respects_max_chars(self):
        """_extract_page_text truncates at max_chars."""
        from skills.research_agent.handler import _extract_page_text
        html = "<html><body>" + "<p>A</p>" * 10000 + "</body></html>"
        text_content = _extract_page_text(html, max_chars=100)
        assert len(text_content) <= 100

    def test_extract_page_title_from_title_tag(self):
        """_extract_page_title extracts from <title> tag."""
        from skills.research_agent.handler import _extract_page_title
        html = "<html><head><title>My Page Title</title></head><body></body></html>"
        assert _extract_page_title(html) == "My Page Title"

    def test_extract_page_title_from_h1(self):
        """_extract_page_title falls back to <h1> when no <title>."""
        from skills.research_agent.handler import _extract_page_title
        html = "<html><body><h1>Header Title</h1></body></html>"
        assert _extract_page_title(html) == "Header Title"

    def test_extract_page_title_empty(self):
        """_extract_page_title returns empty string when nothing found."""
        from skills.research_agent.handler import _extract_page_title
        html = "<html><body><p>No title here</p></body></html>"
        assert _extract_page_title(html) == ""

    @pytest.mark.asyncio
    async def test_fetch_url_timeout(self):
        """_fetch_url returns None on timeout."""
        from skills.research_agent.handler import _fetch_url
        import httpx

        with patch("skills.research_agent.handler.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await _fetch_url("https://example.com/slow")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_url_http_error(self):
        """_fetch_url returns None on HTTP error status."""
        from skills.research_agent.handler import _fetch_url
        import httpx

        with patch("skills.research_agent.handler.httpx.AsyncClient") as mock_client_cls:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "404", request=MagicMock(), response=mock_response
                )
            )

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await _fetch_url("https://example.com/404")
            assert result is None

    def test_ddg_search_failure_returns_empty(self):
        """_ddg_search returns empty list on exception."""
        from skills.research_agent.handler import _ddg_search

        with patch("skills.research_agent.handler.DDGS") as mock_ddgs_cls:
            mock_ddgs = MagicMock()
            mock_ddgs.text = MagicMock(side_effect=Exception("API rate limited"))
            mock_ddgs_cls.return_value = mock_ddgs

            result = _ddg_search("test query")
            assert result == []


# ---------------------------------------------------------------------------
# Report Parsing Tests
# ---------------------------------------------------------------------------

class TestReportParsing:
    """Test the report parsing logic."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    def test_parse_high_confidence(self, skill):
        """Parses HIGH confidence correctly."""
        report = (
            "## Key Findings\n"
            "- Finding one\n"
            "- Finding two\n\n"
            "## Confidence Assessment\n"
            "HIGH - based on multiple reliable sources\n\n"
            "## Knowledge Gaps\n"
            "- Gap one"
        )
        parsed = skill._parse_report(report, [])
        assert parsed["confidence"] == 0.85
        assert len(parsed["key_findings"]) == 2
        assert len(parsed["knowledge_gaps"]) == 1

    def test_parse_medium_confidence(self, skill):
        """Parses MEDIUM confidence correctly."""
        report = "## Confidence Assessment\nMEDIUM - some uncertainty\n"
        parsed = skill._parse_report(report, [])
        assert parsed["confidence"] == 0.6

    def test_parse_low_confidence(self, skill):
        """Parses LOW confidence correctly."""
        report = "## Confidence Assessment\nLOW - limited sources available\n"
        parsed = skill._parse_report(report, [])
        assert parsed["confidence"] == 0.35

    def test_parse_no_findings(self, skill):
        """Returns fallback when no key findings are parseable."""
        report = "## Detailed Analysis\nJust some text.\n"
        parsed = skill._parse_report(report, [])
        assert parsed["key_findings"] == ["See report for details"]

    def test_parse_sources_from_input(self, skill):
        """Sources are derived from input sources, not parsed from report text."""
        sources = [
            {"title": "Source A", "url": "https://a.com", "content": "text"},
            {"title": "Source B", "url": "https://b.com", "content": "text"},
        ]
        parsed = skill._parse_report("## Key Findings\n- F\n", sources)
        assert len(parsed["sources"]) == 2
        assert parsed["sources"][0]["title"] == "Source A"


# ---------------------------------------------------------------------------
# Search and Extract Tests
# ---------------------------------------------------------------------------

class TestSearchAndExtract:
    """Test the search and content extraction pipeline."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    @pytest.mark.asyncio
    async def test_deduplicates_urls(self, skill):
        """Search results with duplicate URLs are deduplicated."""
        ddg_results = [
            {"title": "Page", "href": "https://example.com/same", "body": "snippet"},
            {"title": "Page Again", "href": "https://example.com/same", "body": "snippet"},
            {"title": "Different", "href": "https://example.com/other", "body": "snippet"},
        ]

        html = (
            "<html><head><title>Test Page</title></head>"
            "<body><h1>Dedup Test</h1>"
            "<p>This page contains enough text content for the research agent to extract. "
            "It includes multiple sentences with detailed information about the topic being "
            "researched. The content is sufficient to surpass the 100-character minimum "
            "threshold for valid page extraction.</p></body></html>"
        )

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=html),
        ):
            extracted, errors = await skill._search_and_extract(
                ["test query"], max_results_per_query=3, max_pages=5
            )

        # Should have 2 unique URLs, not 3
        urls = [e["url"] for e in extracted]
        assert len(urls) == 2
        assert len(set(urls)) == 2

    @pytest.mark.asyncio
    async def test_respects_max_pages(self, skill):
        """Extract respects max_pages limit."""
        ddg_results = [
            {"title": f"Page {i}", "href": f"https://example.com/{i}", "body": "s"}
            for i in range(10)
        ]

        html = (
            "<html><head><title>Test Page</title></head>"
            "<body><h1>Max Pages Test</h1>"
            "<p>This page has substantial content for the research agent to extract properly. "
            "It includes detailed text about the topic being researched, with multiple sentences "
            "that provide sufficient length to surpass the minimum content threshold requirement "
            "of 100 characters for valid page extraction.</p></body></html>"
        )

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=html),
        ):
            extracted, _ = await skill._search_and_extract(
                ["test"], max_results_per_query=10, max_pages=3
            )

        assert len(extracted) <= 3

    @pytest.mark.asyncio
    async def test_skips_insufficient_content(self, skill):
        """Pages with less than 100 chars of content are skipped."""
        ddg_results = [
            {"title": "Thin Page", "href": "https://example.com/thin", "body": "s"},
        ]

        html = "<html><body><p>Short</p></body></html>"

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ), patch(
            "skills.research_agent.handler._fetch_url",
            new=AsyncMock(return_value=html),
        ):
            extracted, errors = await skill._search_and_extract(
                ["test"], max_results_per_query=3, max_pages=5
            )

        assert len(extracted) == 0
        assert len(errors) > 0
        assert "insufficient" in errors[0].lower()


# ---------------------------------------------------------------------------
# Synthesis Tests
# ---------------------------------------------------------------------------

class TestSynthesis:
    """Test the LLM synthesis step."""

    @pytest.fixture
    def skill(self):
        from skills.research_agent.handler import ResearchAgentSkill
        return ResearchAgentSkill()

    @pytest.mark.asyncio
    async def test_synthesize_without_brain(self, skill):
        """Synthesis without brain returns partial result."""
        ctx = _make_context_no_brain()
        sources = [{"title": "S1", "url": "https://e.com", "content": "text", "snippet": "s", "query": "q"}]
        result = await skill._synthesize("test", sources, ctx)
        assert result["confidence"] == 0.3
        assert "not available" in result["report"].lower() or "unavailable" in result["report"].lower()

    @pytest.mark.asyncio
    async def test_synthesize_empty_llm_response(self, skill):
        """Synthesis handles empty LLM response."""
        ctx = _make_context("")
        sources = [{"title": "S1", "url": "https://e.com", "content": "text", "snippet": "s", "query": "q"}]
        result = await skill._synthesize("test", sources, ctx)
        assert result["confidence"] == 0.2
        assert "empty" in result["report"].lower()

    @pytest.mark.asyncio
    async def test_synthesize_llm_failure(self, skill):
        """Synthesis handles LLM exception gracefully."""
        ctx = _make_context()
        ctx.brain.think = AsyncMock(side_effect=Exception("LLM timeout"))
        sources = [{"title": "S1", "url": "https://e.com", "content": "text", "snippet": "s", "query": "q"}]
        result = await skill._synthesize("test", sources, ctx)
        assert result["confidence"] == 0.2
        assert "failed" in result["report"].lower()


# ---------------------------------------------------------------------------
# API Integration Test
# ---------------------------------------------------------------------------

class TestResearchAgentAPIIntegration:
    """Verify skill appears in the registry with correct metadata."""

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(skills_dir=os.path.join(BACKEND_DIR, "skills"))
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_skill_in_registry(self):
        """research_agent skill appears in loaded skills registry."""
        assert "research_agent" in self.loaded
        skill = self.loaded["research_agent"]
        assert skill.name == "research_agent"
        assert "network" in skill.permissions

    @pytest.mark.asyncio
    async def test_skill_version_is_upgraded(self):
        """research_agent skill has version 2.0.0."""
        skill = self.loaded["research_agent"]
        assert skill.version == "2.0.0"
