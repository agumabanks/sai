"""
Sanaa AI — Test Configuration
Provides pytest fixtures for async testing, FastAPI TestClient, and database sessions.
"""

import sys
import os
from pathlib import Path

# ==================== SYS.PATH CONFIGURATION ====================
# Ensure the backend directory is on sys.path so `core.*` imports work.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Set test environment variables before any app imports
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("APP_DEBUG", "true")

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# ==================== FASTAPI APP ====================

@pytest.fixture(scope="session")
def app():
    """Provide the FastAPI application instance."""
    from core.main import app as fastapi_app
    return fastapi_app


# ==================== ASYNC HTTP CLIENT ====================

@pytest.fixture
async def client(app):
    """
    Provide an async HTTP client for testing FastAPI endpoints.
    Uses httpx.AsyncClient with ASGITransport for in-process testing.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ==================== DATABASE SESSION ====================

@pytest.fixture
async def db_session():
    """
    Provide an async database session for tests.
    Uses the same database as the application (configured via settings).
    Each test gets its own session that is rolled back after the test.
    """
    from core.config import get_settings
    from core.database import Base

    settings = get_settings()
    test_engine = create_async_engine(settings.database_url_async, echo=False)
    TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with TestSession() as session:
        async with session.begin():
            yield session
            await session.rollback()

    await test_engine.dispose()
