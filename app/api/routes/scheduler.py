"""
Scheduler API endpoints - управление отложенными задачами.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter

from app.config import RATE_LIMIT_GENERAL_PER_MINUTE
from app.services.scheduler_service import get_scheduler_service
from app.utility.helpers import get_client_ip
from app.utility.logging_client import logger

scheduler_router = APIRouter(prefix="/scheduler", tags=["scheduler"])
limiter = Limiter(key_func=get_client_ip)


class ScheduleClientAnalysisRequest(BaseModel):
    """Запрос на планирование анализа клиента."""
    
    client_name: str = Field(..., description="Название клиента")
    inn: str = Field(..., description="ИНН клиента", min_length=10, max_length=12)
    additional_notes: str = Field(default="", description="Дополнительные заметки")
    
    # Время выполнения (один из параметров обязателен)
    delay_minutes: Optional[int] = Field(None, description="Задержка в минутах", ge=1)
    delay_seconds: Optional[int] = Field(None, description="Задержка в секундах", ge=1)
    run_date: Optional[datetime] = Field(None, description="Конкретное время выполнения (ISO 8601)")
    
    task_id: Optional[str] = Field(None, description="Пользовательский ID задачи (опционально)")


class ScheduleTaskResponse(BaseModel):
    """Ответ при создании задачи."""
    
    task_id: str = Field(..., description="ID созданной задачи")
    scheduled_at: datetime = Field(..., description="Время создания задачи")
    run_date: datetime = Field(..., description="Время выполнения задачи")
    status: str = Field(default="scheduled", description="Статус задачи")
    message: str = Field(..., description="Сообщение")


class TaskInfoResponse(BaseModel):
    """Информация о задаче."""
    
    task_id: str
    func_name: str
    scheduled_at: datetime
    run_date: datetime
    status: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SchedulerStatsResponse(BaseModel):
    """Статистика scheduler."""
    
    scheduler_running: bool
    total_scheduled_tasks: int
    total_tasks_history: int
    tasks_by_status: Dict[str, int]


@scheduler_router.post("/schedule-analysis", response_model=ScheduleTaskResponse)
@limiter.limit(f"{RATE_LIMIT_GENERAL_PER_MINUTE}/minute")
async def schedule_client_analysis(
    request: Request,
    req: ScheduleClientAnalysisRequest
) -> ScheduleTaskResponse:
    """
    Запланировать анализ клиента на будущее время.
    
    Создает отложенную задачу, которая выполнит анализ клиента через заданное время.
    
    **Примеры:**
    
    1. Выполнить через 5 минут:
    ```json
    {
        "client_name": "ООО Ромашка",
        "inn": "1234567890",
        "delay_minutes": 5
    }
    ```
    
    2. Выполнить через 30 секунд:
    ```json
    {
        "client_name": "ООО Ромашка",
        "inn": "1234567890",
        "delay_seconds": 30
    }
    ```
    
    3. Выполнить в конкретное время:
    ```json
    {
        "client_name": "ООО Ромашка",
        "inn": "1234567890",
        "run_date": "2025-12-20T15:30:00"
    }
    ```
    """
    # Валидация: хотя бы один параметр времени должен быть указан
    if not any([req.delay_minutes, req.delay_seconds, req.run_date]):
        raise HTTPException(
            status_code=400,
            detail="At least one of delay_minutes, delay_seconds or run_date must be specified"
        )
    
    try:
        scheduler = get_scheduler_service()
        
        task_id = await scheduler.schedule_client_analysis(
            client_name=req.client_name,
            inn=req.inn,
            additional_notes=req.additional_notes,
            delay_minutes=req.delay_minutes,
            delay_seconds=req.delay_seconds,
            run_date=req.run_date,
            task_id=req.task_id,
        )
        
        # Получаем информацию о созданной задаче
        task_info = scheduler.get_task_info(task_id)
        
        logger.structured(
            "info",
            "analysis_scheduled",
            component="scheduler_api",
            task_id=task_id,
            client_name=req.client_name,
            inn=req.inn,
            run_date=task_info["run_date"].isoformat() if task_info else None,
        )
        
        return ScheduleTaskResponse(
            task_id=task_id,
            scheduled_at=task_info["scheduled_at"],
            run_date=task_info["run_date"],
            status="scheduled",
            message=f"Client analysis scheduled for {task_info['run_date'].strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
    except Exception as e:
        logger.error(
            f"Failed to schedule analysis: {e}",
            component="scheduler_api",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to schedule analysis: {str(e)}"
        )


@scheduler_router.delete("/task/{task_id}")
@limiter.limit(f"{RATE_LIMIT_GENERAL_PER_MINUTE}/minute")
async def cancel_scheduled_task(
    request: Request,
    task_id: str
) -> Dict[str, Any]:
    """
    Отменить запланированную задачу.
    
    Args:
        task_id: ID задачи для отмены
        
    Returns:
        Сообщение об успешной отмене
    """
    scheduler = get_scheduler_service()
    
    success = scheduler.cancel_task(task_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found or already completed"
        )
    
    logger.info(
        f"Task cancelled via API: {task_id}",
        component="scheduler_api"
    )
    
    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": "Task successfully cancelled"
    }


@scheduler_router.get("/task/{task_id}", response_model=TaskInfoResponse)
@limiter.limit(f"{RATE_LIMIT_GENERAL_PER_MINUTE}/minute")
async def get_task_info(
    request: Request,
    task_id: str
) -> TaskInfoResponse:
    """
    Получить информацию о задаче.
    
    Args:
        task_id: ID задачи
        
    Returns:
        Подробная информация о задаче
    """
    scheduler = get_scheduler_service()
    
    task_info = scheduler.get_task_info(task_id)
    
    if not task_info:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )
    
    return TaskInfoResponse(**task_info)


@scheduler_router.get("/tasks", response_model=List[TaskInfoResponse])
@limiter.limit(f"{RATE_LIMIT_GENERAL_PER_MINUTE}/minute")
async def list_scheduled_tasks(request: Request) -> List[TaskInfoResponse]:
    """
    Получить список всех запланированных задач.
    
    Returns:
        Список активных задач
    """
    scheduler = get_scheduler_service()
    
    tasks = scheduler.list_scheduled_tasks()
    
    return [TaskInfoResponse(**task) for task in tasks]


@scheduler_router.get("/stats", response_model=SchedulerStatsResponse)
@limiter.limit(f"{RATE_LIMIT_GENERAL_PER_MINUTE}/minute")
async def get_scheduler_stats(request: Request) -> SchedulerStatsResponse:
    """
    Получить статистику scheduler.
    
    Returns:
        Статистика: количество задач, состояние scheduler и т.д.
    """
    scheduler = get_scheduler_service()
    
    stats = scheduler.get_stats()
    
    return SchedulerStatsResponse(**stats)


__all__ = ["scheduler_router"]
