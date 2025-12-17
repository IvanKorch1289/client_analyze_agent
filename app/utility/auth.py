"""
Role-based access control for utility endpoints.

Provides simple token-based authentication for admin-level operations
like cache clearing and system configuration changes.
"""

import os
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
VIEWER_TOKEN = os.getenv("VIEWER_TOKEN", "")


class Role:
    """User roles for access control."""
    ADMIN = "admin"
    VIEWER = "viewer"
    GUEST = "guest"


def generate_token() -> str:
    """
    Generate a secure random token.
    
    Returns:
        str: A 32-character hexadecimal token.
    """
    return secrets.token_hex(16)


def get_current_role(x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token")) -> str:
    """
    Determine user role based on authentication token.
    
    Args:
        x_auth_token: Authentication token from X-Auth-Token header.
        
    Returns:
        str: User role (admin, viewer, or guest).
    """
    if not x_auth_token:
        return Role.GUEST
    
    if ADMIN_TOKEN and x_auth_token == ADMIN_TOKEN:
        return Role.ADMIN
    
    if VIEWER_TOKEN and x_auth_token == VIEWER_TOKEN:
        return Role.VIEWER
    
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
            detail="Требуются права администратора. Укажите X-Auth-Token в заголовке."
        )
    return role


def require_viewer_or_admin(role: str = Depends(get_current_role)) -> str:
    """
    Dependency that requires viewer or admin role.
    
    Args:
        role: Current user role from get_current_role.
        
    Returns:
        str: The role if viewer or admin.
        
    Raises:
        HTTPException: 403 if guest.
    """
    if role == Role.GUEST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуется авторизация. Укажите X-Auth-Token в заголовке."
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


def is_authorized(role: str) -> bool:
    """
    Check if role has any authorization.
    
    Args:
        role: User role string.
        
    Returns:
        bool: True if admin or viewer.
    """
    return role in (Role.ADMIN, Role.VIEWER)
