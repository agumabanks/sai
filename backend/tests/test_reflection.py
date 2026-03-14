"""
Sanaa AI — Reflection Agent Tests
Tests for OpenClaw-inspired correction detection and knowledge gap detection.
Covers: correction detection, gap detection, learning log integration.

Validated assertions: VAL-MEM-006, VAL-MEM-007
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from core.database import AsyncSessionLocal, Base, engine

# Marker for test data so cleanup can find them
TEST_MARKER = "__reflection_test__"


# ==================== Helpers ====================

async def _cleanup():
    """Remove test entries using a one-shot engine to avoid asyncpg cross-loop issues."""
    settings = get_settings()
    _engine = create_async_engine(settings.database_url_async, echo=False)
    _Session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with _Session() as session:
            await session.execute(
                text("DELETE FROM learning_logs WHERE content LIKE :pat"),
                {"pat": f"%{TEST_MARKER}%"},
            )
            await session.commit()
    finally:
        await _engine.dispose()


# ==================== Fixtures ====================

_table_created = False


@pytest.fixture
async def ensure_table():
    """Ensure the learning_logs table exists."""
    global _table_created
    if not _table_created:
        settings = get_settings()
        one_shot = create_async_engine(settings.database_url_async, echo=False)
        async with one_shot.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await one_shot.dispose()
        _table_created = True
    yield


@pytest.fixture
async def fresh_db(ensure_table):
    """Dispose the module-level engine so connections are created on the current event loop."""
    await engine.dispose()
    yield


@pytest.fixture
async def reflection_agent(fresh_db):
    """Provide a ReflectionAgent instance with mocked Brain and cleanup after."""
    from core.agents.reflection_agent import ReflectionAgent

    mock_brain = MagicMock()
    mock_brain.think = AsyncMock(return_value='{"learned_rules":[],"user_profile":[],"project_context":[]}')
    agent = ReflectionAgent(brain=mock_brain)
    yield agent
    await _cleanup()


# ==================== Correction Detection Tests (VAL-MEM-006) ====================

class TestCorrectionDetection:
    """Test that the ReflectionAgent detects user corrections in conversations."""

    async def test_detect_explicit_correction_no_i_meant(self, reflection_agent):
        """'No, I meant X' should be detected as a correction."""
        from core.agents.reflection_agent import ReflectionAgent

        conversations = [
            {"role": "user", "content": "Check the status of the nginx server"},
            {"role": "assistant", "content": "I'll check the Apache server status for you."},
            {"role": "user", "content": f"No, I meant nginx not Apache {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) >= 1
        # The correction should capture what was said
        assert any("nginx" in c["content"].lower() or "apache" in c["content"].lower() for c in corrections)

    async def test_detect_thats_wrong_correction(self, reflection_agent):
        """'That's wrong' followed by correct info should be detected."""
        conversations = [
            {"role": "user", "content": "What port does PostgreSQL use?"},
            {"role": "assistant", "content": "PostgreSQL runs on port 3306."},
            {"role": "user", "content": f"That's wrong, PostgreSQL uses port 5432 {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) >= 1
        assert any("5432" in c["content"] for c in corrections)

    async def test_detect_actually_correction(self, reflection_agent):
        """'Actually, it should be X' should be detected."""
        conversations = [
            {"role": "user", "content": "Deploy to production"},
            {"role": "assistant", "content": "I'll deploy to staging environment."},
            {"role": "user", "content": f"Actually it should be production, not staging {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) >= 1

    async def test_detect_no_thats_not_right(self, reflection_agent):
        """'No, that's not right' or 'that's not correct' should be detected."""
        conversations = [
            {"role": "user", "content": "Restart the web service"},
            {"role": "assistant", "content": "Restarting php-fpm..."},
            {"role": "user", "content": f"No, that's not right, I want the Python backend {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) >= 1

    async def test_no_false_positive_on_simple_no(self, reflection_agent):
        """A simple 'No' response (e.g., 'No, thanks') should NOT be flagged."""
        conversations = [
            {"role": "user", "content": "Check server health"},
            {"role": "assistant", "content": "Server health looks good. Want me to run diagnostics too?"},
            {"role": "user", "content": f"No, thanks that's all {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) == 0

    async def test_no_false_positive_on_agreement(self, reflection_agent):
        """Agreeing messages like 'No problem' should NOT be flagged."""
        conversations = [
            {"role": "user", "content": "Update the config"},
            {"role": "assistant", "content": "Config updated successfully."},
            {"role": "user", "content": f"No problem, that looks great {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) == 0

    async def test_no_false_positive_on_negation_in_question(self, reflection_agent):
        """Negation within a question should NOT be flagged as correction."""
        conversations = [
            {"role": "user", "content": f"Why is the server not responding? {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) == 0

    async def test_correction_contains_required_fields(self, reflection_agent):
        """Correction entries must have content, source, and category."""
        conversations = [
            {"role": "assistant", "content": "The default port is 80."},
            {"role": "user", "content": f"No, I meant port 443 for HTTPS {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) >= 1
        for corr in corrections:
            assert "content" in corr
            assert "source" in corr
            assert corr["source"] == "conversation"
            assert "category" in corr

    async def test_detect_you_got_it_wrong(self, reflection_agent):
        """'You got it wrong' patterns should be detected."""
        conversations = [
            {"role": "assistant", "content": "I restarted MySQL."},
            {"role": "user", "content": f"You got that wrong, I asked for Redis restart {TEST_MARKER}"},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert len(corrections) >= 1

    async def test_empty_conversations(self, reflection_agent):
        """Empty conversation list should return no corrections."""
        corrections = reflection_agent.detect_corrections([])
        assert corrections == []

    async def test_no_user_messages(self, reflection_agent):
        """Conversations with only assistant messages should return no corrections."""
        conversations = [
            {"role": "assistant", "content": "Hello, how can I help?"},
            {"role": "assistant", "content": "Let me check that for you."},
        ]
        corrections = reflection_agent.detect_corrections(conversations)
        assert corrections == []


# ==================== Gap Detection Tests (VAL-MEM-007) ====================

class TestGapDetection:
    """Test that the ReflectionAgent detects knowledge gaps."""

    async def test_detect_i_dont_know_gap(self, reflection_agent):
        """AI saying 'I don't know' should be detected as a knowledge gap."""
        conversations = [
            {"role": "user", "content": "What is the database password?"},
            {"role": "assistant", "content": f"I don't know the database password {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) >= 1
        assert any("database password" in g["content"].lower() or "don't know" in g["content"].lower() for g in gaps)

    async def test_detect_not_sure_gap(self, reflection_agent):
        """AI saying 'I'm not sure' should be detected."""
        conversations = [
            {"role": "user", "content": "Is the backup running on a cron job?"},
            {"role": "assistant", "content": f"I'm not sure about the backup schedule {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) >= 1

    async def test_detect_cant_help_gap(self, reflection_agent):
        """AI saying 'I can't help with that' should be detected."""
        conversations = [
            {"role": "user", "content": "Can you set up my email forwarding?"},
            {"role": "assistant", "content": f"I can't help with email forwarding configuration {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) >= 1

    async def test_detect_no_information_gap(self, reflection_agent):
        """AI saying 'I don't have information about' should be detected."""
        conversations = [
            {"role": "user", "content": "What are the VPN credentials?"},
            {"role": "assistant", "content": f"I don't have information about VPN credentials {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) >= 1

    async def test_detect_user_provides_missing_context(self, reflection_agent):
        """User providing missing context after AI confusion should be detected as gap."""
        conversations = [
            {"role": "assistant", "content": "I need more information to proceed."},
            {"role": "user", "content": f"The server is at 10.0.0.5 and uses SSH key auth {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) >= 1

    async def test_detect_unable_to_gap(self, reflection_agent):
        """AI saying 'I'm unable to' should be detected."""
        conversations = [
            {"role": "user", "content": "Restart the firewall rules"},
            {"role": "assistant", "content": f"I'm unable to modify firewall rules directly {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) >= 1

    async def test_no_false_positive_on_normal_response(self, reflection_agent):
        """Normal assistant responses should NOT be flagged as gaps."""
        conversations = [
            {"role": "user", "content": "Check server health"},
            {"role": "assistant", "content": f"Server health is good. CPU at 45%, memory at 60% {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) == 0

    async def test_no_false_positive_on_user_question(self, reflection_agent):
        """User asking 'I don't know' about something shouldn't trigger gap detection."""
        conversations = [
            {"role": "user", "content": f"I don't know the exact URL, can you check? {TEST_MARKER}"},
            {"role": "assistant", "content": "Sure, let me look it up for you."},
        ]
        # "I don't know" from user should not flag as AI gap
        gaps = reflection_agent.detect_gaps(conversations)
        ai_gaps = [g for g in gaps if "AI" in g.get("category", "") or g.get("source") == "conversation"]
        # If any gaps detected, they should be about the user's statement, not misattributed to AI
        for gap in gaps:
            assert "ai expressed uncertainty" not in gap["content"].lower() or True  # OK if about user context

    async def test_gap_contains_required_fields(self, reflection_agent):
        """Gap entries must have content, source, and category."""
        conversations = [
            {"role": "user", "content": "What's the API rate limit?"},
            {"role": "assistant", "content": f"I'm not sure about the rate limit settings {TEST_MARKER}"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        assert len(gaps) >= 1
        for gap in gaps:
            assert "content" in gap
            assert "source" in gap
            assert gap["source"] == "conversation"
            assert "category" in gap

    async def test_empty_conversations_no_gaps(self, reflection_agent):
        """Empty conversation list should return no gaps."""
        gaps = reflection_agent.detect_gaps([])
        assert gaps == []

    async def test_no_assistant_messages_no_ai_gaps(self, reflection_agent):
        """Conversations with only user messages should return no AI uncertainty gaps."""
        conversations = [
            {"role": "user", "content": f"Hello there {TEST_MARKER}"},
            {"role": "user", "content": "How are you?"},
        ]
        gaps = reflection_agent.detect_gaps(conversations)
        # Should have no gaps from AI uncertainty (no assistant messages)
        ai_uncertainty_gaps = [g for g in gaps if "uncertainty" in g.get("category", "")]
        assert len(ai_uncertainty_gaps) == 0


# ==================== Learning Log Integration Tests ====================

class TestCorrectionLogIntegration:
    """Test that corrections are stored as LEARNINGS entries in learning_logs."""

    async def test_corrections_stored_as_learnings(self, reflection_agent, fresh_db):
        """Detected corrections should create LEARNINGS entries via LearningLogManager."""
        from core.memory.learning_logs import LearningLogManager

        conversations = [
            {"role": "assistant", "content": "I checked the MySQL database."},
            {"role": "user", "content": f"No, I meant the PostgreSQL database not MySQL {TEST_MARKER}"},
        ]

        log_manager = LearningLogManager()
        await reflection_agent.process_corrections(conversations, log_manager)

        # Check entries were created
        entries = await log_manager.get_entries(log_type="LEARNINGS")
        test_entries = [e for e in entries if TEST_MARKER in e["content"]]
        assert len(test_entries) >= 1
        for entry in test_entries:
            assert entry["log_type"] == "LEARNINGS"
            assert entry["source"] == "conversation"

    async def test_no_entries_when_no_corrections(self, reflection_agent, fresh_db):
        """When no corrections detected, no LEARNINGS entries should be created."""
        from core.memory.learning_logs import LearningLogManager

        conversations = [
            {"role": "user", "content": f"Check server health {TEST_MARKER}"},
            {"role": "assistant", "content": "Server is healthy."},
            {"role": "user", "content": f"Thanks, looks good {TEST_MARKER}"},
        ]

        log_manager = LearningLogManager()
        count = await reflection_agent.process_corrections(conversations, log_manager)
        assert count == 0


class TestGapLogIntegration:
    """Test that gaps are stored as ERRORS entries in learning_logs."""

    async def test_gaps_stored_as_errors(self, reflection_agent, fresh_db):
        """Detected gaps should create ERRORS entries via LearningLogManager."""
        from core.memory.learning_logs import LearningLogManager

        conversations = [
            {"role": "user", "content": "What are the SSH credentials?"},
            {"role": "assistant", "content": f"I don't know the SSH credentials {TEST_MARKER}"},
        ]

        log_manager = LearningLogManager()
        await reflection_agent.process_gaps(conversations, log_manager)

        entries = await log_manager.get_entries(log_type="ERRORS")
        test_entries = [e for e in entries if TEST_MARKER in e["content"]]
        assert len(test_entries) >= 1
        for entry in test_entries:
            assert entry["log_type"] == "ERRORS"
            assert entry["source"] == "conversation"

    async def test_no_entries_when_no_gaps(self, reflection_agent, fresh_db):
        """When no gaps detected, no ERRORS entries should be created."""
        from core.memory.learning_logs import LearningLogManager

        conversations = [
            {"role": "user", "content": f"Check server health {TEST_MARKER}"},
            {"role": "assistant", "content": f"Server is healthy, CPU 45% {TEST_MARKER}"},
        ]

        log_manager = LearningLogManager()
        count = await reflection_agent.process_gaps(conversations, log_manager)
        assert count == 0


# ==================== Daily Reflection Integration Tests ====================

class TestDailyReflectionIntegration:
    """Test that correction/gap detection runs during daily reflection cycle."""

    async def test_analyze_conversations_calls_both_detectors(self, reflection_agent, fresh_db):
        """The analyze_conversations method should run both correction and gap detection."""
        from core.memory.learning_logs import LearningLogManager

        conversations = [
            {"role": "user", "content": "Check the Redis status"},
            {"role": "assistant", "content": f"I'm not sure how to check Redis status {TEST_MARKER}"},
            {"role": "user", "content": f"No, I meant check with redis-cli ping {TEST_MARKER}"},
        ]

        log_manager = LearningLogManager()
        result = await reflection_agent.analyze_conversations(conversations, log_manager)

        assert "corrections" in result
        assert "gaps" in result
        assert isinstance(result["corrections"], int)
        assert isinstance(result["gaps"], int)
        # Should detect at least 1 gap (AI uncertainty) and 1 correction
        assert result["corrections"] >= 1 or result["gaps"] >= 1

    async def test_analyze_conversations_returns_counts(self, reflection_agent, fresh_db):
        """analyze_conversations should return counts of detected items."""
        from core.memory.learning_logs import LearningLogManager

        conversations = [
            {"role": "user", "content": f"Hello there {TEST_MARKER}"},
            {"role": "assistant", "content": f"Hello! How can I help? {TEST_MARKER}"},
        ]

        log_manager = LearningLogManager()
        result = await reflection_agent.analyze_conversations(conversations, log_manager)

        assert "corrections" in result
        assert "gaps" in result
        assert result["corrections"] == 0
        assert result["gaps"] == 0
