"""
CachedClientMixin: общий паттерн L1/L2 кэширования для API-клиентов.

Извлечён из PerplexityClient и TavilyClient для устранения дублирования.
Обеспечивает:
- L1 in-memory LRU-кэш (OrderedDict, bounded, TTL)
- L2 кэш через Tarantool (shared across workers)
- Inflight coalescing (один внешний вызов на cache_key)
"""

import asyncio
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

from app.shared.toolkit.logging import logger


class CachedClientMixin:
    """
    Mixin для API-клиентов с L1/L2 кэшированием и inflight coalescing.

    Использование:
        class MyClient(CachedClientMixin):
            def __init__(self):
                self._init_cache(max_size=200, ttl_s=300, source_name="my_client")
    """

    def _init_cache(
        self,
        max_size: int = 200,
        ttl_s: int = 300,
        source_name: str = "unknown",
    ) -> None:
        """Initialize cache state. Call from __init__."""
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._cache_max_size: int = max_size
        self._cache_ttl_s: int = ttl_s
        self._cache_source_name: str = source_name
        self._inflight: Dict[str, asyncio.Future] = {}

    # ------------------------------------------------------------------
    # L1: in-memory LRU cache
    # ------------------------------------------------------------------

    def _cache_get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get from L1 cache with TTL check and LRU promotion."""
        cached = self._cache.get(cache_key)
        if not cached:
            return None
        created_at = cached.get("_created_at", 0.0)
        if created_at and (time.time() - float(created_at)) > self._cache_ttl_s:
            self._cache.pop(cache_key, None)
            return None
        self._cache.move_to_end(cache_key)
        return cached

    def _cache_set(self, cache_key: str, value: Dict[str, Any]) -> None:
        """Set in L1 cache with LRU eviction."""
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
        self._cache[cache_key] = {**value, "_created_at": time.time()}
        while len(self._cache) > self._cache_max_size:
            self._cache.popitem(last=False)

    # ------------------------------------------------------------------
    # L2: Tarantool shared cache
    # ------------------------------------------------------------------

    async def _l2_cache_get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get from L2 (Tarantool) cache. Returns None on miss or error."""
        try:
            from app.storage.tarantool import TarantoolClient

            t = await TarantoolClient.get_instance()
            repo = t.get_cache_repository()
            return await repo.get(cache_key)
        except Exception:
            return None

    async def _l2_cache_set(self, cache_key: str, value: Dict[str, Any]) -> None:
        """Set in L2 (Tarantool) cache. Best-effort, silently ignores errors."""
        try:
            from app.storage.tarantool import TarantoolClient

            t = await TarantoolClient.get_instance()
            repo = t.get_cache_repository()
            await repo.set_with_ttl(
                cache_key,
                value,
                ttl=self._cache_ttl_s,
                source=self._cache_source_name,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Inflight coalescing
    # ------------------------------------------------------------------

    def _inflight_get(self, cache_key: str) -> Optional[asyncio.Future]:
        """Get existing inflight future for cache_key, if any."""
        return self._inflight.get(cache_key)

    def _inflight_start(self, cache_key: str) -> asyncio.Future:
        """Create and register inflight future for cache_key."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._inflight[cache_key] = fut
        return fut

    def _inflight_resolve(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Resolve and remove inflight future."""
        inflight = self._inflight.pop(cache_key, None)
        if inflight is not None and not inflight.done():
            inflight.set_result(result)

    # ------------------------------------------------------------------
    # Combined lookup: L1 → L2 → inflight
    # ------------------------------------------------------------------

    async def _cache_lookup(
        self,
        cache_key: str,
        l2_enabled: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Combined cache lookup: L1 → L2 → inflight.

        Returns cached data or None if miss on all levels.
        """
        # L1
        cached = self._cache_get(cache_key)
        if cached:
            logger.info(
                f"{self._cache_source_name} cache hit (L1)",
                component=self._cache_source_name,
            )
            return cached

        # L2
        if l2_enabled:
            l2 = await self._l2_cache_get(cache_key)
            if l2:
                self._cache_set(cache_key, l2)
                logger.info(
                    f"{self._cache_source_name} cache hit (L2/Tarantool)",
                    component=self._cache_source_name,
                )
                return l2

        # Inflight coalescing
        inflight = self._inflight_get(cache_key)
        if inflight is not None:
            return await inflight

        return None

    async def _cache_store(
        self,
        cache_key: str,
        data: Dict[str, Any],
        l2_enabled: bool = True,
    ) -> None:
        """Store result in L1 + L2 + resolve inflight."""
        cached_data = {**data, "cached": True}
        self._cache_set(cache_key, cached_data)
        if l2_enabled:
            await self._l2_cache_set(cache_key, cached_data)
        self._inflight_resolve(cache_key, cached_data)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Clear L1 cache."""
        self._cache.clear()
        logger.info(
            f"{self._cache_source_name} cache cleared (L1)",
            component=self._cache_source_name,
        )

    def get_cache_stats(self) -> Dict[str, int]:
        """Get L1 cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl_s,
        }
