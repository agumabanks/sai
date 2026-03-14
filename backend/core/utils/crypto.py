"""
Sanaa AI — Encryption Utilities for Sensitive Data at Rest

Provides Fernet symmetric encryption for API keys and other secrets stored
in the system_knowledge database table. The encryption key is derived from
the application's APP_SECRET using PBKDF2-HMAC-SHA256.

Usage:
    from core.utils.crypto import encrypt_value, decrypt_value, maybe_decrypt

    # Encrypt before storing
    encrypted = encrypt_value("sk-ant-api03-...")

    # Decrypt after retrieval
    plaintext = decrypt_value(encrypted)

    # Safe decrypt that handles both encrypted and plaintext values
    value = maybe_decrypt(some_db_value)
"""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Prefix added to encrypted values so we can distinguish them from plaintext
ENCRYPTED_PREFIX = "enc:v1:"

# Salt for key derivation — fixed per installation (changing it invalidates all encrypted data)
_KDF_SALT = b"sanaa-ai-crypto-v1"

# Cached Fernet instance (derived once per process from app_secret)
_fernet_instance: Optional[Fernet] = None


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length app secret.

    Uses PBKDF2-HMAC-SHA256 with a fixed salt. The result is URL-safe
    base64 encoded as required by Fernet.

    Args:
        secret: The application secret string.

    Returns:
        A 44-byte URL-safe base64-encoded key suitable for Fernet.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_KDF_SALT,
        iterations=480_000,
    )
    raw_key = kdf.derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


def _get_fernet() -> Fernet:
    """Get or create the cached Fernet instance using the app secret.

    Returns:
        A Fernet instance keyed to the app's secret.
    """
    global _fernet_instance
    if _fernet_instance is None:
        from core.config import get_settings
        settings = get_settings()
        key = _derive_fernet_key(settings.app_secret)
        _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string value using Fernet.

    The result is prefixed with ENCRYPTED_PREFIX so it can be identified
    as encrypted when read back from the database.

    Args:
        plaintext: The value to encrypt.

    Returns:
        A string in the format "enc:v1:<base64-fernet-token>".
    """
    f = _get_fernet()
    token = f.encrypt(plaintext.encode("utf-8"))
    return ENCRYPTED_PREFIX + token.decode("ascii")


def decrypt_value(encrypted: str) -> str:
    """Decrypt a value that was encrypted with encrypt_value().

    Args:
        encrypted: The encrypted string (with or without the prefix).

    Returns:
        The original plaintext value.

    Raises:
        cryptography.fernet.InvalidToken: If the token is invalid or corrupted.
        ValueError: If the value format is unexpected.
    """
    f = _get_fernet()

    # Strip the prefix if present
    if encrypted.startswith(ENCRYPTED_PREFIX):
        token_str = encrypted[len(ENCRYPTED_PREFIX):]
    else:
        token_str = encrypted

    plaintext_bytes = f.decrypt(token_str.encode("ascii"))
    return plaintext_bytes.decode("utf-8")


def is_encrypted(value: Optional[str]) -> bool:
    """Check if a value appears to be encrypted (has our prefix).

    Args:
        value: The value to check.

    Returns:
        True if the value starts with the encrypted prefix.
    """
    if not value:
        return False
    return value.startswith(ENCRYPTED_PREFIX)


def maybe_decrypt(value: Optional[str]) -> Optional[str]:
    """Decrypt if encrypted, otherwise return as-is.

    This is the safe way to read values that might be either encrypted
    (post-migration) or plaintext (pre-migration).

    Args:
        value: A potentially encrypted value, or None.

    Returns:
        The decrypted value, or the original value if not encrypted, or None.
    """
    if value is None:
        return None
    if not value:
        return value
    if is_encrypted(value):
        try:
            return decrypt_value(value)
        except Exception as e:
            logger.error(f"Failed to decrypt value: {e}")
            # Return the raw value rather than crash — allows graceful degradation
            return value
    return value


def is_sensitive_key(key: str) -> bool:
    """Determine if a system_knowledge key holds a sensitive value that should be encrypted.

    Currently matches keys that store API keys for LLM providers.

    Args:
        key: The system_knowledge key name.

    Returns:
        True if the value for this key should be encrypted.
    """
    sensitive_patterns = (
        "brain.api_key.",
        "smtp_pass",
        "imap_pass",
    )
    return any(key.startswith(pattern) or key == pattern.rstrip(".")
               for pattern in sensitive_patterns)
