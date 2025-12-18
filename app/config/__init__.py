"""
Конфигурация приложения.

Модуль содержит:
- Константы (constants.py)
- Загрузчик конфигурации (config_loader.py)
- Централизованные настройки (settings.py)

Пример использования:
    from app.config import settings
    
    # Доступ к настройкам
    print(settings.app.app_name)
    print(settings.tarantool.host)
    print(settings.perplexity.api_key)
    
    # Доступ к константам
    from app.config import MAX_CONCURRENT_SEARCHES
    print(MAX_CONCURRENT_SEARCHES)
"""

# Импорт settings должен быть первым
from app.config.settings import settings

# Затем константы
from app.config.constants import (
    CASEBOOK_CACHE_TTL_SECONDS,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
    CIRCUIT_BREAKER_TIMEOUT_SECONDS,
    COMPRESSION_LEVEL,
    COMPRESSION_THRESHOLD_BYTES,
    DADATA_CACHE_TTL_SECONDS,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_PAGE_SIZE,
    FeatureFlags,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
    INN_LENGTH_INDIVIDUAL,
    INN_LENGTH_LEGAL,
    INFOSPHERE_CACHE_TTL_SECONDS,
    LOG_MAX_SIZE_MB,
    LOG_ROTATION_DAYS,
    LOGS_DIR,
    MAX_API_RESPONSE_SIZE_BYTES,
    MAX_CACHE_BATCH_SIZE,
    MAX_CONCURRENT_SEARCHES,
    MAX_LOG_MESSAGE_LENGTH,
    MAX_PAGES_LIMIT,
    MAX_REPORT_SIZE_BYTES,
    MAX_RETRIES,
    MAX_WEB_CONTENT_CHARS,
    MAX_CONTENT_LENGTH,
    RATE_LIMIT_ADMIN_PER_MINUTE,
    RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE,
    RATE_LIMIT_GENERAL_PER_MINUTE,
    RATE_LIMIT_GLOBAL_PER_HOUR,
    RATE_LIMIT_GLOBAL_PER_MINUTE,
    RATE_LIMIT_PROMPT_PER_MINUTE,
    RATE_LIMIT_SEARCH_PER_MINUTE,
    REPORTS_CACHE_TTL_SECONDS,
    REPORTS_DIR,
    RiskLevel,
    RiskThresholds,
    SEARCH_CACHE_TTL_SECONDS,
    SEARCH_TIMEOUT_SECONDS,
    SLOW_QUERY_THRESHOLD_MS,
    SLOW_REQUEST_THRESHOLD_MS,
    TarantoolSpaces,
    TEMP_DIR,
    TimeoutConfig,
)

__all__ = [
    # Settings
    "settings",
    # Workflow
    "MAX_CONCURRENT_SEARCHES",
    "SEARCH_TIMEOUT_SECONDS",
    "MAX_WEB_CONTENT_CHARS",
    "MAX_CONTENT_LENGTH",
    # HTTP Client
    "MAX_RETRIES",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
    "CIRCUIT_BREAKER_TIMEOUT_SECONDS",
    "HTTP_MAX_CONNECTIONS",
    "HTTP_MAX_KEEPALIVE_CONNECTIONS",
    # Cache
    "DEFAULT_CACHE_TTL_SECONDS",
    "SEARCH_CACHE_TTL_SECONDS",
    "REPORTS_CACHE_TTL_SECONDS",
    "DADATA_CACHE_TTL_SECONDS",
    "INFOSPHERE_CACHE_TTL_SECONDS",
    "CASEBOOK_CACHE_TTL_SECONDS",
    "COMPRESSION_THRESHOLD_BYTES",
    "COMPRESSION_LEVEL",
    "MAX_CACHE_BATCH_SIZE",
    # Pagination
    "MAX_PAGES_LIMIT",
    "DEFAULT_PAGE_SIZE",
    # Content Limits
    "MAX_REPORT_SIZE_BYTES",
    "MAX_LOG_MESSAGE_LENGTH",
    "MAX_API_RESPONSE_SIZE_BYTES",
    # Rate Limiting
    "RATE_LIMIT_GLOBAL_PER_MINUTE",
    "RATE_LIMIT_GLOBAL_PER_HOUR",
    "RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE",
    "RATE_LIMIT_PROMPT_PER_MINUTE",
    "RATE_LIMIT_GENERAL_PER_MINUTE",
    "RATE_LIMIT_SEARCH_PER_MINUTE",
    "RATE_LIMIT_ADMIN_PER_MINUTE",
    # Timeouts
    "TimeoutConfig",
    # Risk Assessment
    "RiskLevel",
    "RiskThresholds",
    # Paths
    "REPORTS_DIR",
    "LOGS_DIR",
    "TEMP_DIR",
    # Tarantool
    "TarantoolSpaces",
    # Validation
    "INN_LENGTH_LEGAL",
    "INN_LENGTH_INDIVIDUAL",
    # Logging
    "LOG_ROTATION_DAYS",
    "LOG_MAX_SIZE_MB",
    # Performance
    "SLOW_REQUEST_THRESHOLD_MS",
    "SLOW_QUERY_THRESHOLD_MS",
    # Features
    "FeatureFlags",
]
