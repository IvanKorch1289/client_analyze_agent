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


def _is_production() -> bool:
    """Определяет production-окружение по переменной APP_ENV."""
    return os.getenv("APP_ENV", "dev").lower() in ("production", "prod")


def run_backend():
    """Run FastAPI backend on port 8000.

    Production: gunicorn с несколькими Uvicorn workers для параллельной обработки.
    Development: одиночный uvicorn для удобства отладки.
    """
    port = os.getenv("BACKEND_PORT", "8000")
    os.environ["BACKEND_PORT"] = port
    workers = int(os.getenv("WEB_WORKERS", "4" if _is_production() else "1"))

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
            "--max-requests", "2000",
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
    os.environ["STREAMLIT_PORT"] = "5000"
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "app/frontend/app.py",  # Entry point - single-page frontend
        "--server.port=5000",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--browser.gatherUsageStats=false"
    ])


if __name__ == "__main__":
    backend_thread = Thread(target=run_backend, daemon=True)
    backend_thread.start()

    run_streamlit()
