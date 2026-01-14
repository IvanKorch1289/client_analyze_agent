"""
Centralized Pydantic schemas for the application.

Re-exports all schemas for convenient imports:
    from app.schemas import ClientAnalysisRequest, ReportListResponse
"""

from app.schemas.api import (
    AppMetricsResponse,
    HealthComponents,
    HealthComponentPerplexity,
    HealthComponentTavily,
    HealthResponse,
    HealthServiceInfo,
    PerplexitySearchResponse,
    TavilySearchResponse,
    TavilySearchResultItem,
)
from app.schemas.report import (
    ClientAnalysisReport,
    Finding,
    ReportFeedback,
    ReportMetadata,
    RiskAssessment,
    RiskLevel,
    SentimentLabel,
)
from app.schemas.requests import (
    BulkDeleteRequest,
    ClientAnalysisRequest,
    ComparisonRequest,
    FeedbackRequest,
    PDFReportRequest,
    PerplexityRequest,
    PromptRequest,
    ScheduleClientAnalysisRequest,
    ScheduleDataFetchRequest,
    TavilyRequest,
)
from app.schemas.responses import (
    DashboardResponse,
    ReportDetailResponse,
    ReportListResponse,
    ReportStatsResponse,
    ScheduleTaskResponse,
    SchedulerStatsResponse,
    TaskInfoResponse,
    TrendsResponse,
)

__all__ = [
    "AppMetricsResponse",
    "BulkDeleteRequest",
    "ClientAnalysisReport",
    "ClientAnalysisRequest",
    "ComparisonRequest",
    "DashboardResponse",
    "FeedbackRequest",
    "Finding",
    "HealthComponents",
    "HealthComponentPerplexity",
    "HealthComponentTavily",
    "HealthResponse",
    "HealthServiceInfo",
    "PDFReportRequest",
    "PerplexityRequest",
    "PerplexitySearchResponse",
    "PromptRequest",
    "ReportDetailResponse",
    "ReportFeedback",
    "ReportListResponse",
    "ReportMetadata",
    "ReportStatsResponse",
    "RiskAssessment",
    "RiskLevel",
    "ScheduleClientAnalysisRequest",
    "ScheduleDataFetchRequest",
    "ScheduleTaskResponse",
    "SchedulerStatsResponse",
    "SentimentLabel",
    "TaskInfoResponse",
    "TavilyRequest",
    "TavilySearchResponse",
    "TavilySearchResultItem",
    "TrendsResponse",
]
