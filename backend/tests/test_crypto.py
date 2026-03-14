"""
Sanaa AI — Tests for API Key Encryption (core/utils/crypto.py)

Tests encrypt/decrypt round-trip, key derivation from app secret,
migration of plaintext keys, and edge cases.
"""

import os
import sys
from pathlib import Path

# Ensure backend dir on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest


# ==================== Unit Tests for crypto functions ====================


class TestEncryptDecrypt:
    """Test encrypt_value and decrypt_value round-trip."""

    def test_encrypt_returns_string(self):
        from core.utils.crypto import encrypt_value
        result = encrypt_value("sk-test-key-123456")
        assert isinstance(result, str)

    def test_encrypted_value_differs_from_plaintext(self):
        from core.utils.crypto import encrypt_value
        plaintext = "sk-ant-api03-secret-key-here"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext

    def test_decrypt_returns_original(self):
        from core.utils.crypto import encrypt_value, decrypt_value
        plaintext = "gsk_test_groq_api_key_1234567890"
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_round_trip_with_special_characters(self):
        from core.utils.crypto import encrypt_value, decrypt_value
        plaintext = "key-with/special+chars=and==padding"
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_round_trip_with_empty_string(self):
        from core.utils.crypto import encrypt_value, decrypt_value
        encrypted = encrypt_value("")
        decrypted = decrypt_value(encrypted)
        assert decrypted == ""

    def test_round_trip_with_unicode(self):
        from core.utils.crypto import encrypt_value, decrypt_value
        plaintext = "api-key-日本語-🔑"
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_encrypt_same_value_produces_different_ciphertext(self):
        """Fernet tokens include timestamp, so same plaintext yields different ciphertext."""
        from core.utils.crypto import encrypt_value
        plaintext = "sk-test-key-repeat"
        enc1 = encrypt_value(plaintext)
        enc2 = encrypt_value(plaintext)
        # They should decrypt to the same value but be different ciphertext tokens
        assert enc1 != enc2

    def test_decrypt_invalid_token_raises(self):
        from core.utils.crypto import decrypt_value
        with pytest.raises(Exception):
            decrypt_value("not-a-valid-fernet-token")

    def test_encrypted_value_has_prefix(self):
        """Encrypted values should have a recognizable prefix to distinguish from plaintext."""
        from core.utils.crypto import encrypt_value, ENCRYPTED_PREFIX
        encrypted = encrypt_value("test-key")
        assert encrypted.startswith(ENCRYPTED_PREFIX)


class TestIsEncrypted:
    """Test the is_encrypted helper."""

    def test_encrypted_value_detected(self):
        from core.utils.crypto import encrypt_value, is_encrypted
        encrypted = encrypt_value("test-key")
        assert is_encrypted(encrypted) is True

    def test_plaintext_value_not_detected(self):
        from core.utils.crypto import is_encrypted
        assert is_encrypted("sk-ant-api03-plaintext-key") is False

    def test_empty_string_not_detected(self):
        from core.utils.crypto import is_encrypted
        assert is_encrypted("") is False

    def test_none_not_detected(self):
        from core.utils.crypto import is_encrypted
        assert is_encrypted(None) is False


class TestKeyDerivation:
    """Test that encryption key is derived from app secret."""

    def test_derive_key_returns_bytes(self):
        from core.utils.crypto import _derive_fernet_key
        key = _derive_fernet_key("my-app-secret")
        assert isinstance(key, bytes)

    def test_derive_key_is_deterministic(self):
        from core.utils.crypto import _derive_fernet_key
        key1 = _derive_fernet_key("my-app-secret")
        key2 = _derive_fernet_key("my-app-secret")
        assert key1 == key2

    def test_different_secrets_produce_different_keys(self):
        from core.utils.crypto import _derive_fernet_key
        key1 = _derive_fernet_key("secret-one")
        key2 = _derive_fernet_key("secret-two")
        assert key1 != key2

    def test_derive_key_is_valid_fernet_key(self):
        from core.utils.crypto import _derive_fernet_key
        from cryptography.fernet import Fernet
        key = _derive_fernet_key("test-secret")
        # Should not raise - valid Fernet key is 32 url-safe base64-encoded bytes
        f = Fernet(key)
        assert f is not None


class TestMaybeDecrypt:
    """Test the maybe_decrypt helper that handles both encrypted and plaintext values."""

    def test_decrypts_encrypted_value(self):
        from core.utils.crypto import encrypt_value, maybe_decrypt
        plaintext = "sk-test-key"
        encrypted = encrypt_value(plaintext)
        result = maybe_decrypt(encrypted)
        assert result == plaintext

    def test_returns_plaintext_as_is(self):
        from core.utils.crypto import maybe_decrypt
        plaintext = "sk-ant-api03-plaintext"
        result = maybe_decrypt(plaintext)
        assert result == plaintext

    def test_returns_empty_string_as_is(self):
        from core.utils.crypto import maybe_decrypt
        assert maybe_decrypt("") == ""

    def test_returns_none_as_none(self):
        from core.utils.crypto import maybe_decrypt
        assert maybe_decrypt(None) is None


class TestApiKeyDetection:
    """Test detection of API key patterns that should be encrypted."""

    def test_anthropic_key_detected(self):
        from core.utils.crypto import is_sensitive_key
        assert is_sensitive_key("brain.api_key.anthropic") is True

    def test_groq_key_detected(self):
        from core.utils.crypto import is_sensitive_key
        assert is_sensitive_key("brain.api_key.groq") is True

    def test_openrouter_key_detected(self):
        from core.utils.crypto import is_sensitive_key
        assert is_sensitive_key("brain.api_key.openrouter") is True

    def test_non_api_key_not_detected(self):
        from core.utils.crypto import is_sensitive_key
        assert is_sensitive_key("brain.provider") is False

    def test_model_setting_not_detected(self):
        from core.utils.crypto import is_sensitive_key
        assert is_sensitive_key("brain.model.groq") is False
