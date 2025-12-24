"""
Role-based access control for utility endpoints.

Provides simple token-based authentication for admin-level operations
like cache clearing and system configuration changes.
"""

import os
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, status


def get_admin_token() -> str:
    """Get admin token from environment (reads at request time)."""
    return os.getenv("ADMIN_TOKEN", "")


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
