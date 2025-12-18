import asyncio
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes.agent import agent_router
from app.api.routes.data import data_router
from app.api.routes.utility import utility_router
from app.services.http_client import AsyncHttpClient
from app.storage.tarantool import TarantoolClient
from app.utility.logging_client import get_request_id, logger, set_request_id
from app.utility.telemetry import init_telemetry

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
    key_func=get_remote_address,
    default_limits=[
        f"{RATE_LIMIT_GLOBAL_PER_MINUTE}/minute",
        f"{RATE_LIMIT_GLOBAL_PER_HOUR}/hour",
    ],
    storage_uri="memory://",  # Можно использовать Redis: "redis://localhost:6379"
)


# =======================
# Lifespan: управление жизненным циклом приложения
# =======================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Initializes global clients, LLM, and background services on startup.
    Cleans up connections on shutdown.
    """
    logger.info("Инициализация приложения...")

    # Инициализируем OpenTelemetry
    init_telemetry()
    logger.info("OpenTelemetry инициализирован")

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

    logger.info("Клиенты инициализированы")
    yield
    logger.info("Завершение работы приложения...")
    await TarantoolClient.close_global()
    await AsyncHttpClient.close_global()
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
# FastAPI приложение
# =======================

app = FastAPI(
    title="Multi-Agent Client Analysis System",
    description="Сервер агентов для анализа клиентов с поддержкой Tarantool и внешних API",
    lifespan=lifespan,
)

# Добавляем rate limiter в state приложения
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

FastAPIInstrumentor.instrument_app(app, excluded_urls="/utility/health,/utility/metrics")

app.add_middleware(RequestIdMiddleware)

app.include_router(agent_router)
app.include_router(data_router)
app.include_router(utility_router)


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
    print("🌐 Запуск Multi-Agent системы...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("✋ Приложение остановлено вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise
