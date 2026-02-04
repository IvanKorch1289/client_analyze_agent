"""
Tarantool async client with caching, TTL, batch operations and compression.

Refactored to use modular components:
- compression.py: Data compression utilities
- metrics.py: Performance tracking
- connection.py: Connection management
"""

import asyncio
import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import msgpack

from app.config import settings
from app.storage.compression import (
    CompressionHandler,
    CompressionConfig,
)
from app.storage.metrics import CacheMetrics
from app.storage.connection import (
    get_executor,
    get_tarantool_module,
    TARANTOOL_AVAILABLE,
)
from app.shared.toolkit.logging import logger

# Get tarantool module from connection (handles import gracefully)
tarantool = get_tarantool_module()

# Lazy import repositories to avoid circular imports
_cache_repo = None
_reports_repo = None
_threads_repo = None

_executor = get_executor()

# Memory cache size limits to prevent OOM (memory leak fix)
MAX_MEMORY_CACHE_SIZE = 1000  # Maximum entries in main cache
MAX_MEMORY_PERSISTENT_SIZE = 500  # Maximum entries in persistent cache

# Thread-safe lock for in-memory caches (H8)
_cache_lock = threading.Lock()

# Use OrderedDict for LRU eviction
_memory_cache: OrderedDict[str, tuple] = OrderedDict()
_memory_persistent: OrderedDict[str, Any] = OrderedDict()


def _evict_oldest_cache_entry() -> None:
    """Evict oldest entry from memory cache if full. Caller must hold _cache_lock."""
    if len(_memory_cache) >= MAX_MEMORY_CACHE_SIZE:
        oldest_key = next(iter(_memory_cache))
        del _memory_cache[oldest_key]
        logger.warning(
            f"Memory cache full ({MAX_MEMORY_CACHE_SIZE}), evicted: {oldest_key[:50]}...",
            component="tarantool",
        )


def _evict_oldest_persistent_entry() -> None:
    """Evict oldest entry from persistent cache if full. Caller must hold _cache_lock."""
    if len(_memory_persistent) >= MAX_MEMORY_PERSISTENT_SIZE:
        oldest_key = next(iter(_memory_persistent))
        del _memory_persistent[oldest_key]
        logger.warning(
            f"Persistent cache full ({MAX_MEMORY_PERSISTENT_SIZE}), evicted: {oldest_key[:50]}...",
            component="tarantool",
        )


@dataclass
class CacheConfig:
    """Configuration for cache behavior."""

    compression_threshold: int = 1024
    compression_level: int = 6
    default_ttl: int = 3600
    max_batch_size: int = 100
    search_cache_ttl: int = 300
    prefetch_enabled: bool = True


class TarantoolClient:
    """
    Асинхронный клиент для Tarantool с поддержкой кэширования, TTL, batch operations и сжатия.
    Falls back to in-memory storage when Tarantool is not available.
    """

    _instance: Optional["TarantoolClient"] = None
    _lock: Optional[asyncio.Lock] = None
    _initialized: bool = False

    def __new__(cls):
        # Блокируем прямое создание экземпляров
        raise RuntimeError(
            f"Нельзя создавать экземпляр {cls.__name__} напрямую. Используйте {cls.__name__}.get_instance()"
        )

    @classmethod
    async def get_instance(cls) -> "TarantoolClient":
        """
        Thread-safe singleton pattern с async/await.

        Returns:
            TarantoolClient: Единственный экземпляр клиента
        """
        # Быстрая проверка без блокировки
        if cls._instance is not None and cls._initialized:
            return cls._instance

        # Создаем lock если еще нет
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        # Двойная проверка с блокировкой
        async with cls._lock:
            if cls._instance is None:
                # Создаем instance напрямую через object.__new__
                instance = object.__new__(cls)
                instance.__init_once()
                await instance._connect()

                # Атомарно устанавливаем instance и флаг
                cls._initialized = True
                cls._instance = instance

        return cls._instance

    def __init_once(self):
        """Инициализация атрибутов экземпляра (вызывается один раз)."""
        self._connection: Any = None
        self._connected: bool = False
        self._space = "cache"
        self._use_memory = not TARANTOOL_AVAILABLE
        # Back-compat flag used by dashboards/health endpoints
        self._fallback_mode = self._use_memory
        self._config = CacheConfig()
        self._metrics = CacheMetrics()
        self._search_cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._search_cache_maxlen: int = 10000
        # Reconnect state (H9)
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = int(getattr(settings.tarantool, "reconnect_max_attempts", 5))
        self._reconnect_delay: float = float(getattr(settings.tarantool, "reconnect_delay", 2.0))
        # Use modular compression handler
        self._compression = CompressionHandler(
            CompressionConfig(
                threshold=self._config.compression_threshold,
                level=self._config.compression_level,
            )
        )

    async def _connect(self):
        """Асинхронное подключение через пул"""
        if self._use_memory:
            self._connected = True
            logger.info(
                "Using in-memory storage (Tarantool not available)",
                component="tarantool",
            )
            return

        if self._connected and self._connection:
            return

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

        loop = asyncio.get_running_loop()
        self._connection = await loop.run_in_executor(_executor, connect_fn)

        if self._connection is None:
            self._use_memory = True
            self._fallback_mode = True
            logger.info("Falling back to in-memory storage", component="tarantool")
        else:
            self._reconnect_attempts = 0
            logger.info("Tarantool connected successfully", component="tarantool")

        self._connected = True

    async def _reconnect(self) -> bool:
        """Попытка переподключения к Tarantool (H9).

        Returns:
            True если переподключение успешно.
        """
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            return False

        self._reconnect_attempts += 1
        delay = self._reconnect_delay * self._reconnect_attempts
        logger.info(
            f"Tarantool reconnect attempt {self._reconnect_attempts}/{self._max_reconnect_attempts} "
            f"(delay {delay:.1f}s)",
            component="tarantool",
        )
        await asyncio.sleep(delay)

        self._connection = None
        self._connected = False
        self._use_memory = False
        self._fallback_mode = False
        await self._connect()

        if self._connection is not None:
            logger.info("Tarantool reconnected successfully", component="tarantool")
            return True
        return False

    async def _ensure_connection(self):
        """Проверяет соединение, переподключается при необходимости"""
        if not self._connected:
            await self._connect()
        # H9: Если в fallback-режиме — пробуем переподключиться
        if self._use_memory and TARANTOOL_AVAILABLE and self._reconnect_attempts < self._max_reconnect_attempts:
            reconnected = await self._reconnect()
            if reconnected:
                self._use_memory = False
                self._fallback_mode = False

    async def _call(self, func_name: str, *args):
        """
        Вызов Lua-функций в Tarantool через connection.call в отдельном потоке.

        Зачем:
        - tarantool-python клиент синхронный, поэтому выносим IO в executor,
        - часть операций (prefix delete, list entries, truncate) быстрее делать на стороне Tarantool.
        """
        await self._ensure_connection()
        if self._use_memory or not self._connection:
            raise RuntimeError("Tarantool недоступен (in-memory fallback)")

        def do_call():
            return self._connection.call(func_name, args)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_call)

    async def call(self, func_name: str, args: tuple = ()):
        """
        Публичный метод для вызова Lua-функций в Tarantool.

        Usage:
            result = await client.call("box.space.llm_audit:insert", (data1, data2, ...))
            result = await client.call("box.space.llm_audit:select", (None, {"limit": 100}))

        Args:
            func_name: Имя Lua-функции (может быть space:method)
            args: Tuple с аргументами для функции

        Returns:
            Результат выполнения функции
        """
        return await self._call(func_name, *args)

    def _compress(self, data: bytes) -> bytes:
        """Compress data using the compression handler."""
        original_compressed = self._compression._compressed_count
        result = self._compression.compress(data)
        # Sync metrics if compression occurred
        if self._compression._compressed_count > original_compressed:
            stats = self._compression.stats
            self._metrics.compressed_saves = stats["compressed_saves"]
            self._metrics.bytes_saved_by_compression = stats["bytes_saved_by_compression"]
        return result

    def _decompress(self, data: bytes | bytearray) -> bytes:
        """Decompress data using the compression handler."""
        return self._compression.decompress(bytes(data) if isinstance(data, bytearray) else data)

    def _generate_search_key(self, query: str, service: str = "default") -> str:
        normalized = query.lower().strip()
        hash_val = hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()[:12]
        return f"search:{service}:{hash_val}"

    async def get(self, key: str) -> Optional[Dict[Any, Any]]:
        await self._ensure_connection()
        start_time = time.time()

        if self._use_memory:
            if key in _memory_cache:
                packed_tuple = _memory_cache[key]
                # Backward compatibility: support old 2-tuple (value_packed, expires_at)
                if isinstance(packed_tuple, tuple) and len(packed_tuple) >= 2:
                    value_packed = packed_tuple[0]
                    expires_at = packed_tuple[1]
                else:
                    value_packed, expires_at = None, 0
                if time.time() > expires_at:
                    del _memory_cache[key]
                    self._metrics.misses += 1
                    return None
                if value_packed is None:
                    self._metrics.misses += 1
                    return None
                self._metrics.hits += 1
                self._metrics.total_get_time_ms += (time.time() - start_time) * 1000
                data = self._decompress(value_packed)
                return msgpack.unpackb(data, raw=False)
            self._metrics.misses += 1
            self._metrics.total_get_time_ms += (time.time() - start_time) * 1000
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

                data = self._decompress(value_packed)
                unpacked = msgpack.unpackb(
                    data,
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

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(_executor, do_get)
        elapsed = (time.time() - start_time) * 1000
        self._metrics.total_get_time_ms += elapsed
        if result is not None:
            self._metrics.hits += 1
        else:
            self._metrics.misses += 1
        return result

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        compress: bool = True,
        source: str = "api",
    ):
        await self._ensure_connection()
        start_time = time.time()
        ttl_value = ttl if ttl is not None else self._config.default_ttl
        expires_at = time.time() + ttl_value
        created_at = time.time()

        if self._use_memory:
            packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
            if compress:
                packed = self._compress(packed)
            _evict_oldest_cache_entry()  # Prevent memory leak
            _memory_cache[key] = (packed, expires_at, created_at, source)
            self._metrics.sets += 1
            self._metrics.total_set_time_ms += (time.time() - start_time) * 1000
            return

        def do_set():
            try:
                packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                if compress:
                    packed = self._compress(packed)
                # Match init.lua cache schema: (key, value, ttl/expires_at, created_at, source)
                self._connection.replace(self._space, (key, packed, expires_at, created_at, source))
            except Exception as e:
                logger.error(f"Error on SET {key}: {e}", component="tarantool")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, do_set)
        self._metrics.sets += 1
        self._metrics.total_set_time_ms += (time.time() - start_time) * 1000

    async def delete(self, key: str):
        await self._ensure_connection()

        if self._use_memory:
            _memory_cache.pop(key, None)
            self._metrics.deletes += 1
            return

        def do_delete():
            try:
                self._connection.delete(self._space, key)
            except Exception as e:
                logger.error(f"Error deleting key {key}: {e}", component="tarantool")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, do_delete)
        self._metrics.deletes += 1

    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        await self._ensure_connection()
        self._metrics.batch_operations += 1
        start_time = time.time()
        results: Dict[str, Any] = {}

        if self._use_memory:
            now = time.time()
            for key in keys:
                if key in _memory_cache:
                    packed_tuple = _memory_cache[key]
                    value_packed = (
                        packed_tuple[0] if isinstance(packed_tuple, tuple) and len(packed_tuple) >= 2 else None
                    )
                    expires_at = packed_tuple[1] if isinstance(packed_tuple, tuple) and len(packed_tuple) >= 2 else 0
                    if now <= expires_at and value_packed is not None:
                        data = self._decompress(value_packed)
                        results[key] = msgpack.unpackb(data, raw=False)
                        self._metrics.hits += 1
                    else:
                        if key in _memory_cache and now > expires_at:
                            del _memory_cache[key]
                        self._metrics.misses += 1
                else:
                    self._metrics.misses += 1
            elapsed = (time.time() - start_time) * 1000
            self._metrics.total_get_time_ms += elapsed
            return results

        def do_batch_get():
            batch_results: Dict[str, Any] = {}
            now = time.time()
            for key in keys:
                try:
                    result = self._connection.select(self._space, key)
                    if result and len(result[0]) >= 3:
                        value_packed, expires_at = result[0][1], result[0][2]
                        if now <= expires_at and isinstance(value_packed, (bytes, bytearray)):
                            data = self._decompress(value_packed)
                            batch_results[key] = msgpack.unpackb(data, raw=False)
                except Exception as e:
                    logger.warning(f"Error in batch get for {key}: {e}", component="tarantool")
            return batch_results

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(_executor, do_batch_get)
        elapsed = (time.time() - start_time) * 1000
        self._metrics.total_get_time_ms += elapsed
        self._metrics.hits += len(results)
        self._metrics.misses += len(keys) - len(results)
        return results

    async def set_many(
        self,
        items: Dict[str, Any],
        ttl: Optional[int] = None,
        compress: bool = True,
        _is_chunk: bool = False,
    ):
        await self._ensure_connection()
        if not _is_chunk:
            self._metrics.batch_operations += 1
        start_time = time.time()
        ttl_value = ttl if ttl is not None else self._config.default_ttl
        expires_at = time.time() + ttl_value
        created_at = time.time()

        if len(items) > self._config.max_batch_size:
            chunks = [
                dict(list(items.items())[i : i + self._config.max_batch_size])
                for i in range(0, len(items), self._config.max_batch_size)
            ]
            for chunk in chunks:
                await self.set_many(chunk, ttl, compress, _is_chunk=True)
            return

        if self._use_memory:
            for key, value in items.items():
                packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                if compress:
                    packed = self._compress(packed)
                _evict_oldest_cache_entry()  # Prevent memory leak
                _memory_cache[key] = (packed, expires_at, created_at, "api")
            self._metrics.sets += len(items)
            elapsed = (time.time() - start_time) * 1000
            self._metrics.total_set_time_ms += elapsed
            return

        def do_batch_set():
            for key, value in items.items():
                try:
                    packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                    if compress:
                        packed = self._compress(packed)
                    self._connection.replace(self._space, (key, packed, expires_at, created_at, "api"))
                except Exception as e:
                    logger.warning(f"Error in batch set for {key}: {e}", component="tarantool")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, do_batch_set)
        elapsed = (time.time() - start_time) * 1000
        self._metrics.total_set_time_ms += elapsed
        self._metrics.sets += len(items)

    async def delete_many(self, keys: List[str]):
        await self._ensure_connection()
        self._metrics.batch_operations += 1

        if self._use_memory:
            for key in keys:
                _memory_cache.pop(key, None)
            self._metrics.deletes += len(keys)
            return

        def do_batch_delete():
            for key in keys:
                try:
                    self._connection.delete(self._space, key)
                except Exception as e:
                    logger.warning(f"Error in batch delete for {key}: {e}", component="tarantool")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, do_batch_delete)
        self._metrics.deletes += len(keys)

    async def cache_search_result(self, query: str, result: Any, service: str = "default"):
        key = self._generate_search_key(query, service)
        await self.set(
            key,
            result,
            ttl=self._config.search_cache_ttl,
            source=f"search:{service}",
        )
        self._search_cache[key] = (result, time.time() + self._config.search_cache_ttl)
        # LRU eviction: remove oldest entries when exceeding maxlen
        while len(self._search_cache) > self._search_cache_maxlen:
            self._search_cache.popitem(last=False)

    async def get_cached_search(self, query: str, service: str = "default") -> Optional[Any]:
        key = self._generate_search_key(query, service)
        if key in self._search_cache:
            result, expires_at = self._search_cache[key]
            if time.time() <= expires_at:
                self._metrics.hits += 1
                self._search_cache.move_to_end(key)  # LRU: mark as recently used
                return result
            del self._search_cache[key]
        return await self.get(key)

    async def delete_by_prefix(self, prefix: str):
        await self._ensure_connection()

        if self._use_memory:
            keys_to_delete = [k for k in _memory_cache.keys() if k.startswith(prefix)]
            for key in keys_to_delete:
                del _memory_cache[key]
            self._metrics.deletes += len(keys_to_delete)
            return

        # Быстрый путь: Lua-процедура в Tarantool (iterator=GE по primary index)
        try:
            res = await self._call("cache_delete_by_prefix", prefix)
            # tarantool-python обычно возвращает объект с .data
            data = getattr(res, "data", res)
            deleted = 0
            if isinstance(data, (list, tuple)) and data:
                payload = data[0]
                if isinstance(payload, dict):
                    deleted = int(payload.get("deleted", 0) or 0)
            self._metrics.deletes += deleted
            return
        except Exception as e:
            # Фоллбек: старый медленный скан (на случай отсутствия функции в Tarantool)
            logger.warning(
                f"delete_by_prefix() fallback to scan: {e}",
                component="tarantool",
            )

        def do_prefix_delete_scan():
            try:
                result = self._connection.select(self._space)
                deleted = 0
                for row in result:
                    if len(row) >= 1 and isinstance(row[0], str) and row[0].startswith(prefix):
                        self._connection.delete(self._space, row[0])
                        deleted += 1
                return deleted
            except Exception as e:
                logger.error(f"Error deleting by prefix {prefix}: {e}", component="tarantool")
                return 0

        loop = asyncio.get_running_loop()
        deleted = await loop.run_in_executor(_executor, do_prefix_delete_scan)
        self._metrics.deletes += deleted

    def get_metrics(self) -> Dict[str, Any]:
        return self._metrics.to_dict()

    def reset_metrics(self):
        self._metrics.reset()

    def get_cache_size(self) -> int:
        if self._use_memory:
            return len(_memory_cache)
        # Быстрый путь: Tarantool считает len() внутри, без скана.
        try:
            if self._connection:
                res = self._connection.call("cache_len", ())
                data = getattr(res, "data", res)
                if isinstance(data, (list, tuple)) and data:
                    return int(data[0] or 0)
        except Exception:
            pass
        return 0

    async def get_entries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить первые N записей кеша для UI (без полного скана)."""
        await self._ensure_connection()
        entries = []

        if self._use_memory:
            now = time.time()
            for i, (key, packed_tuple) in enumerate(_memory_cache.items()):
                if i >= limit:
                    break
                if not isinstance(packed_tuple, tuple) or len(packed_tuple) < 2:
                    continue
                value_packed = packed_tuple[0]
                expires_at = packed_tuple[1]
                if now <= expires_at:
                    try:
                        data = self._decompress(value_packed)
                        value = msgpack.unpackb(data, raw=False)
                        entries.append(
                            {
                                "key": key,
                                "expires_in": int(expires_at - now),
                                "size_bytes": len(value_packed),
                                "preview": (str(value)[:100] + "..." if len(str(value)) > 100 else str(value)),
                            }
                        )
                    except Exception:
                        entries.append({"key": key, "error": "unpack failed"})
            return entries

        # Быстрый путь: Tarantool делает выборку на своей стороне
        try:
            res = await self._call("cache_get_entries", limit)
            data = getattr(res, "data", res)
            if isinstance(data, (list, tuple)) and data and isinstance(data[0], list):
                return data[0]
            if isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
                return list(data)
        except Exception as e:
            logger.warning(
                f"get_entries() fallback to scan: {e}",
                component="tarantool",
            )

        def do_get_entries():
            result_entries = []
            try:
                result = self._connection.select(self._space, limit=limit)
                now = time.time()
                for row in result[:limit]:
                    if len(row) >= 3:
                        key, value_packed, expires_at = row[0], row[1], row[2]
                        if now <= expires_at:
                            try:
                                data = self._decompress(value_packed)
                                value = msgpack.unpackb(data, raw=False)
                                result_entries.append(
                                    {
                                        "key": key,
                                        "expires_in": int(expires_at - now),
                                        "size_bytes": (len(value_packed) if isinstance(value_packed, bytes) else 0),
                                        "preview": (str(value)[:100] + "..." if len(str(value)) > 100 else str(value)),
                                    }
                                )
                            except Exception:
                                result_entries.append({"key": key, "error": "unpack failed"})
            except Exception as e:
                logger.error(f"Error getting entries: {e}", component="tarantool")
            return result_entries

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_get_entries)

    def get_config(self) -> Dict[str, Any]:
        return {
            "compression_threshold": self._config.compression_threshold,
            "compression_level": self._config.compression_level,
            "default_ttl": self._config.default_ttl,
            "max_batch_size": self._config.max_batch_size,
            "search_cache_ttl": self._config.search_cache_ttl,
            "prefetch_enabled": self._config.prefetch_enabled,
            "use_memory": self._use_memory,
        }

    @property
    def is_connected(self) -> bool:
        """Возвращает True если клиент подключён (включая in-memory режим)."""
        return self._connected

    async def set_persistent(self, key: str, value: Any):
        """Сохраняет данные в постоянное хранилище."""
        await self._ensure_connection()

        if self._use_memory:
            packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
            _evict_oldest_persistent_entry()  # Prevent memory leak
            _memory_persistent[key] = packed
            return

        def do_set():
            try:
                packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                self._connection.replace("persistent", (key, packed))
            except Exception as e:
                logger.error(f"Failed to save persistent {key}: {e}", component="tarantool")

        loop = asyncio.get_running_loop()
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

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_get)

    async def delete_persistent(self, key: str) -> bool:
        """Удаляет данные из persistent space (backward compatibility for repositories/tests)."""
        await self._ensure_connection()

        if self._use_memory:
            existed = key in _memory_persistent
            _memory_persistent.pop(key, None)
            return existed

        def do_delete():
            try:
                self._connection.delete("persistent", key)
                return True
            except Exception as e:
                logger.error(f"Failed to delete persistent {key}: {e}", component="tarantool")
                return False

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_delete)

    async def get_all_persistent_keys(self, prefix: Optional[str] = None) -> List[str]:
        """
        Получает список всех ключей из persistent storage.

        Args:
            prefix: Опциональный префикс для фильтрации ключей (например, 'dlq:')

        Returns:
            Список ключей
        """
        await self._ensure_connection()

        if self._use_memory:
            keys = list(_memory_persistent.keys())
            if prefix:
                keys = [k for k in keys if k.startswith(prefix)]
            return keys

        def do_list_keys():
            try:
                result = self._connection.select("persistent", limit=10000)
                keys = [row[0] for row in result if isinstance(row, (list, tuple)) and len(row) > 0]
                if prefix:
                    keys = [k for k in keys if k.startswith(prefix)]
                return keys
            except Exception as e:
                logger.error(f"Failed to list persistent keys: {e}", component="tarantool")
                return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_list_keys)

    async def list_threads(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Список тредов, сохранённых в persistent (ключи `thread:*`).
        Backward compatibility for ThreadsRepository/tests.
        """
        await self._ensure_connection()

        threads: List[Dict[str, Any]] = []

        if self._use_memory:
            for key, packed in _memory_persistent.items():
                if isinstance(key, str) and key.startswith("thread:"):
                    try:
                        value = msgpack.unpackb(packed, raw=False)
                        if isinstance(value, dict):
                            threads.append(value)
                    except Exception:
                        continue
            threads.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return threads[:limit]

        def do_list():
            result_threads: List[Dict[str, Any]] = []
            try:
                rows = self._connection.select("persistent")
                for row in rows:
                    if len(row) >= 2 and isinstance(row[0], str) and row[0].startswith("thread:"):
                        packed = row[1]
                        if isinstance(packed, (bytes, bytearray)):
                            try:
                                value = msgpack.unpackb(packed, raw=False)
                                if isinstance(value, dict):
                                    result_threads.append(value)
                            except Exception:
                                continue
            except Exception as e:
                logger.error(f"Failed to list threads: {e}", component="tarantool")
            result_threads.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return result_threads[:limit]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_list)

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
                            threads.append(
                                {
                                    "key": key,
                                    "input": value.get("input", "Без запроса"),
                                    "created_at": value.get("created_at", 0),
                                    "message_count": len(value.get("messages", [])),
                                }
                            )
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
                                    threads.append(
                                        {
                                            "key": row[0],
                                            "input": value.get("input", "Без запроса"),
                                            "created_at": value.get("created_at", 0),
                                            "message_count": len(value.get("messages", [])),
                                        }
                                    )
                        except Exception as e:
                            logger.warning(f"Failed to unpack thread {row[0]}: {e}")
                return threads
            except Exception as e:
                logger.error(f"Error scanning threads: {e}")
                return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_scan)

    async def search_threads_by_field(
        self,
        field_name: str,
        field_value: str,
        limit: int = 50,
        partial_match: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Поиск тредов по значению поля с ранней фильтрацией.

        Оптимизация: фильтрация происходит во время итерации,
        а не после загрузки всех данных в память.

        Args:
            field_name: Имя поля для поиска (inn, client_name, etc.)
            field_value: Искомое значение
            limit: Максимальное количество результатов
            partial_match: True для частичного совпадения (contains)

        Returns:
            Список тредов, соответствующих критерию
        """
        await self._ensure_connection()
        threads: List[Dict[str, Any]] = []

        if self._use_memory:
            for key, packed in _memory_persistent.items():
                if len(threads) >= limit:
                    break
                if isinstance(key, str) and key.startswith("thread:"):
                    try:
                        value = msgpack.unpackb(packed, raw=False)
                        if isinstance(value, dict):
                            stored_value = value.get(field_name)
                            if stored_value is not None:
                                if partial_match:
                                    if field_value.lower() in str(stored_value).lower():
                                        threads.append(value)
                                elif str(stored_value) == str(field_value):
                                    threads.append(value)
                    except Exception:
                        continue
            threads.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return threads

        def do_search():
            result_threads: List[Dict[str, Any]] = []
            try:
                rows = self._connection.select("persistent")
                for row in rows:
                    if len(result_threads) >= limit:
                        break
                    if len(row) >= 2 and isinstance(row[0], str) and row[0].startswith("thread:"):
                        packed = row[1]
                        if isinstance(packed, (bytes, bytearray)):
                            try:
                                value = msgpack.unpackb(packed, raw=False)
                                if isinstance(value, dict):
                                    stored_value = value.get(field_name)
                                    if stored_value is not None:
                                        if partial_match:
                                            if field_value.lower() in str(stored_value).lower():
                                                result_threads.append(value)
                                        elif str(stored_value) == str(field_value):
                                            result_threads.append(value)
                            except Exception:
                                continue
            except Exception as e:
                logger.error(
                    f"Failed to search threads by {field_name}: {e}",
                    component="tarantool",
                )
            result_threads.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return result_threads

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, do_search)

    async def invalidate_all_keys(self, confirm: bool = False):
        """Полная инвалидация всех ключей."""
        if not confirm:
            logger.warning(
                "invalidate_all_keys() called without confirm=True. Aborted.",
                component="tarantool",
            )
            return

        await self._ensure_connection()

        await self.clear_cache()
        logger.warning("All cache keys invalidated", component="tarantool")

    async def clear_cache(self):
        """Очистить весь кеш. В Tarantool — через truncate (очень быстро)."""
        await self._ensure_connection()

        if self._use_memory:
            _memory_cache.clear()
            return

        try:
            await self._call("cache_clear")
            return
        except Exception as e:
            logger.warning(
                f"cache_clear() not available, fallback to scan: {e}",
                component="tarantool",
            )

        def do_clear():
            try:
                # Best-effort scan and delete (portable across tarantool-python versions)
                try:
                    rows = self._connection.select(self._space)
                except Exception:
                    rows = []
                for row in rows:
                    try:
                        if row and isinstance(row[0], str):
                            self._connection.delete(self._space, row[0])
                    except Exception:
                        continue
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}", component="tarantool")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, do_clear)

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Async wrapper for cache metrics (backward compatibility)."""
        return self.get_metrics()

    async def close(self):
        """Закрывает соединение."""
        if self._connection and not self._use_memory:

            def close_fn():
                try:
                    self._connection.close()
                    logger.info("Tarantool connection closed", component="tarantool")
                except Exception as e:
                    logger.error(f"Error closing Tarantool: {e}", component="tarantool")

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_executor, close_fn)
        self._connected = False
        self._connection = None

    def get_cache_repository(self):
        """
        Получить CacheRepository для работы с cache space.

        Returns:
            CacheRepository instance
        """
        global _cache_repo
        if _cache_repo is None:
            from app.storage.repositories.cache_repository import CacheRepository

            _cache_repo = CacheRepository(self)
        return _cache_repo

    def get_reports_repository(self):
        """
        Получить ReportsRepository для работы с reports space.

        Returns:
            ReportsRepository instance
        """
        global _reports_repo
        if _reports_repo is None:
            from app.storage.repositories.reports_repository import ReportsRepository

            _reports_repo = ReportsRepository(self)
        return _reports_repo

    def get_threads_repository(self):
        """
        Получить ThreadsRepository для работы с threads space.

        Returns:
            ThreadsRepository instance
        """
        global _threads_repo
        if _threads_repo is None:
            from app.storage.repositories.threads_repository import ThreadsRepository

            _threads_repo = ThreadsRepository(self)
        return _threads_repo

    @classmethod
    async def close_global(cls):
        """Закрывает глобальный экземпляр."""
        global _cache_repo, _reports_repo, _threads_repo

        if cls._instance is not None:
            await cls._instance.close()
            if cls._lock is not None:
                async with cls._lock:
                    cls._instance = None
                    cls._initialized = False
                    # Сброс repositories
                    _cache_repo = None
                    _reports_repo = None
                    _threads_repo = None
            else:
                cls._instance = None
                cls._initialized = False
                # Сброс repositories
                _cache_repo = None
                _reports_repo = None
                _threads_repo = None


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

        final_state = data.get("final_state", {})
        if isinstance(final_state, dict):
            serializable_state = {
                k: v
                for k, v in final_state.items()
                if k not in ("llm", "_llm")
                and not k.startswith("_")
                and isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
        else:
            serializable_state = str(final_state)

        record = {
            "messages": processed_messages,
            "created_at": data.get("created_at", time.time()),
            "input": str(data.get("input", "")),
            "thread_id": normalized_id,
            "final_state": serializable_state,
        }

        await client.set_persistent(f"thread:{normalized_id}", record)
        logger.info(f"Thread saved: thread:{normalized_id}")

    except Exception as e:
        logger.error(f"Ошибка при сохранении: {e}")
