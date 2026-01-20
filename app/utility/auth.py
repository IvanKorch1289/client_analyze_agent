"""
Backward-compatible re-export of authentication utilities.

DEPRECATED: Use app.shared.toolkit.auth directly for new code.
This module exists only for backward compatibility.

SECURITY NOTE: This module now uses the secure version from toolkit
which does NOT have the dev bypass vulnerability.
"""

from app.shared.toolkit.auth import (
    Role,
    generate_token,
    get_admin_token,
    get_current_role,
    is_admin,
    require_admin,
)

__all__ = [
    "Role",
    "get_admin_token",
    "generate_token",
    "get_current_role",
    "require_admin",
    "is_admin",
]
