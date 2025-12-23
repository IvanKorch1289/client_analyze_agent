"""
File watcher for hot config reloads.

Uses watchdog (inotify on Linux) to watch the config directory and trigger
settings reload without restarting the server.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Event
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config.reload import reload_settings
from app.utility.logging_client import logger


class _ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, *, debounce_seconds: float = 0.5):
        super().__init__()
        self._debounce_seconds = debounce_seconds
        self._last_ts = 0.0

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = (event.src_path or "").lower()
        if not src.endswith((".yaml", ".yml", ".env")):
            return

        now = time.time()
        if now - self._last_ts < self._debounce_seconds:
            return
        self._last_ts = now

        logger.structured(
            "info",
            "config_file_changed",
            component="config",
            event_type=getattr(event, "event_type", "unknown"),
            path=event.src_path,
        )
        reload_settings(reason="watchdog")


class ConfigWatchdog:
    def __init__(self, path: str | Path, *, enabled: bool = True):
        self._path = Path(path)
        self._enabled = enabled
        self._observer: Optional[Observer] = None
        self._stop_event = Event()

    def start(self) -> None:
        if not self._enabled:
            logger.structured("info", "config_watchdog_disabled", component="config")
            return

        if not self._path.exists():
            logger.structured(
                "warning",
                "config_watchdog_path_missing",
                component="config",
                path=str(self._path),
            )
            return

        handler = _ConfigChangeHandler()
        observer = Observer()
        observer.schedule(handler, str(self._path), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer

        logger.structured(
            "info",
            "config_watchdog_started",
            component="config",
            path=str(self._path),
        )

    def stop(self) -> None:
        obs = self._observer
        if not obs:
            return
        try:
            obs.stop()
            obs.join(timeout=2.0)
        except Exception:
            pass
        logger.structured("info", "config_watchdog_stopped", component="config")


def create_config_watchdog() -> ConfigWatchdog:
    enabled = (os.getenv("CONFIG_WATCHDOG_ENABLED") or "").strip().lower()
    if enabled == "":
        # Default: enabled when reload is enabled in dev workflows.
        enabled_bool = True
    else:
        enabled_bool = enabled in ("1", "true", "yes", "y", "on")
    return ConfigWatchdog(Path("config"), enabled=enabled_bool)
