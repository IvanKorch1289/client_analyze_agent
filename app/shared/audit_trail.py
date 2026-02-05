"""
Audit trail for tracking all API actions (Phase 6.7).

Provides immutable logging of user actions for compliance and security.
All entries are append-only and include user role, action, and result.

Usage:
    from app.shared.audit_trail import audit_log

    audit_log.record(
        action="analysis.create",
        role="analyst",
        details={"client_name": "Test", "inn": "7707083893"},
        request_id="req-123",
    )
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.shared.toolkit.logging import logger


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit trail entry."""

    id: str
    timestamp: float
    action: str
    role: str
    details: Dict[str, Any]
    request_id: Optional[str]
    ip_address: Optional[str]
    success: bool
    error: Optional[str]


class AuditTrail:
    """Append-only audit trail.

    Stores entries in a bounded deque (in-memory) and logs to structured logger.
    For production, entries should also be persisted to Tarantool or external log.
    """

    def __init__(self, max_entries: int = 50000):
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)

    def record(
        self,
        action: str,
        role: str = "guest",
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> AuditEntry:
        """Record an audit entry.

        Args:
            action: Action identifier (e.g., "analysis.create", "report.delete")
            role: User role that performed the action
            details: Action-specific details (sanitized, no PII)
            request_id: Correlation ID for request tracing
            ip_address: Client IP address
            success: Whether the action succeeded
            error: Error message if action failed
        """
        entry = AuditEntry(
            id=str(uuid.uuid4())[:12],
            timestamp=time.time(),
            action=action,
            role=role,
            details=details or {},
            request_id=request_id,
            ip_address=ip_address,
            success=success,
            error=error,
        )
        self._entries.append(entry)

        logger.structured(
            "info" if success else "warning",
            "audit_trail",
            component="audit",
            action=action,
            role=role,
            success=success,
            request_id=request_id,
            error=error,
        )

        return entry

    def query(
        self,
        action: Optional[str] = None,
        role: Optional[str] = None,
        success: Optional[bool] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit entries with filters.

        Args:
            action: Filter by action prefix (e.g., "analysis" matches "analysis.create")
            role: Filter by role
            success: Filter by success/failure
            since: Only entries after this Unix timestamp
            limit: Maximum entries to return

        Returns:
            List of audit entries (newest first)
        """
        results = []
        for entry in reversed(self._entries):
            if action and not entry.action.startswith(action):
                continue
            if role and entry.role != role:
                continue
            if success is not None and entry.success != success:
                continue
            if since and entry.timestamp < since:
                continue

            results.append(
                {
                    "id": entry.id,
                    "timestamp": entry.timestamp,
                    "action": entry.action,
                    "role": entry.role,
                    "details": entry.details,
                    "request_id": entry.request_id,
                    "ip_address": entry.ip_address,
                    "success": entry.success,
                    "error": entry.error,
                }
            )
            if len(results) >= limit:
                break

        return results

    def stats(self) -> Dict[str, Any]:
        """Get audit trail statistics."""
        total = len(self._entries)
        if total == 0:
            return {"total": 0, "by_action": {}, "by_role": {}, "failures": 0}

        by_action: Dict[str, int] = {}
        by_role: Dict[str, int] = {}
        failures = 0

        for entry in self._entries:
            action_prefix = entry.action.split(".")[0]
            by_action[action_prefix] = by_action.get(action_prefix, 0) + 1
            by_role[entry.role] = by_role.get(entry.role, 0) + 1
            if not entry.success:
                failures += 1

        return {
            "total": total,
            "by_action": by_action,
            "by_role": by_role,
            "failures": failures,
        }

    @property
    def size(self) -> int:
        """Current number of audit entries."""
        return len(self._entries)


# Global singleton
audit_log = AuditTrail()
