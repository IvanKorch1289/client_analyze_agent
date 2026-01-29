import asyncio
import ipaddress
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from slowapi import Limiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from app.api.error_handlers import install_error_handlers
from app.api.routes.agent import agent_router
from app.api.routes.data import data_router
from app.api.routes.favorites import favorites_router
from app.api.routes.scheduler import scheduler_router
from app.api.routes.utility import utility_router
from app.api.v1 import v1_app
from app.config.settings import settings
from app.config.watchdog import create_config_watchdog
from app.services.http_client import AsyncHttpClient
from app.storage.tarantool import TarantoolClient
from app.utility.app_circuit_breaker import (
    AppCircuitBreaker,
    AppCircuitBreakerConfig,
    AppCircuitBreakerMiddleware,
)
from app.utility.app_metrics import app_metrics
from app.utility.helpers import get_client_ip
from app.utility.logging_client import get_request_id, logger, set_request_id
from app.utility.telemetry import init_telemetry

# Prometheus metrics
from prometheus_fastapi_instrumentator import Instrumentator

# Get backend port from environment or use default
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# =======================
# Rate Limiting Configuration
# =======================

from app.config.constants import (
    RATE_LIMIT_GLOBAL_PER_HOUR,
    RATE_LIMIT_GLOBAL_PER_MINUTE,
)

# Создаем limiter для защиты от DDoS
limiter = Limiter(
    # Важно: учитываем X-Forwarded-For / X-Real-IP (если приложение за прокси).
    # Это уменьшает “слипание” лимитов и делает защиту корректнее в проде.
    key_func=get_client_ip,
    default_limits=[
        f"{RATE_LIMIT_GLOBAL_PER_MINUTE}/minute",
        f"{RATE_LIMIT_GLOBAL_PER_HOUR}/hour",
    ],
    # Можно использовать Redis: "redis://localhost:6379"
    storage_uri=settings.secure.rate_limit_storage or "memory://",
)


def _bool_env(name: str, default: bool = False) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "y", "on")


# =======================
# Lifespan: управление жизненным циклом приложения
# =======================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Менеджер жизненного цикла приложения.

    Инициализирует глобальные клиенты, LLM и фоновые сервисы при старте.
    Закрывает соединения и освобождает ресурсы при остановке.
    """
    logger.info("Инициализация приложения...")

    # Security check on startup (warns if ADMIN_TOKEN is weak/missing)
    from app.shared.toolkit.auth import check_security_on_startup

    check_security_on_startup()

    # Инициализируем OpenTelemetry
    init_telemetry()
    logger.info("OpenTelemetry инициализирован")

    # Запускаем watchdog для hot-reload конфигов (YAML/.env).
    cfg_watchdog = create_config_watchdog()
    cfg_watchdog.start()
    app.state.config_watchdog = cfg_watchdog

    # Создаём папку для отчётов
    os.makedirs("reports", exist_ok=True)

    # Инициализируем глобальные клиенты
    await AsyncHttpClient.get_instance()
    await TarantoolClient.get_instance()

    # Инициализируем LLM
    try:
        from app.agents.llm_init import llm

        app.state.llm = llm
        logger.info("LLM инициализирован")
    except Exception as e:
        logger.warning(f"LLM не инициализирован: {e}")
        app.state.llm = None

    # Запускаем Scheduler для отложенных задач
    from app.services.scheduler_service import get_scheduler_service

    scheduler = get_scheduler_service()
    scheduler.start()
    logger.info("Scheduler запущен для отложенных задач")

    # Запускаем Memory Monitor для защиты от утечек памяти
    from app.shared.memory_monitor import get_memory_monitor

    memory_monitor = get_memory_monitor(
        check_interval=60,  # Проверка каждую минуту
        auto_gc=True,
    )

    # Background task для периодической проверки памяти
    async def memory_check_task():
        """Фоновая задача мониторинга памяти."""
        while True:
            try:
                await memory_monitor.check_and_protect()
            except Exception as e:
                logger.error(f"Memory monitor error: {e}", exc_info=True)
            await asyncio.sleep(60)  # Проверка каждую минуту

    memory_task = asyncio.create_task(memory_check_task())
    app.state.memory_task = memory_task
    logger.info("Memory Monitor запущен для защиты от утечек памяти")

    logger.info("Клиенты инициализированы")
    yield
    logger.info("Завершение работы приложения...")

    # Останавливаем Memory Monitor task
    try:
        memory_task = getattr(app.state, "memory_task", None)
        if memory_task and not memory_task.done():
            memory_task.cancel()
            try:
                await memory_task
            except asyncio.CancelledError:
                pass
        logger.info("Memory Monitor остановлен")
    except Exception as e:
        logger.error(f"Error stopping memory monitor: {e}")

    # Останавливаем watchdog
    try:
        wd = getattr(app.state, "config_watchdog", None)
        if wd:
            wd.stop()
    except Exception:
        pass

    # Останавливаем Scheduler
    scheduler.shutdown()
    logger.info("Scheduler остановлен")

    # H11: Порядок shutdown — сначала HTTP, потом publisher, потом хранилище.
    # Это гарантирует, что in-flight запросы завершатся до закрытия хранилища.
    await AsyncHttpClient.close_global()

    # Закрываем RabbitMQ publisher (H7)
    try:
        from app.messaging.publisher import get_rabbit_publisher

        publisher = get_rabbit_publisher()
        await publisher.close()
        logger.info("RabbitMQ publisher закрыт")
    except Exception as e:
        logger.warning(f"Error closing RabbitMQ publisher: {e}")

    await TarantoolClient.close_global()
    logger.info("Все соединения закрыты")


# =======================
# Request ID Middleware
# =======================


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware for request ID tracking and request logging."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or set_request_id()
        if not get_request_id():
            set_request_id(request_id)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            response.headers["X-Request-ID"] = request_id
            # Полезно для профилирования на клиенте/прокси без логов.
            response.headers["X-Process-Time-ms"] = str(round(duration_ms, 2))

            if duration_ms > 1000:
                logger.structured(
                    "warning",
                    "slow_request",
                    component="http",
                    method=request.method,
                    path=str(request.url.path),
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 2),
                    request_id=request_id,
                )

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.log_exception(
                e,
                component="http",
                context={
                    "method": request.method,
                    "path": str(request.url.path),
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                },
            )
            raise


# =======================
# Request tracing & app metrics (debug)
# =======================


class RequestTraceMiddleware(BaseHTTPMiddleware):
    """
    Debug-friendly per-request tracing.

    Enabled by:
    - APP_DEBUG=true (settings.app.debug) OR
    - HTTP_TRACE_ENABLED=true

    Body logging (small payloads) is opt-in via HTTP_TRACE_BODY=true.
    """

    def __init__(self, app: FastAPI):
        super().__init__(app)
        # Don't cache config here; it can change at runtime via watchdog.
        self._max_body = int(os.getenv("HTTP_TRACE_MAX_BODY_BYTES", "4096"))

    async def dispatch(self, request: Request, call_next):
        enabled = bool(getattr(settings.app, "debug", False)) or _bool_env("HTTP_TRACE_ENABLED", False)
        if not enabled:
            return await call_next(request)

        log_body = _bool_env("HTTP_TRACE_BODY", False)
        request_id = request.headers.get("X-Request-ID") or get_request_id() or set_request_id()
        set_request_id(request_id)

        body_preview = None
        if log_body and request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                if body:
                    body_preview = body[: self._max_body].decode("utf-8", errors="replace")
            except Exception:
                body_preview = None

        logger.structured(
            "debug",
            "request_start",
            component="http",
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            query=str(request.url.query),
            root_path=str(request.scope.get("root_path") or ""),
            body=body_preview,
        )

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Metrics: try to use route template if available
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or str(request.url.path)
        app_metrics.observe(
            method=request.method,
            route=str(route_path),
            status_code=int(response.status_code),
            duration_ms=float(duration_ms),
        )

        logger.structured(
            "debug",
            "request_end",
            component="http",
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            status_code=int(response.status_code),
            duration_ms=round(duration_ms, 2),
        )
        return response


# =======================
# Security Headers Middleware
# =======================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Лёгкий middleware для базовых security headers.

    Делается отдельно от CORS, чтобы:
    - не тащить зависимости
    - держать логику в одном месте
    - не ломать поведение эндпоинтов
    """

    def __init__(self, app: FastAPI):
        super().__init__(app)
        # Don't cache config here; it can change at runtime via watchdog.

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        secure = settings.secure
        if not bool(secure.enable_security_headers):
            return response

        # Старайтесь не “перетира́ть” заголовки, если их уже выставил прокси.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

        if bool(secure.hsts_enabled):
            # HSTS имеет смысл только под HTTPS, но выставление под HTTP не критично.
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={int(secure.hsts_max_age)}; includeSubDomains",
            )

        if bool(secure.csp_enabled):
            response.headers.setdefault(
                "Content-Security-Policy",
                secure.csp_directives or "default-src 'self'",
            )

        return response


# =======================
# IP allow/deny filtering (optional)
# =======================


class IpFilterMiddleware(BaseHTTPMiddleware):
    """
    Optional IP allow/deny lists from settings.secure.

    Supports:
    - single IPs ("1.2.3.4")
    - CIDRs ("10.0.0.0/8")
    """

    def __init__(self, app: FastAPI):
        super().__init__(app)
        # Config is dynamic; parse on demand with caching.

    async def dispatch(self, request: Request, call_next):
        wl = settings.secure.ip_whitelist or []
        bl = settings.secure.ip_blacklist or []
        enabled = bool(wl or bl)
        if not enabled:
            return await call_next(request)

        allow_rules = _parse_ip_list_cached(tuple(wl))
        deny_rules = _parse_ip_list_cached(tuple(bl))

        ip = get_client_ip(request)
        rid = request.headers.get("X-Request-ID") or get_request_id() or set_request_id()
        set_request_id(rid)

        if _ip_in_rules(ip, deny_rules):
            return JSONResponse(
                status_code=403,
                content={
                    "status": "error",
                    "error": {
                        "code": "forbidden",
                        "message": "IP is blocked",
                        "request_id": rid,
                    },
                },
                headers={"X-Request-ID": rid},
            )

        if allow_rules and not _ip_in_rules(ip, allow_rules):
            return JSONResponse(
                status_code=403,
                content={
                    "status": "error",
                    "error": {
                        "code": "forbidden",
                        "message": "IP is not allowed",
                        "request_id": rid,
                    },
                },
                headers={"X-Request-ID": rid},
            )

        return await call_next(request)


from functools import lru_cache


@lru_cache(maxsize=128)
def _parse_ip_list_cached(values: tuple[str, ...]):
    rules = []
    for v in values:
        try:
            v = (v or "").strip()
            if not v:
                continue
            if "/" in v:
                rules.append(ipaddress.ip_network(v, strict=False))
            else:
                rules.append(ipaddress.ip_address(v))
        except Exception:
            # Ignore invalid entries (config should not crash app).
            continue
    return rules


def _ip_in_rules(ip: str, rules) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
    except Exception:
        return False
    for r in rules:
        try:
            if isinstance(r, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
                if ip_obj in r:
                    return True
            else:
                if ip_obj == r:
                    return True
        except Exception:
            continue
    return False


# =======================
# Dynamic trusted host check (config hot-reload friendly)
# =======================


class DynamicTrustedHostMiddleware(BaseHTTPMiddleware):
    """
    Trusted-host validation driven by settings.secure.trusted_hosts.

    This replaces Starlette's TrustedHostMiddleware to allow hot reload.
    """

    async def dispatch(self, request: Request, call_next):
        allowed = settings.secure.trusted_hosts or []
        if not allowed:
            return await call_next(request)

        host = request.headers.get("host", "")
        # strip port
        host = host.split(":")[0].strip().lower()
        if not host:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Missing Host header"},
            )

        if not _host_allowed(host, allowed):
            rid = request.headers.get("X-Request-ID") or get_request_id() or set_request_id()
            set_request_id(rid)
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "error": {
                        "code": "invalid_host",
                        "message": "Invalid host header",
                        "request_id": rid,
                    },
                },
                headers={"X-Request-ID": rid},
            )

        return await call_next(request)


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    from fnmatch import fnmatch

    for pattern in allowed_hosts:
        p = (pattern or "").strip().lower()
        if not p:
            continue
        if p == "*":
            return True
        if fnmatch(host, p):
            return True
    return False


# =======================
# HTTPS Redirect Middleware
# =======================


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Redirects HTTP requests to HTTPS when enabled.

    Controlled by settings.secure.https_redirect_enabled.
    Respects X-Forwarded-Proto header for apps behind proxies.
    Excludes health check endpoints to allow internal HTTP monitoring.
    """

    _excluded_paths = ("/utility/health", "/api/v1/utility/health", "/metrics")

    async def dispatch(self, request: Request, call_next):
        if not getattr(settings.secure, "https_redirect_enabled", False):
            return await call_next(request)

        # Skip health checks (internal monitoring should work over HTTP)
        if request.url.path in self._excluded_paths:
            return await call_next(request)

        # Check if already HTTPS (direct or via proxy)
        scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
        if scheme == "https":
            return await call_next(request)

        # Redirect to HTTPS
        https_url = request.url.replace(scheme="https")
        return RedirectResponse(url=str(https_url), status_code=307)


# =======================
# Legacy API deprecation headers
# =======================


class LegacyApiDeprecationMiddleware(BaseHTTPMiddleware):
    """
    Adds deprecation hints for unversioned endpoints.

    This keeps backward compatibility while nudging clients to /api/v1.
    """

    _legacy_prefixes = ("/agent", "/data", "/scheduler", "/utility")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only legacy (root app) requests; mounted v1 has root_path="/api/v1".
        root_path = request.scope.get("root_path") or ""
        if root_path:
            return response

        path = request.url.path
        if not path.startswith(self._legacy_prefixes):
            return response

        # Minimal standardized signals for clients/proxies.
        response.headers.setdefault("Deprecation", "true")
        response.headers.setdefault("Link", '</api/v1>; rel="latest"')
        response.headers.setdefault("Sunset", "Thu, 31 Dec 2026 23:59:59 GMT")
        return response


# =======================
# FastAPI приложение
# =======================

app = FastAPI(
    title="Multi-Agent Client Analysis System",
    description="Сервер агентов для анализа клиентов с поддержкой Tarantool и внешних API",
    lifespan=lifespan,
    # Root app only hosts redirects + legacy endpoints.
    # Real OpenAPI lives under /api/v1 to avoid duplicated schemas.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Добавляем rate limiter в state приложения
app.state.limiter = limiter
# Centralized error shape (includes RateLimitExceeded).
install_error_handlers(app)

_otel_excluded_urls = "/utility/health,/utility/metrics,/api/v1/utility/health,/api/v1/utility/metrics"
FastAPIInstrumentor.instrument_app(app, excluded_urls=_otel_excluded_urls)

# =======================
# Prometheus Metrics
# =======================
# Instrumentator автоматически собирает метрики HTTP запросов
# Метрики доступны на /metrics endpoint
instrumentator = Instrumentator(
    should_group_status_codes=False,  # Детальные status codes
    should_ignore_untemplated=False,  # Не игнорируем нетемплейтные пути
    should_respect_env_var=True,  # Учитываем ENABLE_METRICS env var
    should_instrument_requests_inprogress=True,  # Метрики in-progress requests
    excluded_handlers=["/metrics", "/metrics/custom"],  # Исключаем endpoints метрик
    env_var_name="ENABLE_METRICS",
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
)

# Добавляем стандартные HTTP метрики
instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Добавляем endpoint для кастомных application-level метрик
from app.shared.prometheus_metrics import metrics as custom_metrics
from starlette.responses import Response


@app.get("/metrics/custom", include_in_schema=False)
async def custom_metrics_endpoint():
    """
    Кастомные метрики приложения (LLM, cache, risk scores, etc.).

    Используйте /metrics для HTTP метрик и /metrics/custom для application метрик.
    Или объедините оба в вашем Prometheus scrape config.
    """
    return Response(
        content=custom_metrics.get_metrics(),
        media_type=custom_metrics.get_content_type(),
    )


logger.info("Prometheus metrics enabled at /metrics and /metrics/custom")

# Сжатие больших ответов (отчёты/метрики/история). Минимальный размер — чтобы
# не тратить CPU на мелкие ответы.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS (для Streamlit/UI и внешних интеграций).
if settings.secure.cors_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.secure.cors_origins or [],
        allow_credentials=bool(settings.secure.cors_credentials),
        allow_methods=settings.secure.cors_methods or ["*"],
        allow_headers=settings.secure.cors_headers or ["*"],
    )

# HTTPS redirect (for production behind HTTPS termination proxy)
app.add_middleware(HTTPSRedirectMiddleware)

# Базовые security headers.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LegacyApiDeprecationMiddleware)
app.add_middleware(IpFilterMiddleware)
app.add_middleware(DynamicTrustedHostMiddleware)

# Circuit breaker на уровне приложения (fail-fast при всплеске 5xx).
app_circuit_breaker = AppCircuitBreaker(
    AppCircuitBreakerConfig(
        failure_threshold=int(os.getenv("APP_CB_FAILURE_THRESHOLD", "30")),
        window_seconds=int(os.getenv("APP_CB_WINDOW_SECONDS", "60")),
        open_seconds=int(os.getenv("APP_CB_OPEN_SECONDS", "30")),
    )
)
app.state.app_circuit_breaker = app_circuit_breaker
app.add_middleware(AppCircuitBreakerMiddleware, breaker=app_circuit_breaker)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestTraceMiddleware)


# -----------------------
# Root UX helpers
# -----------------------
@app.get("/", include_in_schema=False)
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "message": "Use versioned API under /api/v1",
            "docs": "/api/v1/docs",
            "openapi": "/api/v1/openapi.json",
        }
    )


@app.get("/docs", include_in_schema=False)
async def root_docs_redirect() -> RedirectResponse:
    return RedirectResponse(url="/api/v1/docs")


@app.get("/openapi.json", include_in_schema=False)
async def root_openapi_redirect() -> RedirectResponse:
    return RedirectResponse(url="/api/v1/openapi.json")


# -----------------------
# API versioning
# -----------------------
# v1: primary, versioned API (recommended for integrations).
v1_app.state.app_circuit_breaker = app_circuit_breaker
FastAPIInstrumentor.instrument_app(v1_app, excluded_urls="/utility/health,/utility/metrics")
app.mount("/api/v1", v1_app)

# Legacy (unversioned) endpoints: kept for backward compatibility,
# but hidden from OpenAPI to avoid duplicated schemas.
app.include_router(agent_router, include_in_schema=False)
app.include_router(data_router, include_in_schema=False)
app.include_router(favorites_router, include_in_schema=False)
app.include_router(scheduler_router, include_in_schema=False)
app.include_router(utility_router, include_in_schema=False)


# =======================
# Основная функция запуска
# =======================


async def main():
    """Запускает основной FastAPI сервер."""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=BACKEND_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


# =======================
# Точка входа
# =======================

if __name__ == "__main__":
    logger.info("Starting Multi-Agent system...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("✋ Приложение остановлено вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise
