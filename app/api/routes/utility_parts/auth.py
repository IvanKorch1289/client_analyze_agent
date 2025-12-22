from __future__ import annotations

from typing import Any, Dict

from app.api.routes.utility import utility_router
from app.utility.auth import Role, get_current_role
from fastapi import Depends


@utility_router.get("/auth/role")
async def get_auth_role(role: str = Depends(get_current_role)) -> Dict[str, Any]:
    """
    Get current authentication role.
    """
    return {
        "role": role,
        "is_admin": role == Role.ADMIN,
    }

