import asyncio
import gzip
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import msgpack

from app.advanced_funcs.logging_client import logger
from app.settings import settings

try:
    import tarantool
    TARANTOOL_AVAILABLE = True
except ImportError:
    tarantool = None
    TARANTOOL_AVAILABLE = False
    logger.warning("Tarantool not available, using in-memory fallback", component="tarantool")

_executor = ThreadPoolExecutor(max_workers=5)

_memory_cache: Dict[str, tuple] = {}
_memory_persistent: Dict[str, Any] = {}


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    batch_operations: int = 0
    compressed_saves: int = 0
    bytes_saved_by_compression: int = 0
    total_get_time_ms: float = 0.0
    total_set_time_ms: float = 0.0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    @property
    def avg_get_time_ms(self) -> float:
        total = self.hits + self.misses
        return (self.total_get_time_ms / total) if total > 0 else 0.0

    @property
    def avg_set_time_ms(self) -> float:
        return (self.total_set_time_ms / self.sets) if self.sets > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(self.hit_rate, 2),
            "sets": self.sets,
            "deletes": self.deletes,
            "batch_operations": self.batch_operations,
            "compressed_saves": self.compressed_saves,
            "bytes_saved_by_compression": self.bytes_saved_by_compression,
            "avg_get_time_ms": round(self.avg_get_time_ms, 2),
            "avg_set_time_ms": round(self.avg_set_time_ms, 2),
        }

    def reset(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.batch_operations = 0
        self.compressed_saves = 0
        self.bytes_saved_by_compression = 0
        self.total_get_time_ms = 0.0
        self.total_set_time_ms = 0.0


@dataclass
class CacheConfig:
    compression_threshold: int = 1024
    compression_level: int = 6
    default_ttl: int = 3600
    max_batch_size: int = 100
    search_cache_ttl: int = 300
    prefetch_enabled: bool = True


COMPRESSION_MARKER = b"\x1f\x8b"


class TarantoolClient:
    """
    Асинхронный клиент для Tarantool с поддержкой кэширования, TTL, batch operations и сжатия.
    Falls back to in-memory storage when Tarantool is not available.
    """

    _instance: Optional["TarantoolClient"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def get_instance(cls) -> "TarantoolClient":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    instance = cls()
                    await instance._connect()
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._connection: Any = None
        self._connected: bool = False
        self._space = "cache"
        self._use_memory = not TARANTOOL_AVAILABLE
        self._config = CacheConfig()
        self._metrics = CacheMetrics()
        self._search_cache: Dict[str, Tuple[Any, float]] = {}
        self._initialized = True

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

    def _compress(self, data: bytes) -> bytes:
        if data and len(data) >= self._config.compression_threshold:
            compressed = gzip.compress(data, compresslevel=self._config.compression_level)
            if len(compressed) < len(data):
                self._metrics.compressed_saves += 1
                self._metrics.bytes_saved_by_compression += len(data) - len(compressed)
                return compressed
        return data

    def _decompress(self, data: bytes) -> bytes:
        if data and len(data) >= 2 and data[:2] == COMPRESSION_MARKER:
            return gzip.decompress(data)
        return data

    def _generate_search_key(self, query: str, service: str = "default") -> str:
        normalized = query.lower().strip()
        hash_val = hashlib.md5(normalized.encode()).hexdigest()[:12]
        return f"search:{service}:{hash_val}"

    async def get(self, key: str) -> Optional[Dict[Any, Any]]:
        await self._ensure_connection()
        start_time = time.time()

        if self._use_memory:
            if key in _memory_cache:
                value_packed, expires_at = _memory_cache[key]
                if time.time() > expires_at:
                    del _memory_cache[key]
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

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, do_get)
        elapsed = (time.time() - start_time) * 1000
        self._metrics.total_get_time_ms += elapsed
        if result is not None:
            self._metrics.hits += 1
        else:
            self._metrics.misses += 1
        return result

    async def set(self, key: str, value: Any, ttl: Optional[int] = None, compress: bool = True):
        await self._ensure_connection()
        start_time = time.time()
        ttl_value = ttl if ttl is not None else self._config.default_ttl
        expires_at = time.time() + ttl_value

        if self._use_memory:
            packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
            if compress:
                packed = self._compress(packed)
            _memory_cache[key] = (packed, expires_at)
            self._metrics.sets += 1
            self._metrics.total_set_time_ms += (time.time() - start_time) * 1000
            return

        def do_set():
            try:
                packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                if compress:
                    packed = self._compress(packed)
                self._connection.replace(self._space, (key, packed, expires_at))
            except Exception as e:
                logger.error(f"Error on SET {key}: {e}", component="tarantool")

        loop = asyncio.get_event_loop()
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

        loop = asyncio.get_event_loop()
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
                    value_packed, expires_at = _memory_cache[key]
                    if now <= expires_at:
                        data = self._decompress(value_packed)
                        results[key] = msgpack.unpackb(data, raw=False)
                        self._metrics.hits += 1
                    else:
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

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(_executor, do_batch_get)
        elapsed = (time.time() - start_time) * 1000
        self._metrics.total_get_time_ms += elapsed
        self._metrics.hits += len(results)
        self._metrics.misses += len(keys) - len(results)
        return results

    async def set_many(self, items: Dict[str, Any], ttl: Optional[int] = None, compress: bool = True, _is_chunk: bool = False):
        await self._ensure_connection()
        if not _is_chunk:
            self._metrics.batch_operations += 1
        start_time = time.time()
        ttl_value = ttl if ttl is not None else self._config.default_ttl
        expires_at = time.time() + ttl_value

        if len(items) > self._config.max_batch_size:
            chunks = [dict(list(items.items())[i:i + self._config.max_batch_size])
                      for i in range(0, len(items), self._config.max_batch_size)]
            for chunk in chunks:
                await self.set_many(chunk, ttl, compress, _is_chunk=True)
            return

        if self._use_memory:
            for key, value in items.items():
                packed = msgpack.packb(value, use_bin_type=True, strict_types=False)
                if compress:
                    packed = self._compress(packed)
                _memory_cache[key] = (packed, expires_at)
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
                    self._connection.replace(self._space, (key, packed, expires_at))
                except Exception as e:
                    logger.warning(f"Error in batch set for {key}: {e}", component="tarantool")

        loop = asyncio.get_event_loop()
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

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, do_batch_delete)
        self._metrics.deletes += len(keys)

    async def cache_search_result(self, query: str, result: Any, service: str = "default"):
        key = self._generate_search_key(query, service)
        await self.set(key, result, ttl=self._config.search_cache_ttl)
        self._search_cache[key] = (result, time.time() + self._config.search_cache_ttl)

    async def get_cached_search(self, query: str, service: str = "default") -> Optional[Any]:
        key = self._generate_search_key(query, service)
        if key in self._search_cache:
            result, expires_at = self._search_cache[key]
            if time.time() <= expires_at:
                self._metrics.hits += 1
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

        def do_prefix_delete():
            try:
                result = self._connection.select(self._space)
                deleted = 0
                for row in result:
                    if len(row) >= 1 and row[0].startswith(prefix):
                        self._connection.delete(self._space, row[0])
                        deleted += 1
                return deleted
            except Exception as e:
                logger.error(f"Error deleting by prefix {prefix}: {e}", component="tarantool")
                return 0

        loop = asyncio.get_event_loop()
        deleted = await loop.run_in_executor(_executor, do_prefix_delete)
        self._metrics.deletes += deleted

    def get_metrics(self) -> Dict[str, Any]:
        return self._metrics.to_dict()

    def reset_metrics(self):
        self._metrics.reset()

    def get_cache_size(self) -> int:
        if self._use_memory:
            return len(_memory_cache)
        return 0

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
