"""
Sanaa AI — Password Hashing Utilities
Provides bcrypt-based password hashing and verification for admin authentication.
"""

import bcrypt


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using bcrypt.
    Returns the hashed password as a UTF-8 string.
    """
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.
    Returns True if the password matches, False otherwise.
    """
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except (ValueError, TypeError):
        return False


def is_bcrypt_hash(value: str) -> bool:
    """
    Check whether a string looks like a bcrypt hash.
    Bcrypt hashes start with $2b$, $2a$, or $2y$ and are 60 characters long.
    """
    if not value or len(value) != 60:
        return False
    return value.startswith(("$2b$", "$2a$", "$2y$"))
