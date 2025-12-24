"""
Shared utilities and components for agents.

DEPRECATED: This module is being phased out in favor of:
- app.shared (for config, security, logger, utils)
- app.mcp_server.prompts (for typed prompts)

Please update imports:
- validate_inn → app.shared.security.validate_inn
- truncate, format_ts → app.shared.utils.formatters
- System prompts → app.mcp_server.prompts.system_prompts
"""

import warnings

warnings.warn(
    "app.agents.shared is deprecated. Use app.shared and app.mcp_server.prompts instead.",
    DeprecationWarning,
    stacklevel=2,
)

from app.agents.shared.llm import get_llm_manager
from app.agents.shared.schemas import ClientAnalysisState, ReportData

# Re-export from new locations (for compatibility)
from app.shared.security import validate_inn
from app.shared.utils.formatters import format_ts, truncate

__all__ = [
    "get_llm_manager",
    "ClientAnalysisState",
    "ReportData",
    "format_ts",
    "truncate",
    "validate_inn",
]
