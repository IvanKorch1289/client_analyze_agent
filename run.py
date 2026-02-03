import asyncio
import os
import subprocess
import sys
import time
from threading import Thread

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv('.env')
    print(f"✅ .env загружен. ADMIN_TOKEN: {'установлен' if os.getenv('ADMIN_TOKEN') else 'НЕ УСТАНОВЛЕН'}")
except ImportError:
    print("⚠️ python-dotenv не установлен, используем системные переменные")

from app.config.settings import settings


def run_backend():
    """Run FastAPI backend on port 8000.

    Production: gunicorn с несколькими Uvicorn workers для параллельной обработки.
    Development: одиночный uvicorn для удобства отладки.
    """
    app_cfg = settings.app
    port = str(app_cfg.backend_port)
    os.environ["BACKEND_PORT"] = port
    workers = app_cfg.workers

    if workers > 1:
        # Production: gunicorn + uvicorn workers
        subprocess.run([
            sys.executable, "-m", "gunicorn",
            "app.main:app",
            "--bind", f"0.0.0.0:{port}",
            "--workers", str(workers),
            "--worker-class", "uvicorn.workers.UvicornWorker",
            "--timeout", "120",
            "--graceful-timeout", "30",
            "--keep-alive", "5",
            "--max-requests", str(app_cfg.max_requests),
            "--max-requests-jitter", "200",
            "--access-logfile", "-",
        ])
    else:
        # Development: single uvicorn
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", port,
        ])


def run_streamlit():
    """Run Streamlit frontend on port 5000."""
    time.sleep(2)
    port = str(settings.app.streamlit_port)
    os.environ["STREAMLIT_PORT"] = port
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "app/frontend/app.py",  # Entry point - single-page frontend
        f"--server.port={port}",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--browser.gatherUsageStats=false"
    ])


if __name__ == "__main__":
    backend_thread = Thread(target=run_backend, daemon=True)
    backend_thread.start()

    run_streamlit()
