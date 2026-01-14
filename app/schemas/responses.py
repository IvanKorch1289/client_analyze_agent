"""
Response schemas for API endpoints.

Centralized Pydantic models for all API response payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ReportListResponse(BaseModel):
    """Response for list of reports."""

    status: str = "success"
    reports: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int
    has_more: bool


class ReportDetailResponse(BaseModel):
    """Response for single report details."""

    status: str = "success"
    report: Dict[str, Any]


class ReportStatsResponse(BaseModel):
    """Response for reports statistics."""

    status: str = "success"
    stats: Dict[str, Any]


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


class DashboardResponse(BaseModel):
    """Response for dashboard analytics."""

    status: str = "success"
    data: Dict[str, Any]


class TrendsResponse(BaseModel):
    """Response for risk trends."""

    status: str = "success"
    trends: Dict[str, Any]
