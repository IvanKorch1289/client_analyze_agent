"""
Shared utilities and components for agents.

This module contains common functions, schemas, and utilities
used across multiple agents to avoid code duplication.
"""

from app.agents.shared.llm import get_llm_manager
from app.agents.shared.prompts import (
    ANALYZER_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
)
from app.agents.shared.schemas import ClientAnalysisState, ReportData
from app.agents.shared.utils import format_ts, truncate, validate_inn

__all__ = [
    "get_llm_manager",
    "ORCHESTRATOR_SYSTEM_PROMPT",
    "ANALYZER_SYSTEM_PROMPT",
    "ClientAnalysisState",
    "ReportData",
    "format_ts",
    "truncate",
    "validate_inn",
]

