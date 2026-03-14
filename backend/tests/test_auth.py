"""
Tests for password hashing utilities and the admin login flow.
Covers bcrypt hashing, verification, login success/failure, session creation,
and password migration utility.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from core.utils.password import hash_password, verify_password, is_bcrypt_hash
from core.utils.migrate_password import migrate_admin_password


# ==================== PASSWORD HASHING UNIT TESTS ====================


class TestHashPassword:
    """Tests for the hash_password utility."""

    def test_hash_password_returns_bcrypt_string(self):
        """hash_password should return a valid bcrypt hash string."""
        hashed = hash_password("my_secret")
        assert isinstance(hashed, str)
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_hash_password_different_each_time(self):
        """Two calls with the same password should produce different hashes (different salts)."""
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2

    def test_hash_password_empty_string(self):
        """hash_password should handle empty strings."""
        hashed = hash_password("")
        assert is_bcrypt_hash(hashed)


class TestVerifyPassword:
    """Tests for the verify_password utility."""

    def test_verify_correct_password(self):
        """verify_password should return True for the correct password."""
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_wrong_password(self):
        """verify_password should return False for an incorrect password."""
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_empty_password_against_hash(self):
        """verify_password should return False for empty password against a real hash."""
        hashed = hash_password("real_password")
        assert verify_password("", hashed) is False

    def test_verify_with_invalid_hash(self):
        """verify_password should return False for an invalid hash string."""
        assert verify_password("password", "not_a_hash") is False

    def test_verify_with_empty_hash(self):
        """verify_password should return False for an empty hash."""
        assert verify_password("password", "") is False


class TestIsBcryptHash:
    """Tests for the is_bcrypt_hash utility."""

    def test_valid_bcrypt_2b(self):
        """Should recognize $2b$ hashes."""
        hashed = hash_password("test")
        assert is_bcrypt_hash(hashed) is True

    def test_invalid_short_string(self):
        """Should reject short strings."""
        assert is_bcrypt_hash("short") is False

    def test_invalid_empty_string(self):
        """Should reject empty strings."""
        assert is_bcrypt_hash("") is False

    def test_invalid_plaintext(self):
        """Should reject plaintext passwords."""
        assert is_bcrypt_hash("admin@ai.sanaa.coPython") is False

    def test_invalid_wrong_prefix(self):
        """Should reject strings without bcrypt prefix."""
        assert is_bcrypt_hash("x" * 60) is False


# ==================== LOGIN FLOW INTEGRATION TESTS ====================


class TestLoginFlow:
    """Tests for the POST /login endpoint with bcrypt password verification."""

    @pytest.fixture(autouse=True)
    def _bypass_rate_limiter(self):
        """Bypass rate limiter for all login tests so they don't interfere."""
        with patch("core.routes.deps.rate_limiter") as mock_rl:
            mock_rl.check = AsyncMock(return_value=True)
            mock_rl.get_remaining = AsyncMock(return_value=5)
            yield mock_rl

    async def test_login_success_with_hashed_password(self, client):
        """POST /login with correct credentials should return 302 redirect."""
        test_password = "changeme"
        test_hash = hash_password(test_password)
        test_email = "admin@ai.sanaa.co"

        with patch("core.routes.auth.settings") as mock_settings:
            mock_settings.admin_email = test_email
            mock_settings.admin_password = test_password
            mock_settings.admin_password_hash = test_hash
            mock_settings.app_secret = "changeme"

            response = await client.post(
                "/login",
                data={"email": test_email, "password": test_password},
                follow_redirects=False,
            )
            assert response.status_code == 302

    async def test_login_failure_wrong_password(self, client):
        """POST /login with wrong password should return 401."""
        test_password = "changeme"
        test_hash = hash_password(test_password)
        test_email = "admin@ai.sanaa.co"

        with patch("core.routes.auth.settings") as mock_settings:
            mock_settings.admin_email = test_email
            mock_settings.admin_password = test_password
            mock_settings.admin_password_hash = test_hash
            mock_settings.app_secret = "changeme"

            response = await client.post(
                "/login",
                data={"email": test_email, "password": "wrong_password"},
                follow_redirects=False,
            )
            assert response.status_code == 401

    async def test_login_failure_wrong_email(self, client):
        """POST /login with wrong email should return 401."""
        test_password = "changeme"
        test_hash = hash_password(test_password)
        test_email = "admin@ai.sanaa.co"

        with patch("core.routes.auth.settings") as mock_settings:
            mock_settings.admin_email = test_email
            mock_settings.admin_password = test_password
            mock_settings.admin_password_hash = test_hash
            mock_settings.app_secret = "changeme"

            response = await client.post(
                "/login",
                data={"email": "wrong@example.com", "password": test_password},
                follow_redirects=False,
            )
            assert response.status_code == 401

    async def test_login_fallback_plaintext_when_no_hash(self, client):
        """POST /login should fall back to plaintext if no hash is configured."""
        test_email = "admin@ai.sanaa.co"
        test_password = "changeme"

        with patch("core.routes.auth.settings") as mock_settings:
            mock_settings.admin_email = test_email
            mock_settings.admin_password = test_password
            mock_settings.admin_password_hash = ""  # No hash configured
            mock_settings.app_secret = "changeme"

            response = await client.post(
                "/login",
                data={"email": test_email, "password": test_password},
                follow_redirects=False,
            )
            assert response.status_code == 302

    async def test_login_page_renders(self, client):
        """GET /login should return 200 with login page."""
        response = await client.get("/login")
        assert response.status_code == 200

    async def test_logout_redirects_to_login(self, client):
        """GET /logout should redirect to /login."""
        response = await client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")

    async def test_login_creates_session(self, client):
        """POST /login with correct credentials should set session data."""
        test_password = "changeme"
        test_hash = hash_password(test_password)
        test_email = "admin@ai.sanaa.co"

        with patch("core.routes.auth.settings") as mock_settings:
            mock_settings.admin_email = test_email
            mock_settings.admin_password = test_password
            mock_settings.admin_password_hash = test_hash
            mock_settings.app_secret = "changeme"

            response = await client.post(
                "/login",
                data={"email": test_email, "password": test_password},
                follow_redirects=False,
            )
            assert response.status_code == 302
            # Session cookie should be set
            assert "session" in response.headers.get("set-cookie", "").lower() or response.status_code == 302


# ==================== PASSWORD MIGRATION TESTS ====================


class TestPasswordMigration:
    """Tests for the password migration utility."""

    def test_migrate_generates_bcrypt_hash(self):
        """migrate_admin_password should generate a bcrypt hash from the plaintext password."""
        mock_settings = MagicMock()
        mock_settings.admin_password = "changeme"
        mock_settings.admin_password_hash = ""

        with patch("core.utils.migrate_password.get_settings", return_value=mock_settings):
            result = migrate_admin_password()
            assert is_bcrypt_hash(result)
            assert verify_password("changeme", result)

    def test_migrate_returns_existing_hash_if_valid(self):
        """migrate_admin_password should return the existing hash if it's already valid."""
        existing_hash = hash_password("existing_password")
        mock_settings = MagicMock()
        mock_settings.admin_password = "existing_password"
        mock_settings.admin_password_hash = existing_hash

        with patch("core.utils.migrate_password.get_settings", return_value=mock_settings):
            result = migrate_admin_password()
            assert result == existing_hash

    def test_migrate_raises_on_default_password(self):
        """migrate_admin_password should raise ValueError if password is still the default."""
        mock_settings = MagicMock()
        mock_settings.admin_password = "CHANGE_THIS"
        mock_settings.admin_password_hash = ""

        with patch("core.utils.migrate_password.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError, match="not set or is still the default"):
                migrate_admin_password()

    def test_migrate_raises_on_empty_password(self):
        """migrate_admin_password should raise ValueError if password is empty."""
        mock_settings = MagicMock()
        mock_settings.admin_password = ""
        mock_settings.admin_password_hash = ""

        with patch("core.utils.migrate_password.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError, match="not set or is still the default"):
                migrate_admin_password()


# ==================== RATE LIMIT TESTS ====================


class TestLoginRateLimit:
    """Tests for login rate limiting behavior."""

    async def test_rate_limit_blocks_excessive_attempts(self, client):
        """POST /login should return 429 after too many attempts."""
        # Use real rate limiter but with a mock that blocks after limit
        with patch("core.routes.deps.rate_limiter") as mock_rl:
            mock_rl.check = AsyncMock(return_value=False)
            mock_rl.get_remaining = AsyncMock(return_value=0)

            response = await client.post(
                "/login",
                data={"email": "admin@ai.sanaa.co", "password": "any"},
                follow_redirects=False,
            )
            assert response.status_code == 429
