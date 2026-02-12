"""
Threads Repository - управление историей диалогов/анализов.

Работает с threads space, предоставляя API для:
- Сохранения истории анализов
- Поиска по ИНН и названию клиента
- Пагинации и сортировки
- Без TTL (хранится бессрочно)
"""

import time
from typing import Any, Dict, List, Optional

from app.storage.repositories import BaseRepository
from app.shared.toolkit.logging import logger


class ThreadsRepository(BaseRepository[Dict[str, Any]]):
    """
    Repository для threads space.

    Управляет историей диалогов/анализов клиентов.
    Данные хранятся бессрочно (без TTL).
    """

    def __init__(self, tarantool_client):
        super().__init__(tarantool_client)
        self.space_name = "threads"

    async def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить thread по ID.

        Args:
            thread_id: Уникальный ID thread

        Returns:
            Thread data или None если не найден
        """
        try:
            # Threads хранятся с ключом thread:{id}
            key = f"thread:{thread_id}" if not thread_id.startswith("thread:") else thread_id
            result = await self.client.get_persistent(key)

            if result is None:
                return None

            return result

        except Exception as e:
            logger.error(f"Thread get error for {thread_id}: {e}", component="threads_repo")
            return None

    async def create(self, data: Dict[str, Any]) -> str:
        """
        Создать новый thread.

        Args:
            data: Данные thread, должны содержать:
                - thread_id: str (уникальный ID)
                - thread_data: dict (основные данные)
                - client_name: str (optional)
                - inn: str (optional)

        Returns:
            thread_id
        """
        thread_id = data.get("thread_id")
        if not thread_id:
            raise ValueError("thread_id is required")

        thread_data = data.get("thread_data", {})
        client_name = data.get("client_name", "")
        inn = data.get("inn", "")
        now = time.time()

        # Если client_name/inn не переданы, пытаемся извлечь из thread_data
        if not client_name and isinstance(thread_data, dict):
            client_name = thread_data.get("client_name", "")
        if not inn and isinstance(thread_data, dict):
            inn = thread_data.get("inn", "")

        thread_record = {
            "thread_id": thread_id,
            "thread_data": thread_data,
            "created_at": now,
            "updated_at": now,
            "client_name": client_name,
            "inn": inn,
        }

        try:
            key = f"thread:{thread_id}"
            await self.client.set_persistent(key, thread_record)

            logger.structured(
                "info",
                "thread_created",
                component="threads_repo",
                thread_id=thread_id,
                client_name=client_name[:30] if client_name else "",
            )

            return thread_id

        except Exception as e:
            logger.error(f"Thread create error: {e}", component="threads_repo")
            raise

    async def save_thread(
        self,
        thread_id: str,
        thread_data: Dict[str, Any],
        client_name: str = "",
        inn: str = "",
    ) -> str:
        """
        Сохранить или обновить thread (упрощенный метод).

        Args:
            thread_id: ID thread
            thread_data: Данные thread
            client_name: Название клиента (optional)
            inn: ИНН клиента (optional)

        Returns:
            thread_id
        """
        existing = await self.get(thread_id)

        if existing:
            # Обновляем существующий
            return (
                await self.update(
                    thread_id,
                    {
                        "thread_data": thread_data,
                        "client_name": client_name or existing.get("client_name", ""),
                        "inn": inn or existing.get("inn", ""),
                    },
                )
                and thread_id
                or thread_id
            )
        else:
            # Создаем новый
            return await self.create(
                {
                    "thread_id": thread_id,
                    "thread_data": thread_data,
                    "client_name": client_name,
                    "inn": inn,
                }
            )

    async def update(self, thread_id: str, data: Dict[str, Any]) -> bool:
        """
        Обновить существующий thread.

        Args:
            thread_id: ID thread
            data: Новые данные (частичное обновление)

        Returns:
            True если обновлено
        """
        try:
            existing = await self.get(thread_id)
            if not existing:
                logger.warning(
                    f"Thread not found for update: {thread_id}",
                    component="threads_repo",
                )
                return False

            # Обновляем поля
            existing.update(data)
            existing["updated_at"] = time.time()

            # Сохраняем обратно
            key = f"thread:{thread_id}"
            await self.client.set_persistent(key, existing)

            logger.debug(f"Thread updated: {thread_id}", component="threads_repo")
            return True

        except Exception as e:
            logger.error(f"Thread update error for {thread_id}: {e}", component="threads_repo")
            return False

    async def delete(self, thread_id: str) -> bool:
        """
        Удалить thread.

        Args:
            thread_id: ID thread

        Returns:
            True если удалено
        """
        try:
            key = f"thread:{thread_id}"
            await self.client.delete_persistent(key)

            logger.debug(f"Thread deleted: {thread_id}", component="threads_repo")
            return True

        except Exception as e:
            logger.error(f"Thread delete error for {thread_id}: {e}", component="threads_repo")
            return False

    async def list(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Получить список threads с пагинацией.

        Сортировка: по created_at DESC (новые первые).

        Args:
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список threads
        """
        try:
            # Используем существующий метод list_threads из TarantoolClient
            threads = await self.client.list_threads(limit=limit)
            return threads

        except Exception as e:
            logger.error(f"Threads list error: {e}", component="threads_repo")
            return []

    async def list_threads_by_inn(self, inn: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получить threads по ИНН.

        Args:
            inn: ИНН клиента
            limit: Максимальное количество

        Returns:
            Список threads для данного ИНН
        """
        from app.shared.security import mask_inn

        logger.debug(f"Get threads by INN: {mask_inn(inn)}", component="threads_repo")
        # Оптимизированный поиск с ранней фильтрацией
        return await self.client.search_threads_by_field(
            field_name="inn",
            field_value=inn,
            limit=limit,
            partial_match=False,
        )

    async def list_threads_by_client_name(self, client_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получить threads по названию клиента.

        Args:
            client_name: Название клиента (точное совпадение)
            limit: Максимальное количество

        Returns:
            Список threads для данного клиента
        """
        logger.debug(f"Get threads by client name: {client_name}", component="threads_repo")
        # Оптимизированный поиск с ранней фильтрацией
        return await self.client.search_threads_by_field(
            field_name="client_name",
            field_value=client_name,
            limit=limit,
            partial_match=False,
        )

    async def search_threads(self, filters: Optional[Dict[str, Any]] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Поиск threads с фильтрами.

        Args:
            filters: Фильтры:
                - inn: str
                - client_name: str (partial match)
                - date_from: timestamp
                - date_to: timestamp
            limit: Максимальное количество

        Returns:
            Список threads, соответствующих фильтрам
        """
        if not filters:
            return await self.list(limit=limit)

        # Оптимизация: используем поиск по полю с ранней фильтрацией
        # если есть только один фильтр (INN или client_name)
        has_date_filters = "date_from" in filters or "date_to" in filters

        # Если только INN фильтр - используем оптимизированный поиск
        if "inn" in filters and "client_name" not in filters and not has_date_filters:
            return await self.client.search_threads_by_field(
                field_name="inn",
                field_value=filters["inn"],
                limit=limit,
                partial_match=False,
            )

        # Если только client_name фильтр - используем оптимизированный поиск
        if "client_name" in filters and "inn" not in filters and not has_date_filters:
            return await self.client.search_threads_by_field(
                field_name="client_name",
                field_value=filters["client_name"],
                limit=limit,
                partial_match=True,  # partial match для client_name
            )

        # Для комбинированных фильтров: сначала фильтруем по главному полю,
        # затем применяем остальные фильтры
        if "inn" in filters:
            filtered = await self.client.search_threads_by_field(
                field_name="inn",
                field_value=filters["inn"],
                limit=limit * 2,  # берем больше для последующей фильтрации
                partial_match=False,
            )
        elif "client_name" in filters:
            filtered = await self.client.search_threads_by_field(
                field_name="client_name",
                field_value=filters["client_name"],
                limit=limit * 2,
                partial_match=True,
            )
        else:
            # Только date фильтры - загружаем все
            filtered = await self.list(limit=limit * 2)

        # Применяем оставшиеся фильтры
        if "date_from" in filters:
            filtered = [t for t in filtered if t.get("created_at", 0) >= filters["date_from"]]

        if "date_to" in filters:
            filtered = [t for t in filtered if t.get("created_at", 0) <= filters["date_to"]]

        return filtered[:limit]

    async def count(self) -> int:
        """
        Получить общее количество threads.

        Ограничение: максимум 10000 записей для in-memory режима.
        Для production с Tarantool рекомендуется использовать box.space:len().

        Returns:
            Количество threads в space (до 10000)
        """
        try:
            threads = await self.client.list_threads(limit=10000)
            return len(threads)
        except Exception as e:
            logger.error(f"Threads count error: {e}", component="threads_repo")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику по threads.

        Returns:
            Статистика: total, recent, etc.
        """
        try:
            threads = await self.client.list_threads(limit=10000)
            total = len(threads)
            now = time.time()
            day_ago = now - 86400
            week_ago = now - 604800
            month_ago = now - 2592000

            recent_24h = sum(1 for t in threads if t.get("created_at", 0) >= day_ago)
            recent_7d = sum(1 for t in threads if t.get("created_at", 0) >= week_ago)
            recent_30d = sum(1 for t in threads if t.get("created_at", 0) >= month_ago)

            return {
                "total": total,
                "recent_24h": recent_24h,
                "recent_7d": recent_7d,
                "recent_30d": recent_30d,
            }
        except Exception as e:
            logger.error(f"Threads stats error: {e}", component="threads_repo")
            return {
                "total": 0,
                "recent_24h": 0,
                "recent_7d": 0,
                "recent_30d": 0,
            }


__all__ = ["ThreadsRepository"]
