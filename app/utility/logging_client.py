import contextvars
import json
import logging
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.text import Text

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

app_logger = logging.getLogger("mcp-server")
app_logger.setLevel(logging.DEBUG)
app_logger.handlers.clear()

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def generate_request_id() -> str:
    return str(uuid.uuid4())[:8]


def get_request_id() -> Optional[str]:
    return request_id_var.get()


def set_request_id(request_id: Optional[str] = None) -> str:
    rid = request_id or generate_request_id()
    request_id_var.set(rid)
    return rid


class AppLogger:
    _instance = None
    _console = Console()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_handlers()
        return cls._instance

    def _setup_handlers(self):
        rich_handler = RichHandler(
            console=self._console,
            show_time=True,
            show_path=False,
            markup=True,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
        )
        rich_handler.setFormatter(logging.Formatter("%(message)s"))
        app_logger.addHandler(rich_handler)
        self._add_timed_file_handler()

    def _add_timed_file_handler(self):
        today = datetime.now().strftime("%Y-%m-%d")
        file_path = LOGS_DIR / f"{today}.log"
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s | %(name)s | %(message)s", datefmt="%H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        app_logger.addHandler(file_handler)

    def _renew_file_handler(self):
        for handler in app_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                app_logger.removeHandler(handler)
        self._add_timed_file_handler()

    def _ensure_daily_log(self):
        today = datetime.now().strftime("%Y-%m-%d")
        current_file = LOGS_DIR / f"{today}.log"
        if not any(
            isinstance(h, logging.FileHandler) and Path(h.baseFilename) == current_file
            for h in app_logger.handlers
        ):
            self._renew_file_handler()

    def log_request(self, request: httpx.Request):
        self._ensure_daily_log()
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold cyan", width=10)
        table.add_column()
        table.add_row("➡️ ЗАПРОС", "")
        table.add_row("Метод", request.method)
        table.add_row("URL", str(request.url))
        table.add_row("Заголовки", self._format_headers(request.headers))
        if request.content:
            body = request.content.decode("utf-8", errors="replace")
            table.add_row("Тело", self._truncate(body, 500))
        app_logger.info("")
        self._console.print(table)

    def log_response(self, response: httpx.Response, duration: float = 0.0):
        self._ensure_daily_log()
        request = response.request
        status_color = "red" if response.is_error else "green"
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold cyan", width=12)
        table.add_column()
        table.add_row("⬅️ ОТВЕТ", "")
        table.add_row("Метод", request.method)
        table.add_row("URL", str(request.url))
        table.add_row("Статус", Text(str(response.status_code), style=status_color))
        table.add_row("Время", f"{duration:.2f} с")
        try:
            body = response.text
            if body:
                table.add_row("Тело", self._truncate(body, 500))
        except Exception as e:
            app_logger.debug(f"Failed to add body to table: {e}")
        app_logger.info("")
        self._console.print(table)

    def _format_headers(self, headers: httpx.Headers) -> str:
        return "\n".join(
            f"{k}: {v}"
            for k, v in headers.items()
            if k.lower() not in ["authorization", "cookie"]
        )

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def info(self, message: str, component: str = "app"):
        self._ensure_daily_log()
        app_logger.info(f"[{component.upper()}] {message}")

    def error(self, message: str, component: str = "app", exc_info=False):
        self._ensure_daily_log()
        app_logger.error(f"[{component.upper()}] {message}", exc_info=exc_info)

    def debug(self, message: str, component: str = "app"):
        self._ensure_daily_log()
        app_logger.debug(f"[{component.upper()}] {message}")

    def warning(self, message: str, component: str = "app"):
        self._ensure_daily_log()
        app_logger.warning(f"[{component.upper()}] {message}")

    def exception(self, message: str, component: str = "app"):
        self._ensure_daily_log()
        app_logger.exception(f"[{component.upper()}] {message}")

    def structured(self, level: str, event: str, component: str = "app", **extra: Any):
        self._ensure_daily_log()
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.upper(),
            "event": event,
            "component": component,
            "request_id": get_request_id(),
            **extra,
        }
        json_str = json.dumps(log_entry, ensure_ascii=False, default=str)
        log_func = getattr(app_logger, level.lower(), app_logger.info)
        log_func(f"[STRUCTURED] {json_str}")

    def log_exception(
        self,
        exc: Exception,
        component: str = "app",
        context: Optional[Dict[str, Any]] = None,
    ):
        self._ensure_daily_log()
        exc_info = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc(),
            "request_id": get_request_id(),
        }
        if context:
            exc_info["context"] = context
        self.structured("error", "exception", component=component, **exc_info)

    def timed(self, operation: str, component: str = "app"):
        return TimedOperation(operation, component, self)


class TimedOperation:
    def __init__(self, operation: str, component: str, logger_instance: "AppLogger"):
        self.operation = operation
        self.component = component
        self.logger = logger_instance
        self.start_time: float = 0
        self.extra: Dict[str, Any] = {}

    def add_context(self, **kwargs: Any):
        self.extra.update(kwargs)
        return self

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        if exc_type is not None:
            self.logger.structured(
                "error",
                f"{self.operation}_failed",
                component=self.component,
                duration_ms=round(duration_ms, 2),
                error=str(exc_val),
                **self.extra,
            )
        else:
            self.logger.structured(
                "info",
                f"{self.operation}_completed",
                component=self.component,
                duration_ms=round(duration_ms, 2),
                **self.extra,
            )
        return False

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


logger = AppLogger()
