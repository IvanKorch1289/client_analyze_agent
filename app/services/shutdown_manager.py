"""
Graceful Shutdown Manager for FastAPI application.
Handles SIGTERM/SIGINT with workflow draining.
"""

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import Callable, List, Optional

from app.services.http_client import AsyncHttpClient
from app.utility.logging_client import logger


class ShutdownManager:
    """
    Manages graceful shutdown of application components.

    Features:
    - Reject new requests with 503 Service Unavailable
    - Wait for in-flight workflows (configurable timeout)
    - Close HTTP clients, DB connections
    - Flush message queues
    """

    def __init__(self, drain_timeout: float = 30.0):
        self.drain_timeout = drain_timeout
        self._shutdown_requested = False
        self._in_flight_tasks: List[asyncio.Task] = []
        self._cleanup_callbacks: List[Callable] = []
        self._lock = asyncio.Lock()

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown was requested."""
        return self._shutdown_requested

    def register_cleanup(self, callback: Callable) -> None:
        """Register cleanup callback to run on shutdown."""
        self._cleanup_callbacks.append(callback)

    async def track_task(self, coro):
        """Track async task for graceful shutdown."""
        task = asyncio.create_task(coro)
        async with self._lock:
            self._in_flight_tasks.append(task)

        try:
            result = await task
            return result
        finally:
            async with self._lock:
                if task in self._in_flight_tasks:
                    self._in_flight_tasks.remove(task)

    async def initiate_shutdown(self, sig: Optional[signal.Signals] = None):
        """Initiate graceful shutdown sequence."""
        if self._shutdown_requested:
            logger.warning("Shutdown already in progress", component="shutdown")
            return

        self._shutdown_requested = True
        signal_name = sig.name if sig else "MANUAL"
        logger.info(
            f"🛑 Graceful shutdown initiated (signal: {signal_name})",
            component="shutdown",
        )

        # Step 1: Wait for in-flight tasks
        await self._drain_in_flight_tasks()

        # Step 2: Run cleanup callbacks
        await self._run_cleanup_callbacks()

        logger.info("✅ Graceful shutdown completed", component="shutdown")

    async def _drain_in_flight_tasks(self):
        """Wait for in-flight tasks to complete."""
        async with self._lock:
            pending_count = len(self._in_flight_tasks)

        if pending_count == 0:
            logger.info("No in-flight tasks to drain", component="shutdown")
            return

        logger.info(
            f"Waiting for {pending_count} in-flight tasks (timeout: {self.drain_timeout}s)",
            component="shutdown",
        )

        try:
            async with self._lock:
                tasks = list(self._in_flight_tasks)

            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.drain_timeout,
            )
            logger.info(f"✅ All {pending_count} tasks completed", component="shutdown")

        except asyncio.TimeoutError:
            async with self._lock:
                remaining = len(self._in_flight_tasks)
            logger.warning(
                f"⚠️ Timeout reached, {remaining} tasks still running (forcing shutdown)",
                component="shutdown",
            )

            # Cancel remaining tasks
            async with self._lock:
                for task in self._in_flight_tasks:
                    if not task.done():
                        task.cancel()

    async def _run_cleanup_callbacks(self):
        """Execute all registered cleanup callbacks."""
        logger.info(
            f"Running {len(self._cleanup_callbacks)} cleanup callbacks",
            component="shutdown",
        )

        for i, callback in enumerate(self._cleanup_callbacks, 1):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
                logger.info(f"✅ Cleanup callback {i} completed", component="shutdown")
            except Exception as e:
                logger.error(
                    f"❌ Cleanup callback {i} failed: {e}",
                    component="shutdown",
                )


# Global instance
shutdown_manager = ShutdownManager(drain_timeout=30.0)


@asynccontextmanager
async def lifespan_manager(app):
    """
    FastAPI lifespan context manager for startup/shutdown.

    Usage in main.py:
        app = FastAPI(lifespan=lifespan_manager)
    """
    # Startup
    logger.info("🚀 Application startup", component="lifespan")

    # Register cleanup callbacks
    async def cleanup_http_client():
        await AsyncHttpClient.close_global()
        logger.info("HTTP client closed", component="cleanup")

    async def cleanup_tarantool():
        from app.storage.tarantool import TarantoolClient

        client = await TarantoolClient.get_instance()
        await client.close()
        logger.info("Tarantool client closed", component="cleanup")

    shutdown_manager.register_cleanup(cleanup_http_client)
    shutdown_manager.register_cleanup(cleanup_tarantool)

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler(sig):
        logger.info(f"Received signal {sig.name}", component="signal")
        asyncio.create_task(shutdown_manager.initiate_shutdown(sig))

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    yield  # Application runs here

    # Shutdown
    logger.info("🛑 Application shutdown", component="lifespan")
    if not shutdown_manager.is_shutting_down:
        await shutdown_manager.initiate_shutdown()
