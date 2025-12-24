"""
OpenTelemetry integration for the application.
Provides tracing, logging, and metrics collection.
"""

import logging
import os
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import SpanKind

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "counterparty-analysis")


class InMemorySpanExporter(SpanExporter):
    """In-memory span exporter that stores traces for UI display."""

    def __init__(self, max_spans: int = 1000):
        self._spans: deque = deque(maxlen=max_spans)
        self._lock = Lock()

    def export(self, spans) -> SpanExportResult:
        with self._lock:
            for span in spans:
                ctx = span.context
                trace_id = format(ctx.trace_id, "032x") if ctx else "unknown"
                span_id = format(ctx.span_id, "016x") if ctx else "unknown"

                start_ts = span.start_time or 0
                end_ts = span.end_time

                span_data = {
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "name": span.name,
                    "kind": span.kind.name if span.kind else "INTERNAL",
                    "start_time": datetime.fromtimestamp(start_ts / 1e9).isoformat(),
                    "end_time": (datetime.fromtimestamp(end_ts / 1e9).isoformat() if end_ts else None),
                    "duration_ms": (round((end_ts - start_ts) / 1e6, 2) if end_ts else None),
                    "status": span.status.status_code.name if span.status else "UNSET",
                    "attributes": dict(span.attributes) if span.attributes else {},
                    "events": (
                        [
                            {
                                "name": event.name,
                                "timestamp": datetime.fromtimestamp(event.timestamp / 1e9).isoformat(),
                                "attributes": (dict(event.attributes) if event.attributes else {}),
                            }
                            for event in span.events
                        ]
                        if span.events
                        else []
                    ),
                }
                self._spans.append(span_data)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def get_spans(self, limit: int = 100, since_minutes: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get stored spans, optionally filtered by time."""
        with self._lock:
            spans = list(self._spans)

        if since_minutes:
            cutoff = datetime.now().timestamp() - (since_minutes * 60)
            spans = [s for s in spans if datetime.fromisoformat(s["start_time"]).timestamp() > cutoff]

        return list(reversed(spans[-limit:]))

    def get_trace_stats(self) -> Dict[str, Any]:
        """Get trace statistics."""
        with self._lock:
            spans = list(self._spans)

        if not spans:
            return {
                "total_spans": 0,
                "avg_duration_ms": 0,
                "error_count": 0,
                "by_kind": {},
                "by_status": {},
            }

        durations = [s["duration_ms"] for s in spans if s["duration_ms"]]

        by_kind: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        error_count = 0

        for span in spans:
            kind = span.get("kind", "INTERNAL")
            by_kind[kind] = by_kind.get(kind, 0) + 1

            status = span.get("status", "UNSET")
            by_status[status] = by_status.get(status, 0) + 1

            if status == "ERROR":
                error_count += 1

        return {
            "total_spans": len(spans),
            "avg_duration_ms": (round(sum(durations) / len(durations), 2) if durations else 0),
            "error_count": error_count,
            "by_kind": by_kind,
            "by_status": by_status,
        }

    def clear(self):
        """Clear all stored spans."""
        with self._lock:
            self._spans.clear()


class LogStore:
    """In-memory log storage for UI display."""

    def __init__(self, max_logs: int = 5000):
        self._logs: deque = deque(maxlen=max_logs)
        self._lock = Lock()

    def add(
        self,
        level: str,
        message: str,
        logger_name: str = "",
        extra: Optional[Dict] = None,
    ):
        with self._lock:
            self._logs.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "level": level,
                    "message": message,
                    "logger": logger_name,
                    "extra": extra or {},
                }
            )

    def get_logs(
        self,
        limit: int = 100,
        since_minutes: Optional[int] = None,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            logs = list(self._logs)

        if since_minutes:
            cutoff = datetime.now().timestamp() - (since_minutes * 60)
            logs = [log for log in logs if datetime.fromisoformat(log["timestamp"]).timestamp() > cutoff]

        if level:
            logs = [log for log in logs if log["level"] == level.upper()]

        return list(reversed(logs[-limit:]))

    def get_stats(self) -> Dict[str, int]:
        with self._lock:
            logs = list(self._logs)

        stats = {"total": len(logs)}
        for log in logs:
            lvl = log["level"]
            stats[lvl] = stats.get(lvl, 0) + 1
        return stats

    def clear(self):
        with self._lock:
            self._logs.clear()


class LogStoreHandler(logging.Handler):
    """Logging handler that stores logs in LogStore."""

    def __init__(self, log_store: LogStore):
        super().__init__()
        self.log_store = log_store

    def emit(self, record: logging.LogRecord):
        try:
            message = self.format(record)
            extra = {}
            if hasattr(record, "__dict__"):
                extra = {
                    k: v
                    for k, v in record.__dict__.items()
                    if k
                    not in (
                        "name",
                        "msg",
                        "args",
                        "created",
                        "filename",
                        "funcName",
                        "levelname",
                        "levelno",
                        "lineno",
                        "module",
                        "msecs",
                        "pathname",
                        "process",
                        "processName",
                        "relativeCreated",
                        "thread",
                        "threadName",
                        "exc_info",
                        "exc_text",
                        "stack_info",
                        "message",
                    )
                }
            self.log_store.add(
                level=record.levelname,
                message=message,
                logger_name=record.name,
                extra=extra,
            )
        except Exception:
            pass


_span_exporter: Optional[InMemorySpanExporter] = None
_log_store: Optional[LogStore] = None
_tracer: Optional[trace.Tracer] = None


def init_telemetry():
    """Initialize OpenTelemetry tracing and logging."""
    global _span_exporter, _log_store, _tracer

    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": "1.0.0",
        }
    )

    provider = TracerProvider(resource=resource)

    _span_exporter = InMemorySpanExporter(max_spans=1000)
    provider.add_span_processor(SimpleSpanProcessor(_span_exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(__name__)

    _log_store = LogStore(max_logs=5000)
    handler = LogStoreHandler(_log_store)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG)
    app_logger.addHandler(handler)

    return provider


def get_tracer() -> trace.Tracer:
    """Get the application tracer."""
    global _tracer
    if _tracer is None:
        init_telemetry()
    if _tracer is None:
        return trace.get_tracer(__name__)
    return _tracer


def get_span_exporter() -> Optional[InMemorySpanExporter]:
    """Get the span exporter for accessing stored traces."""
    return _span_exporter


def get_log_store() -> Optional[LogStore]:
    """Get the log store for accessing stored logs."""
    return _log_store


def create_span(name: str, kind: SpanKind = SpanKind.INTERNAL, attributes: Optional[Dict] = None):
    """Create a new span context manager."""
    tracer = get_tracer()
    return tracer.start_as_current_span(name, kind=kind, attributes=attributes)
