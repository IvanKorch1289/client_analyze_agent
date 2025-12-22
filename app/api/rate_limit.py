"""
Small helpers to standardize SlowAPI limiter creation across routers.

Wave 2 goal:
- reduce boilerplate in `app/api/routes/*`
- keep behavior the same (limits/constants/key_func) unless explicitly changed
"""

from __future__ import annotations

from collections.abc import Callable

from slowapi import Limiter

from app.utility.helpers import get_client_ip


def create_limiter(key_func: Callable) -> Limiter:
    """
    Factory for Limiter instances.

    We intentionally return a new Limiter per router module to keep behavior
    consistent with the previous code (separate in-memory storages).
    """

    return Limiter(key_func=key_func)


def limiter_for_client_ip() -> Limiter:
    return create_limiter(get_client_ip)

