"""
Scheduler Service - управление отложенными задачами.

Позволяет создавать отложенные задачи, которые выполнятся через заданное время.
Использует APScheduler для планирования и выполнения задач.

Примеры использования:
    # Создать задачу, которая выполнится через 5 минут
    task_id = await scheduler.schedule_client_analysis(
        client_name="ООО Ромашка",
        inn="1234567890",
        delay_minutes=5
    )

    # Создать задачу на конкретное время
    task_id = await scheduler.schedule_client_analysis_at(
        client_name="ООО Ромашка",
        inn="1234567890",
        run_date=datetime(2025, 12, 20, 15, 30)
    )

    # Отменить задачу
    await scheduler.cancel_task(task_id)
"""

import asyncio
import fcntl
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.shared.toolkit.logging import logger

# Ключ для хранения задач в Tarantool
SCHEDULER_JOBS_KEY = "scheduler:pending_jobs"

# Distributed lock: only one gunicorn worker should run the scheduler.
try:
    from app.config.settings import settings as _sched_settings

    _SCHEDULER_LOCK_PATH = Path(_sched_settings.scheduler.lock_path)
except Exception:
    _SCHEDULER_LOCK_PATH = Path("/tmp/scheduler.lock")


class SchedulerService:
    """
    Сервис для управления отложенными задачами.

    Использует APScheduler для планирования асинхронных задач.
    Поддерживает одноразовые отложенные задачи и периодические задачи.
    """

    _instance: Optional["SchedulerService"] = None

    def __init__(self):
        """Инициализация Scheduler."""
        self.scheduler = AsyncIOScheduler(
            timezone="Europe/Moscow",
            job_defaults={
                "coalesce": False,
                "max_instances": 3,
                "misfire_grace_time": 300,  # 5 минут
            },
        )

        # Хранилище метаданных задач (bounded to prevent memory leak)
        self._tasks_metadata: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._tasks_metadata_max_size: int = 1000

        self._started = False

        logger.info("SchedulerService initialized", component="scheduler")

    async def _persist_task(self, task_id: str, task_data: Dict[str, Any]) -> None:
        """
        P1: Сохраняет задачу в Tarantool для персистентности.

        При перезапуске сервиса задачи могут быть восстановлены из storage.
        """
        try:
            from app.storage.tarantool import TarantoolClient

            client = await TarantoolClient.get_instance()

            # Получаем текущий список задач
            jobs_data = await client.get_persistent(SCHEDULER_JOBS_KEY) or {"jobs": {}}
            jobs = jobs_data.get("jobs", {})

            # Добавляем/обновляем задачу
            jobs[task_id] = {
                **task_data,
                "scheduled_at": (
                    task_data["scheduled_at"].isoformat()
                    if isinstance(task_data.get("scheduled_at"), datetime)
                    else task_data.get("scheduled_at")
                ),
                "run_date": (
                    task_data["run_date"].isoformat()
                    if isinstance(task_data.get("run_date"), datetime)
                    else task_data.get("run_date")
                ),
            }

            await client.set_persistent(SCHEDULER_JOBS_KEY, {"jobs": jobs})
            logger.debug(f"Task {task_id} persisted to storage", component="scheduler")

        except Exception as e:
            logger.warning(f"Failed to persist task {task_id}: {e}", component="scheduler")

    async def _remove_persisted_task(self, task_id: str) -> None:
        """Удаляет завершённую/отменённую задачу из persistent storage."""
        try:
            from app.storage.tarantool import TarantoolClient

            client = await TarantoolClient.get_instance()
            jobs_data = await client.get_persistent(SCHEDULER_JOBS_KEY) or {"jobs": {}}
            jobs = jobs_data.get("jobs", {})

            if task_id in jobs:
                del jobs[task_id]
                await client.set_persistent(SCHEDULER_JOBS_KEY, {"jobs": jobs})
                logger.debug(
                    f"Task {task_id} removed from persistent storage",
                    component="scheduler",
                )

        except Exception as e:
            logger.warning(f"Failed to remove persisted task {task_id}: {e}", component="scheduler")

    async def restore_pending_jobs(self) -> int:
        """
        P1: Восстанавливает ожидающие задачи из persistent storage.

        Вызывается при старте сервиса для восстановления задач после перезапуска.

        Returns:
            Количество восстановленных задач
        """
        try:
            from app.storage.tarantool import TarantoolClient

            client = await TarantoolClient.get_instance()
            jobs_data = await client.get_persistent(SCHEDULER_JOBS_KEY) or {"jobs": {}}
            jobs = jobs_data.get("jobs", {})

            restored = 0
            now = datetime.now()

            for task_id, task_data in list(jobs.items()):
                try:
                    run_date_str = task_data.get("run_date")
                    if not run_date_str:
                        continue

                    run_date = datetime.fromisoformat(run_date_str)

                    # Пропускаем просроченные задачи
                    if run_date < now:
                        logger.warning(
                            f"Skipping expired task {task_id} (was scheduled for {run_date})",
                            component="scheduler",
                        )
                        await self._remove_persisted_task(task_id)
                        continue

                    # Для client_analysis задач - восстанавливаем
                    func_name = task_data.get("func_name", "")
                    metadata = task_data.get("metadata", {})

                    if func_name == "_execute_analysis" and metadata:
                        await self.schedule_client_analysis(
                            client_name=metadata.get("client_name", "Unknown"),
                            inn=metadata.get("inn", ""),
                            additional_notes=metadata.get("additional_notes", ""),
                            run_date=run_date,
                            task_id=task_id,
                        )
                        restored += 1
                        logger.info(f"Restored task {task_id}", component="scheduler")

                except Exception as e:
                    logger.error(f"Failed to restore task {task_id}: {e}", component="scheduler")

            if restored > 0:
                logger.info(
                    f"Restored {restored} pending tasks from storage",
                    component="scheduler",
                )

            return restored

        except Exception as e:
            logger.error(f"Failed to restore pending jobs: {e}", component="scheduler")
            return 0

    @classmethod
    def get_instance(cls) -> "SchedulerService":
        """
        Получить singleton экземпляр SchedulerService.

        Returns:
            SchedulerService: Единственный экземпляр
        """
        if cls._instance is None:
            cls._instance = SchedulerService()
        return cls._instance

    def _acquire_leader_lock(self) -> bool:
        """Try to acquire a file-based leader lock (prevents duplicate schedulers in multi-worker setup)."""
        try:
            self._lock_fd = open(_SCHEDULER_LOCK_PATH, "w")
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
            return True
        except (IOError, OSError):
            logger.info("Scheduler lock held by another worker, skipping", component="scheduler")
            return False

    def _release_leader_lock(self) -> None:
        """Release the file-based leader lock."""
        fd = getattr(self, "_lock_fd", None)
        if fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                fd.close()
            except Exception:
                pass

    def start(self):
        """Запустить scheduler (only if this worker acquires the leader lock)."""
        if not self._started:
            if not self._acquire_leader_lock():
                return
            self.scheduler.start()
            self._started = True
            logger.info("Scheduler started (leader worker)", component="scheduler")

    def shutdown(self):
        """Остановить scheduler и освободить leader lock."""
        if self._started:
            self.scheduler.shutdown(wait=True)
            self._started = False
            self._release_leader_lock()
            logger.info("Scheduler stopped", component="scheduler")

    async def schedule_task(
        self,
        func: Callable,
        task_id: Optional[str] = None,
        delay_seconds: Optional[int] = None,
        delay_minutes: Optional[int] = None,
        run_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        Запланировать выполнение задачи.

        Args:
            func: Функция для выполнения
            task_id: ID задачи (если None - генерируется автоматически)
            delay_seconds: Задержка в секундах
            delay_minutes: Задержка в минутах
            run_date: Конкретная дата/время выполнения
            metadata: Метаданные задачи (для отслеживания)
            **kwargs: Аргументы для func

        Returns:
            str: ID созданной задачи

        Raises:
            ValueError: Если не указано ни delay, ни run_date
        """
        if not self._started:
            self.start()

        # Генерируем ID если не указан
        if task_id is None:
            task_id = f"task_{uuid.uuid4()}"

        # Определяем время выполнения
        if run_date is None:
            if delay_seconds:
                run_date = datetime.now() + timedelta(seconds=delay_seconds)
            elif delay_minutes:
                run_date = datetime.now() + timedelta(minutes=delay_minutes)
            else:
                raise ValueError("Either delay_seconds, delay_minutes or run_date must be specified")

        # Сохраняем метаданные (evict oldest if at capacity)
        if len(self._tasks_metadata) >= self._tasks_metadata_max_size:
            self._tasks_metadata.popitem(last=False)
        self._tasks_metadata[task_id] = {
            "task_id": task_id,
            "func_name": func.__name__,
            "scheduled_at": datetime.now(),
            "run_date": run_date,
            "status": "scheduled",
            "metadata": metadata or {},
        }

        # Добавляем задачу в scheduler
        self.scheduler.add_job(
            func=func,
            trigger=DateTrigger(run_date=run_date),
            id=task_id,
            kwargs=kwargs,
            replace_existing=True,
        )

        logger.structured(
            "info",
            "task_scheduled",
            component="scheduler",
            task_id=task_id,
            func=func.__name__,
            run_date=run_date.isoformat(),
            delay_seconds=(run_date - datetime.now()).total_seconds(),
        )

        # P1: Сохраняем в persistent storage
        asyncio.create_task(self._persist_task(task_id, self._tasks_metadata[task_id]))

        return task_id

    async def schedule_client_analysis(
        self,
        client_name: str,
        inn: str,
        additional_notes: str = "",
        delay_minutes: Optional[int] = None,
        delay_seconds: Optional[int] = None,
        run_date: Optional[datetime] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        Запланировать анализ клиента.

        Args:
            client_name: Название клиента
            inn: ИНН клиента
            additional_notes: Дополнительные заметки
            delay_minutes: Задержка в минутах
            delay_seconds: Задержка в секундах
            run_date: Конкретное время выполнения
            task_id: ID задачи (опционально)

        Returns:
            str: ID созданной задачи

        Example:
            # Выполнить через 5 минут
            task_id = await scheduler.schedule_client_analysis(
                client_name="ООО Ромашка",
                inn="1234567890",
                delay_minutes=5
            )
        """
        metadata = {
            "type": "client_analysis",
            "client_name": client_name,
            "inn": inn,
            "additional_notes": additional_notes,
        }

        return await self.schedule_task(
            func=self._execute_client_analysis,
            task_id=task_id,
            delay_minutes=delay_minutes,
            delay_seconds=delay_seconds,
            run_date=run_date,
            metadata=metadata,
            client_name=client_name,
            inn=inn,
            additional_notes=additional_notes,
        )

    async def _execute_client_analysis(self, client_name: str, inn: str, additional_notes: str = ""):
        """
        Внутренний метод для выполнения анализа клиента.

        Вызывается scheduler'ом в нужное время.
        """
        # Если включён RabbitMQ режим — отдаём выполнение воркеру (FastStream),
        # а scheduler остаётся только “планировщиком”.
        #
        # Это даёт горизонтальное масштабирование и разгружает web-процесс.
        from app.services.app_actions import dispatch_client_analysis

        # Scheduler “fire-and-forget”: если включена очередь — вернётся ACK,
        # если нет — выполнится синхронно (in-process).
        dispatch_result = await dispatch_client_analysis(
            client_name=client_name,
            inn=inn,
            additional_notes=additional_notes,
            save_report=True,
            prefer_queue=None,
        )
        if dispatch_result.get("queued"):
            logger.info("Задача отправлена в очередь RabbitMQ", component="scheduler")
            return

        # Если не queued — значит выполнили in-process и получили полный результат.
        result = dispatch_result
        task_id = f"analysis_{inn}_{int(time.time())}"

        logger.info(
            f"Starting scheduled client analysis: {client_name} (INN: {inn})",
            component="scheduler",
        )

        status = str(result.get("status") or "unknown")
        is_ok = status == "completed"

        logger.structured(
            "info" if is_ok else "warning",
            "scheduled_analysis_completed" if is_ok else "scheduled_analysis_finished",
            component="scheduler",
            client_name=client_name,
            inn=inn,
            status=status,
            session_id=result.get("session_id"),
        )

        # Обновляем метаданные задачи (если мы действительно трекаем этот task_id).
        if task_id in self._tasks_metadata:
            self._tasks_metadata[task_id].update(
                {
                    "status": "completed" if is_ok else "failed",
                    "result_status": status,
                    "session_id": result.get("session_id"),
                    "completed_at": datetime.now(),
                }
            )

            # P1: Удаляем завершённую задачу из persistent storage
            await self._remove_persisted_task(task_id)

    async def schedule_data_fetch(
        self,
        inn: str,
        sources: List[str],
        search_query: Optional[str] = None,
        perplexity_recency: str = "month",
        tavily_depth: str = "basic",
        tavily_max_results: int = 5,
        tavily_include_answer: bool = True,
        delay_minutes: Optional[int] = None,
        delay_seconds: Optional[int] = None,
        run_date: Optional[datetime] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        Запланировать сбор данных из внешних источников.

        Args:
            inn: ИНН компании
            sources: Список источников (dadata, casebook, infosphere, perplexity, tavily)
            search_query: Поисковый запрос (для perplexity/tavily)
            perplexity_recency: Фильтр актуальности Perplexity (day/week/month)
            tavily_depth: Глубина поиска Tavily (basic/advanced)
            tavily_max_results: Максимум результатов Tavily
            tavily_include_answer: Включить краткий ответ Tavily
            delay_minutes: Задержка в минутах
            delay_seconds: Задержка в секундах
            run_date: Конкретное время выполнения
            task_id: ID задачи (опционально)

        Returns:
            str: ID созданной задачи
        """
        metadata = {
            "type": "data_fetch",
            "inn": inn,
            "sources": sources,
            "search_query": search_query,
            "perplexity_recency": perplexity_recency,
            "tavily_depth": tavily_depth,
            "tavily_max_results": tavily_max_results,
            "tavily_include_answer": tavily_include_answer,
        }

        return await self.schedule_task(
            func=self._execute_data_fetch,
            task_id=task_id,
            delay_minutes=delay_minutes,
            delay_seconds=delay_seconds,
            run_date=run_date,
            metadata=metadata,
            inn=inn,
            sources=sources,
            search_query=search_query,
            perplexity_recency=perplexity_recency,
            tavily_depth=tavily_depth,
            tavily_max_results=tavily_max_results,
            tavily_include_answer=tavily_include_answer,
        )

    async def _execute_data_fetch(
        self,
        inn: str,
        sources: List[str],
        search_query: Optional[str] = None,
        perplexity_recency: str = "month",
        tavily_depth: str = "basic",
        tavily_max_results: int = 5,
        tavily_include_answer: bool = True,
    ):
        """
        Внутренний метод для сбора данных из внешних источников.
        """
        import asyncio

        from app.services.fetch_data import (
            fetch_from_casebook,
            fetch_from_dadata,
            fetch_from_infosphere,
        )
        from app.services.perplexity_client import PerplexityClient
        from app.services.tavily_client import TavilyClient

        logger.info(
            f"Starting scheduled data fetch for INN {inn} from sources: {sources}",
            component="scheduler",
        )

        results = {}
        tasks = []

        if "dadata" in sources:
            tasks.append(("dadata", fetch_from_dadata(inn)))
        if "casebook" in sources:
            tasks.append(("casebook", fetch_from_casebook(inn)))
        if "infosphere" in sources:
            tasks.append(("infosphere", fetch_from_infosphere(inn)))

        if "perplexity" in sources and search_query:

            async def fetch_perplexity():
                client = PerplexityClient.get_instance()
                if client.is_configured():
                    return await client.ask(
                        question=f"ИНН {inn}: {search_query}. Ответь только фактами.",
                        search_recency_filter=perplexity_recency,
                    )
                return {"success": False, "error": "Perplexity not configured"}

            tasks.append(("perplexity", fetch_perplexity()))

        if "tavily" in sources and search_query:

            async def fetch_tavily():
                client = TavilyClient.get_instance()
                if client.is_configured():
                    return await client.search(
                        query=f"ИНН {inn} {search_query}",
                        search_depth=tavily_depth,
                        max_results=tavily_max_results,
                        include_answer=tavily_include_answer,
                    )
                return {"success": False, "error": "Tavily not configured"}

            tasks.append(("tavily", fetch_tavily()))

        if tasks:
            gathered = await asyncio.gather(
                *[t[1] for t in tasks],
                return_exceptions=True,
            )
            for i, (source_name, _) in enumerate(tasks):
                result = gathered[i]
                if isinstance(result, Exception):
                    results[source_name] = {"error": str(result)}
                else:
                    results[source_name] = result

        logger.structured(
            "info",
            "scheduled_data_fetch_completed",
            component="scheduler",
            inn=inn,
            sources=sources,
            results_count=len(results),
        )

        return results

    async def cancel_task(self, task_id: str) -> bool:
        """
        Отменить запланированную задачу.

        Args:
            task_id: ID задачи для отмены

        Returns:
            bool: True если задача отменена, False если не найдена
        """
        try:
            self.scheduler.remove_job(task_id)

            # Обновляем метаданные
            if task_id in self._tasks_metadata:
                self._tasks_metadata[task_id]["status"] = "cancelled"

            # P1: Удаляем из persistent storage
            await self._remove_persisted_task(task_id)

            logger.info(f"Task cancelled: {task_id}", component="scheduler")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}", component="scheduler")
            return False

    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о задаче.

        Args:
            task_id: ID задачи

        Returns:
            Dict[str, Any]: Информация о задаче или None если не найдена
        """
        if task_id not in self._tasks_metadata:
            return None

        metadata = self._tasks_metadata[task_id].copy()

        # Проверяем, есть ли задача в scheduler
        job = self.scheduler.get_job(task_id)
        if job:
            metadata["next_run_time"] = job.next_run_time
            metadata["status"] = "scheduled"
        else:
            # Если задачи нет в scheduler, значит она выполнена или отменена
            if metadata["status"] == "scheduled":
                metadata["status"] = "completed"

        return metadata

    def list_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """
        Получить список всех запланированных задач.

        Returns:
            List[Dict[str, Any]]: Список задач с метаданными
        """
        tasks = []

        for job in self.scheduler.get_jobs():
            task_info = {
                "task_id": job.id,
                "func_name": job.func.__name__,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger),
            }

            # Добавляем метаданные если есть
            if job.id in self._tasks_metadata:
                task_info.update(self._tasks_metadata[job.id])

            tasks.append(task_info)

        return tasks

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику scheduler.

        Returns:
            Dict[str, Any]: Статистика (количество задач, состояние и т.д.)
        """
        jobs = self.scheduler.get_jobs()

        stats = {
            "scheduler_running": self._started,
            "total_scheduled_tasks": len(jobs),
            "total_tasks_history": len(self._tasks_metadata),
            "tasks_by_status": {},
        }

        # Подсчитываем по статусам
        for _task_id, metadata in self._tasks_metadata.items():
            status = metadata.get("status", "unknown")
            stats["tasks_by_status"][status] = stats["tasks_by_status"].get(status, 0) + 1

        return stats


# Singleton instance
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """
    Получить singleton экземпляр SchedulerService.

    Returns:
        SchedulerService: Экземпляр сервиса
    """
    global _scheduler_service

    if _scheduler_service is None:
        _scheduler_service = SchedulerService.get_instance()

    return _scheduler_service


__all__ = [
    "SchedulerService",
    "get_scheduler_service",
]
