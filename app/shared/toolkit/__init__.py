"""
Unified toolkit module for the application.

This module consolidates utilities from:
- app/shared/utils (pure utilities: formatters, parsers, helpers)
- app/utility (application services: logging, auth, metrics, telemetry, decorators)

All exports are available for backward compatibility.
"""

from app.shared.toolkit.formatters import (
    format_csv,
    format_json,
    format_ts,
    truncate,
)
from app.shared.toolkit.parsers import (
    parse_csv,
    parse_json,
)
from app.shared.toolkit.helpers import (
    chunk_text,
    clean_xml_dict,
    format_inn,
    get_client_ip,
    retry_async,
    safe_dict_get,
    validate_inn,
)
from app.shared.toolkit.logging import (
    AppLogger,
    TimedOperation,
    app_logger,
    generate_request_id,
    get_request_id,
    logger,
    LOGS_DIR,
    request_id_var,
    set_request_id,
)
from app.shared.toolkit.auth import (
    Role,
    generate_token,
    get_admin_token,
    get_current_role,
    is_admin,
    require_admin,
)
from app.shared.toolkit.decorators import (
    async_retry,
    cache_with_tarantool,
)
from app.shared.toolkit.telemetry import (
    SERVICE_NAME,
    InMemorySpanExporter,
    LogStore,
    LogStoreHandler,
    create_span,
    get_log_store,
    get_span_exporter,
    get_tracer,
    init_telemetry,
)
from app.shared.toolkit.metrics import (
    AppMetrics,
    RouteMetrics,
    app_metrics,
)
from app.shared.toolkit.circuit_breaker import (
    AppCircuitBreaker,
    AppCircuitBreakerConfig,
    AppCircuitBreakerMiddleware,
)
from app.shared.toolkit.pdf import (
    ReportPDF,
    generate_analysis_pdf,
    normalize_report_for_pdf,
    save_pdf_report,
    transliterate_cyrillic,
)
from app.shared.toolkit.export import (
    format_bytes_size,
    normalize_report_for_export,
    report_to_csv,
    report_to_json,
    reports_summary_to_csv,
)
from app.shared.toolkit.pagination import (
    CursorPaginatedResponse,
    CursorPaginationParams,
    PaginatedResponse,
    PaginationParams,
    paginate_list,
)

__all__ = [
    # Formatters
    "format_csv",
    "format_json",
    "format_ts",
    "truncate",
    # Parsers
    "parse_csv",
    "parse_json",
    # Helpers
    "chunk_text",
    "clean_xml_dict",
    "format_inn",
    "get_client_ip",
    "retry_async",
    "safe_dict_get",
    "validate_inn",
    # Logging
    "AppLogger",
    "TimedOperation",
    "app_logger",
    "generate_request_id",
    "get_request_id",
    "logger",
    "LOGS_DIR",
    "request_id_var",
    "set_request_id",
    # Auth
    "Role",
    "generate_token",
    "get_admin_token",
    "get_current_role",
    "is_admin",
    "require_admin",
    # Decorators
    "async_retry",
    "cache_with_tarantool",
    # Telemetry
    "SERVICE_NAME",
    "InMemorySpanExporter",
    "LogStore",
    "LogStoreHandler",
    "create_span",
    "get_log_store",
    "get_span_exporter",
    "get_tracer",
    "init_telemetry",
    # Metrics
    "AppMetrics",
    "RouteMetrics",
    "app_metrics",
    # Circuit Breaker
    "AppCircuitBreaker",
    "AppCircuitBreakerConfig",
    "AppCircuitBreakerMiddleware",
    # PDF
    "ReportPDF",
    "generate_analysis_pdf",
    "normalize_report_for_pdf",
    "save_pdf_report",
    "transliterate_cyrillic",
    # Export
    "format_bytes_size",
    "normalize_report_for_export",
    "report_to_csv",
    "report_to_json",
    "reports_summary_to_csv",
    # Pagination
    "CursorPaginatedResponse",
    "CursorPaginationParams",
    "PaginatedResponse",
    "PaginationParams",
    "paginate_list",
]
