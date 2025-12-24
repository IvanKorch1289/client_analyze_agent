"""
Circuit breaker на уровне приложения (middleware).

Зачем:
- защищает приложение от лавинообразных ошибок (например, перегруз CPU/IO, падения
  зависимостей, ошибки в critical path)
- даёт быстрый "fail-fast" вместо накапливания очередей и таймаутов

Это НЕ заменяет circuit breaker для внешних сервисов (он уже есть в http_client),
а защищает сам web-процесс.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


@dataclass
class AppCircuitBreakerConfig:
    """
    Конфигурация app-level circuit breaker.

    failure_threshold: сколько "плохих" ответов в окне нужно, чтобы открыть breaker
    window_seconds: длина скользящего окна
    open_seconds: сколько секунд держать состояние OPEN
    status_codes: какие HTTP-коды считаем "ошибками" для breaker'а
    """

    failure_threshold: int = 30
    window_seconds: int = 60
    open_seconds: int = 30
    status_codes: tuple[int, ...] = (500, 502, 503, 504)
    exclude_paths: tuple[str, ...] = (
        "/utility/health",
        "/utility/metrics",
        "/utility/asyncapi",
        "/utility/asyncapi.json",
        "/openapi.json",
    )


class AppCircuitBreaker:
    """Простой in-memory circuit breaker со скользящим окном."""

    def __init__(self, config: AppCircuitBreakerConfig):
        self.config = config
        self._failures: Deque[float] = deque()
        self._opened_until_ts: float = 0.0

    def is_open(self) -> bool:
        return time.time() < self._opened_until_ts

    def _trim(self, now: float) -> None:
        cutoff = now - float(self.config.window_seconds)
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def record_failure(self) -> None:
        now = time.time()
        self._failures.append(now)
        self._trim(now)
        if len(self._failures) >= int(self.config.failure_threshold):
            self._opened_until_ts = max(self._opened_until_ts, now + float(self.config.open_seconds))

    def record_success(self) -> None:
        # Для простоты не записываем успехи; сброс идёт по истечению open_seconds
        # и по вытеснению ошибок из окна.
        now = time.time()
        self._trim(now)

    def status(self) -> dict:
        now = time.time()
        self._trim(now)
        return {
            "state": "open" if self.is_open() else "closed",
            "failures_in_window": len(self._failures),
            "window_seconds": self.config.window_seconds,
            "failure_threshold": self.config.failure_threshold,
            "open_seconds": self.config.open_seconds,
            "opened_until": self._opened_until_ts if self._opened_until_ts else None,
        }

    def reset(self) -> None:
        self._failures.clear()
        self._opened_until_ts = 0.0


class AppCircuitBreakerMiddleware(BaseHTTPMiddleware):
    """
    Middleware, который:
    - в состоянии OPEN быстро возвращает 503
    - считает ошибки по ответам (5xx) и по исключениям
    """

    def __init__(self, app, breaker: AppCircuitBreaker):
        super().__init__(app)
        self.breaker = breaker

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in self.breaker.config.exclude_paths:
            return await call_next(request)

        if self.breaker.is_open():
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable (app circuit breaker open)",
                },
                headers={"Retry-After": str(self.breaker.config.open_seconds)},
            )

        try:
            response = await call_next(request)
            if response.status_code in self.breaker.config.status_codes:
                self.breaker.record_failure()
            else:
                self.breaker.record_success()
            return response
        except Exception:
            self.breaker.record_failure()
            raise


__all__ = [
    "AppCircuitBreakerConfig",
    "AppCircuitBreaker",
    "AppCircuitBreakerMiddleware",
]
