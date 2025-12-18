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
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.config import settings
from app.utility.logging_client import logger


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
                'coalesce': False,
                'max_instances': 3,
                'misfire_grace_time': 300  # 5 минут
            }
        )
        
        # Хранилище метаданных задач
        self._tasks_metadata: Dict[str, Dict[str, Any]] = {}
        
        self._started = False
        
        logger.info("SchedulerService initialized", component="scheduler")
    
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
    
    def start(self):
        """Запустить scheduler."""
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("Scheduler started", component="scheduler")
    
    def shutdown(self):
        """Остановить scheduler."""
        if self._started:
            self.scheduler.shutdown(wait=True)
            self._started = False
            logger.info("Scheduler stopped", component="scheduler")
    
    async def schedule_task(
        self,
        func: Callable,
        task_id: Optional[str] = None,
        delay_seconds: Optional[int] = None,
        delay_minutes: Optional[int] = None,
        run_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
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
        
        # Сохраняем метаданные
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
    
    async def _execute_client_analysis(
        self,
        client_name: str,
        inn: str,
        additional_notes: str = ""
    ):
        """
        Внутренний метод для выполнения анализа клиента.
        
        Вызывается scheduler'ом в нужное время.
        """
        # Если включён RabbitMQ режим — отдаём выполнение воркеру (FastStream),
        # а scheduler остаётся только “планировщиком”.
        #
        # Это даёт горизонтальное масштабирование и разгружает web-процесс.
        if getattr(settings.queue, "enabled", False):
            from app.messaging.publisher import get_rabbit_publisher

            await get_rabbit_publisher().publish_client_analysis(
                client_name=client_name,
                inn=inn,
                additional_notes=additional_notes,
                save_report=True,
            )
            logger.info(
                "Задача отправлена в очередь RabbitMQ",
                component="scheduler",
            )
            return

        # Иначе — выполняем in-process.
        from app.services.analysis_executor import execute_client_analysis
        task_id = f"analysis_{inn}_{int(time.time())}"
        
        logger.info(
            f"Starting scheduled client analysis: {client_name} (INN: {inn})",
            component="scheduler"
        )
        
        try:
            result = await execute_client_analysis(
                client_name=client_name,
                inn=inn,
                additional_notes=additional_notes,
                save_report=True,
            )
            
            logger.structured(
                "info",
                "scheduled_analysis_completed",
                component="scheduler",
                client_name=client_name,
                inn=inn,
                status=result.get("status"),
                session_id=result.get("session_id"),
            )
            
            # Обновляем метаданные задачи
            if task_id in self._tasks_metadata:
                self._tasks_metadata[task_id].update({
                    "status": "completed",
                    "result_status": result.get("status"),
                    "session_id": result.get("session_id"),
                    "completed_at": datetime.now(),
                })
            
        except Exception as e:
            logger.error(
                f"Scheduled analysis failed for {client_name}: {e}",
                component="scheduler",
                exc_info=True
            )
            
            # Сохраняем ошибку в метаданные
            if task_id in self._tasks_metadata:
                self._tasks_metadata[task_id].update({
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.now(),
                })
    
    def cancel_task(self, task_id: str) -> bool:
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
            
            logger.info(
                f"Task cancelled: {task_id}",
                component="scheduler"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to cancel task {task_id}: {e}",
                component="scheduler"
            )
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
        for task_id, metadata in self._tasks_metadata.items():
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
