"""
Lightweight in-process application metrics (no external deps).

Designed for debugging / basic observability:
- request counts by route/method/status
- latency percentiles (rolling window)
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Any, Deque, Dict, List, Tuple


@dataclass
class RouteMetrics:
    count: int = 0
    by_status: Dict[int, int] = None  # type: ignore[assignment]
    durations_ms: Deque[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_status is None:
            self.by_status = defaultdict(int)
        if self.durations_ms is None:
            self.durations_ms = deque(maxlen=2000)


class AppMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._started_at = time.time()
        self._routes: Dict[Tuple[str, str], RouteMetrics] = {}

    def observe(self, *, method: str, route: str, status_code: int, duration_ms: float) -> None:
        key = (method.upper(), route)
        with self._lock:
            rm = self._routes.get(key)
            if rm is None:
                rm = RouteMetrics()
                self._routes[key] = rm
            rm.count += 1
            rm.by_status[status_code] += 1
            rm.durations_ms.append(duration_ms)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            routes = list(self._routes.items())
            started_at = self._started_at

        out: Dict[str, Any] = {
            "started_at": started_at,
            "uptime_seconds": round(time.time() - started_at, 2),
            "routes": [],
        }
        for (method, route), rm in sorted(routes, key=lambda x: (x[0][1], x[0][0])):
            durs = list(rm.durations_ms)
            out["routes"].append(
                {
                    "method": method,
                    "route": route,
                    "count": rm.count,
                    "by_status": dict(rm.by_status),
                    "latency_ms": _latency_stats(durs),
                }
            )
        return out

    def reset(self) -> None:
        with self._lock:
            self._routes.clear()
            self._started_at = time.time()


def _latency_stats(durations_ms: List[float]) -> Dict[str, float]:
    if not durations_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0, "max": 0.0}
    s = sorted(durations_ms)
    n = len(s)

    def pct(p: float) -> float:
        if n == 1:
            return float(s[0])
        idx = int(round((p / 100.0) * (n - 1)))
        idx = max(0, min(n - 1, idx))
        return float(s[idx])

    return {
        "p50": round(pct(50), 2),
        "p95": round(pct(95), 2),
        "p99": round(pct(99), 2),
        "avg": round(sum(s) / n, 2),
        "max": round(max(s), 2),
    }


app_metrics = AppMetrics()


__all__ = [
    "RouteMetrics",
    "AppMetrics",
    "app_metrics",
]
