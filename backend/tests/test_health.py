"""
Tests for the GET /api/health endpoint.
Verifies the public health check returns correct status and metadata.
"""

import pytest


class TestHealthEndpoint:
    """Tests for the /api/health endpoint."""

    async def test_health_returns_200(self, client):
        """GET /api/health should return HTTP 200."""
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_returns_status_ok(self, client):
        """GET /api/health should return {status: 'ok'}."""
        response = await client.get("/api/health")
        data = response.json()
        assert data["status"] == "ok"

    async def test_health_contains_service_name(self, client):
        """GET /api/health should include the service name."""
        response = await client.get("/api/health")
        data = response.json()
        assert "service" in data
        assert isinstance(data["service"], str)
        assert len(data["service"]) > 0

    async def test_health_contains_version(self, client):
        """GET /api/health should include a version string."""
        response = await client.get("/api/health")
        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    async def test_health_contains_channels(self, client):
        """GET /api/health should include a channels list."""
        response = await client.get("/api/health")
        data = response.json()
        assert "channels" in data
        assert isinstance(data["channels"], list)
