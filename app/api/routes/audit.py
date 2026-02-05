"""
Audit trail API endpoints (Phase 6).

Provides read-only access to the system audit trail for compliance monitoring.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.shared.audit_trail import audit_log
from app.shared.toolkit.auth import Permission, require_permission

audit_router = APIRouter(prefix="/audit", tags=["Audit"])


@audit_router.get(
    "/entries",
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
)
async def get_audit_entries(
    action: Optional[str] = Query(None, description="Filter by action prefix (e.g., 'analysis')"),
    role: Optional[str] = Query(None, description="Filter by user role"),
    success: Optional[bool] = Query(None, description="Filter by success/failure"),
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
) -> Dict[str, Any]:
    """
    Query audit trail entries with optional filters.

    Entries are returned newest-first. Use action prefix to filter
    (e.g., 'analysis' matches 'analysis.create', 'analysis.batch').
    """
    entries = audit_log.query(
        action=action,
        role=role,
        success=success,
        limit=limit,
    )
    return {
        "status": "success",
        "count": len(entries),
        "entries": entries,
    }


@audit_router.get(
    "/stats",
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
)
async def get_audit_stats() -> Dict[str, Any]:
    """
    Get aggregate audit trail statistics.

    Returns counts grouped by action category, role, and failure count.
    """
    stats = audit_log.stats()
    return {
        "status": "success",
        **stats,
    }


__all__ = ["audit_router"]
