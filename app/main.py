import asyncio
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from threading import Thread

import uvicorn
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.advanced_funcs.logging_client import get_request_id, logger, set_request_id
from app.api.routes.agent import agent_router
from app.api.routes.data import data_router
from app.api.routes.utility import utility_router
from app.server.mcp_server import run_mcp_server
from app.services.http_client import AsyncHttpClient
from app.storage.tarantool import TarantoolClient

# Get backend port from environment or use default
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "5000"))


# =======================
# Streamlit startup
# =======================


def run_streamlit():
    """Run Streamlit frontend on specified port."""
    import time

    time.sleep(2)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app/streamlit_app.py",
            f"--server.port={STREAMLIT_PORT}",
            "--server.address=0.0.0.0",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]
    )


# =======================
# Lifespan: управление жизненным циклом приложения
# =======================


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Инициализация приложения...")

    # Создаём папку для заметок
    os.makedirs("notes", exist_ok=True)

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

    # Запускаем Streamlit в фоновом потоке
    streamlit_thread = Thread(target=run_streamlit, daemon=True)
    streamlit_thread.start()
    logger.info(f"Streamlit запущен на порту {STREAMLIT_PORT}")

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
    title="Multi-Agent System with MCP",
    description="Сервер агентов с поддержкой MCP, Tarantool и внешних API",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)

app.include_router(agent_router)
app.include_router(data_router)
app.include_router(utility_router)


# =======================
# Фоновые задачи: MCP
# =======================


async def start_background_services():
    """Запускает MCP-сервер в фоне."""
    asyncio.create_task(run_mcp_server())
    logger.info("MCP-сервер запущен в фоне на порту 8001")


# =======================
# Основная функция запуска
# =======================


async def main():
    """Запускает фоновые сервисы и основной FastAPI сервер."""
    await start_background_services()

    config = uvicorn.Config(
        app,
        host="localhost",
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
