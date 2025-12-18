"""
Hot-reload of YAML-based settings without restarting the app.

Important constraint:
- Many modules import singleton settings objects. To ensure updates propagate,
  we refresh those singleton objects *in place* (mutate existing instances),
  rather than replacing references.
"""

from __future__ import annotations

import threading
from typing import Iterable, Tuple, Type

from pydantic_settings import BaseSettings

from app.config.config_loader import ConfigLoader
from app.utility.logging_client import logger


_reload_lock = threading.Lock()


def _iter_singleton_settings_instances() -> Iterable[Tuple[str, BaseSettings]]:
    # Only refresh cached singleton settings objects (created via get_instance()).
    for key, value in list(ConfigLoader._cache.items()):  # noqa: SLF001
        if isinstance(key, str) and key.startswith("settings:") and isinstance(value, BaseSettings):
            yield key, value


def _refresh_settings_in_place(instance: BaseSettings) -> None:
    cls: Type[BaseSettings] = instance.__class__
    fresh = cls()  # reload from YAML/Vault/Env via BaseSettingsWithLoader __init__
    # Update only model fields (avoid internal attributes).
    for name in fresh.model_fields:
        try:
            setattr(instance, name, getattr(fresh, name))
        except Exception:
            # Don't break reload on a single field; best-effort.
            continue


def reload_settings(reason: str = "config_change") -> None:
    """
    Reload YAML/Vault caches and refresh singleton settings objects in place.
    """
    with _reload_lock:
        logger.structured("info", "settings_reload_start", component="config", reason=reason)
        # Clear cached YAML/Vault dicts but keep in-memory singleton instances alive.
        # (We don't clear the whole cache because it also stores those instances.)
        keys_to_delete = [
            k
            for k in list(ConfigLoader._cache.keys())  # noqa: SLF001
            if isinstance(k, str) and (k.startswith("yaml:") or k.startswith("vault:"))
        ]
        for k in keys_to_delete:
            try:
                del ConfigLoader._cache[k]  # noqa: SLF001
            except Exception:
                continue

        refreshed = 0
        for key, inst in _iter_singleton_settings_instances():
            try:
                _refresh_settings_in_place(inst)
                refreshed += 1
            except Exception as e:
                logger.structured(
                    "warning",
                    "settings_reload_failed",
                    component="config",
                    cache_key=key,
                    error=str(e),
                )

        logger.structured(
            "info",
            "settings_reload_complete",
            component="config",
            refreshed_instances=refreshed,
        )

