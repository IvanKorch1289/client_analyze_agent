"""
Utility API routes (aggregator).

This module keeps the public import path (`app.api.routes.utility.utility_router`)
stable while splitting the implementation into `app.api.routes.utility_parts.*`.
"""

from fastapi import APIRouter
from slowapi import Limiter

from app.utility.helpers import get_client_ip

utility_router = APIRouter(
    prefix="/utility",
    tags=["Утилиты"],
    responses={404: {"description": "Не найдено"}},
)

# Rate limiter for admin endpoints
limiter = Limiter(key_func=get_client_ip)


# Import endpoint groups (side-effect: registers routes on utility_router)
from app.api.routes.utility_parts import asyncapi as _asyncapi  # noqa: F401
from app.api.routes.utility_parts import auth as _auth  # noqa: F401
from app.api.routes.utility_parts import cache as _cache  # noqa: F401
from app.api.routes.utility_parts import circuit_metrics as _circuit_metrics  # noqa: F401
from app.api.routes.utility_parts import config as _config  # noqa: F401
from app.api.routes.utility_parts import health as _health  # noqa: F401
from app.api.routes.utility_parts import reports as _reports  # noqa: F401
from app.api.routes.utility_parts import services as _services  # noqa: F401
from app.api.routes.utility_parts import telemetry as _telemetry  # noqa: F401


__all__ = ["utility_router"]
