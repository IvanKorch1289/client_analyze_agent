"""
Role-based access control (RBAC) with granular permissions.

Provides token-based authentication with 4 roles:
- admin: Full system access
- analyst: Analysis, reports, data, LLM operations
- viewer: Read-only access to reports and analysis results
- guest: Minimal read access (unauthenticated)

Token resolution: ADMIN_TOKEN → admin, ANALYST_TOKEN → analyst, VIEWER_TOKEN → viewer.
"""

import os
import secrets
import warnings
from typing import Optional, Set, Tuple

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
    """Get admin token from config (Vault -> ENV -> YAML)."""
    try:
        from app.config.settings import settings

        return settings.secure.admin_token or ""
    except Exception:
        return os.getenv("ADMIN_TOKEN", "")


def _get_analyst_token() -> str:
    """Get analyst token from env."""
    return os.getenv("ANALYST_TOKEN", "")


def _get_viewer_token() -> str:
    """Get viewer token from env."""
    return os.getenv("VIEWER_TOKEN", "")


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
            f"SECURITY WARNING: {message}\n"
            f"Set a strong ADMIN_TOKEN (32+ random characters) in .env\n"
            f'Generate with: python -c "import secrets; print(secrets.token_hex(32))"\n'
            f"{'=' * 60}\n",
            UserWarning,
            stacklevel=2,
        )

    _security_warning_shown = True


class Role:
    """User roles for access control.

    Hierarchy: admin > analyst > viewer > guest
    Each higher role inherits all permissions of lower roles.
    """

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"
    GUEST = "guest"

    ALL = {ADMIN, ANALYST, VIEWER, GUEST}
    AUTHENTICATED = {ADMIN, ANALYST, VIEWER}


class Permission:
    """Granular permissions for RBAC."""

    # Analysis
    ANALYSIS_CREATE = "analysis:create"
    ANALYSIS_READ = "analysis:read"
    ANALYSIS_BATCH = "analysis:batch"

    # Reports
    REPORT_READ = "report:read"
    REPORT_DELETE = "report:delete"
    REPORT_EXPORT = "report:export"

    # Data
    DATA_FETCH = "data:fetch"

    # LLM
    LLM_INVOKE = "llm:invoke"
    LLM_PROVIDERS = "llm:providers"

    # Admin
    ADMIN_CACHE = "admin:cache"
    ADMIN_CONFIG = "admin:config"
    ADMIN_USERS = "admin:users"
    ADMIN_WEBHOOKS = "admin:webhooks"

    # Audit
    AUDIT_READ = "audit:read"


# Role -> permissions mapping
ROLE_PERMISSIONS: dict[str, Set[str]] = {
    Role.ADMIN: {
        Permission.ANALYSIS_CREATE,
        Permission.ANALYSIS_READ,
        Permission.ANALYSIS_BATCH,
        Permission.REPORT_READ,
        Permission.REPORT_DELETE,
        Permission.REPORT_EXPORT,
        Permission.DATA_FETCH,
        Permission.LLM_INVOKE,
        Permission.LLM_PROVIDERS,
        Permission.ADMIN_CACHE,
        Permission.ADMIN_CONFIG,
        Permission.ADMIN_USERS,
        Permission.ADMIN_WEBHOOKS,
        Permission.AUDIT_READ,
    },
    Role.ANALYST: {
        Permission.ANALYSIS_CREATE,
        Permission.ANALYSIS_READ,
        Permission.ANALYSIS_BATCH,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
        Permission.DATA_FETCH,
        Permission.LLM_INVOKE,
        Permission.LLM_PROVIDERS,
        Permission.AUDIT_READ,
    },
    Role.VIEWER: {
        Permission.ANALYSIS_READ,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
        Permission.LLM_PROVIDERS,
    },
    Role.GUEST: {
        Permission.ANALYSIS_READ,
        Permission.REPORT_READ,
    },
}


def role_has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


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

    Token resolution order: admin -> analyst -> viewer -> guest.

    Args:
        x_auth_token: Authentication token from X-Auth-Token header.

    Returns:
        str: User role.
    """
    if not x_auth_token:
        return Role.GUEST

    token = x_auth_token.strip()

    admin_token = get_admin_token()
    if admin_token and token == admin_token.strip():
        return Role.ADMIN

    analyst_token = _get_analyst_token()
    if analyst_token and token == analyst_token.strip():
        return Role.ANALYST

    viewer_token = _get_viewer_token()
    if viewer_token and token == viewer_token.strip():
        return Role.VIEWER

    return Role.GUEST


def require_admin(role: str = Depends(get_current_role)) -> str:
    """
    Dependency that requires admin role.

    Raises:
        HTTPException: 403 if not admin.
    """
    if role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора. Укажите X-Auth-Token в заголовке.",
        )
    return role


def require_role(*allowed_roles: str):
    """
    Factory for role-based access dependencies.

    Usage:
        @router.get("/reports", dependencies=[Depends(require_role(Role.VIEWER, Role.ANALYST, Role.ADMIN))])

    Args:
        allowed_roles: One or more roles that are allowed access.
    """
    allowed = set(allowed_roles)

    def _check(role: str = Depends(get_current_role)) -> str:
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостаточно прав. Требуется роль: {', '.join(sorted(allowed))}",
            )
        return role

    return _check


def require_permission(permission: str):
    """
    Factory for permission-based access dependencies.

    Usage:
        @router.post("/analyze", dependencies=[Depends(require_permission(Permission.ANALYSIS_CREATE))])

    Args:
        permission: Required permission string.
    """

    def _check(role: str = Depends(get_current_role)) -> str:
        if not role_has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостаточно прав. Требуется разрешение: {permission}",
            )
        return role

    return _check


def is_admin(role: str) -> bool:
    """Check if role is admin."""
    return role == Role.ADMIN


__all__ = [
    "Role",
    "Permission",
    "ROLE_PERMISSIONS",
    "get_admin_token",
    "generate_token",
    "get_current_role",
    "require_admin",
    "require_role",
    "require_permission",
    "role_has_permission",
    "is_admin",
    "validate_admin_token_security",
    "check_security_on_startup",
]
