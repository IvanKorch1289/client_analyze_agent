"""
MCP Resources for API specifications and reference data.

Provides Swagger specs, API documentation, and reference data
for external APIs.
"""

from app.mcp_server.resources.api_specs import (
    get_api_spec,
    get_field_reference,
)
from app.mcp_server.resources.reference_data import (
    RISK_CATEGORIES,
    RISK_LEVELS,
    SEARCH_CATEGORIES,
)

__all__ = [
    # API specs
    "get_api_spec",
    "get_field_reference",
    # Reference data
    "RISK_CATEGORIES",
    "RISK_LEVELS",
    "SEARCH_CATEGORIES",
]
