"""
Memory Monitor - защита от утечек памяти.

Отслеживает использование памяти процессом и выполняет защитные действия:
- Логирование предупреждений при высоком использовании
- Принудительный garbage collection при превышении порогов
- Graceful degradation вместо crash
"""

from __future__ import annotations

import gc
import os
import time
from dataclasses import dataclass
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None

from app.shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryStats:
    """Статистика использования памяти."""

    rss_mb: float  # Resident Set Size (физическая память)
    vms_mb: float  # Virtual Memory Size
    percent: float  # Процент использования
    timestamp: float  # Unix timestamp


@dataclass
class MemoryLimits:
    """Пороговые значения использования памяти."""

    warning_mb: float = 512.0  # Предупреждение при >512 MB
    critical_mb: float = 1024.0  # Критично при >1 GB
    max_percent: float = 80.0  # Максимум 80% от системной памяти


class MemoryMonitor:
    """
    Монитор памяти с защитой от утечек.

    Usage:
        monitor = MemoryMonitor(check_interval=60)
        await monitor.start()

        # В middleware или background task
        await monitor.check_and_protect()
    """

    def __init__(
        self,
        *,
        check_interval: int = 60,
        limits: Optional[MemoryLimits] = None,
        auto_gc: bool = True,
    ):
        """
        Args:
            check_interval: Интервал проверки в секундах (default: 60)
            limits: Пороговые значения (default: MemoryLimits())
            auto_gc: Автоматический garbage collection (default: True)
        """
        self.check_interval = check_interval
        self.limits = limits or MemoryLimits()
        self.auto_gc = auto_gc

        self._last_check: float = 0
        self._last_gc: float = 0
        self._gc_cooldown: int = 30  # Минимум 30 секунд между GC

        self._process: Optional[psutil.Process] = None
        self._enabled = psutil is not None

        if not self._enabled:
            logger.warning(
                "Memory Monitor disabled: psutil not installed",
                component="memory_monitor",
            )

    def _get_process(self) -> Optional[psutil.Process]:
        """Получить psutil.Process для текущего процесса."""
        if not self._enabled:
            return None

        if self._process is None:
            try:
                self._process = psutil.Process(os.getpid())
            except Exception as e:
                logger.error(
                    f"Failed to initialize psutil.Process: {e}",
                    component="memory_monitor",
                    exc_info=True,
                )
                self._enabled = False
                return None

        return self._process

    def get_memory_stats(self) -> Optional[MemoryStats]:
        """
        Получить текущую статистику памяти.

        Returns:
            MemoryStats или None если psutil недоступен
        """
        process = self._get_process()
        if not process:
            return None

        try:
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()

            return MemoryStats(
                rss_mb=memory_info.rss / 1024 / 1024,
                vms_mb=memory_info.vms / 1024 / 1024,
                percent=memory_percent,
                timestamp=time.time(),
            )
        except Exception as e:
            logger.error(
                f"Failed to get memory stats: {e}",
                component="memory_monitor",
                exc_info=True,
            )
            return None

    def _should_check(self) -> bool:
        """Проверка нужна ли проверка (throttling)."""
        now = time.time()
        if now - self._last_check >= self.check_interval:
            self._last_check = now
            return True
        return False

    def _should_run_gc(self) -> bool:
        """Можно ли запустить GC (cooldown)."""
        now = time.time()
        return now - self._last_gc >= self._gc_cooldown

    def _run_gc(self) -> None:
        """Принудительный garbage collection."""
        if not self.auto_gc:
            return

        if not self._should_run_gc():
            logger.debug("GC cooldown active, skipping", component="memory_monitor")
            return

        try:
            gc_start = time.time()
            collected = gc.collect()
            gc_duration = (time.time() - gc_start) * 1000

            self._last_gc = time.time()

            logger.info(
                f"Manual GC completed: {collected} objects collected in {gc_duration:.1f}ms",
                component="memory_monitor",
            )
        except Exception as e:
            logger.error(f"GC failed: {e}", component="memory_monitor", exc_info=True)

    async def check_and_protect(self) -> Optional[MemoryStats]:
        """
        Проверить память и выполнить защитные действия.

        Returns:
            MemoryStats если проверка выполнена, None если пропущена (throttling)
        """
        if not self._enabled:
            return None

        if not self._should_check():
            return None

        stats = self.get_memory_stats()
        if not stats:
            return None

        # Проверка пороговых значений
        is_critical = stats.rss_mb > self.limits.critical_mb or stats.percent > self.limits.max_percent
        is_warning = stats.rss_mb > self.limits.warning_mb

        if is_critical:
            logger.error(
                f"CRITICAL memory usage: {stats.rss_mb:.1f} MB ({stats.percent:.1f}%) "
                f"- exceeds limits (critical: {self.limits.critical_mb} MB, "
                f"max percent: {self.limits.max_percent}%)",
                component="memory_monitor",
            )

            # Принудительный GC при критическом уровне
            self._run_gc()

            # Повторная проверка после GC
            after_gc = self.get_memory_stats()
            if after_gc:
                freed_mb = stats.rss_mb - after_gc.rss_mb
                logger.info(
                    f"Memory after GC: {after_gc.rss_mb:.1f} MB (freed: {freed_mb:.1f} MB)",
                    component="memory_monitor",
                )

        elif is_warning:
            logger.warning(
                f"High memory usage: {stats.rss_mb:.1f} MB ({stats.percent:.1f}%) "
                f"- approaching limit ({self.limits.warning_mb} MB)",
                component="memory_monitor",
            )

            # Мягкий GC при предупреждении (если давно не было)
            if self._should_run_gc():
                self._run_gc()

        else:
            # Нормальный уровень - логируем только в debug
            logger.debug(
                f"Memory OK: {stats.rss_mb:.1f} MB ({stats.percent:.1f}%)",
                component="memory_monitor",
            )

        return stats

    def get_status(self) -> dict:
        """
        Получить статус монитора для health checks.

        Returns:
            Dict с информацией о состоянии монитора
        """
        if not self._enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "psutil not available",
            }

        stats = self.get_memory_stats()
        if not stats:
            return {
                "enabled": True,
                "status": "error",
                "message": "Failed to get memory stats",
            }

        is_critical = stats.rss_mb > self.limits.critical_mb or stats.percent > self.limits.max_percent
        is_warning = stats.rss_mb > self.limits.warning_mb

        if is_critical:
            status = "critical"
            message = f"Memory usage critical: {stats.rss_mb:.1f} MB"
        elif is_warning:
            status = "warning"
            message = f"Memory usage high: {stats.rss_mb:.1f} MB"
        else:
            status = "healthy"
            message = f"Memory usage normal: {stats.rss_mb:.1f} MB"

        return {
            "enabled": True,
            "status": status,
            "message": message,
            "stats": {
                "rss_mb": round(stats.rss_mb, 2),
                "vms_mb": round(stats.vms_mb, 2),
                "percent": round(stats.percent, 2),
            },
            "limits": {
                "warning_mb": self.limits.warning_mb,
                "critical_mb": self.limits.critical_mb,
                "max_percent": self.limits.max_percent,
            },
        }


# Singleton instance
_memory_monitor: Optional[MemoryMonitor] = None


def get_memory_monitor(
    *,
    check_interval: int = 60,
    limits: Optional[MemoryLimits] = None,
    auto_gc: bool = True,
) -> MemoryMonitor:
    """
    Получить singleton instance монитора памяти.

    Args:
        check_interval: Интервал проверки в секундах
        limits: Пороговые значения
        auto_gc: Автоматический GC

    Returns:
        MemoryMonitor instance
    """
    global _memory_monitor

    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor(
            check_interval=check_interval,
            limits=limits,
            auto_gc=auto_gc,
        )
        logger.info(
            f"Memory Monitor initialized: "
            f"check_interval={check_interval}s, "
            f"limits=(warning={limits.warning_mb if limits else 512}MB, "
            f"critical={limits.critical_mb if limits else 1024}MB)",
            component="memory_monitor",
        )

    return _memory_monitor
