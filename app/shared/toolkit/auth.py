"""
Role-based access control for utility endpoints.

Provides simple token-based authentication for admin-level operations
like cache clearing and system configuration changes.
"""

import os
import secrets
import warnings
from typing import Optional, Tuple

from fastapi import Depends, Header, HTTPException, status

# Weak/default tokens that should trigger warnings
_WEAK_TOKENS = {
    "",
    "your_admin_token_here",
    "your_admin_token",
    "admin",
    "admin123",
    "password",
    "token",
    "secret",
    "test",
    "changeme",
}

_security_warning_shown = False


def get_admin_token() -> str:
    """Get admin token from config (Vault → ENV → YAML)."""
    try:
        from app.config.settings import settings

        return settings.secure.admin_token or ""
    except Exception:
        return os.getenv("ADMIN_TOKEN", "")


def validate_admin_token_security() -> Tuple[bool, str]:
    """
    Validate ADMIN_TOKEN security for production use.

    Returns:
        Tuple[bool, str]: (is_secure, warning_message)

    Security checks:
    - Token must be set
    - Token must be at least 32 characters
    - Token must not be a known weak/default value
    """
    token = get_admin_token().strip()

    # Check 1: Token is set
    if not token:
        return False, "ADMIN_TOKEN is not set. Admin endpoints are unprotected!"

    # Check 2: Token is not weak/default
    if token.lower() in _WEAK_TOKENS:
        return (
            False,
            "ADMIN_TOKEN is using a weak/default value. Change it immediately!",
        )

    # Check 3: Token length (minimum 32 characters for security)
    if len(token) < 32:
        return (
            False,
            f"ADMIN_TOKEN is only {len(token)} characters. Minimum 32 recommended for production.",
        )

    return True, "ADMIN_TOKEN security check passed"


def check_security_on_startup() -> None:
    """
    Check security configuration on application startup.

    Logs warnings if ADMIN_TOKEN is weak or missing.
    Should be called once during application initialization.
    """
    global _security_warning_shown

    if _security_warning_shown:
        return

    is_secure, message = validate_admin_token_security()

    if not is_secure:
        # Use warnings module for visibility
        warnings.warn(
            f"\n{'=' * 60}\n"
            f"⚠️  SECURITY WARNING: {message}\n"
            f"Set a strong ADMIN_TOKEN (32+ random characters) in .env\n"
            f'Generate with: python -c "import secrets; print(secrets.token_hex(32))"\n'
            f"{'=' * 60}\n",
            UserWarning,
            stacklevel=2,
        )

    _security_warning_shown = True


class Role:
    """User roles for access control."""

    ADMIN = "admin"
    GUEST = "guest"


def generate_token() -> str:
    """
    Generate a secure random token.

    Returns:
        str: A 32-character hexadecimal token.
    """
    return secrets.token_hex(16)


def get_current_role(
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token"),
) -> str:
    """
    Determine user role based on authentication token.

    Args:
        x_auth_token: Authentication token from X-Auth-Token header.

    Returns:
        str: User role (admin or guest).
    """
    if not x_auth_token:
        return Role.GUEST

    admin_token = get_admin_token()
    if admin_token and x_auth_token.strip() == admin_token.strip():
        return Role.ADMIN

    return Role.GUEST


def require_admin(role: str = Depends(get_current_role)) -> str:
    """
    Dependency that requires admin role.

    Args:
        role: Current user role from get_current_role.

    Returns:
        str: The role if admin.

    Raises:
        HTTPException: 403 if not admin.
    """
    if role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора. Укажите X-Auth-Token в заголовке.",
        )
    return role


def is_admin(role: str) -> bool:
    """
    Check if role is admin.

    Args:
        role: User role string.

    Returns:
        bool: True if admin.
    """
    return role == Role.ADMIN


__all__ = [
    "Role",
    "get_admin_token",
    "generate_token",
    "get_current_role",
    "require_admin",
    "is_admin",
    "validate_admin_token_security",
    "check_security_on_startup",
]
