"""
Sanaa AI — Alert system tests.
Covers:
  - AlertRule model CRUD (create, read, update, delete)
  - Alert routing (AlertRouter matches alerts to rules)
  - Escalation engine (escalates after timeout)
  - Quiet hours suppress non-critical alerts
  - Email alerts sent via SMTP to rule recipients

Fulfills: VAL-UI-004, VAL-UI-005, VAL-CROSS-008
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


def auth_headers():
    """Return auth headers using the configured API key."""
    from core.config import get_settings
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.mac_client_api_key}"}


def unique(prefix: str = "rule") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def alert_client():
    """Module-scoped async client."""
    from core.database import engine
    await engine.dispose()

    from core.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await engine.dispose()


# ==================== ALERT RULE MODEL TESTS ====================


class TestAlertRuleModel:
    """VAL-UI-004: AlertRule model with condition, threshold, severity, recipients, escalation config."""

    def test_alert_rule_model_exists(self):
        """AlertRule model should exist in database module."""
        from core.database import AlertRule
        assert AlertRule is not None

    def test_alert_rule_has_required_columns(self):
        """AlertRule must have condition, threshold, severity, recipients, escalation_policy, quiet_hours."""
        from core.database import AlertRule
        col_names = [c.name for c in AlertRule.__table__.columns]
        for col in ["id", "name", "condition", "threshold", "severity",
                     "recipients", "escalation_policy", "quiet_hours",
                     "enabled", "created_at"]:
            assert col in col_names, f"Column '{col}' missing from AlertRule model"

    def test_alert_rule_severity_values(self):
        """AlertRule severity should be a string column for low/medium/high/critical."""
        from core.database import AlertRule
        col = AlertRule.__table__.columns["severity"]
        assert col.nullable is False


# ==================== ALERT RULE CRUD API TESTS ====================


class TestAlertRuleCRUD:
    """VAL-UI-004: CRUD endpoints for alert rules work."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_create_alert_rule(self, alert_client):
        """POST /api/alert-rules creates a new rule."""
        rule_data = {
            "name": unique("cpu-high"),
            "condition": "cpu_usage > threshold",
            "threshold": 90.0,
            "severity": "high",
            "recipients": ["admin@sanaa.co"],
            "escalation_policy": {
                "levels": [
                    {"channel": "email", "timeout_minutes": 0},
                    {"channel": "whatsapp", "timeout_minutes": 15},
                    {"channel": "all", "timeout_minutes": 30},
                ]
            },
            "quiet_hours": {"start": "22:00", "end": "07:00", "timezone": "Africa/Kampala"},
        }
        resp = await alert_client.post("/api/alert-rules", json=rule_data, headers=auth_headers())
        assert resp.status_code == 201, f"Create rule failed: {resp.text}"
        data = resp.json()
        assert data["name"] == rule_data["name"]
        assert data["threshold"] == 90.0
        assert data["severity"] == "high"
        assert "id" in data

    @pytest.mark.asyncio(loop_scope="module")
    async def test_list_alert_rules(self, alert_client):
        """GET /api/alert-rules returns list of rules."""
        # Create a rule first
        rule_data = {
            "name": unique("list-test"),
            "condition": "disk_usage > threshold",
            "threshold": 85.0,
            "severity": "medium",
            "recipients": ["ops@sanaa.co"],
        }
        await alert_client.post("/api/alert-rules", json=rule_data, headers=auth_headers())

        resp = await alert_client.get("/api/alert-rules", headers=auth_headers())
        assert resp.status_code == 200
        rules = resp.json()
        assert isinstance(rules, list)
        assert len(rules) >= 1

    @pytest.mark.asyncio(loop_scope="module")
    async def test_update_alert_rule(self, alert_client):
        """PUT /api/alert-rules/{id} updates a rule."""
        # Create
        create_resp = await alert_client.post("/api/alert-rules", json={
            "name": unique("update-test"),
            "condition": "mem_usage > threshold",
            "threshold": 80.0,
            "severity": "low",
            "recipients": ["dev@sanaa.co"],
        }, headers=auth_headers())
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        # Update
        resp = await alert_client.put(f"/api/alert-rules/{rule_id}", json={
            "threshold": 95.0,
            "severity": "critical",
            "recipients": ["admin@sanaa.co", "ops@sanaa.co"],
        }, headers=auth_headers())
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["threshold"] == 95.0
        assert updated["severity"] == "critical"
        assert len(updated["recipients"]) == 2

    @pytest.mark.asyncio(loop_scope="module")
    async def test_delete_alert_rule(self, alert_client):
        """DELETE /api/alert-rules/{id} removes a rule."""
        # Create
        create_resp = await alert_client.post("/api/alert-rules", json={
            "name": unique("delete-test"),
            "condition": "test_condition",
            "threshold": 50.0,
            "severity": "low",
            "recipients": ["test@sanaa.co"],
        }, headers=auth_headers())
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        # Delete
        resp = await alert_client.delete(f"/api/alert-rules/{rule_id}", headers=auth_headers())
        assert resp.status_code == 200

        # Verify gone
        get_resp = await alert_client.get(f"/api/alert-rules/{rule_id}", headers=auth_headers())
        assert get_resp.status_code == 404

    @pytest.mark.asyncio(loop_scope="module")
    async def test_get_single_alert_rule(self, alert_client):
        """GET /api/alert-rules/{id} returns a single rule."""
        create_resp = await alert_client.post("/api/alert-rules", json={
            "name": unique("single-get"),
            "condition": "api_latency > threshold",
            "threshold": 2000.0,
            "severity": "high",
            "recipients": ["eng@sanaa.co"],
        }, headers=auth_headers())
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        resp = await alert_client.get(f"/api/alert-rules/{rule_id}", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == rule_id
        assert data["condition"] == "api_latency > threshold"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_create_rule_missing_required_fields(self, alert_client):
        """POST /api/alert-rules with missing fields returns 422."""
        resp = await alert_client.post("/api/alert-rules", json={
            "name": unique("missing-fields"),
        }, headers=auth_headers())
        assert resp.status_code == 422

    @pytest.mark.asyncio(loop_scope="module")
    async def test_create_rule_auth_required(self, alert_client):
        """POST /api/alert-rules without auth returns 401."""
        resp = await alert_client.post("/api/alert-rules", json={
            "name": "no-auth-rule",
            "condition": "test",
            "threshold": 50.0,
            "severity": "low",
            "recipients": ["test@sanaa.co"],
        })
        assert resp.status_code == 401


# ==================== ALERT ROUTER TESTS ====================


class TestAlertRouter:
    """AlertRouter matches alerts to rules and routes to channels."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_router_matches_alert_to_rule(self):
        """AlertRouter should find matching rules for an alert based on condition."""
        from core.alerts.router import AlertRouter
        from core.database import AlertRule

        # Create a rule
        rule = await AlertRule.create(
            name=unique("router-match"),
            condition="cpu_usage",
            threshold=90.0,
            severity="high",
            recipients=["admin@sanaa.co"],
            enabled=True,
        )

        router = AlertRouter()
        matched = await router.find_matching_rules(metric="cpu_usage", value=95.0)
        assert len(matched) >= 1
        rule_ids = [r.id for r in matched]
        assert rule.id in rule_ids

    @pytest.mark.asyncio(loop_scope="module")
    async def test_router_ignores_disabled_rules(self):
        """AlertRouter should skip disabled rules."""
        from core.alerts.router import AlertRouter
        from core.database import AlertRule

        rule = await AlertRule.create(
            name=unique("disabled-rule"),
            condition="disabled_metric",
            threshold=50.0,
            severity="medium",
            recipients=["test@sanaa.co"],
            enabled=False,
        )

        router = AlertRouter()
        matched = await router.find_matching_rules(metric="disabled_metric", value=100.0)
        rule_ids = [r.id for r in matched]
        assert rule.id not in rule_ids

    @pytest.mark.asyncio(loop_scope="module")
    async def test_router_respects_threshold(self):
        """AlertRouter should not match when value is below threshold."""
        from core.alerts.router import AlertRouter
        from core.database import AlertRule

        rule = await AlertRule.create(
            name=unique("threshold-test"),
            condition="memory_usage",
            threshold=80.0,
            severity="high",
            recipients=["admin@sanaa.co"],
            enabled=True,
        )

        router = AlertRouter()
        # Below threshold
        matched = await router.find_matching_rules(metric="memory_usage", value=70.0)
        rule_ids = [r.id for r in matched]
        assert rule.id not in rule_ids

        # Above threshold
        matched = await router.find_matching_rules(metric="memory_usage", value=85.0)
        rule_ids = [r.id for r in matched]
        assert rule.id in rule_ids

    @pytest.mark.asyncio(loop_scope="module")
    async def test_router_routes_alert_sends_email(self):
        """AlertRouter.route_alert should send email for matched rules."""
        from core.alerts.router import AlertRouter
        from core.database import AlertRule

        rule = await AlertRule.create(
            name=unique("route-email"),
            condition="test_email_metric",
            threshold=50.0,
            severity="high",
            recipients=["test@sanaa.co"],
            enabled=True,
        )

        router = AlertRouter()
        with patch("core.alerts.email_sender.send_alert_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await router.route_alert(
                metric="test_email_metric",
                value=60.0,
                message="Test alert message",
            )
            assert result["routed"] is True
            mock_send.assert_called()


# ==================== QUIET HOURS TESTS ====================


class TestQuietHours:
    """Quiet hours suppress non-critical alerts."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_quiet_hours_suppresses_low_severity(self):
        """Non-critical alerts during quiet hours should be suppressed."""
        from core.alerts.router import AlertRouter
        from core.database import AlertRule

        rule = await AlertRule.create(
            name=unique("quiet-low"),
            condition="quiet_test_metric",
            threshold=10.0,
            severity="low",
            recipients=["test@sanaa.co"],
            quiet_hours={"start": "00:00", "end": "23:59", "timezone": "UTC"},
            enabled=True,
        )

        router = AlertRouter()
        with patch("core.alerts.email_sender.send_alert_email", new_callable=AsyncMock) as mock_send:
            result = await router.route_alert(
                metric="quiet_test_metric",
                value=20.0,
                message="Low severity during quiet hours",
            )
            # Should be suppressed because it's low severity during quiet hours
            assert result.get("suppressed_count", 0) >= 1

    @pytest.mark.asyncio(loop_scope="module")
    async def test_quiet_hours_allows_critical(self):
        """Critical alerts should always go through, even during quiet hours."""
        from core.alerts.router import AlertRouter
        from core.database import AlertRule

        rule = await AlertRule.create(
            name=unique("quiet-crit"),
            condition="quiet_critical_metric",
            threshold=10.0,
            severity="critical",
            recipients=["test@sanaa.co"],
            quiet_hours={"start": "00:00", "end": "23:59", "timezone": "UTC"},
            enabled=True,
        )

        router = AlertRouter()
        with patch("core.alerts.email_sender.send_alert_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await router.route_alert(
                metric="quiet_critical_metric",
                value=20.0,
                message="Critical alert during quiet hours",
            )
            # Critical should NOT be suppressed
            assert result["routed"] is True
            mock_send.assert_called()


# ==================== ESCALATION ENGINE TESTS ====================


class TestEscalationEngine:
    """VAL-UI-005: Alert escalation triggers after configurable timeout."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_escalation_creates_entry(self):
        """Escalation engine should create an escalation tracking entry."""
        from core.alerts.escalation import EscalationEngine

        engine = EscalationEngine()
        escalation_policy = {
            "levels": [
                {"channel": "email", "timeout_minutes": 0},
                {"channel": "whatsapp", "timeout_minutes": 15},
                {"channel": "all", "timeout_minutes": 30},
            ]
        }
        entry = await engine.start_escalation(
            alert_rule_id=1,
            message="Test escalation",
            recipients=["admin@sanaa.co"],
            policy=escalation_policy,
        )
        assert entry is not None
        assert entry["current_level"] == 0
        assert entry["channel"] == "email"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_escalation_advances_level(self):
        """After timeout, escalation should advance to next level."""
        from core.alerts.escalation import EscalationEngine

        engine = EscalationEngine()
        escalation_policy = {
            "levels": [
                {"channel": "email", "timeout_minutes": 0},
                {"channel": "whatsapp", "timeout_minutes": 15},
                {"channel": "all", "timeout_minutes": 30},
            ]
        }
        entry = await engine.start_escalation(
            alert_rule_id=2,
            message="Test advance",
            recipients=["admin@sanaa.co"],
            policy=escalation_policy,
        )

        # Simulate timeout passed by advancing
        next_level = await engine.check_and_escalate(
            entry["id"],
            force=True,  # Force escalation for testing
        )
        assert next_level is not None
        assert next_level["current_level"] == 1
        assert next_level["channel"] == "whatsapp"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_escalation_max_level(self):
        """After reaching max level, escalation should not advance further."""
        from core.alerts.escalation import EscalationEngine

        engine = EscalationEngine()
        policy = {
            "levels": [
                {"channel": "email", "timeout_minutes": 0},
            ]
        }
        entry = await engine.start_escalation(
            alert_rule_id=3,
            message="Max level test",
            recipients=["admin@sanaa.co"],
            policy=policy,
        )

        result = await engine.check_and_escalate(entry["id"], force=True)
        # Should be None or same level — can't go beyond max
        assert result is None or result["current_level"] == 0

    @pytest.mark.asyncio(loop_scope="module")
    async def test_escalation_sends_email_at_level_0(self):
        """First escalation level (email) should send email via SMTP."""
        from core.alerts.escalation import EscalationEngine

        engine = EscalationEngine()
        policy = {
            "levels": [
                {"channel": "email", "timeout_minutes": 0},
                {"channel": "whatsapp", "timeout_minutes": 15},
            ]
        }

        with patch("core.alerts.email_sender.send_alert_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            entry = await engine.start_escalation(
                alert_rule_id=4,
                message="Email escalation test",
                recipients=["admin@sanaa.co"],
                policy=policy,
            )
            mock_send.assert_called_once()


# ==================== EMAIL DELIVERY TESTS ====================


class TestEmailAlertDelivery:
    """VAL-CROSS-008: Email alerts actually delivered via SMTP."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_send_alert_email_calls_smtp(self):
        """send_alert_email should use SMTP to send emails."""
        from core.alerts.email_sender import send_alert_email

        with patch("core.alerts.email_sender.settings") as mock_settings, \
             patch("core.alerts.email_sender.smtplib.SMTP") as mock_smtp_class, \
             patch("core.database.SystemKnowledge.get_pref", new_callable=AsyncMock) as mock_pref:
            mock_settings.smtp_host = "mail.test.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@test.com"
            mock_settings.smtp_pass = "pass"
            mock_settings.smtp_from = "Sanaa AI <alert@test.com>"
            mock_pref.return_value = True

            mock_server = MagicMock()
            mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

            result = await send_alert_email(
                subject="Test Alert",
                body="Alert body content",
                recipients=["admin@sanaa.co"],
            )
            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio(loop_scope="module")
    async def test_send_alert_email_with_multiple_recipients(self):
        """Email should be sent to all specified recipients."""
        from core.alerts.email_sender import send_alert_email

        with patch("core.alerts.email_sender.settings") as mock_settings, \
             patch("core.alerts.email_sender.smtplib.SMTP") as mock_smtp_class, \
             patch("core.database.SystemKnowledge.get_pref", new_callable=AsyncMock) as mock_pref:
            mock_settings.smtp_host = "mail.test.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@test.com"
            mock_settings.smtp_pass = "pass"
            mock_settings.smtp_from = "Sanaa AI <alert@test.com>"
            mock_pref.return_value = True

            mock_server = MagicMock()
            mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

            recipients = ["admin@sanaa.co", "ops@sanaa.co", "dev@sanaa.co"]
            result = await send_alert_email(
                subject="Multi-recipient Alert",
                body="Alert for all",
                recipients=recipients,
            )
            assert result is True
            # Verify sendmail was called with all recipients
            call_args = mock_server.sendmail.call_args
            assert set(call_args[0][1]) == set(recipients)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_send_alert_email_handles_smtp_failure(self):
        """send_alert_email should return False on SMTP failure."""
        from core.alerts.email_sender import send_alert_email

        with patch("core.alerts.email_sender.settings") as mock_settings, \
             patch("core.alerts.email_sender.smtplib.SMTP") as mock_smtp_class:
            mock_settings.smtp_host = "mail.test.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@test.com"
            mock_settings.smtp_pass = "pass"
            mock_settings.smtp_from = "Sanaa AI <alert@test.com>"

            mock_smtp_class.side_effect = Exception("SMTP connection failed")

            result = await send_alert_email(
                subject="Failing Alert",
                body="This should fail",
                recipients=["admin@sanaa.co"],
            )
            assert result is False

    @pytest.mark.asyncio(loop_scope="module")
    async def test_send_alert_email_skips_when_disabled(self):
        """Email sending should respect the alert.enabled preference."""
        from core.alerts.email_sender import send_alert_email

        with patch("core.alerts.email_sender.settings") as mock_settings:
            mock_settings.smtp_host = "mail.test.com"

            with patch("core.database.SystemKnowledge.get_pref", new_callable=AsyncMock) as mock_pref:
                mock_pref.return_value = "false"
                result = await send_alert_email(
                    subject="Disabled Alert",
                    body="Should not send",
                    recipients=["admin@sanaa.co"],
                )
                assert result is False
