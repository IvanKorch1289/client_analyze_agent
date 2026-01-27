"""
Reports API маршруты - управление отчетами по анализу клиентов.

Предоставляет эндпоинты для:
- Список отчётов с пагинацией и фильтрами
- Получение деталей отчёта
- Поиск отчётов по ИНН, уровню риска и т.д.
- Статистика отчётов
- Массовые операции
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.rate_limit import limiter_for_client_ip
from app.config.constants import (
    RATE_LIMIT_ADMIN_PER_MINUTE,
    RATE_LIMIT_SEARCH_PER_MINUTE,
)
from app.schemas import (
    BulkDeleteRequest,
    ReportDetailResponse,
    ReportListResponse,
    ReportStatsResponse,
)
from app.storage.tarantool import TarantoolClient
from app.utility.auth import require_admin
from app.utility.export_helpers import (
    normalize_report_for_export,
    report_to_csv,
    report_to_json,
    reports_summary_to_csv,
)
from app.utility.logging_client import logger

reports_router = APIRouter(
    prefix="/reports",
    tags=["Отчёты"],
    responses={404: {"description": "Не найдено"}},
)

limiter = limiter_for_client_ip()


@reports_router.get("", response_model=ReportListResponse)
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def list_reports(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    inn: Optional[str] = Query(None, description="Фильтр по ИНН"),
    risk_level: Optional[str] = Query(None, description="Фильтр по уровню риска (low/medium/high/critical)"),
    client_name: Optional[str] = Query(None, description="Поиск по названию компании"),
    date_from: Optional[datetime] = Query(None, description="Фильтр: дата от"),
    date_to: Optional[datetime] = Query(None, description="Фильтр: дата до"),
    min_risk_score: Optional[int] = Query(None, ge=0, le=100),
    max_risk_score: Optional[int] = Query(None, ge=0, le=100),
) -> ReportListResponse:
    """
    Получить список отчётов с фильтрацией и пагинацией.

    Сортировка: по дате создания DESC (новые первые).

    **Фильтры:**
    - inn: точное совпадение ИНН
    - risk_level: уровень риска (low, medium, high, critical)
    - client_name: частичное совпадение названия (case-insensitive)
    - date_from/date_to: временной диапазон
    - min_risk_score/max_risk_score: диапазон баллов риска

    **Пагинация:**
    - limit: количество записей (1-500, default: 50)
    - offset: смещение (default: 0)
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        # Формирование фильтров
        filters = {}
        if inn:
            filters["inn"] = inn
        if risk_level:
            filters["risk_level"] = risk_level
        if client_name:
            filters["client_name"] = client_name
        if date_from:
            filters["date_from"] = int(date_from.timestamp())
        if date_to:
            filters["date_to"] = int(date_to.timestamp())
        if min_risk_score is not None:
            filters["min_risk_score"] = min_risk_score
        if max_risk_score is not None:
            filters["max_risk_score"] = max_risk_score

        # Получение отчётов
        if filters:
            # Расширенный поиск с фильтрами
            reports = await reports_repo.search_reports(filters=filters, limit=limit + 1)
        else:
            # Простой список
            reports = await reports_repo.list(limit=limit + 1, offset=offset)

        # Проверка наличия дополнительных результатов
        has_more = len(reports) > limit
        if has_more:
            reports = reports[:limit]

        # Получение общего количества (приблизительно для производительности)
        total = await reports_repo.count()

        logger.structured(
            "debug",
            "reports_list",
            component="reports_api",
            count=len(reports),
            limit=limit,
            offset=offset,
            filters=filters,
        )

        return ReportListResponse(
            status="success",
            reports=reports,
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    except Exception as e:
        logger.error(f"List reports error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}") from e


@reports_router.get("/{report_id}", response_model=ReportDetailResponse)
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_report(request: Request, report_id: str) -> ReportDetailResponse:
    """
    Получить полный отчёт по ID.

    Args:
        report_id: Уникальный ID отчёта

    Returns:
        Полные данные отчёта включая report_data
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        report = await reports_repo.get(report_id)

        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        logger.structured(
            "debug",
            "report_get",
            component="reports_api",
            report_id=report_id,
        )

        return ReportDetailResponse(
            status="success",
            report=report,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get report error for {report_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get report: {str(e)}") from e


@reports_router.get("/inn/{inn}")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_reports_by_inn(request: Request, inn: str, limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """
    Получить все отчёты по ИНН.

    Args:
        inn: ИНН компании (10 или 12 цифр)
        limit: Максимальное количество результатов

    Returns:
        Список отчётов для указанного ИНН
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        reports = await reports_repo.get_reports_by_inn(inn, limit=limit)

        logger.structured(
            "debug",
            "reports_by_inn",
            component="reports_api",
            inn=inn,
            count=len(reports),
        )

        return {
            "status": "success",
            "inn": inn,
            "reports": reports,
            "count": len(reports),
        }

    except Exception as e:
        logger.error(f"Get reports by INN error for {inn}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get reports: {str(e)}") from e


@reports_router.delete("/{report_id}")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def delete_report(request: Request, report_id: str, role: str = Depends(require_admin)) -> Dict[str, Any]:
    """
    Удалить отчёт (admin only).

    Args:
        report_id: ID отчёта для удаления
        role: Роль пользователя (проверяется автоматически)

    Returns:
        Статус удаления
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        # Проверка существования
        report = await reports_repo.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Отчёт {report_id} не найден")

        # Удаление
        success = await reports_repo.delete(report_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete report")

        logger.info(
            f"Report deleted: {report_id}",
            component="reports_api",
        )

        return {
            "status": "success",
            "message": f"Report {report_id} deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete report error for {report_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {str(e)}") from e


@reports_router.post("/bulk-delete")
@limiter.limit(f"{RATE_LIMIT_ADMIN_PER_MINUTE}/minute")
async def bulk_delete_reports(
    request: Request, payload: BulkDeleteRequest, role: str = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Массовое удаление отчётов (admin only).

    Args:
        payload: Список report_ids для удаления (1-100 шт.)
        role: Роль пользователя (проверяется автоматически)

    Returns:
        Статистика удаления: успешные и неудачные
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        deleted = []
        failed = []

        for report_id in payload.report_ids:
            try:
                success = await reports_repo.delete(report_id)
                if success:
                    deleted.append(report_id)
                else:
                    failed.append({"id": report_id, "reason": "delete_failed"})
            except Exception as e:
                failed.append({"id": report_id, "reason": str(e)})

        logger.info(
            f"Bulk delete: {len(deleted)} deleted, {len(failed)} failed",
            component="reports_api",
        )

        return {
            "status": "success",
            "deleted": deleted,
            "failed": failed,
            "total_requested": len(payload.report_ids),
            "deleted_count": len(deleted),
            "failed_count": len(failed),
        }

    except Exception as e:
        logger.error(f"Bulk delete error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to bulk delete: {str(e)}") from e


@reports_router.get("/stats/summary", response_model=ReportStatsResponse)
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_reports_stats(request: Request) -> ReportStatsResponse:
    """
    Получить статистику по отчётам.

    Returns:
        Агрегированная статистика:
        - total: общее количество отчётов
        - by_risk_level: распределение по уровням риска
        - avg_risk_score: средний балл риска
        - today: анализов сегодня
        - this_week: анализов за неделю
        - high_risk_count: количество высокого/критического риска
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        stats = await reports_repo.get_stats()

        logger.structured(
            "debug",
            "reports_stats",
            component="reports_api",
            total=stats.get("total", 0),
        )

        return ReportStatsResponse(
            status="success",
            stats=stats,
        )

    except Exception as e:
        logger.error(f"Get reports stats error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}") from e


@reports_router.get("/stats/timeline")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_risk_timeline(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Количество дней для анализа"),
) -> Dict[str, Any]:
    """
    Получить временную линию рисков за N дней.

    Возвращает данные для построения графиков:
    - Количество анализов по дням
    - Средний балл риска по дням
    - Распределение по уровням риска по дням

    Args:
        days: Количество дней (1-90, default: 7)

    Returns:
        Timeline: [{date, count, avg_risk, by_risk}, ...]
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        timeline = await reports_repo.get_risk_timeline(days=days)

        logger.structured(
            "debug",
            "risk_timeline",
            component="reports_api",
            days=days,
            entries=len(timeline),
        )

        return {
            "status": "success",
            "days": days,
            "timeline": timeline,
        }

    except Exception as e:
        logger.error(f"Get risk timeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get timeline: {str(e)}") from e


@reports_router.get("/{report_id}/export")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def export_report(
    request: Request,
    report_id: str,
    format: Literal["json", "csv"] = Query("json", description="Export format"),
):
    """
    Экспортировать отчёт в указанном формате.

    Поддерживаемые форматы:
    - json: Полные данные отчёта в JSON
    - csv: Findings и risk factors в CSV

    Args:
        report_id: ID отчёта
        format: Формат экспорта (json, csv)

    Returns:
        Файл в выбранном формате
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        report = await reports_repo.get(report_id)

        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        # Нормализация отчёта
        normalized = normalize_report_for_export(report)

        if format == "json":
            content = report_to_json(normalized, pretty=True)
            media_type = "application/json"
            filename = f"report_{report_id}.json"
        elif format == "csv":
            content = report_to_csv(normalized)
            media_type = "text/csv"
            filename = f"report_{report_id}.csv"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

        logger.structured(
            "debug",
            "report_export",
            component="reports_api",
            report_id=report_id,
            format=format,
        )

        return PlainTextResponse(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export report error for {report_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to export report: {str(e)}") from e


@reports_router.post("/bulk-export")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def bulk_export_reports(
    request: Request,
    payload: BulkDeleteRequest,  # Reuse same structure (list of report_ids)
    format: Literal["csv"] = Query("csv", description="Export format"),
) -> PlainTextResponse:
    """
    Массовый экспорт отчётов в CSV.

    Создаёт сводную таблицу со всеми отчётами.

    Args:
        payload: Список report_ids для экспорта
        format: Формат (пока только csv)

    Returns:
        CSV файл со сводкой отчётов
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        reports = []
        for report_id in payload.report_ids:
            report = await reports_repo.get(report_id)
            if report:
                reports.append(report)

        if not reports:
            raise HTTPException(status_code=404, detail="No reports found")

        if format == "csv":
            content = reports_summary_to_csv(reports)
            media_type = "text/csv"
            filename = f"reports_export_{len(reports)}_items.csv"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

        logger.structured(
            "debug",
            "bulk_export",
            component="reports_api",
            count=len(reports),
            format=format,
        )

        return PlainTextResponse(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to bulk export: {str(e)}") from e


@reports_router.get("/compare/{report_id_1}/{report_id_2}")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def compare_reports(
    request: Request,
    report_id_1: str,
    report_id_2: str,
) -> Dict[str, Any]:
    """
    Сравнить два отчёта side-by-side.

    Sprint 2: Analysis Comparison feature.

    Args:
        report_id_1: ID первого отчёта (обычно старый)
        report_id_2: ID второго отчёта (обычно новый)

    Returns:
        Структурированное сравнение с diff по всем ключевым метрикам
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        # Получаем оба отчёта
        report1 = await reports_repo.get(report_id_1)
        report2 = await reports_repo.get(report_id_2)

        if not report1:
            raise HTTPException(status_code=404, detail=f"Report {report_id_1} not found")
        if not report2:
            raise HTTPException(status_code=404, detail=f"Report {report_id_2} not found")

        # Проверяем что отчёты для одной компании
        report1_data = report1.get("report_data", {})
        report2_data = report2.get("report_data", {})

        client_name_1 = report1.get("client_name", "")
        client_name_2 = report2.get("client_name", "")

        if client_name_1 != client_name_2:
            logger.warning(
                f"Comparing reports for different clients: '{client_name_1}' vs '{client_name_2}'",
                component="reports_api",
            )

        # Извлекаем ключевые метрики для сравнения
        def extract_metrics(report_data: Dict[str, Any]) -> Dict[str, Any]:
            risk = report_data.get("risk_assessment", {})
            metadata = report_data.get("metadata", {})

            return {
                "risk_score": risk.get("score", 0),
                "risk_level": risk.get("level", "unknown"),
                "risk_factors": risk.get("factors", []),
                "findings_count": len(report_data.get("findings", [])),
                "findings": report_data.get("findings", []),
                "recommendations_count": len(report_data.get("recommendations", [])),
                "recommendations": report_data.get("recommendations", []),
                "data_quality_percent": metadata.get("data_quality_percent", 100.0),
                "successful_sources": metadata.get("successful_sources", 0),
                "version": report_data.get("version", 1),
                "analysis_date": metadata.get("analysis_date", ""),
            }

        metrics1 = extract_metrics(report1_data)
        metrics2 = extract_metrics(report2_data)

        # Вычисляем diff
        diff = {
            "risk_score": {
                "old": metrics1["risk_score"],
                "new": metrics2["risk_score"],
                "delta": metrics2["risk_score"] - metrics1["risk_score"],
                "changed": metrics1["risk_score"] != metrics2["risk_score"],
            },
            "risk_level": {
                "old": metrics1["risk_level"],
                "new": metrics2["risk_level"],
                "changed": metrics1["risk_level"] != metrics2["risk_level"],
            },
            "risk_factors": {
                "old": metrics1["risk_factors"],
                "new": metrics2["risk_factors"],
                "added": list(set(metrics2["risk_factors"]) - set(metrics1["risk_factors"])),
                "removed": list(set(metrics1["risk_factors"]) - set(metrics2["risk_factors"])),
                "changed": set(metrics1["risk_factors"]) != set(metrics2["risk_factors"]),
            },
            "findings_count": {
                "old": metrics1["findings_count"],
                "new": metrics2["findings_count"],
                "delta": metrics2["findings_count"] - metrics1["findings_count"],
                "changed": metrics1["findings_count"] != metrics2["findings_count"],
            },
            "data_quality": {
                "old": metrics1["data_quality_percent"],
                "new": metrics2["data_quality_percent"],
                "delta": round(
                    metrics2["data_quality_percent"] - metrics1["data_quality_percent"],
                    1,
                ),
                "changed": metrics1["data_quality_percent"] != metrics2["data_quality_percent"],
            },
        }

        # Определяем общее направление изменений
        improvements = []
        regressions = []

        if diff["risk_score"]["delta"] < 0:
            improvements.append(f"Risk score decreased by {abs(diff['risk_score']['delta'])} points")
        elif diff["risk_score"]["delta"] > 0:
            regressions.append(f"Risk score increased by {diff['risk_score']['delta']} points")

        if diff["data_quality"]["delta"] > 0:
            improvements.append(f"Data quality improved by {diff['data_quality']['delta']}%")
        elif diff["data_quality"]["delta"] < 0:
            regressions.append(f"Data quality decreased by {abs(diff['data_quality']['delta'])}%")

        if diff["risk_factors"]["removed"]:
            improvements.append(f"Removed {len(diff['risk_factors']['removed'])} risk factors")
        if diff["risk_factors"]["added"]:
            regressions.append(f"Added {len(diff['risk_factors']['added'])} new risk factors")

        logger.structured(
            "info",
            "reports_compared",
            component="reports_api",
            report_id_1=report_id_1,
            report_id_2=report_id_2,
            risk_score_delta=diff["risk_score"]["delta"],
        )

        return {
            "status": "success",
            "report1": {
                "id": report_id_1,
                "client_name": client_name_1,
                "created_at": report1.get("created_at"),
                "metrics": metrics1,
            },
            "report2": {
                "id": report_id_2,
                "client_name": client_name_2,
                "created_at": report2.get("created_at"),
                "metrics": metrics2,
            },
            "diff": diff,
            "summary": {
                "improvements": improvements,
                "regressions": regressions,
                "total_changes": sum(1 for v in diff.values() if v.get("changed", False)),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Compare reports error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compare reports: {str(e)}") from e


__all__ = ["reports_router"]
