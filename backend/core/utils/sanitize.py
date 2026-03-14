"""
Sanaa AI — Input Sanitization Utilities

Provides functions to sanitize and validate user input before it reaches
subprocess calls or other sensitive operations. Prevents shell injection
by detecting and rejecting shell metacharacters.
"""

import re
import shlex
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Shell metacharacters that indicate injection attempts
SHELL_METACHARACTERS = re.compile(r'[;|&`$(){}]|&&|\|\||\$\(')

# Patterns that indicate shell injection attempts (backticks, $(...), etc.)
INJECTION_PATTERNS = [
    r'`[^`]*`',         # backtick command substitution
    r'\$\([^)]*\)',      # $(...) command substitution
    r'\$\{[^}]*\}',     # ${...} variable expansion
    r';\s*\w',           # command chaining with ;
    r'\|\s*\w',          # piping with |
    r'&&\s*\w',         # logical AND chaining
    r'\|\|\s*\w',       # logical OR chaining
    r'>\s*/',            # output redirection to absolute path
    r'<\s*/',            # input redirection from absolute path
]

INJECTION_RE = re.compile('|'.join(INJECTION_PATTERNS))


def contains_shell_metacharacters(value: str) -> bool:
    """Check if a string contains shell metacharacters that could enable injection.

    Args:
        value: The string to check.

    Returns:
        True if dangerous metacharacters are found, False otherwise.
    """
    if not value:
        return False
    return bool(SHELL_METACHARACTERS.search(value))


def validate_shell_input(value: str, context: str = "input") -> str:
    """Validate that a string is safe for use as a shell argument.

    Raises ValueError if the input contains shell metacharacters.

    Args:
        value: The string to validate.
        context: Description of the input for error messages.

    Returns:
        The original string if safe.

    Raises:
        ValueError: If the input contains shell metacharacters.
    """
    if not value:
        return value

    if contains_shell_metacharacters(value):
        logger.warning(
            f"Shell injection attempt blocked in {context}: {value[:100]!r}"
        )
        raise ValueError(
            f"Dangerous characters detected in {context}. "
            f"Shell metacharacters (;, |, &&, backticks, $()) are not allowed."
        )
    return value


def sanitize_command_string(command: str) -> list[str]:
    """Convert a command string into a safe argument list for subprocess.

    Uses shlex.split() to properly tokenize the command, which handles
    quoting and escaping correctly. Also validates each argument for
    injection patterns.

    Args:
        command: The command string to split into arguments.

    Returns:
        List of command arguments suitable for subprocess with shell=False.

    Raises:
        ValueError: If the command contains dangerous injection patterns.
    """
    if not command:
        raise ValueError("Empty command")

    # Check for injection patterns in the raw command
    if INJECTION_RE.search(command):
        logger.warning(f"Shell injection pattern detected in command: {command[:200]!r}")
        raise ValueError(
            "Command contains shell injection patterns "
            "(;, |, &&, backticks, $()) which are not allowed."
        )

    try:
        args = shlex.split(command)
    except ValueError as e:
        raise ValueError(f"Invalid command syntax: {e}")

    if not args:
        raise ValueError("Empty command after parsing")

    return args


def sanitize_service_name(service: str) -> str:
    """Validate a systemd service name to prevent injection.

    Service names should only contain alphanumeric characters, hyphens,
    underscores, dots, and @ symbols.

    Args:
        service: The service name to validate.

    Returns:
        The validated service name.

    Raises:
        ValueError: If the service name contains invalid characters.
    """
    if not service:
        raise ValueError("Empty service name")

    if not re.match(r'^[a-zA-Z0-9._@-]+$', service):
        logger.warning(f"Invalid service name blocked: {service!r}")
        raise ValueError(
            f"Invalid service name: {service!r}. "
            f"Only alphanumeric, hyphens, underscores, dots, and @ are allowed."
        )

    return service


def sanitize_ip_address(ip: str) -> str:
    """Validate an IP address string to prevent injection.

    Args:
        ip: The IP address to validate.

    Returns:
        The validated IP address.

    Raises:
        ValueError: If the IP address format is invalid.
    """
    if not ip:
        raise ValueError("Empty IP address")

    # Simple but effective IPv4/IPv6 validation
    import ipaddress
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError(f"Invalid IP address: {ip!r}")

    return ip


def sanitize_file_path(path: str) -> str:
    """Validate a file path to prevent path traversal and injection.

    Args:
        path: The file path to validate.

    Returns:
        The validated file path.

    Raises:
        ValueError: If the path contains dangerous patterns.
    """
    if not path:
        raise ValueError("Empty file path")

    # Check for shell metacharacters
    if contains_shell_metacharacters(path):
        raise ValueError(f"File path contains dangerous characters: {path!r}")

    # Check for null bytes
    if '\x00' in path:
        raise ValueError("File path contains null bytes")

    return path


def sanitize_sql_identifier(identifier: str) -> str:
    """Validate a SQL identifier (table name, column name) to prevent injection.

    Args:
        identifier: The SQL identifier to validate.

    Returns:
        The validated identifier.

    Raises:
        ValueError: If the identifier contains invalid characters.
    """
    if not identifier:
        raise ValueError("Empty SQL identifier")

    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")

    return identifier
