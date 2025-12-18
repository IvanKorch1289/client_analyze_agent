"""
Cache Repository - управление кешем в Tarantool.

Работает с cache space, предоставляя удобный API для:
- Сохранения данных с TTL
- Получения с автоматической проверкой истечения
- Статистики по источникам данных
- Очистки просроченных записей
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from app.storage.repositories import BaseRepository
from app.utility.logging_client import logger


class CacheRepository(BaseRepository[Dict[str, Any]]):
    """
    Repository для cache space.
    
    Управляет кешем с TTL для API запросов и других временных данных.
    Автоматически проверяет и удаляет просроченные записи.
    """
    
    def __init__(self, tarantool_client):
        super().__init__(tarantool_client)
        self.space_name = "cache"
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Получить значение из кеша.
        
        Автоматически проверяет TTL и удаляет просроченные записи.
        
        Args:
            key: Ключ кеша
            
        Returns:
            Значение или None если не найдено/просрочено
        """
        try:
            result = await self.client.get(key)
            if result is None:
                return None
            
            # Проверка TTL (если это dict с ttl)
            if isinstance(result, dict) and "ttl" in result:
                if result["ttl"] < time.time():
                    # Просрочен, удаляем
                    await self.delete(key)
                    logger.debug(
                        f"Cache key expired and deleted: {key}",
                        component="cache_repo"
                    )
                    return None
            
            return result
            
        except Exception as e:
            logger.error(
                f"Cache get error for key {key}: {e}",
                component="cache_repo"
            )
            return None
    
    async def create(self, data: Dict[str, Any]) -> str:
        """
        Создать запись в кеше.
        
        Args:
            data: Должен содержать 'key', 'value', 'ttl' (optional), 'source' (optional)
            
        Returns:
            Ключ созданной записи
            
        Raises:
            ValueError: Если key не указан
        """
        key = data.get("key")
        value = data.get("value")
        ttl = data.get("ttl", 3600)  # Default 1 hour
        source = data.get("source", "unknown")
        
        if not key:
            raise ValueError("Cache key is required")
        
        await self.client.set(key, value, ttl)
        
        logger.debug(
            f"Cache created: {key} (ttl={ttl}s, source={source})",
            component="cache_repo"
        )
        
        return key
    
    async def set_with_ttl(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        source: str = "api"
    ) -> bool:
        """
        Упрощенный метод для установки значения с TTL.
        
        Args:
            key: Ключ кеша
            value: Значение (любой сериализуемый тип)
            ttl: TTL в секундах (default: 3600 = 1 час)
            source: Источник данных для статистики (default: "api")
            
        Returns:
            True если успешно сохранено
        """
        try:
            await self.client.set(key, value, ttl)
            return True
        except Exception as e:
            logger.error(
                f"Cache set error for key {key}: {e}",
                component="cache_repo"
            )
            return False
    
    async def update(self, key: str, data: Dict[str, Any]) -> bool:
        """
        Обновить запись в кеше.
        
        Для cache это эквивалентно create (перезапись).
        
        Args:
            key: Ключ кеша
            data: Новые данные
            
        Returns:
            True если успешно
        """
        try:
            await self.create({**data, "key": key})
            return True
        except Exception as e:
            logger.error(
                f"Cache update error for key {key}: {e}",
                component="cache_repo"
            )
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Удалить запись из кеша.
        
        Args:
            key: Ключ кеша
            
        Returns:
            True если удалено (или не существовало)
        """
        try:
            await self.client.delete(key)
            logger.debug(f"Cache deleted: {key}", component="cache_repo")
            return True
        except Exception as e:
            logger.error(
                f"Cache delete error for key {key}: {e}",
                component="cache_repo"
            )
            return False
    
    async def list(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Получить список записей из кеша.
        
        Note: Не рекомендуется для больших кешей, так как требует
        полного сканирования space.
        
        Args:
            limit: Максимальное количество записей
            offset: Смещение
            
        Returns:
            Список записей (может быть пустым)
        """
        logger.warning(
            "Cache list() не оптимален для больших объемов",
            component="cache_repo"
        )
        # TODO: Implement через прямое обращение к Tarantool
        # Пока возвращаем пустой список
        return []
    
    async def clear_all(self) -> int:
        """
        Очистить весь кеш.
        
        ВНИМАНИЕ: Удаляет ВСЕ записи из cache space.
        
        Returns:
            Количество удаленных записей (0 если Tarantool не возвращает count)
        """
        try:
            await self.client.clear_cache()
            logger.info("All cache cleared", component="cache_repo")
            return 0  # Tarantool clear не возвращает count
        except Exception as e:
            logger.error(f"Cache clear error: {e}", component="cache_repo")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику кеша.
        
        Returns:
            Статистика: hits, misses, hit_rate, avg_get_time, etc.
        """
        try:
            stats = await self.client.get_cache_stats()
            return stats
        except Exception as e:
            logger.error(f"Cache stats error: {e}", component="cache_repo")
            return {
                "hits": 0,
                "misses": 0,
                "hit_rate_percent": 0,
                "error": str(e)
            }
    
    async def get_stats_by_source(self, source: str) -> Dict[str, int]:
        """
        Получить статистику по источнику данных.
        
        Args:
            source: Название источника (например, "dadata", "perplexity")
            
        Returns:
            Статистика для источника
            
        Note:
            Требует прямой запрос к Tarantool по индексу source_idx.
            Пока возвращает заглушку.
        """
        # TODO: Implement через прямое обращение к Tarantool
        logger.debug(
            f"Stats by source requested: {source}",
            component="cache_repo"
        )
        return {"count": 0, "source": source}
    
    async def cleanup_expired(self) -> int:
        """
        Принудительная очистка просроченных записей.
        
        Note: Обычно не требуется, так как фоновая задача в Tarantool
        автоматически очищает просроченные записи каждый час.
        
        Returns:
            Количество удаленных записей (0 если не реализовано)
        """
        logger.info(
            "Cleanup expired cache triggered (runs automatically in Tarantool)",
            component="cache_repo"
        )
        # Cleanup выполняется автоматически фоновой задачей в init.lua
        return 0
    
    async def count(self) -> int:
        """
        Получить количество записей в cache.
        
        Returns:
            Количество записей
        """
        try:
            # TarantoolClient может не иметь прямого метода len()
            # Пока возвращаем 0
            return 0
        except Exception:
            return 0


__all__ = ["CacheRepository"]
