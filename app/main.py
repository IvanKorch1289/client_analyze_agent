import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.advanced_funcs.logging_client import logger
from app.api.routes.agent import agent_router
from app.api.routes.data import data_router
from app.api.routes.utility import utility_router
from app.server.mcp_server import run_mcp_server
from app.services.http_client import AsyncHttpClient
from app.storage.tarantool import TarantoolClient

# =======================
# Lifespan: управление жизненным циклом приложения
# =======================


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("✅ Инициализация приложения...")

    # Создаём папку для заметок
    os.makedirs("notes", exist_ok=True)

    # Инициализируем глобальные клиенты
    await AsyncHttpClient.get_instance()
    await TarantoolClient.get_instance()

    logger.info("✅ Клиенты инициализированы")
    yield
    logger.info("🛑 Завершение работы приложения...")
    await TarantoolClient.close_global()
    await AsyncHttpClient.close_global()
    logger.info("✅ Все соединения закрыты")


# =======================
# FastAPI приложение
# =======================

app = FastAPI(
    title="Multi-Agent System with MCP",
    description="Сервер агентов с поддержкой MCP, Tarantool и внешних API",
    lifespan=lifespan,
)

# Подключаем роутеры
app.include_router(agent_router, prefix="/agent")
app.include_router(data_router, prefix="/data")
app.include_router(utility_router, prefix="/utility")


# =======================
# Фоновые задачи: MCP и Streamlit
# =======================


async def start_background_services():
    """Запускает MCP-сервер и Streamlit в фоне."""

    # Запуск MCP-сервера (должен быть async)
    asyncio.create_task(run_mcp_server())
    logger.info("MCP-сервер запущен в фоне на порту 8001")

    # Запуск Streamlit через threading (не async)
    def run_streamlit():
        time.sleep(3)  # Ждём, пока основной сервер запустится
        os.system("streamlit run app/streamlit_app.py --server.port=8501")

    threading.Thread(target=run_streamlit, daemon=True).start()
    logger.info("Streamlit UI запущен на порту 8501")


# =======================
# Основная функция запуска
# =======================


async def main():
    """Запускает фоновые сервисы и основной FastAPI сервер."""
    await start_background_services()

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
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
