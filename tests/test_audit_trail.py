"""
Tests for audit trail system — Phase 6.7.

Covers: recording, querying with filters, statistics, bounded deque,
immutability of entries.
"""

import time

import pytest

from app.shared.audit_trail import AuditEntry, AuditTrail

# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


class TestAuditRecording:
    """Test audit entry recording."""

    def test_record_creates_entry(self):
        trail = AuditTrail()
        entry = trail.record(action="analysis.create", role="admin")

        assert isinstance(entry, AuditEntry)
        assert entry.action == "analysis.create"
        assert entry.role == "admin"
        assert entry.success is True
        assert entry.error is None

    def test_record_with_all_fields(self):
        trail = AuditTrail()
        entry = trail.record(
            action="report.delete",
            role="analyst",
            details={"report_id": "r-123"},
            request_id="req-456",
            ip_address="192.168.1.1",
            success=False,
            error="Permission denied",
        )

        assert entry.action == "report.delete"
        assert entry.role == "analyst"
        assert entry.details == {"report_id": "r-123"}
        assert entry.request_id == "req-456"
        assert entry.ip_address == "192.168.1.1"
        assert entry.success is False
        assert entry.error == "Permission denied"

    def test_record_assigns_unique_ids(self):
        trail = AuditTrail()
        e1 = trail.record(action="a1", role="admin")
        e2 = trail.record(action="a2", role="admin")
        assert e1.id != e2.id

    def test_record_assigns_timestamps(self):
        trail = AuditTrail()
        before = time.time()
        entry = trail.record(action="test", role="guest")
        after = time.time()

        assert before <= entry.timestamp <= after

    def test_record_defaults_empty_details(self):
        trail = AuditTrail()
        entry = trail.record(action="test", role="guest")
        assert entry.details == {}


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestAuditImmutability:
    """Verify AuditEntry is frozen (immutable)."""

    def test_entry_is_frozen(self):
        trail = AuditTrail()
        entry = trail.record(action="test", role="guest")

        with pytest.raises(AttributeError):
            entry.action = "modified"

    def test_entry_is_frozen_success(self):
        trail = AuditTrail()
        entry = trail.record(action="test", role="guest")

        with pytest.raises(AttributeError):
            entry.success = False


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------


class TestAuditQuerying:
    """Test query filters."""

    def _populated_trail(self) -> AuditTrail:
        trail = AuditTrail()
        trail.record(action="analysis.create", role="admin")
        trail.record(action="analysis.batch", role="analyst")
        trail.record(action="report.delete", role="admin", success=False, error="Not found")
        trail.record(action="webhook.register", role="admin")
        trail.record(action="analysis.read", role="viewer")
        return trail

    def test_query_all(self):
        trail = self._populated_trail()
        results = trail.query()
        assert len(results) == 5

    def test_query_by_action_prefix(self):
        trail = self._populated_trail()
        results = trail.query(action="analysis")
        assert len(results) == 3
        assert all(r["action"].startswith("analysis") for r in results)

    def test_query_by_role(self):
        trail = self._populated_trail()
        results = trail.query(role="admin")
        assert len(results) == 3

    def test_query_by_success(self):
        trail = self._populated_trail()
        failures = trail.query(success=False)
        assert len(failures) == 1
        assert failures[0]["error"] == "Not found"

    def test_query_by_since(self):
        trail = AuditTrail()
        trail.record(action="old", role="guest")
        cutoff = time.time()
        time.sleep(0.01)
        trail.record(action="new", role="guest")

        results = trail.query(since=cutoff)
        assert len(results) == 1
        assert results[0]["action"] == "new"

    def test_query_limit(self):
        trail = self._populated_trail()
        results = trail.query(limit=2)
        assert len(results) == 2

    def test_query_newest_first(self):
        trail = AuditTrail()
        trail.record(action="first", role="guest")
        time.sleep(0.01)
        trail.record(action="second", role="guest")

        results = trail.query()
        assert results[0]["action"] == "second"
        assert results[1]["action"] == "first"

    def test_query_combined_filters(self):
        trail = self._populated_trail()
        results = trail.query(action="analysis", role="admin")
        assert len(results) == 1
        assert results[0]["action"] == "analysis.create"


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestAuditStats:
    """Test statistics aggregation."""

    def test_stats_empty(self):
        trail = AuditTrail()
        stats = trail.stats()
        assert stats["total"] == 0
        assert stats["by_action"] == {}
        assert stats["by_role"] == {}
        assert stats["failures"] == 0

    def test_stats_counts(self):
        trail = AuditTrail()
        trail.record(action="analysis.create", role="admin")
        trail.record(action="analysis.batch", role="analyst")
        trail.record(action="report.delete", role="admin", success=False)

        stats = trail.stats()
        assert stats["total"] == 3
        assert stats["by_action"]["analysis"] == 2
        assert stats["by_action"]["report"] == 1
        assert stats["by_role"]["admin"] == 2
        assert stats["by_role"]["analyst"] == 1
        assert stats["failures"] == 1


# ---------------------------------------------------------------------------
# Bounded deque
# ---------------------------------------------------------------------------


class TestAuditBounded:
    """Test bounded deque eviction."""

    def test_max_entries_enforced(self):
        trail = AuditTrail(max_entries=5)
        for i in range(10):
            trail.record(action=f"action.{i}", role="guest")

        assert trail.size == 5
        # Oldest entries should be evicted
        results = trail.query()
        actions = {r["action"] for r in results}
        assert "action.0" not in actions
        assert "action.9" in actions

    def test_size_property(self):
        trail = AuditTrail()
        assert trail.size == 0
        trail.record(action="test", role="guest")
        assert trail.size == 1
