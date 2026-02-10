"""
Tests for RBAC (Role-Based Access Control) — Phase 6.1.

Covers: role hierarchy, permission mapping, token resolution,
require_role / require_permission factories, edge cases.
"""

import os
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Role & Permission basics
# ---------------------------------------------------------------------------


class TestRoleDefinitions:
    """Verify role constants and sets."""

    def test_four_roles_defined(self):
        from app.shared.toolkit.auth import Role

        assert Role.ADMIN == "admin"
        assert Role.ANALYST == "analyst"
        assert Role.VIEWER == "viewer"
        assert Role.GUEST == "guest"

    def test_all_set_contains_every_role(self):
        from app.shared.toolkit.auth import Role

        assert Role.ALL == {"admin", "analyst", "viewer", "guest"}

    def test_authenticated_excludes_guest(self):
        from app.shared.toolkit.auth import Role

        assert Role.GUEST not in Role.AUTHENTICATED
        assert Role.ADMIN in Role.AUTHENTICATED
        assert Role.ANALYST in Role.AUTHENTICATED
        assert Role.VIEWER in Role.AUTHENTICATED


class TestPermissionMapping:
    """Verify ROLE_PERMISSIONS mapping is consistent."""

    def test_admin_has_all_permissions(self):
        from app.shared.toolkit.auth import Permission, ROLE_PERMISSIONS, Role

        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        # Collect all permission values from Permission class
        all_perms = {v for k, v in vars(Permission).items() if not k.startswith("_") and isinstance(v, str)}
        assert admin_perms == all_perms

    def test_analyst_has_no_admin_permissions(self):
        from app.shared.toolkit.auth import ROLE_PERMISSIONS, Role

        analyst_perms = ROLE_PERMISSIONS[Role.ANALYST]
        assert "admin:cache" not in analyst_perms
        assert "admin:config" not in analyst_perms
        assert "admin:users" not in analyst_perms
        assert "admin:webhooks" not in analyst_perms

    def test_viewer_has_read_only(self):
        from app.shared.toolkit.auth import ROLE_PERMISSIONS, Role

        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        assert "analysis:read" in viewer_perms
        assert "report:read" in viewer_perms
        assert "analysis:create" not in viewer_perms
        assert "llm:invoke" not in viewer_perms

    def test_guest_minimal_access(self):
        from app.shared.toolkit.auth import ROLE_PERMISSIONS, Role

        guest_perms = ROLE_PERMISSIONS[Role.GUEST]
        assert len(guest_perms) == 2
        assert "analysis:read" in guest_perms
        assert "report:read" in guest_perms

    def test_role_has_permission_positive(self):
        from app.shared.toolkit.auth import role_has_permission

        assert role_has_permission("admin", "admin:cache") is True

    def test_role_has_permission_negative(self):
        from app.shared.toolkit.auth import role_has_permission

        assert role_has_permission("guest", "admin:cache") is False

    def test_role_has_permission_unknown_role(self):
        from app.shared.toolkit.auth import role_has_permission

        assert role_has_permission("unknown_role", "admin:cache") is False


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------


class TestTokenResolution:
    """Test get_current_role token matching."""

    def test_no_token_returns_guest(self):
        from app.shared.toolkit.auth import get_current_role

        role = get_current_role(x_auth_token=None)
        assert role == "guest"

    def test_empty_token_returns_guest(self):
        from app.shared.toolkit.auth import get_current_role

        role = get_current_role(x_auth_token="")
        assert role == "guest"

    @patch.dict(os.environ, {"ADMIN_TOKEN": "admin-secret-token-xyz"})
    def test_admin_token_match(self):
        from app.shared.toolkit.auth import get_current_role

        with patch(
            "app.shared.toolkit.auth.get_admin_token",
            return_value="admin-secret-token-xyz",
        ):
            role = get_current_role(x_auth_token="admin-secret-token-xyz")
            assert role == "admin"

    @patch.dict(os.environ, {"ANALYST_TOKEN": "analyst-tok"})
    def test_analyst_token_match(self):
        from app.shared.toolkit.auth import get_current_role

        with patch("app.shared.toolkit.auth.get_admin_token", return_value="admin-different"):
            with patch("app.shared.toolkit.auth._get_analyst_token", return_value="analyst-tok"):
                role = get_current_role(x_auth_token="analyst-tok")
                assert role == "analyst"

    @patch.dict(os.environ, {"VIEWER_TOKEN": "viewer-tok"})
    def test_viewer_token_match(self):
        from app.shared.toolkit.auth import get_current_role

        with patch("app.shared.toolkit.auth.get_admin_token", return_value="admin-different"):
            with patch(
                "app.shared.toolkit.auth._get_analyst_token",
                return_value="analyst-different",
            ):
                with patch(
                    "app.shared.toolkit.auth._get_viewer_token",
                    return_value="viewer-tok",
                ):
                    role = get_current_role(x_auth_token="viewer-tok")
                    assert role == "viewer"

    def test_unknown_token_returns_guest(self):
        from app.shared.toolkit.auth import get_current_role

        with patch("app.shared.toolkit.auth.get_admin_token", return_value="admin-tok"):
            with patch("app.shared.toolkit.auth._get_analyst_token", return_value="analyst-tok"):
                with patch(
                    "app.shared.toolkit.auth._get_viewer_token",
                    return_value="viewer-tok",
                ):
                    role = get_current_role(x_auth_token="unknown-token")
                    assert role == "guest"


# ---------------------------------------------------------------------------
# require_role / require_permission factories
# ---------------------------------------------------------------------------


class TestRequireRole:
    """Test require_role dependency factory."""

    def test_require_role_allows_matching(self):
        from app.shared.toolkit.auth import Role

        # Build the inner check function
        from app.shared.toolkit.auth import require_role

        checker = require_role(Role.ADMIN, Role.ANALYST)

        # The factory produces a function with a Depends default for role,
        # but we can call it directly with role= keyword argument.
        returned = checker(role="admin")
        assert returned == "admin"

    def test_require_role_blocks_unauthorized(self):
        from app.shared.toolkit.auth import require_role, Role
        from fastapi import HTTPException

        checker = require_role(Role.ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            checker(role="guest")
        assert exc_info.value.status_code == 403


class TestRequirePermission:
    """Test require_permission dependency factory."""

    def test_require_permission_allows_matching(self):
        from app.shared.toolkit.auth import require_permission, Permission

        checker = require_permission(Permission.ANALYSIS_CREATE)
        # admin has analysis:create
        result = checker(role="admin")
        assert result == "admin"

    def test_require_permission_blocks_unauthorized(self):
        from app.shared.toolkit.auth import require_permission, Permission
        from fastapi import HTTPException

        checker = require_permission(Permission.ADMIN_CACHE)
        with pytest.raises(HTTPException) as exc_info:
            checker(role="viewer")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Security validation
# ---------------------------------------------------------------------------


class TestSecurityValidation:
    """Test token security validation."""

    def test_missing_token_is_insecure(self):
        from app.shared.toolkit.auth import validate_admin_token_security

        with patch("app.shared.toolkit.auth.get_admin_token", return_value=""):
            is_secure, msg = validate_admin_token_security()
            assert is_secure is False
            assert "not set" in msg

    def test_weak_token_is_insecure(self):
        from app.shared.toolkit.auth import validate_admin_token_security

        with patch("app.shared.toolkit.auth.get_admin_token", return_value="admin123"):
            is_secure, msg = validate_admin_token_security()
            assert is_secure is False
            assert "weak" in msg.lower()

    def test_short_token_is_insecure(self):
        from app.shared.toolkit.auth import validate_admin_token_security

        with patch("app.shared.toolkit.auth.get_admin_token", return_value="short-but-not-weak"):
            is_secure, msg = validate_admin_token_security()
            assert is_secure is False
            assert "characters" in msg

    def test_strong_token_is_secure(self):
        from app.shared.toolkit.auth import validate_admin_token_security

        strong = "a" * 32 + "unique-suffix"
        with patch("app.shared.toolkit.auth.get_admin_token", return_value=strong):
            is_secure, msg = validate_admin_token_security()
            assert is_secure is True

    def test_generate_token_length(self):
        from app.shared.toolkit.auth import generate_token

        token = generate_token()
        assert len(token) == 32
        assert all(c in "0123456789abcdef" for c in token)
