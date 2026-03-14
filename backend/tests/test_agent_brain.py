"""
Tests for shared Brain context across agents.

Covers VAL-FOUND-008: Shared Brain context across agents.
Verifies that agents use a shared Brain instance (or share memory context)
instead of creating isolated Brain instances, and that a memory stored by
one agent is accessible to another.
"""

import pytest

from core.brain.engine import Brain, get_shared_brain, reset_shared_brain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_SOURCE = "test_agent_brain_suite"


async def _cleanup():
    """Remove memories created by this test suite."""
    from core.database import engine, AsyncSessionLocal
    from sqlalchemy import text

    await engine.dispose()
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("DELETE FROM agent_memory WHERE source = :src"),
            {"src": TEST_SOURCE},
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def cleanup_shared_brain():
    """Reset the shared Brain singleton before and after each test."""
    reset_shared_brain()
    yield
    reset_shared_brain()


@pytest.fixture
async def fresh_db():
    """Dispose the module-level engine so connections are created on the
    current event loop."""
    from core.database import engine

    await engine.dispose()
    yield
    await engine.dispose()


# ===========================================================================
# 1. Shared Brain Factory
# ===========================================================================


class TestSharedBrainFactory:
    """Test that get_shared_brain() returns a true singleton."""

    def test_returns_brain_instance(self):
        """get_shared_brain() should return a Brain instance."""
        brain = get_shared_brain()
        assert isinstance(brain, Brain)

    def test_returns_same_instance(self):
        """Multiple calls should return the exact same object."""
        brain1 = get_shared_brain()
        brain2 = get_shared_brain()
        assert brain1 is brain2

    def test_reset_clears_singleton(self):
        """reset_shared_brain() should allow a new instance to be created."""
        brain1 = get_shared_brain()
        reset_shared_brain()
        brain2 = get_shared_brain()
        assert brain1 is not brain2

    def test_shared_brain_has_memory(self):
        """The shared brain should have a working memory property."""
        brain = get_shared_brain()
        assert brain.memory is not None

    def test_shared_brain_has_context_assembler(self):
        """The shared brain should have a working context_assembler property."""
        brain = get_shared_brain()
        assert brain.context_assembler is not None


# ===========================================================================
# 2. Agents Share the Same Brain
# ===========================================================================


class TestAgentsShareBrain:
    """Test that different agents get the same shared Brain instance."""

    def test_server_health_uses_shared_brain(self):
        """ServerHealthAgent should use the shared Brain."""
        from core.agents.server_health import ServerHealthAgent

        agent = ServerHealthAgent()
        shared = get_shared_brain()
        assert agent.brain is shared

    def test_email_agent_uses_shared_brain(self):
        """EmailInboxAgent should use the shared Brain."""
        from core.agents.email_agent import EmailInboxAgent

        agent = EmailInboxAgent()
        shared = get_shared_brain()
        assert agent.brain is shared

    def test_reflection_agent_uses_shared_brain(self):
        """ReflectionAgent should use the shared Brain."""
        from core.agents.reflection_agent import ReflectionAgent

        agent = ReflectionAgent()
        shared = get_shared_brain()
        assert agent.brain is shared

    def test_report_agent_uses_shared_brain(self):
        """ReportAgent should use the shared Brain."""
        from core.agents.report_agent import ReportAgent

        agent = ReportAgent()
        shared = get_shared_brain()
        assert agent.brain is shared

    def test_wisdom_agent_uses_shared_brain(self):
        """WisdomAgent should use the shared Brain."""
        from core.agents.wisdom import WisdomAgent

        agent = WisdomAgent()
        shared = get_shared_brain()
        assert agent.brain is shared

    def test_app_monitor_uses_shared_brain(self):
        """AppMonitorAgent should use the shared Brain."""
        from core.agents.app_monitor import AppMonitorAgent

        agent = AppMonitorAgent()
        shared = get_shared_brain()
        assert agent.brain is shared

    def test_news_agent_uses_shared_brain(self):
        """NewsAgent should use the shared Brain."""
        from core.agents.news_agent import NewsAgent

        agent = NewsAgent()
        shared = get_shared_brain()
        assert agent.brain is shared

    def test_all_agents_share_same_brain(self):
        """All agents created with default constructor share exactly one Brain."""
        from core.agents.server_health import ServerHealthAgent
        from core.agents.email_agent import EmailInboxAgent
        from core.agents.reflection_agent import ReflectionAgent
        from core.agents.report_agent import ReportAgent
        from core.agents.wisdom import WisdomAgent

        agents = [
            ServerHealthAgent(),
            EmailInboxAgent(),
            ReflectionAgent(),
            ReportAgent(),
            WisdomAgent(),
        ]
        brains = [a.brain for a in agents]
        # All should be the exact same object
        assert all(b is brains[0] for b in brains)

    def test_agents_share_memory_manager(self):
        """All agents' brains should point to the same MemoryManager."""
        from core.agents.server_health import ServerHealthAgent
        from core.agents.wisdom import WisdomAgent

        health = ServerHealthAgent()
        wisdom = WisdomAgent()
        assert health.brain.memory is wisdom.brain.memory


# ===========================================================================
# 3. Cross-Agent Memory Sharing (Integration)
# ===========================================================================


class TestCrossAgentMemorySharing:
    """Test that memories stored by one agent are accessible to another."""

    @pytest.mark.asyncio
    async def test_memory_stored_by_agent_a_visible_to_agent_b(self, fresh_db):
        """A memory stored via agent A's brain is retrievable by agent B."""
        from core.agents.server_health import ServerHealthAgent
        from core.agents.wisdom import WisdomAgent

        agent_a = ServerHealthAgent()
        agent_b = WisdomAgent()

        try:
            # Agent A stores a memory
            memory_id = await agent_a.brain.memory.store(
                content="Nginx proxy was restarted at 3am due to high load average",
                category="fact",
                source=TEST_SOURCE,
                confidence=0.9,
            )
            assert memory_id > 0

            # Agent B searches for it
            results = await agent_b.brain.memory.search(
                "Nginx restart high load", limit=5
            )
            assert len(results) > 0
            found = any(r["id"] == memory_id for r in results)
            assert found, (
                f"Memory {memory_id} stored by ServerHealthAgent not found by "
                f"WisdomAgent. Got IDs: {[r['id'] for r in results]}"
            )
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_memory_stored_by_brain_recall(self, fresh_db):
        """Brain.remember() from one agent, Brain.recall() from another."""
        from core.agents.email_agent import EmailInboxAgent
        from core.agents.reflection_agent import ReflectionAgent

        agent_a = EmailInboxAgent()
        agent_b = ReflectionAgent()

        try:
            # Agent A remembers something
            await agent_a.brain.remember(
                content="SMTP server mail.undpf.org uses port 587 with STARTTLS",
                category="fact",
                source=TEST_SOURCE,
            )

            # Agent B recalls it
            results = await agent_b.brain.recall("SMTP mail server port", limit=5)
            assert len(results) > 0
            assert any("587" in r["content"] for r in results)
        finally:
            await _cleanup()

    @pytest.mark.asyncio
    async def test_context_assembler_shared(self, fresh_db):
        """The context assembler is the same instance across agents."""
        from core.agents.server_health import ServerHealthAgent
        from core.agents.report_agent import ReportAgent

        agent_a = ServerHealthAgent()
        agent_b = ReportAgent()

        # Both use the shared brain's context assembler
        assert agent_a.brain.context_assembler is agent_b.brain.context_assembler


# ===========================================================================
# 4. Agent-Specific Context (Each Agent Keeps Its Own Session)
# ===========================================================================


class TestAgentSpecificContext:
    """Each agent still has its own session/conversation context."""

    def test_agents_can_accept_custom_brain(self):
        """Agents can still accept a custom Brain via constructor."""
        from core.agents.server_health import ServerHealthAgent

        custom_brain = Brain()
        agent = ServerHealthAgent(brain=custom_brain)
        assert agent.brain is custom_brain
        assert agent.brain is not get_shared_brain()
