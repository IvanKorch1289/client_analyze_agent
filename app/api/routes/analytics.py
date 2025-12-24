"""
Analytics API routes - аналитика и статистика по анализам клиентов.

Provides endpoints for:
- Dashboard data (key metrics, charts)
- Risk trends analysis
- Reports comparison
- Analytics for frontend dashboards
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.rate_limit import limiter_for_client_ip
from app.config.constants import RATE_LIMIT_SEARCH_PER_MINUTE
from app.services.openrouter_client import get_openrouter_client
from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient
from app.storage.tarantool import TarantoolClient
from app.utility.logging_client import logger

analytics_router = APIRouter(
    prefix="/analytics",
    tags=["Аналитика"],
    responses={404: {"description": "Не найдено"}},
)

limiter = limiter_for_client_ip()


class DashboardResponse(BaseModel):
    """Response for dashboard analytics."""

    status: str = "success"
    data: Dict[str, Any]


class TrendsResponse(BaseModel):
    """Response for risk trends."""

    status: str = "success"
    trends: Dict[str, Any]


class ComparisonRequest(BaseModel):
    """Request for reports comparison."""

    report_ids: List[str] = Field(..., min_items=2, max_items=10)


@analytics_router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_dashboard_analytics(request: Request) -> DashboardResponse:
    """
    Получить данные для главного dashboard.

    Возвращает агрегированную статистику для отображения:
    - Ключевые метрики (всего анализов, сегодня, средний риск)
    - Статус внешних сервисов
    - Распределение по уровням риска
    - График анализов за последние 7 дней

    Returns:
        Данные для dashboard:
        - total_analyses: общее количество анализов
        - today_analyses: анализов сегодня
        - this_week_analyses: анализов за неделю
        - avg_risk_score: средний балл риска
        - high_risk_count: количество высокого риска
        - risk_distribution: {low, medium, high, critical}
        - timeline_7d: данные для графика за 7 дней
        - services_status: статус внешних сервисов
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        # Get reports stats
        stats = await reports_repo.get_stats()

        # Get timeline for chart (7 days)
        timeline = await reports_repo.get_risk_timeline(days=7)

        # Get services status
        perplexity = PerplexityClient.get_instance()
        tavily = TavilyClient.get_instance()
        openrouter = get_openrouter_client()

        services_status = {
            "openrouter": {
                "configured": bool(openrouter.api_key),
                "name": "OpenRouter LLM",
            },
            "perplexity": {
                "configured": perplexity.is_configured(),
                "name": "Perplexity AI",
            },
            "tavily": {
                "configured": tavily.is_configured(),
                "name": "Tavily Search",
            },
        }

        # Get cache stats
        cache_metrics = client.get_metrics()

        dashboard_data = {
            "total_analyses": stats.get("total", 0),
            "today_analyses": stats.get("today", 0),
            "this_week_analyses": stats.get("this_week", 0),
            "avg_risk_score": stats.get("avg_risk_score", 0),
            "high_risk_count": stats.get("high_risk_count", 0),
            "risk_distribution": stats.get("by_risk_level", {}),
            "timeline_7d": timeline,
            "services_status": services_status,
            "cache": {
                "hit_rate": cache_metrics.get("hit_rate", 0),
                "size": client.get_cache_size(),
            },
        }

        logger.structured(
            "debug",
            "dashboard_analytics",
            component="analytics_api",
            total=stats.get("total", 0),
        )

        return DashboardResponse(
            status="success",
            data=dashboard_data,
        )

    except Exception as e:
        logger.error(f"Dashboard analytics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}") from e


@analytics_router.get("/trends", response_model=TrendsResponse)
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_risk_trends(
    request: Request,
    days: int = Query(30, ge=7, le=90, description="Количество дней для анализа трендов"),
) -> TrendsResponse:
    """
    Получить тренды рисков за N дней.

    Анализирует динамику изменения рисков:
    - Временная линия среднего риска
    - Изменения по уровням риска
    - Тренд: растущий/падающий/стабильный

    Args:
        days: Количество дней для анализа (7-90, default: 30)

    Returns:
        Данные о трендах:
        - timeline: [{date, count, avg_risk, by_risk}, ...]
        - trend_direction: "up" | "down" | "stable"
        - avg_change: изменение среднего риска (%)
        - risk_level_changes: изменения по уровням
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        # Get timeline
        timeline = await reports_repo.get_risk_timeline(days=days)

        # Calculate trend
        trend_direction = "stable"
        avg_change = 0.0

        if len(timeline) >= 2:
            # Compare first week avg to last week avg
            first_week = timeline[: min(7, len(timeline))]
            last_week = timeline[-min(7, len(timeline)) :]

            first_avg = sum(d["avg_risk"] for d in first_week if d["count"] > 0) / max(
                1, len([d for d in first_week if d["count"] > 0])
            )
            last_avg = sum(d["avg_risk"] for d in last_week if d["count"] > 0) / max(
                1, len([d for d in last_week if d["count"] > 0])
            )

            if first_avg > 0:
                avg_change = ((last_avg - first_avg) / first_avg) * 100

                if avg_change > 5:
                    trend_direction = "up"
                elif avg_change < -5:
                    trend_direction = "down"

        # Calculate risk level changes
        risk_level_changes = {}
        if len(timeline) >= 2:
            first_day = timeline[0]
            last_day = timeline[-1]

            for level in ["low", "medium", "high", "critical"]:
                first_count = first_day.get("by_risk", {}).get(level, 0)
                last_count = last_day.get("by_risk", {}).get(level, 0)
                risk_level_changes[level] = last_count - first_count

        trends_data = {
            "timeline": timeline,
            "days": days,
            "trend_direction": trend_direction,
            "avg_change_percent": round(avg_change, 2),
            "risk_level_changes": risk_level_changes,
        }

        logger.structured(
            "debug",
            "risk_trends",
            component="analytics_api",
            days=days,
            trend=trend_direction,
        )

        return TrendsResponse(
            status="success",
            trends=trends_data,
        )

    except Exception as e:
        logger.error(f"Risk trends error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get trends: {str(e)}") from e


@analytics_router.post("/comparison")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def compare_reports(request: Request, payload: ComparisonRequest) -> Dict[str, Any]:
    """
    Сравнение нескольких отчётов.

    Позволяет сравнить 2-10 отчётов side-by-side:
    - Основные метрики (risk_score, risk_level)
    - Общие и уникальные findings
    - Различия в оценках

    Args:
        payload: Список report_ids для сравнения (2-10 шт.)

    Returns:
        Сравнительная таблица и анализ различий
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        # Fetch all reports
        reports = []
        not_found = []

        for report_id in payload.report_ids:
            report = await reports_repo.get(report_id)
            if report:
                reports.append(report)
            else:
                not_found.append(report_id)

        if not reports:
            raise HTTPException(status_code=404, detail="No reports found")

        if not_found:
            logger.warning(f"Reports not found: {not_found}", component="analytics_api")

        # Build comparison data
        comparison = {
            "reports_count": len(reports),
            "not_found": not_found,
            "reports_summary": [],
            "risk_comparison": {},
            "common_factors": [],
            "unique_factors": {},
        }

        # Extract summaries
        all_factors = []

        for report in reports:
            report_data = report.get("report_data", {})
            risk_assessment = report_data.get("risk_assessment", {})

            summary = {
                "report_id": report["report_id"],
                "client_name": report["client_name"],
                "inn": report["inn"],
                "created_at": report["created_at"],
                "risk_level": report["risk_level"],
                "risk_score": report["risk_score"],
                "factors_count": len(risk_assessment.get("factors", [])),
            }

            comparison["reports_summary"].append(summary)

            # Collect factors
            factors = risk_assessment.get("factors", [])
            all_factors.extend([(report["report_id"], f) for f in factors])

        # Find common factors (appear in multiple reports)
        factor_counts = {}
        for report_id, factor in all_factors:
            if factor not in factor_counts:
                factor_counts[factor] = set()
            factor_counts[factor].add(report_id)

        comparison["common_factors"] = [
            {"factor": factor, "count": len(report_ids)}
            for factor, report_ids in factor_counts.items()
            if len(report_ids) > 1
        ]

        # Risk comparison
        risk_scores = [r["risk_score"] for r in comparison["reports_summary"]]
        comparison["risk_comparison"] = {
            "min_score": min(risk_scores) if risk_scores else 0,
            "max_score": max(risk_scores) if risk_scores else 0,
            "avg_score": (round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0),
            "score_range": max(risk_scores) - min(risk_scores) if risk_scores else 0,
        }

        logger.structured(
            "debug",
            "reports_comparison",
            component="analytics_api",
            count=len(reports),
        )

        return {
            "status": "success",
            "comparison": comparison,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reports comparison error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compare reports: {str(e)}") from e


@analytics_router.get("/top-companies")
@limiter.limit(f"{RATE_LIMIT_SEARCH_PER_MINUTE}/minute")
async def get_top_companies(request: Request, limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
    """
    Получить топ проверенных компаний.

    Показывает наиболее часто анализируемые компании
    (по количеству отчётов).

    Args:
        limit: Количество результатов (1-50, default: 10)

    Returns:
        Топ компаний: [{inn, client_name, reports_count, last_risk_level}, ...]
    """
    try:
        client = await TarantoolClient.get_instance()
        reports_repo = client.get_reports_repository()

        # Get all reports (simplified, in production should be optimized)
        reports = await reports_repo.list(limit=500, offset=0)

        # Count by INN
        inn_counts = {}
        for report in reports:
            inn = report.get("inn", "")
            if not inn:
                continue

            if inn not in inn_counts:
                inn_counts[inn] = {
                    "inn": inn,
                    "client_name": report.get("client_name", ""),
                    "count": 0,
                    "last_risk_level": report.get("risk_level", "unknown"),
                    "last_created_at": report.get("created_at", 0),
                }

            inn_counts[inn]["count"] += 1

            # Update if this report is newer
            if report.get("created_at", 0) > inn_counts[inn]["last_created_at"]:
                inn_counts[inn]["last_risk_level"] = report.get("risk_level", "unknown")
                inn_counts[inn]["last_created_at"] = report.get("created_at", 0)

        # Sort by count
        top_companies = sorted(
            inn_counts.values(),
            key=lambda x: (x["count"], x["last_created_at"]),
            reverse=True,
        )[:limit]

        # Clean up timestamps
        for company in top_companies:
            del company["last_created_at"]

        logger.structured(
            "debug",
            "top_companies",
            component="analytics_api",
            count=len(top_companies),
        )

        return {
            "status": "success",
            "companies": top_companies,
            "total": len(top_companies),
        }

    except Exception as e:
        logger.error(f"Top companies error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get top companies: {str(e)}") from e


__all__ = ["analytics_router"]
