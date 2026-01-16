"""
Tarantool connection management.

Provides async-safe connection handling with fallback to in-memory storage.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from app.config import settings
from app.utility.logging_client import logger

try:
    import tarantool

    TARANTOOL_AVAILABLE = True
except ImportError:
    tarantool = None
    TARANTOOL_AVAILABLE = False
    logger.warning("Tarantool not available, using in-memory fallback", component="tarantool")

_executor = ThreadPoolExecutor(max_workers=5)


class ConnectionManager:
    """
    Manages Tarantool connection lifecycle.

    Features:
    - Async-safe connection handling
    - Automatic fallback to in-memory when Tarantool unavailable
    - Thread pool executor for sync operations
    """

    def __init__(self):
        self._connection: Any = None
        self._connected: bool = False
        self._use_memory: bool = not TARANTOOL_AVAILABLE
        self._fallback_mode: bool = self._use_memory

    @property
    def is_connected(self) -> bool:
        """Check if connection is established."""
        return self._connected

    @property
    def is_memory_mode(self) -> bool:
        """Check if using in-memory fallback."""
        return self._use_memory

    @property
    def connection(self) -> Any:
        """Get raw connection object."""
        return self._connection

    async def connect(self) -> bool:
        """
        Establish connection to Tarantool.

        Returns:
            True if connected (including memory mode), False on failure
        """
        if self._use_memory:
            self._connected = True
            logger.info(
                "Using in-memory storage (Tarantool not available)",
                component="tarantool",
            )
            return True

        if self._connected and self._connection:
            return True

        def connect_fn():
            try:
                conn = tarantool.connect(
                    host=settings.tarantool.host,
                    port=settings.tarantool.port,
                    user=settings.tarantool.user,
                    password=settings.tarantool.password,
                )
                return conn
            except Exception as e:
                logger.warning(
                    f"Tarantool connection failed: {e}, using in-memory fallback",
                    component="tarantool",
                )
                return None

        loop = asyncio.get_event_loop()
        self._connection = await loop.run_in_executor(_executor, connect_fn)

        if self._connection is None:
            self._use_memory = True
            self._fallback_mode = True
            logger.info("Falling back to in-memory storage", component="tarantool")
        else:
            logger.info("Tarantool connected successfully", component="tarantool")

        self._connected = True
        return True

    async def ensure_connection(self) -> None:
        """Ensure connection is established, reconnect if needed."""
        if not self._connected:
            await self.connect()

    async def execute(self, func: callable, *args, **kwargs) -> Any:
        """
        Execute a function in the thread pool executor.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of the function
        """
        await self.ensure_connection()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: func(*args, **kwargs))

    async def call(self, func_name: str, *args) -> Any:
        """
        Call a Lua function in Tarantool.

        Args:
            func_name: Name of the Lua function
            *args: Arguments for the function

        Returns:
            Result from Tarantool

        Raises:
            RuntimeError: If Tarantool is not available
        """
        await self.ensure_connection()

        if self._use_memory or not self._connection:
            raise RuntimeError("Tarantool unavailable (in-memory fallback active)")

        def do_call():
            return self._connection.call(func_name, args)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, do_call)

    async def select(self, space: str, key: Any = None, **kwargs) -> list:
        """
        Select from a Tarantool space.

        Args:
            space: Space name
            key: Optional key for selection
            **kwargs: Additional select parameters

        Returns:
            List of tuples from Tarantool
        """
        await self.ensure_connection()

        if self._use_memory or not self._connection:
            return []

        def do_select():
            if key is not None:
                return self._connection.select(space, key, **kwargs)
            return self._connection.select(space, **kwargs)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, do_select)

    async def replace(self, space: str, data: tuple) -> Any:
        """
        Replace a record in Tarantool space.

        Args:
            space: Space name
            data: Tuple to insert/replace

        Returns:
            Result from Tarantool
        """
        await self.ensure_connection()

        if self._use_memory or not self._connection:
            return None

        def do_replace():
            return self._connection.replace(space, data)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, do_replace)

    async def delete(self, space: str, key: Any) -> Any:
        """
        Delete a record from Tarantool space.

        Args:
            space: Space name
            key: Key to delete

        Returns:
            Result from Tarantool
        """
        await self.ensure_connection()

        if self._use_memory or not self._connection:
            return None

        def do_delete():
            return self._connection.delete(space, key)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, do_delete)

    async def close(self) -> None:
        """Close the connection."""
        if self._connection and not self._use_memory:

            def close_fn():
                try:
                    self._connection.close()
                    logger.info("Tarantool connection closed", component="tarantool")
                except Exception as e:
                    logger.error(f"Error closing Tarantool: {e}", component="tarantool")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, close_fn)

        self._connected = False
        self._connection = None


# Global executor for module-level access
def get_executor() -> ThreadPoolExecutor:
    """Get the shared thread pool executor."""
    return _executor
