"""
Константы приложения.

Все магические числа и строки вынесены в этот файл для централизованного управления.
"""

from enum import Enum
from typing import Final

# =======================
# Workflow Constants
# =======================

MAX_CONCURRENT_SEARCHES: Final[int] = 5
"""Максимальное количество параллельных поисковых запросов"""

SEARCH_TIMEOUT_SECONDS: Final[int] = 60
"""Таймаут для поисковых запросов (секунды)"""

MAX_WEB_CONTENT_CHARS: Final[int] = 2500
"""Максимальная длина контента из веб-поиска (символы)"""

# =======================
# HTTP Client Constants
# =======================

MAX_RETRIES: Final[int] = 3
"""Максимальное количество повторных попыток HTTP запроса"""

CIRCUIT_BREAKER_FAILURE_THRESHOLD: Final[int] = 5
"""Порог ошибок для открытия circuit breaker"""

CIRCUIT_BREAKER_SUCCESS_THRESHOLD: Final[int] = 2
"""Количество успешных запросов для закрытия circuit breaker"""

CIRCUIT_BREAKER_TIMEOUT_SECONDS: Final[float] = 30.0
"""Таймаут circuit breaker в открытом состоянии (секунды)"""

HTTP_MAX_CONNECTIONS: Final[int] = 50
"""Максимальное количество HTTP соединений в пуле"""

HTTP_MAX_KEEPALIVE_CONNECTIONS: Final[int] = 20
"""Максимальное количество keep-alive соединений"""

# =======================
# Cache & Storage Constants
# =======================

DEFAULT_CACHE_TTL_SECONDS: Final[int] = 3600
"""TTL по умолчанию для кеша (1 час)"""

SEARCH_CACHE_TTL_SECONDS: Final[int] = 300
"""TTL для кеша поисковых запросов (5 минут)"""

REPORTS_CACHE_TTL_SECONDS: Final[int] = 2_592_000
"""TTL для хранения отчётов (30 дней)"""

DADATA_CACHE_TTL_SECONDS: Final[int] = 7200
"""TTL для кеша DaData (2 часа)"""

INFOSPHERE_CACHE_TTL_SECONDS: Final[int] = 3600
"""TTL для кеша InfoSphere (1 час)"""

CASEBOOK_CACHE_TTL_SECONDS: Final[int] = 9600
"""TTL для кеша Casebook (2.67 часа)"""

COMPRESSION_THRESHOLD_BYTES: Final[int] = 1024
"""Минимальный размер данных для сжатия (байты)"""

COMPRESSION_LEVEL: Final[int] = 6
"""Уровень сжатия gzip (0-9)"""

MAX_CACHE_BATCH_SIZE: Final[int] = 100
"""Максимальный размер batch операции с кешем"""

# =======================
# Pagination Constants
# =======================

MAX_PAGES_LIMIT: Final[int] = 100
"""Максимальное количество страниц для пагинации (защита от бесконечных циклов)"""

DEFAULT_PAGE_SIZE: Final[int] = 20
"""Размер страницы по умолчанию"""

# =======================
# Content Limits
# =======================

MAX_REPORT_SIZE_BYTES: Final[int] = 10_485_760
"""Максимальный размер отчёта (10MB)"""

MAX_LOG_MESSAGE_LENGTH: Final[int] = 5000
"""Максимальная длина лог-сообщения (символы)"""

MAX_API_RESPONSE_SIZE_BYTES: Final[int] = 5_242_880
"""Максимальный размер ответа от внешнего API (5MB)"""

# =======================
# Rate Limiting Constants
# =======================

RATE_LIMIT_GLOBAL_PER_MINUTE: Final[int] = 100
"""Глобальный лимит запросов в минуту на IP"""

RATE_LIMIT_GLOBAL_PER_HOUR: Final[int] = 2000
"""Глобальный лимит запросов в час на IP"""

RATE_LIMIT_ANALYZE_CLIENT_PER_MINUTE: Final[int] = 5
"""Лимит для эндпоинта анализа клиента (дорогая операция)"""

RATE_LIMIT_SEARCH_PER_MINUTE: Final[int] = 30
"""Лимит для поисковых эндпоинтов"""

RATE_LIMIT_ADMIN_PER_MINUTE: Final[int] = 60
"""Лимит для административных операций"""

# =======================
# Timeouts
# =======================

class TimeoutConfig:
    """Таймауты для различных операций"""
    
    DADATA_CONNECT: Final[float] = 5.0
    DADATA_READ: Final[float] = 30.0
    DADATA_WRITE: Final[float] = 10.0
    
    INFOSPHERE_CONNECT: Final[float] = 5.0
    INFOSPHERE_READ: Final[float] = 45.0
    INFOSPHERE_WRITE: Final[float] = 10.0
    
    CASEBOOK_CONNECT: Final[float] = 5.0
    CASEBOOK_READ: Final[float] = 30.0
    CASEBOOK_WRITE: Final[float] = 10.0
    
    PERPLEXITY_REQUEST: Final[float] = 60.0
    TAVILY_REQUEST: Final[float] = 60.0
    
    DEFAULT_REQUEST: Final[float] = 30.0

# =======================
# Risk Assessment
# =======================

class RiskLevel(str, Enum):
    """Уровни риска для оценки клиентов"""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskThresholds:
    """Пороги для определения уровня риска"""
    
    LOW_MAX: Final[int] = 24
    """Максимальный балл для низкого риска (0-24)"""
    
    MEDIUM_MAX: Final[int] = 49
    """Максимальный балл для среднего риска (25-49)"""
    
    HIGH_MAX: Final[int] = 74
    """Максимальный балл для высокого риска (50-74)"""
    
    # CRITICAL = 75-100


# =======================
# File Paths
# =======================

REPORTS_DIR: Final[str] = "reports"
"""Директория для сохранения отчётов"""

LOGS_DIR: Final[str] = "logs"
"""Директория для логов"""

TEMP_DIR: Final[str] = "temp"
"""Директория для временных файлов"""

# =======================
# Tarantool Spaces
# =======================

class TarantoolSpaces:
    """Имена spaces в Tarantool"""
    
    CACHE: Final[str] = "cache"
    """Space для временного кеша"""
    
    REPORTS: Final[str] = "reports"
    """Space для отчётов (TTL 30 дней)"""
    
    THREADS: Final[str] = "threads"
    """Space для истории тредов (persistent)"""
    
    PERSISTENT: Final[str] = "persistent"
    """Space для постоянных данных"""


# =======================
# Validation Patterns
# =======================

INN_LENGTH_LEGAL: Final[int] = 10
"""Длина ИНН для юридических лиц"""

INN_LENGTH_INDIVIDUAL: Final[int] = 12
"""Длина ИНН для ИП и физических лиц"""

# =======================
# Logging
# =======================

LOG_ROTATION_DAYS: Final[int] = 7
"""Количество дней хранения логов перед ротацией"""

LOG_MAX_SIZE_MB: Final[int] = 100
"""Максимальный размер файла лога (MB)"""

# =======================
# Performance
# =======================

SLOW_REQUEST_THRESHOLD_MS: Final[float] = 1000.0
"""Порог для логирования медленных запросов (миллисекунды)"""

SLOW_QUERY_THRESHOLD_MS: Final[float] = 500.0
"""Порог для логирования медленных запросов к БД (миллисекунды)"""

# =======================
# Feature Flags
# =======================

class FeatureFlags:
    """Флаги для включения/выключения функций"""
    
    ENABLE_CACHING: Final[bool] = True
    ENABLE_RATE_LIMITING: Final[bool] = True
    ENABLE_TELEMETRY: Final[bool] = True
    ENABLE_EMAIL_NOTIFICATIONS: Final[bool] = False  # По умолчанию выключено
    ENABLE_PREFETCHING: Final[bool] = True
    ENABLE_REQUEST_COALESCING: Final[bool] = True
