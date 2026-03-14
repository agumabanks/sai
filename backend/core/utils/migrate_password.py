"""
Sanaa AI — Password Migration Utility
Hashes the existing admin password from settings and outputs the bcrypt hash.
Run this once to generate ADMIN_PASSWORD_HASH for the .env file.

Usage:
    /opt/antigravity/venv/bin/python3 -m core.utils.migrate_password
"""

import sys
import os
from pathlib import Path

# Ensure the backend directory is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config import get_settings
from core.utils.password import hash_password, is_bcrypt_hash


def migrate_admin_password() -> str:
    """
    Read the current admin password from settings and return a bcrypt hash.
    If ADMIN_PASSWORD_HASH is already set and valid, returns it unchanged.
    """
    settings = get_settings()

    if settings.admin_password_hash and is_bcrypt_hash(settings.admin_password_hash):
        return settings.admin_password_hash

    if not settings.admin_password or settings.admin_password == "CHANGE_THIS":
        raise ValueError("ADMIN_PASSWORD is not set or is still the default. Set it in .env first.")

    return hash_password(settings.admin_password)


def update_env_file(hashed: str) -> bool:
    """
    Append or update ADMIN_PASSWORD_HASH in the .env file.
    Returns True if the file was modified.
    """
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return False

    lines = env_path.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("ADMIN_PASSWORD_HASH="):
            lines[i] = f"ADMIN_PASSWORD_HASH={hashed}"
            found = True
            break

    if not found:
        lines.append(f"ADMIN_PASSWORD_HASH={hashed}")

    env_path.write_text("\n".join(lines) + "\n")
    return True


def main():
    """Run the password migration."""
    try:
        hashed = migrate_admin_password()
        print(f"Bcrypt hash generated: {hashed}")

        if update_env_file(hashed):
            print("✅ ADMIN_PASSWORD_HASH written to .env file.")
        else:
            print("⚠️  .env file not found. Add this to your .env manually:")
            print(f"   ADMIN_PASSWORD_HASH={hashed}")

    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
