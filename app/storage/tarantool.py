import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import msgpack

from app.advanced_funcs.logging_client import logger
from app.settings import settings

# Try to import tarantool, but make it optional
try:
    import tarantool
    TARANTOOL_AVAILABLE = True
except ImportError:
    tarantool = None
    TARANTOOL_AVAILABLE = False
    logger.warning("Tarantool not available, using in-memory fallback", component="tarantool")

# Пул для blocking-операций
_executor = ThreadPoolExecutor(max_workers=3)

# In-memory fallback storage
_memory_cache: Dict[str, tuple] = {}
_memory_persistent: Dict[str, Any] = {}


class TarantoolClient:
    """
    Асинхронный клиент для Tarantool с поддержкой кэширования и TTL.
    Falls back to in-memory storage when Tarantool is not available.
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def get_instance(cls) -> "TarantoolClient":
        """Асинхронный Singleton с lazy-init"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    instance = cls()
                    await instance._connect()
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        self._connection = None
        self._connected: bool = False
        self._space = "cache"
        self._use_memory = not TARANTOOL_AVAILABLE

    async def _connect(self):
        """Асинхронное подключение через пул"""
        if self._use_memory:
            self._connected = True
            logger.info("Using in-memory storage (Tarantool not available)", component="tarantool")
            return

        if self._connected and self._connection:
            return

        def connect_fn():
            try:
                conn = tarantool.connect(
                    host=settings.tarantool_host,
                    port=settings.tarantool_port,
                    user=settings.tarantool_user,
                    password=settings.tarantool_password,
                )
                return conn
            except Exception as e:
                logger.warning(f"Tarantool connection failed: {e}, using in-memory fallback", component="tarantool")
                return None

        loop = asyncio.get_event_loop()
        self._connection = await loop.run_in_executor(_executor, connect_fn)
        
        if self._connection is None:
            self._use_memory = True
            logger.info("Falling back to in-memory storage", component="tarantool")
        else:
            logger.info("Tarantool connected successfully", component="tarantool")
        
        self._connected = True

    async def _ensure_connection(self):
        """Проверяет соединение, переподключается при необходимости"""
        if not self._connected:
            await self._connect()

    async def get(self, key: str) -> Optional[Dict[Any, Any]]:
        """Получает значение по ключу."""
        await self._ensure_connection()

        if self._use_memory:
            if key in _memory_cache:
                value_packed, expires_at = _memory_cache[key]
                if time.time() > expires_at:
                    del _memory_cache[key]
                    return None
                return msgpack.unpackb(value_packed, raw=False)
            return None

        def do_get():
            try:
                if not self._connection:
                    return None

                result = self._connection.select(self._space, key)
                if not result:
                    return None

                row = result[0]
                if len(row) < 3:
                    return None

                value_packed, expires_at = row[1], row[2]

                if not isinstance(value_packed, (bytes, bytearray)):
                    return None

                now = time.time()
                if now > expires_at:
                    self._connection.delete(self._space, key)
                    return None

                unpacked = msgpack.unpackb(
                    value_packed,
                    raw=False,
                    max_str_len=100_000,
                    max_bin_len=100_000,
                    max_array_len=1000,
                    max_map_len=1000,
                    max_ext_len=100_000,
                )

                if not isinstance(unpacked, (dict, list)):
                    return None

                return unpacked

            except Exception as e:
                logger.error(f"Error on GET {key}: {e}", component="tarantool")
                return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, do_get)

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Сохраняет значение с TTL."""
        await self._ensure_connection()

        expires_at = time.time() + (ttl if ttl is not None else 315360000)

        if self._use_memory:
            packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
            _memory_cache[key] = (packed, expires_at)
            return

        def do_set():
            try:
                packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                self._connection.replace(self._space, (key, packed, expires_at))
            except Exception as e:
                logger.error(f"Error on SET {key}: {e}", component="tarantool")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, do_set)

    async def delete(self, key: str):
        """Удаляет ключ."""
        await self._ensure_connection()

        if self._use_memory:
            _memory_cache.pop(key, None)
            return

        def do_delete():
            try:
                self._connection.delete(self._space, key)
            except Exception as e:
                logger.error(f"Error deleting key {key}: {e}", component="tarantool")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, do_delete)

    async def set_persistent(self, key: str, value: Any):
        """Сохраняет данные в постоянное хранилище."""
        await self._ensure_connection()

        if self._use_memory:
            packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
            _memory_persistent[key] = packed
            return

        def do_set():
            try:
                packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                self._connection.replace("persistent", (key, packed))
            except Exception as e:
                logger.error(f"Failed to save persistent {key}: {e}", component="tarantool")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, do_set)

    async def get_persistent(self, key: str) -> Optional[Dict[Any, Any]]:
        """Получает данные из постоянного хранилища."""
        await self._ensure_connection()

        if self._use_memory:
            if key in _memory_persistent:
                packed = _memory_persistent[key]
                return msgpack.unpackb(packed, raw=False)
            return None

        def do_get():
            try:
                result = self._connection.select("persistent", key)
                if not result:
                    return None
                packed = result[0][1]
                if not isinstance(packed, (bytes, bytearray)):
                    return None
                return msgpack.unpackb(packed, raw=False)
            except Exception as e:
                logger.error(f"Failed to get persistent {key}: {e}")
                return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, do_get)

    async def scan_threads(self) -> List[Dict[str, Any]]:
        """Сканирует все треды в постоянном хранилище."""
        await self._ensure_connection()

        if self._use_memory:
            threads = []
            for key, packed in _memory_persistent.items():
                if key.startswith("thread:"):
                    try:
                        value = msgpack.unpackb(packed, raw=False)
                        if isinstance(value, dict) and "input" in value:
                            threads.append({
                                "key": key,
                                "input": value.get("input", "Без запроса"),
                                "created_at": value.get("created_at", 0),
                                "message_count": len(value.get("messages", [])),
                            })
                    except Exception as e:
                        logger.warning(f"Failed to unpack thread {key}: {e}")
            return threads

        def do_scan():
            try:
                result = self._connection.select("persistent")
                threads = []
                for row in result:
                    if len(row) >= 2 and row[0].startswith("thread:"):
                        try:
                            if isinstance(row[1], (bytes, bytearray)):
                                value = msgpack.unpackb(row[1], raw=False)
                                if isinstance(value, dict) and "input" in value:
                                    threads.append({
                                        "key": row[0],
                                        "input": value.get("input", "Без запроса"),
                                        "created_at": value.get("created_at", 0),
                                        "message_count": len(value.get("messages", [])),
                                    })
                        except Exception as e:
                            logger.warning(f"Failed to unpack thread {row[0]}: {e}")
                return threads
            except Exception as e:
                logger.error(f"Error scanning threads: {e}")
                return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, do_scan)

    async def invalidate_all_keys(self, confirm: bool = False):
        """Полная инвалидация всех ключей."""
        if not confirm:
            logger.warning("invalidate_all_keys() called without confirm=True. Aborted.", component="tarantool")
            return

        await self._ensure_connection()

        if self._use_memory:
            _memory_cache.clear()
            logger.warning("All cache keys invalidated (in-memory)", component="tarantool")
            return

        def do_truncate():
            try:
                self._connection.call("box.space.cache:truncate")
                logger.warning("All cache keys invalidated (space 'cache' truncated)", component="tarantool")
            except Exception as e:
                logger.error(f"Failed to invalidate all keys: {e}", component="tarantool")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, do_truncate)

    async def close(self):
        """Закрывает соединение."""
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

    @classmethod
    async def close_global(cls):
        """Закрывает глобальный экземпляр."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None


async def save_thread_to_tarantool(thread_id: str, data: Dict[str, Any]):
    """Сохраняет состояние графа в Tarantool/память как персистентный тред."""
    try:
        client = await TarantoolClient.get_instance()

        if thread_id.startswith("thread_"):
            normalized_id = thread_id
        else:
            normalized_id = f"thread_{thread_id}"

        if not isinstance(data, dict):
            data = {"content": str(data)}

        processed_messages = []
        messages = data.get("messages", [])
        for msg in messages:
            try:
                if hasattr(msg, "dict") and callable(msg.dict):
                    processed_messages.append(msg.dict())
                elif hasattr(msg, "__dict__"):
                    processed_messages.append(msg.__dict__)
                elif isinstance(msg, dict):
                    processed_messages.append(msg)
                else:
                    processed_messages.append({"content": str(msg)})
            except Exception as e:
                logger.warning(f"Failed to serialize message: {e}")
                processed_messages.append({"error": str(e)})

        record = {
            "messages": processed_messages,
            "created_at": data.get("created_at", time.time()),
            "input": str(data.get("input", "")),
            "thread_id": normalized_id,
            "final_state": data,
        }

        await client.set_persistent(f"thread:{normalized_id}", record)
        logger.info(f"Thread saved: thread:{normalized_id}")

    except Exception as e:
        logger.error(f"Ошибка при сохранении: {e}")
