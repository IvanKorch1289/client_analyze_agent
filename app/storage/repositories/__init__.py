"""
Repository pattern для работы с Tarantool.

Каждый repository отвечает за один space и предоставляет
типизированный API для работы с данными.

Архитектура:
- BaseRepository: абстрактный базовый класс
- CacheRepository: cache space (TTL)
- ReportsRepository: reports space (TTL 30 дней)
- ThreadsRepository: threads space (без TTL)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """
    Базовый класс для всех repositories.

    Определяет общий интерфейс для CRUD операций.
    Каждый наследник работает с конкретным Tarantool space.

    Generic параметр T определяет тип возвращаемых данных.
    """

    def __init__(self, tarantool_client):
        """
        Args:
            tarantool_client: Экземпляр TarantoolClient
        """
        self.client = tarantool_client
        self.space_name: str = ""  # Должен быть переопределен в наследниках

    @abstractmethod
    async def get(self, key: str) -> Optional[T]:
        """
        Получить запись по ключу.

        Args:
            key: Первичный ключ записи

        Returns:
            Запись или None если не найдена
        """
        pass

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> str:
        """
        Создать новую запись.

        Args:
            data: Данные для создания записи

        Returns:
            Ключ созданной записи
        """
        pass

    @abstractmethod
    async def update(self, key: str, data: Dict[str, Any]) -> bool:
        """
        Обновить существующую запись.

        Args:
            key: Первичный ключ записи
            data: Новые данные

        Returns:
            True если обновлено, False если не найдено
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Удалить запись.

        Args:
            key: Первичный ключ записи

        Returns:
            True если удалено, False если не найдено
        """
        pass

    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> List[T]:
        """
        Получить список записей с пагинацией.

        Args:
            limit: Максимальное количество записей
            offset: Смещение для пагинации

        Returns:
            Список записей
        """
        pass

    async def exists(self, key: str) -> bool:
        """
        Проверить существование записи.

        Args:
            key: Первичный ключ записи

        Returns:
            True если запись существует
        """
        result = await self.get(key)
        return result is not None

    async def count(self) -> int:
        """
        Получить общее количество записей в space.

        Returns:
            Количество записей

        Note:
            Эта операция может быть медленной для больших space.
        """
        try:
            # Tarantool box.space.X:len() - быстрая операция
            # Реализация в наследниках через client
            return 0
        except Exception:
            return 0


from app.storage.repositories.cache_repository import CacheRepository
from app.storage.repositories.reports_repository import (
    REPORT_TTL_DAYS,
    REPORT_TTL_SECONDS,
    ReportsRepository,
)
from app.storage.repositories.threads_repository import ThreadsRepository

__all__ = [
    "BaseRepository",
    "CacheRepository",
    "ReportsRepository",
    "ThreadsRepository",
    "REPORT_TTL_DAYS",
    "REPORT_TTL_SECONDS",
]
