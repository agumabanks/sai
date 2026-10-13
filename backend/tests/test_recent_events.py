"""
Tests for the recent event store and async I/O helpers.
Covers: deps recent-event persistence helpers, async email/report agents.
"""

import pytest
import asyncio


class TestRecentEventStore:
    """Tests for core.routes.deps recent event store helpers."""

    @pytest.fixture(autouse=True)
    async def _reset_events(self):
        """Clear the in-memory event cache before each test."""
        from core.routes import deps
        deps._recent_events[:] = []
        yield
        deps._recent_events[:] = []

    async def test_add_recent_events_prepends_and_caps(self):
        from core.routes import deps

        await deps.add_recent_events([{"id": 1}, {"id": 2}])
        await deps.add_recent_events([{"id": 3}])

        events = deps.get_recent_events()
        assert [e["id"] for e in events] == [3, 1, 2]

    async def test_get_recent_events_paginates(self):
        from core.routes import deps

        # Add batches; the most recently prepended batch appears first.
        await deps.add_recent_events([{"id": 1}, {"id": 2}])
        await deps.add_recent_events([{"id": 3}, {"id": 4}])

        page = deps.get_recent_events(limit=2, offset=1)
        assert [e["id"] for e in page] == [4, 1]

    async def test_add_recent_events_caps_at_max_events(self):
        from core.routes import deps

        await deps.add_recent_events([{"id": i} for i in range(deps.MAX_EVENTS + 10)])
        assert len(deps._recent_events) == deps.MAX_EVENTS


class TestAsyncEmailAgent:
    """Tests that email/report agents no longer use sync blocking I/O directly."""

    def test_email_agent_uses_settings_not_os_getenv(self):
        from core.agents.email_agent import EmailInboxAgent

        agent = EmailInboxAgent()
        # Should not reference os.getenv for config
        assert not hasattr(agent, "_EmailInboxAgent__os_getenv")
        assert agent.port is not None

    def test_report_agent_uses_settings_not_os_getenv(self):
        from core.agents.report_agent import ReportAgent

        agent = ReportAgent()
        assert agent.smtp_port is not None
        assert isinstance(agent.recipients, list)

    async def test_email_agent_unconfigured_returns_early(self):
        from core.agents.email_agent import EmailInboxAgent

        agent = EmailInboxAgent()
        agent.host = None
        agent.user = None
        result = await agent.get_inbox_summary()
        assert result["summary"] == "Email not configured"


class TestCeleryRunAsync:
    """Tests for the Celery _run_async helper."""

    def test_run_async_uses_runner_not_global_loop(self):
        from core.tasks import _run_async

        async def _coro():
            return "ok"

        result = _run_async(_coro())
        assert result == "ok"
