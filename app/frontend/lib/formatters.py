from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def format_ts(ts: Any, default: str = "N/A") -> str:
    if ts is None:
        return default
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return default
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ts if ts else default
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    return str(ts) if ts else default


def get_risk_emoji(level: Optional[str]) -> str:
    level = (level or "").lower().strip()
    return {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "critical": "🔴",
    }.get(level, "⚪")


def get_status_emoji(status: Optional[str]) -> str:
    status = (status or "").lower().strip()
    return {
        "closed": "🟢",
        "open": "🔴",
        "half-open": "🟡",
        "half_open": "🟡",
        "healthy": "🟢",
        "degraded": "🟡",
        "unhealthy": "🔴",
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
    }.get(status, "⚪")
