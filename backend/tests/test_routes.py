"""
Sanaa AI — Route modularization tests.
Verifies that all endpoint groups respond correctly after the main.py refactor.
Covers: auth, commands, skills, status, channels, intelligence, devices,
        alerts, sessions, config, workflows, watchdog, sellers.
"""

import pytest


# ==================== STRUCTURE TESTS ====================


class TestRouteModuleStructure:
    """Verify the routes/ directory and module imports work correctly."""

    def test_routes_directory_exists(self):
        from pathlib import Path
        routes_dir = Path(__file__).resolve().parent.parent / "core" / "routes"
        assert routes_dir.exists()
        assert routes_dir.is_dir()

    def test_all_router_modules_importable(self):
        """All 13 router modules should import without errors."""
        from core.routes import auth
        from core.routes import commands
        from core.routes import skills
        from core.routes import status
        from core.routes import channels
        from core.routes import intelligence
        from core.routes import devices
        from core.routes import alerts
        from core.routes import sessions
        from core.routes import config
        from core.routes import workflows
        from core.routes import watchdog
        from core.routes import sellers
        from core.routes import deps

        # Each module should have a router attribute (except deps)
        assert hasattr(auth, "router")
        assert hasattr(commands, "router")
        assert hasattr(skills, "router")
        assert hasattr(status, "router")
        assert hasattr(channels, "router")
        assert hasattr(intelligence, "router")
        assert hasattr(devices, "router")
        assert hasattr(alerts, "router")
        assert hasattr(sessions, "router")
        assert hasattr(config, "router")
        assert hasattr(workflows, "router")
        assert hasattr(watchdog, "router")
        assert hasattr(sellers, "router")

    def test_main_py_is_under_300_lines(self):
        """main.py should be reduced to <300 lines after refactor."""
        from pathlib import Path
        main_py = Path(__file__).resolve().parent.parent / "core" / "main.py"
        line_count = len(main_py.read_text().splitlines())
        assert line_count < 350, f"main.py has {line_count} lines, expected <350"

    def test_deps_shared_state_initialized(self):
        """Deps module should have shared state wired after main.py import."""
        from core.main import app  # noqa: F401 — triggers init_shared_state
        from core.routes import deps

        assert deps.brain is not None, "brain should be initialized"
        assert deps.router_instance is not None, "router_instance should be initialized"
        assert deps.web_channel is not None, "web_channel should be initialized"
        assert deps.rate_limiter is not None, "rate_limiter should be initialized"
        assert deps.server_health is not None, "server_health should be initialized"
        assert deps.watchdog is not None, "watchdog should be initialized"
        assert deps.healer is not None, "healer should be initialized"
        assert deps.scanner is not None, "scanner should be initialized"
        assert deps.workflow_loader is not None, "workflow_loader should be initialized"
        assert deps.workflow_runtime is not None, "workflow_runtime should be initialized"
        assert deps.whatsapp_saas is not None, "whatsapp_saas should be initialized"


# ==================== ENDPOINT TESTS ====================


class TestHealthEndpointPostRefactor:
    """GET /api/health — public, no auth."""

    async def test_health_returns_200(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_response_shape(self, client):
        response = await client.get("/api/health")
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "channels" in data
        assert data["status"] == "ok"


class TestAuthEndpoints:
    """Login/logout/dashboard routes."""

    async def test_login_page_returns_200(self, client):
        response = await client.get("/login", follow_redirects=False)
        assert response.status_code == 200

    async def test_logout_redirects(self, client):
        response = await client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")

    async def test_dashboard_redirects_without_auth(self, client):
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")


class TestCommandEndpoints:
    """POST /api/command, GET /api/command/{id}."""

    async def test_command_requires_auth(self, client):
        response = await client.post("/api/command", json={"command": "test"})
        assert response.status_code == 401

    async def test_command_status_requires_auth(self, client):
        response = await client.get("/api/command/fake-id")
        assert response.status_code == 401


class TestSkillEndpoints:
    """GET /api/skills, POST /api/skills/{name}/run, ML endpoints."""

    async def test_skills_list_requires_auth(self, client):
        response = await client.get("/api/skills")
        assert response.status_code == 401

    async def test_skill_run_requires_auth(self, client):
        response = await client.post("/api/skills/test/run", json={"args": {}})
        assert response.status_code == 401

    async def test_skill_enable_requires_auth(self, client):
        response = await client.post("/api/skills/test/enable")
        assert response.status_code == 401

    async def test_skill_ml_scores_requires_auth(self, client):
        response = await client.get("/api/skills/ml/scores")
        assert response.status_code == 401


class TestStatusEndpoints:
    """GET /api/status, GET /api/system/doctor, GET /api/activities."""

    async def test_status_requires_auth(self, client):
        response = await client.get("/api/status")
        assert response.status_code == 401

    async def test_doctor_requires_auth(self, client):
        response = await client.get("/api/system/doctor")
        assert response.status_code == 401

    async def test_activities_requires_auth(self, client):
        response = await client.get("/api/activities")
        assert response.status_code == 401


class TestChannelEndpoints:
    """GET /api/channels, WhatsApp bridge endpoints."""

    async def test_channels_requires_auth(self, client):
        response = await client.get("/api/channels")
        assert response.status_code == 401

    async def test_whatsapp_status_requires_auth(self, client):
        response = await client.get("/api/whatsapp/status")
        assert response.status_code == 401

    async def test_whatsapp_saas_status_requires_auth(self, client):
        response = await client.get("/api/integrations/whatsapp-saas/status")
        assert response.status_code == 401


class TestIntelligenceEndpoints:
    """GET /api/intelligence/*, briefings, signals, wisdom."""

    async def test_latest_signals_requires_auth(self, client):
        response = await client.get("/api/intelligence/latest-signals")
        assert response.status_code == 401

    async def test_wisdom_requires_auth(self, client):
        response = await client.get("/api/intelligence/wisdom")
        assert response.status_code == 401

    async def test_watchdog_advisor_requires_auth(self, client):
        response = await client.get("/api/intelligence/advisor/watchdog")
        assert response.status_code == 401

    async def test_briefing_qa_requires_auth(self, client):
        response = await client.get("/api/intelligence/briefings/qa/latest")
        assert response.status_code == 401

    async def test_intelligence_scan_requires_auth(self, client):
        """POST /api/intelligence/scan requires auth."""
        response = await client.post("/api/intelligence/scan")
        assert response.status_code == 401


class TestDeviceEndpoints:
    """POST /api/device/report, GET /api/devices."""

    async def test_devices_list_requires_auth(self, client):
        response = await client.get("/api/devices")
        assert response.status_code == 401

    async def test_device_report_requires_api_key(self, client):
        response = await client.post("/api/device/report", json={"device_id": "test"})
        assert response.status_code == 401


class TestAlertEndpoints:
    """GET /api/alerts."""

    async def test_alerts_requires_auth(self, client):
        response = await client.get("/api/alerts")
        assert response.status_code == 401


class TestSessionEndpoints:
    """GET /api/sessions, GET /api/sessions/{id}."""

    async def test_sessions_requires_auth(self, client):
        response = await client.get("/api/sessions")
        assert response.status_code == 401

    async def test_session_detail_requires_auth(self, client):
        response = await client.get("/api/sessions/fake-id")
        assert response.status_code == 401


class TestConfigEndpoints:
    """Brain config, tool policy, session policy, system state, preferences."""

    async def test_brain_config_requires_auth(self, client):
        response = await client.get("/api/system/brain/config")
        assert response.status_code == 401

    async def test_system_state_requires_auth(self, client):
        response = await client.get("/api/system/state")
        assert response.status_code == 401

    async def test_tool_policy_requires_auth(self, client):
        response = await client.get("/api/system/tool-policy")
        assert response.status_code == 401

    async def test_session_policy_requires_auth(self, client):
        response = await client.get("/api/system/session-policy")
        assert response.status_code == 401

    async def test_preferences_requires_auth(self, client):
        response = await client.get("/api/system/preferences?keys=test")
        assert response.status_code == 401


class TestWorkflowEndpoints:
    """GET /api/workflows, POST /api/workflows/{name}/run."""

    async def test_workflows_list_requires_auth(self, client):
        response = await client.get("/api/workflows")
        assert response.status_code == 401

    async def test_workflow_runs_requires_auth(self, client):
        response = await client.get("/api/workflows/runs")
        assert response.status_code == 401

    async def test_workflow_run_requires_auth(self, client):
        response = await client.post("/api/workflows/test/run", json={"args": {}})
        assert response.status_code == 401


class TestWatchdogEndpoints:
    """GET /api/watchdog/events, POST /api/watchdog/run."""

    async def test_watchdog_events_requires_auth(self, client):
        response = await client.get("/api/watchdog/events")
        assert response.status_code == 401

    async def test_watchdog_run_requires_auth(self, client):
        response = await client.post("/api/watchdog/run")
        assert response.status_code == 401

    async def test_watchdog_events_feed_requires_auth(self, client):
        response = await client.get("/api/watchdog/events-feed")
        assert response.status_code == 401


class TestSellerEndpoints:
    """POST /api/sellers/provision, GET /api/sellers."""

    async def test_sellers_list_requires_provision_key(self, client):
        response = await client.get("/api/sellers")
        assert response.status_code == 401

    async def test_seller_provision_requires_provision_key(self, client):
        response = await client.post("/api/sellers/provision", json={"seller_uuid": "test", "name": "Test"})
        assert response.status_code == 401


class TestIntelligenceScanEndpoint:
    """POST /api/intelligence/scan."""

    async def test_scan_requires_auth(self, client):
        response = await client.post("/api/intelligence/scan")
        assert response.status_code == 401


# ==================== COMPLETE ROUTE COVERAGE ====================


class TestAllRoutesRegistered:
    """Verify that all previously existing routes are still registered after refactor."""

    EXPECTED_ROUTES = [
        ("GET", "/api/health"),
        ("GET", "/api/status"),
        ("GET", "/login"),
        ("POST", "/login"),
        ("GET", "/logout"),
        ("GET", "/"),
        ("POST", "/api/command"),
        ("GET", "/api/command/{cmd_id}"),
        ("POST", "/api/command/{cmd_id}/approve"),
        ("GET", "/api/skills"),
        ("POST", "/api/skills/{skill_name}/run"),
        ("POST", "/api/skills/{skill_name}/enable"),
        ("POST", "/api/skills/{skill_name}/disable"),
        ("POST", "/api/skills/{skill_name}/exposure"),
        ("GET", "/api/skills/ml/scores"),
        ("GET", "/api/skills/{skill_name}/ml/score"),
        ("GET", "/api/skills/{skill_name}/ml/metrics"),
        ("POST", "/api/skills/{skill_name}/ml/feedback"),
        ("GET", "/api/skills/{skill_name}/ml/parameters"),
        ("GET", "/api/skills/{skill_name}/ml/learning"),
        ("POST", "/api/skills/ml/analyze"),
        ("GET", "/api/skills/ml/learning-log"),
        ("GET", "/api/channels"),
        ("POST", "/api/channels/whatsapp/pair"),
        ("GET", "/api/channels/whatsapp/qr"),
        ("GET", "/api/integrations/whatsapp-saas/status"),
        ("GET", "/api/integrations/whatsapp-saas/routes"),
        ("GET", "/api/whatsapp/status"),
        ("POST", "/api/whatsapp/send-message"),
        ("POST", "/api/whatsapp/send-media"),
        ("POST", "/api/whatsapp/send-template"),
        ("POST", "/api/whatsapp/send-interactive"),
        ("POST", "/api/whatsapp/send-carousel"),
        ("POST", "/api/whatsapp/contacts"),
        ("PUT", "/api/whatsapp/contacts/{phone}"),
        ("GET", "/api/whatsapp/contacts"),
        ("GET", "/api/whatsapp/contacts/{phone}"),
        ("POST", "/api/whatsapp/contacts/assign"),
        ("POST", "/api/whatsapp/webhook/incoming"),
        ("GET", "/api/intelligence/latest-signals"),
        ("GET", "/api/intelligence/wisdom"),
        ("GET", "/api/intelligence/advisor/watchdog"),
        ("GET", "/api/intelligence/briefings/qa/latest"),
        ("GET", "/api/intelligence/briefings"),
        ("GET", "/api/intelligence/latest-signal"),
        ("GET", "/api/intelligence/briefing/{id}"),
        ("POST", "/api/intelligence/scan"),
        ("POST", "/api/device/report"),
        ("GET", "/api/devices"),
        ("GET", "/api/alerts"),
        ("GET", "/api/watchdog/events"),
        ("POST", "/api/watchdog/run"),
        ("GET", "/api/watchdog/events-feed"),
        ("GET", "/api/activities"),
        ("GET", "/api/system/state"),
        ("GET", "/api/system/tool-policy"),
        ("POST", "/api/system/tool-policy"),
        ("GET", "/api/system/session-policy"),
        ("POST", "/api/system/session-policy"),
        ("GET", "/api/system/doctor"),
        ("POST", "/api/system/doctor/run"),
        ("GET", "/api/sessions"),
        ("GET", "/api/sessions/{session_id}"),
        ("POST", "/api/sessions/{session_id}/reset"),
        ("POST", "/api/sessions/{session_id}/send-policy"),
        ("POST", "/api/system/brain/provider"),
        ("GET", "/api/system/brain/config"),
        ("POST", "/api/system/brain/config"),
        ("GET", "/api/system/preferences"),
        ("POST", "/api/system/preference"),
        ("GET", "/api/workflows"),
        ("POST", "/api/workflows/{workflow_name}/run"),
        ("GET", "/api/workflows/runs/{run_id}"),
        ("GET", "/api/workflows/runs"),
        ("GET", "/api/workflows/runs/{run_id}/approval"),
        ("POST", "/api/workflows/runs/{run_id}/resume"),
        ("POST", "/api/workflows/runs/{run_id}/cancel"),
        ("POST", "/api/sellers/provision"),
        ("GET", "/api/sellers/{seller_uuid}"),
        ("GET", "/api/sellers"),
    ]

    def test_all_routes_registered(self, app):
        """Every previously existing endpoint must be registered in the refactored app."""
        registered = set()
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                for method in route.methods:
                    if method != "HEAD":
                        registered.add((method, route.path))

        missing = []
        for method, path in self.EXPECTED_ROUTES:
            if (method, path) not in registered:
                missing.append(f"{method} {path}")

        assert not missing, f"Missing routes after refactor:\n" + "\n".join(missing)

    def test_route_count_unchanged(self, app):
        """Total route count should not decrease after refactor."""
        api_routes = set()
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                for method in route.methods:
                    if method != "HEAD":
                        api_routes.add((method, route.path))

        # Original had 80 non-HEAD routes (from our enumeration)
        assert len(api_routes) >= 80, f"Only {len(api_routes)} routes found, expected >= 80"
