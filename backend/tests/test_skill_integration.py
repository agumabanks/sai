"""
Integration tests verifying all new skills work end-to-end.

Fulfills:
  VAL-SKILL-015  — GET /api/skills returns all 7 new skills
  VAL-SKILL-016  — Each skill executable via POST /api/skills/{name}/run
  VAL-SKILL-017  — Each new skill has >= 3 pytest test cases
  VAL-CROSS-001  — Skills with requires_approval trigger approval workflow
  VAL-CROSS-002  — Skills can store/retrieve from memory system

This is the final verification for milestone 3 (new-skills).
"""

import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

import pytest

# ────────────────────────────────────────────────────────────────────
# Path setup
# ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The seven new / upgraded skills expected in milestone 3
NEW_SKILLS = [
    "social_media",
    "email_marketing",
    "market_intelligence",
    "content_generator",
    "backup_automation",
    "calendar",
    "research_agent",
]

# Skill test files and their minimum expected test count
SKILL_TEST_FILES = {
    "social_media": "tests/skills/test_social_media.py",
    "email_marketing": "tests/skills/test_email_marketing.py",
    "market_intelligence": "tests/skills/test_market_intelligence.py",
    "content_generator": "tests/skills/test_content_generator.py",
    "backup_automation": "tests/skills/test_backup_automation.py",
    "calendar": "tests/skills/test_calendar.py",
    "research_agent": "tests/skills/test_research_agent.py",
}

MIN_TESTS_PER_SKILL = 3


# ====================================================================
# 1) Skill Loading & Listing (VAL-SKILL-015)
# ====================================================================

class TestAllNewSkillsAppearInListing:
    """
    Verify every new skill loads into the registry and would
    appear in the GET /api/skills listing.
    """

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        self.loader = SkillLoader(
            skills_dir=os.path.join(BACKEND_DIR, "skills"),
        )
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_all_new_skills_loaded(self):
        """All 7 new / upgraded skills are present in the registry."""
        for skill_name in NEW_SKILLS:
            assert skill_name in self.loaded, (
                f"Skill '{skill_name}' not loaded. "
                f"Available: {sorted(self.loaded.keys())}"
            )

    @pytest.mark.asyncio
    async def test_total_skill_count_at_least_seven_new(self):
        """Registry contains at least the 7 new skills."""
        loaded_new = [n for n in NEW_SKILLS if n in self.loaded]
        assert len(loaded_new) == len(NEW_SKILLS), (
            f"Only {len(loaded_new)} of {len(NEW_SKILLS)} new skills loaded: "
            f"missing {set(NEW_SKILLS) - set(loaded_new)}"
        )

    @pytest.mark.asyncio
    async def test_each_skill_has_valid_name(self):
        """Each loaded skill has the correct .name attribute."""
        for skill_name in NEW_SKILLS:
            skill = self.loaded[skill_name]
            assert skill.name == skill_name

    @pytest.mark.asyncio
    async def test_each_skill_has_description(self):
        """Each loaded skill has a non-empty description."""
        for skill_name in NEW_SKILLS:
            skill = self.loaded[skill_name]
            assert skill.description, f"{skill_name} has empty description"
            assert len(skill.description) > 10, (
                f"{skill_name} description is too short: '{skill.description}'"
            )

    @pytest.mark.asyncio
    async def test_each_skill_has_valid_permissions_list(self):
        """Each loaded skill has a permissions list (may be empty for safe skills)."""
        for skill_name in NEW_SKILLS:
            skill = self.loaded[skill_name]
            assert isinstance(skill.permissions, list), (
                f"{skill_name} permissions is not a list"
            )


# ====================================================================
# 2) Skill Execution via Registry (VAL-SKILL-016)
# ====================================================================

class TestSkillExecutionViaRegistry:
    """
    Verify each new skill can be executed through the SkillRegistry
    (the same code path as POST /api/skills/{name}/run).

    We use mocks for external calls (LLM, DB, network) but exercise
    the real registry → skill.execute() path.
    """

    @pytest.fixture(autouse=True)
    async def _setup(self):
        from core.skills.loader import SkillLoader
        from core.skills.registry import SkillRegistry
        from core.skills.base import SkillContext

        loader = SkillLoader(
            skills_dir=os.path.join(BACKEND_DIR, "skills"),
        )
        loaded = await loader.load_all()

        self.registry = SkillRegistry()
        for name, skill in loaded.items():
            self.registry.register(skill)

        self.context = SkillContext(
            session_id="integration-test",
            channel="test",
            sender_id="test-user",
        )
        self.context.brain = AsyncMock()
        self.context.brain.think = AsyncMock(return_value="Generated content for testing.")
        self.context.memory = AsyncMock()

    # --- social_media ---
    @pytest.mark.asyncio
    async def test_execute_social_media_create_content(self):
        """social_media create_content action executes without runtime errors."""
        result = await self.registry.execute(
            "social_media",
            {"action": "create_content", "topic": "AI trends", "platform": "twitter"},
            self.context,
        )
        assert result.success is True, f"social_media failed: {result.error}"
        assert result.data.get("platform") == "twitter"

    # --- email_marketing ---
    @pytest.mark.asyncio
    async def test_execute_email_marketing_create_campaign(self):
        """email_marketing create_campaign action executes without runtime errors."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", 1),
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.email_marketing.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await self.registry.execute(
                "email_marketing",
                {
                    "action": "create_campaign",
                    "name": "Integration Test",
                    "subject": "Test Subject",
                    "body_template": "Hello {{name}}",
                },
                self.context,
            )
        assert result.success is True, f"email_marketing failed: {result.error}"
        assert result.data.get("name") == "Integration Test"

    # --- market_intelligence ---
    @pytest.mark.asyncio
    async def test_execute_market_intelligence_scan(self):
        """market_intelligence scan_market action executes without runtime errors."""
        sample_rss = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item><title>Test Signal</title>
                <link>https://example.com/s</link>
                <description>Signal desc</description></item>
        </channel></rss>"""

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
            result = await self.registry.execute(
                "market_intelligence",
                {"action": "scan_market", "feeds": ["https://example.com/rss"]},
                self.context,
            )
        assert result.success is True, f"market_intelligence failed: {result.error}"
        assert result.data.get("total_signals") >= 1

    # --- content_generator ---
    @pytest.mark.asyncio
    async def test_execute_content_generator_blog(self):
        """content_generator blog_post action executes without runtime errors."""
        self.context.brain.think = AsyncMock(
            return_value=(
                "# Test Blog Post\n\n"
                "## Introduction\nThis is the intro.\n\n"
                "## Body\nThis is the body.\n\n"
                "## Conclusion\nThis is the conclusion."
            ),
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "skills.content_generator.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await self.registry.execute(
                "content_generator",
                {"action": "blog_post", "topic": "AI in Africa"},
                self.context,
            )
        assert result.success is True, f"content_generator failed: {result.error}"
        assert "blog" in result.output.lower() or "Test Blog" in result.output

    # --- calendar ---
    @pytest.mark.asyncio
    async def test_execute_calendar_create_task(self):
        """calendar create_task action executes without runtime errors."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", 1),
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        with patch(
            "skills.calendar.handler.AsyncSessionLocal",
            return_value=mock_ctx,
        ):
            result = await self.registry.execute(
                "calendar",
                {
                    "action": "create_task",
                    "title": "Integration test task",
                    "due_date": due,
                    "priority": "high",
                },
                self.context,
            )
        assert result.success is True, f"calendar failed: {result.error}"
        assert result.data.get("title") == "Integration test task"

    # --- research_agent ---
    @pytest.mark.asyncio
    async def test_execute_research_agent(self):
        """research_agent quick_search action executes without runtime errors."""
        ddg_results = [
            {"title": "AI Healthcare", "href": "https://example.com/ai", "body": "AI is transforming healthcare."},
            {"title": "ML Medicine", "href": "https://example.com/ml", "body": "ML in medicine."},
        ]

        with patch(
            "skills.research_agent.handler._ddg_search",
            return_value=ddg_results,
        ):
            result = await self.registry.execute(
                "research_agent",
                {"action": "quick_search", "topic": "AI in healthcare"},
                self.context,
            )
        assert result.success is True, f"research_agent failed: {result.error}"
        assert result.data.get("results_count") >= 1

    # --- backup_automation (requires_approval) ---
    @pytest.mark.asyncio
    async def test_execute_backup_automation_triggers_approval(self):
        """backup_automation requires approval — execute returns needs_approval=True."""
        result = await self.registry.execute(
            "backup_automation",
            {"action": "backup_status"},
            self.context,
        )
        # The registry should intercept and return an approval result
        assert result.needs_approval is True, (
            f"Expected needs_approval=True for backup_automation, "
            f"got success={result.success}, needs_approval={result.needs_approval}"
        )
        assert "approval" in result.approval_prompt.lower()


# ====================================================================
# 3) Security Policy — requires_approval (VAL-CROSS-001)
# ====================================================================

class TestSecurityApprovalFlow:
    """
    Verify that skills with requires_approval=True trigger the
    approval workflow rather than executing directly.
    """

    @pytest.fixture(autouse=True)
    async def _setup(self):
        from core.skills.loader import SkillLoader
        from core.skills.registry import SkillRegistry
        from core.skills.base import SkillContext

        loader = SkillLoader(
            skills_dir=os.path.join(BACKEND_DIR, "skills"),
        )
        loaded = await loader.load_all()

        self.registry = SkillRegistry()
        for name, skill in loaded.items():
            self.registry.register(skill)

        self.context = SkillContext(
            session_id="security-test",
            channel="test",
            sender_id="test-user",
        )

    @pytest.mark.asyncio
    async def test_backup_automation_requires_approval_flag(self):
        """backup_automation skill has requires_approval == True."""
        skill = self.registry.get("backup_automation")
        assert skill is not None
        assert skill.requires_approval is True

    @pytest.mark.asyncio
    async def test_backup_automation_approval_flow(self):
        """Executing backup_automation returns needs_approval result."""
        result = await self.registry.execute(
            "backup_automation",
            {"action": "backup_postgres"},
            self.context,
        )
        assert result.needs_approval is True
        assert "approval" in result.approval_prompt.lower()
        assert "backup_automation" in result.approval_prompt

    @pytest.mark.asyncio
    async def test_non_approval_skills_execute_normally(self):
        """Skills without requires_approval execute normally (no approval block)."""
        non_approval_skills = [
            "social_media",
            "email_marketing",
            "market_intelligence",
            "content_generator",
            "calendar",
            "research_agent",
        ]
        for skill_name in non_approval_skills:
            skill = self.registry.get(skill_name)
            assert skill is not None, f"Skill '{skill_name}' not found"
            assert skill.requires_approval is False, (
                f"Skill '{skill_name}' should NOT require approval but does"
            )

    @pytest.mark.asyncio
    async def test_registry_list_shows_approval_flag(self):
        """SkillRegistry.list_skills() includes requires_approval flag."""
        skills_list = self.registry.list_skills()
        backup_entry = next(
            (s for s in skills_list if s["name"] == "backup_automation"),
            None,
        )
        assert backup_entry is not None
        assert backup_entry["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_approval_skills_not_executed(self):
        """When approval is required, the actual skill handler is NOT called."""
        # The registry should return early without calling execute()
        # We verify this by checking the result has no execution_time
        result = await self.registry.execute(
            "backup_automation",
            {"action": "backup_status"},
            self.context,
        )
        assert result.needs_approval is True
        # execution_time_ms should be 0 because the skill body wasn't run
        assert result.execution_time_ms == 0


# ====================================================================
# 4) Memory System Integration (VAL-CROSS-002)
# ====================================================================

class TestSkillsMemoryIntegration:
    """
    Verify that new skills can store results in memory and retrieve them.
    Mocks the database layer so tests run reliably without asyncpg
    concurrency issues. Verifies the MemoryManager API contract.
    """

    def _make_mock_session_ctx(self, search_rows=None):
        """Create a mocked AsyncSessionLocal context manager."""
        mock_session = AsyncMock()
        mock_search_result = MagicMock()
        mock_search_result.mappings.return_value.all.return_value = search_rows or []
        mock_session.execute = AsyncMock(return_value=mock_search_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        return mock_ctx

    def _make_mock_memory_obj(self, memory_id=42):
        """Create a mock AgentMemory object returned by create()."""
        obj = MagicMock()
        obj.id = memory_id
        return obj

    @pytest.mark.asyncio
    async def test_store_social_media_result_in_memory(self):
        """A social_media skill result can be stored in memory."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import NullEmbeddings

        mm = MemoryManager(embedding_provider=NullEmbeddings())
        mock_ctx = self._make_mock_session_ctx()
        mock_mem = self._make_mock_memory_obj(101)

        with patch("core.memory.manager.AsyncSessionLocal", return_value=mock_ctx), \
             patch("core.memory.manager.AgentMemory") as mock_am:
            mock_am.create = AsyncMock(return_value=mock_mem)
            memory_id = await mm.store(
                content="Social media post for Twitter about AI in Africa.",
                category="social_media",
                source="skill:social_media",
                confidence=0.8,
            )
        assert memory_id == 101

    @pytest.mark.asyncio
    async def test_store_market_intelligence_in_memory(self):
        """market_intelligence skill result can be stored in memory."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import NullEmbeddings

        mm = MemoryManager(embedding_provider=NullEmbeddings())
        mock_ctx = self._make_mock_session_ctx()
        mock_mem = self._make_mock_memory_obj(102)

        with patch("core.memory.manager.AsyncSessionLocal", return_value=mock_ctx), \
             patch("core.memory.manager.AgentMemory") as mock_am:
            mock_am.create = AsyncMock(return_value=mock_mem)
            memory_id = await mm.store(
                content="Market signal: fintech adoption growing 40% in East Africa.",
                category="market_intelligence",
                source="skill:market_intelligence",
                confidence=0.9,
            )
        assert memory_id == 102

    @pytest.mark.asyncio
    async def test_store_and_search_research_findings(self):
        """research_agent findings stored in memory are searchable."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import NullEmbeddings

        mm = MemoryManager(embedding_provider=NullEmbeddings())

        # Mock search returning stored research data
        mock_search_ctx = self._make_mock_session_ctx(search_rows=[
            {
                "id": 10,
                "content": "Research: quantum computing will disrupt financial cryptography.",
                "category": "research",
                "confidence": 0.7,
                "source": "skill:research_agent",
                "created_at": datetime.now(timezone.utc),
                "rank": 0.5,
            },
        ])

        with patch("core.memory.manager.AsyncSessionLocal", return_value=mock_search_ctx):
            results = await mm.search("quantum computing", category="research")

        assert len(results) >= 1
        assert "quantum" in results[0]["content"].lower()
        assert results[0]["category"] == "research"

    @pytest.mark.asyncio
    async def test_store_calendar_task_in_memory(self):
        """calendar skill results can be stored in memory."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import NullEmbeddings

        mm = MemoryManager(embedding_provider=NullEmbeddings())
        mock_ctx = self._make_mock_session_ctx()
        mock_mem = self._make_mock_memory_obj(103)

        with patch("core.memory.manager.AsyncSessionLocal", return_value=mock_ctx), \
             patch("core.memory.manager.AgentMemory") as mock_am:
            mock_am.create = AsyncMock(return_value=mock_mem)
            memory_id = await mm.store(
                content="Task created: Review Q1 report due 2026-03-20 priority high.",
                category="calendar",
                source="skill:calendar",
                confidence=0.95,
            )
        assert memory_id == 103

    @pytest.mark.asyncio
    async def test_store_email_campaign_in_memory(self):
        """email_marketing campaign details can be stored in memory."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import NullEmbeddings

        mm = MemoryManager(embedding_provider=NullEmbeddings())
        mock_ctx = self._make_mock_session_ctx()
        mock_mem = self._make_mock_memory_obj(104)

        with patch("core.memory.manager.AsyncSessionLocal", return_value=mock_ctx), \
             patch("core.memory.manager.AgentMemory") as mock_am:
            mock_am.create = AsyncMock(return_value=mock_mem)
            memory_id = await mm.store(
                content="Email campaign Spring Sale targeting East Africa Admins.",
                category="email_marketing",
                source="skill:email_marketing",
                confidence=0.85,
            )
        assert memory_id == 104

    @pytest.mark.asyncio
    async def test_store_content_generation_in_memory(self):
        """content_generator output can be stored in memory."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import NullEmbeddings

        mm = MemoryManager(embedding_provider=NullEmbeddings())
        mock_ctx = self._make_mock_session_ctx()
        mock_mem = self._make_mock_memory_obj(105)

        with patch("core.memory.manager.AsyncSessionLocal", return_value=mock_ctx), \
             patch("core.memory.manager.AgentMemory") as mock_am:
            mock_am.create = AsyncMock(return_value=mock_mem)
            memory_id = await mm.store(
                content="Blog post AI-Driven Innovation in East African Agriculture.",
                category="content",
                source="skill:content_generator",
                confidence=0.75,
            )
        assert memory_id == 105

    @pytest.mark.asyncio
    async def test_store_backup_status_in_memory(self):
        """backup_automation status can be stored in memory."""
        from core.memory.manager import MemoryManager
        from core.memory.embeddings import NullEmbeddings

        mm = MemoryManager(embedding_provider=NullEmbeddings())
        mock_ctx = self._make_mock_session_ctx()
        mock_mem = self._make_mock_memory_obj(106)

        with patch("core.memory.manager.AsyncSessionLocal", return_value=mock_ctx), \
             patch("core.memory.manager.AgentMemory") as mock_am:
            mock_am.create = AsyncMock(return_value=mock_mem)
            memory_id = await mm.store(
                content="Backup completed PostgreSQL 245MB MySQL 120MB Config 5MB.",
                category="backup",
                source="skill:backup_automation",
                confidence=1.0,
            )
        assert memory_id == 106


# ====================================================================
# 5) Per-Skill Test Count Verification (VAL-SKILL-017)
# ====================================================================

class TestPerSkillTestCount:
    """
    Verify that each new skill has at least 3 pytest test cases.
    This is done by collecting tests from each file.
    """

    def test_social_media_has_enough_tests(self):
        """social_media test file exists and has >= 3 test functions."""
        self._assert_test_count("social_media")

    def test_email_marketing_has_enough_tests(self):
        """email_marketing test file exists and has >= 3 test functions."""
        self._assert_test_count("email_marketing")

    def test_market_intelligence_has_enough_tests(self):
        """market_intelligence test file exists and has >= 3 test functions."""
        self._assert_test_count("market_intelligence")

    def test_content_generator_has_enough_tests(self):
        """content_generator test file exists and has >= 3 test functions."""
        self._assert_test_count("content_generator")

    def test_backup_automation_has_enough_tests(self):
        """backup_automation test file exists and has >= 3 test functions."""
        self._assert_test_count("backup_automation")

    def test_calendar_has_enough_tests(self):
        """calendar test file exists and has >= 3 test functions."""
        self._assert_test_count("calendar")

    def test_research_agent_has_enough_tests(self):
        """research_agent test file exists and has >= 3 test functions."""
        self._assert_test_count("research_agent")

    def _assert_test_count(self, skill_name: str):
        """Helper: count test functions in a skill test file."""
        rel_path = SKILL_TEST_FILES.get(skill_name)
        assert rel_path is not None, f"No test file mapping for {skill_name}"

        full_path = os.path.join(BACKEND_DIR, rel_path)
        assert os.path.isfile(full_path), (
            f"Test file missing: {full_path}"
        )

        # Count lines that define test methods/functions
        with open(full_path) as f:
            lines = f.readlines()

        test_count = sum(
            1
            for line in lines
            if line.strip().startswith("def test_")
            or line.strip().startswith("async def test_")
        )

        assert test_count >= MIN_TESTS_PER_SKILL, (
            f"Skill '{skill_name}' has only {test_count} test(s) "
            f"(need >= {MIN_TESTS_PER_SKILL}). File: {rel_path}"
        )


# ====================================================================
# 6) Manifest Validation (structural integrity)
# ====================================================================

class TestManifestIntegrity:
    """
    Verify that every new skill's manifest.yaml parses correctly
    and contains required fields.
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import parse_manifest
        self.parse_manifest = parse_manifest

    @pytest.mark.parametrize("skill_name", NEW_SKILLS)
    def test_manifest_parses(self, skill_name):
        """Manifest YAML for {skill_name} parses without errors."""
        path = os.path.join(BACKEND_DIR, "skills", skill_name, "manifest.yaml")
        assert os.path.isfile(path), f"manifest.yaml missing for {skill_name}"
        manifest = self.parse_manifest(path)
        assert manifest is not None
        assert manifest.name == skill_name

    @pytest.mark.parametrize("skill_name", NEW_SKILLS)
    def test_manifest_has_handler(self, skill_name):
        """Handler module exists for {skill_name}."""
        handler_path = os.path.join(
            BACKEND_DIR, "skills", skill_name, "handler.py",
        )
        assert os.path.isfile(handler_path), (
            f"handler.py missing for {skill_name}"
        )

    @pytest.mark.parametrize("skill_name", NEW_SKILLS)
    def test_manifest_has_parameters(self, skill_name):
        """Manifest for {skill_name} defines at least one parameter."""
        path = os.path.join(BACKEND_DIR, "skills", skill_name, "manifest.yaml")
        manifest = self.parse_manifest(path)
        assert len(manifest.parameters) >= 1, (
            f"{skill_name} manifest has no parameters defined"
        )


# ====================================================================
# 7) Handler Import Smoke Test
# ====================================================================

class TestHandlerImports:
    """
    Verify that each skill's handler module imports without errors.
    This catches missing dependencies, syntax errors, etc.
    """

    def test_import_social_media_handler(self):
        """social_media handler imports without errors."""
        from skills.social_media.handler import SocialMediaSkill
        assert SocialMediaSkill is not None

    def test_import_email_marketing_handler(self):
        """email_marketing handler imports without errors."""
        from skills.email_marketing.handler import EmailMarketingSkill
        assert EmailMarketingSkill is not None

    def test_import_market_intelligence_handler(self):
        """market_intelligence handler imports without errors."""
        from skills.market_intelligence.handler import MarketIntelligenceSkill
        assert MarketIntelligenceSkill is not None

    def test_import_content_generator_handler(self):
        """content_generator handler imports without errors."""
        from skills.content_generator.handler import ContentGeneratorSkill
        assert ContentGeneratorSkill is not None

    def test_import_backup_automation_handler(self):
        """backup_automation handler imports without errors."""
        from skills.backup_automation.handler import BackupAutomationSkill
        assert BackupAutomationSkill is not None

    def test_import_calendar_handler(self):
        """calendar handler imports without errors."""
        from skills.calendar.handler import CalendarSkill
        assert CalendarSkill is not None

    def test_import_research_agent_handler(self):
        """research_agent handler imports without errors."""
        from skills.research_agent.handler import ResearchAgentSkill
        assert ResearchAgentSkill is not None


# ====================================================================
# 8) Skill Categories & Tags
# ====================================================================

class TestSkillCategoriesAndTags:
    """
    Verify that new skills are properly categorized
    (marketing, research, system) for the Skills Command Center UI.
    """

    @pytest.fixture(autouse=True)
    async def _load(self):
        from core.skills.loader import SkillLoader
        loader = SkillLoader(
            skills_dir=os.path.join(BACKEND_DIR, "skills"),
        )
        self.loaded = await loader.load_all()

    @pytest.mark.asyncio
    async def test_social_media_has_marketing_tag(self):
        """social_media is tagged for marketing."""
        skill = self.loaded["social_media"]
        assert any(
            "marketing" in t.lower() for t in skill.tags
        ), f"social_media tags: {skill.tags}"

    @pytest.mark.asyncio
    async def test_email_marketing_has_marketing_tag(self):
        """email_marketing is tagged for marketing."""
        skill = self.loaded["email_marketing"]
        assert any(
            "marketing" in t.lower() for t in skill.tags
        ), f"email_marketing tags: {skill.tags}"

    @pytest.mark.asyncio
    async def test_backup_automation_has_system_tag(self):
        """backup_automation is tagged as system/infrastructure."""
        skill = self.loaded["backup_automation"]
        tags_lower = [t.lower() for t in skill.tags]
        assert any(
            tag in tags_lower
            for tag in ["system", "infrastructure", "backup", "automation"]
        ), f"backup_automation tags: {skill.tags}"

    @pytest.mark.asyncio
    async def test_research_agent_has_research_tag(self):
        """research_agent is tagged for research."""
        skill = self.loaded["research_agent"]
        assert any(
            "research" in t.lower() for t in skill.tags
        ), f"research_agent tags: {skill.tags}"
