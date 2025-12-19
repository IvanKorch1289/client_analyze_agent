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


def run_backend():
    """Run FastAPI backend on port 8000."""
    os.environ["BACKEND_PORT"] = "8000"
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ])


def run_streamlit():
    """Run Streamlit frontend on port 5000."""
    time.sleep(2)
    os.environ["STREAMLIT_PORT"] = "5000"
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "app/frontend/pages/0_🏠_Главная.py",  # Entry point - главная страница
        "--server.port=5000",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--browser.gatherUsageStats=false"
    ])


if __name__ == "__main__":
    backend_thread = Thread(target=run_backend, daemon=True)
    backend_thread.start()
    
    run_streamlit()
