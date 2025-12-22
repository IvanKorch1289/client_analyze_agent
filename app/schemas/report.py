from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical", "unknown"]
SentimentLabel = Literal["positive", "neutral", "negative", "unknown"]


class ReportMetadata(BaseModel):
    client_name: str
    inn: str = ""
    analysis_date: datetime
    data_sources_count: int = 0
    successful_sources: int = 0


class RiskAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    level: RiskLevel = "unknown"
    factors: List[str] = Field(default_factory=list)


class Finding(BaseModel):
    category: str
    sentiment: SentimentLabel = "neutral"
    key_points: str = ""


class ClientAnalysisReport(BaseModel):
    """
    Канонический формат отчёта по клиенту.

    Этот объект можно:
    - сохранять в JSON (file_writer)
    - отдавать через API
    - конвертировать в PDF (pdf_generator.normalize_report_for_pdf)
    """

    metadata: ReportMetadata
    company_info: Dict[str, Any] = Field(default_factory=dict)
    legal_cases_count: int = 0
    risk_assessment: RiskAssessment
    findings: List[Finding] = Field(default_factory=list)
    summary: str = ""
    citations: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

