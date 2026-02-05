"""
Tests for webhook notification system — Phase 6.5.

Covers: registration, unregistration, dispatch, HMAC signing,
delivery tracking, event filtering.
"""

import pytest

from app.shared.webhooks import WebhookDelivery, WebhookEndpoint, WebhookManager

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestWebhookRegistration:
    """Webhook endpoint registration and management."""

    def test_register_creates_endpoint(self):
        mgr = WebhookManager()
        ep = mgr.register("https://example.com/hook", events=["analysis.completed"])

        assert isinstance(ep, WebhookEndpoint)
        assert ep.url == "https://example.com/hook"
        assert ep.events == ["analysis.completed"]
        assert ep.enabled is True

    def test_register_with_secret(self):
        mgr = WebhookManager()
        ep = mgr.register(
            "https://example.com/hook",
            events=["analysis.completed"],
            secret="my-hmac-secret",
            description="Test hook",
        )

        assert ep.secret == "my-hmac-secret"
        assert ep.description == "Test hook"

    def test_register_assigns_unique_ids(self):
        mgr = WebhookManager()
        ep1 = mgr.register("https://a.com", events=["e1"])
        ep2 = mgr.register("https://b.com", events=["e2"])
        assert ep1.id != ep2.id

    def test_list_endpoints(self):
        mgr = WebhookManager()
        mgr.register("https://a.com", events=["e1"])
        mgr.register("https://b.com", events=["e2"], secret="s")

        listing = mgr.list_endpoints()
        assert len(listing) == 2
        assert listing[0]["url"] == "https://a.com"
        assert listing[0]["has_secret"] is False
        assert listing[1]["has_secret"] is True

    def test_list_endpoints_hides_secret_value(self):
        mgr = WebhookManager()
        mgr.register("https://a.com", events=["e1"], secret="top-secret")

        listing = mgr.list_endpoints()
        assert "secret" not in listing[0]
        assert listing[0]["has_secret"] is True


# ---------------------------------------------------------------------------
# Unregistration
# ---------------------------------------------------------------------------


class TestWebhookUnregistration:
    """Webhook endpoint unregistration."""

    def test_unregister_existing(self):
        mgr = WebhookManager()
        ep = mgr.register("https://a.com", events=["e1"])
        assert mgr.unregister(ep.id) is True
        assert mgr.list_endpoints() == []

    def test_unregister_nonexistent(self):
        mgr = WebhookManager()
        assert mgr.unregister("nonexistent-id") is False


# ---------------------------------------------------------------------------
# HMAC Signing
# ---------------------------------------------------------------------------


class TestHMACSigning:
    """Test payload signature generation."""

    def test_sign_payload_deterministic(self):
        payload = b'{"event": "test"}'
        sig1 = WebhookManager._sign_payload(payload, "secret")
        sig2 = WebhookManager._sign_payload(payload, "secret")
        assert sig1 == sig2

    def test_sign_payload_different_secrets(self):
        payload = b'{"event": "test"}'
        sig1 = WebhookManager._sign_payload(payload, "secret1")
        sig2 = WebhookManager._sign_payload(payload, "secret2")
        assert sig1 != sig2

    def test_sign_payload_hex_format(self):
        sig = WebhookManager._sign_payload(b"test", "secret")
        assert len(sig) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in sig)


# ---------------------------------------------------------------------------
# Dispatch & Delivery
# ---------------------------------------------------------------------------


class TestWebhookDispatch:
    """Test event dispatch and delivery tracking."""

    @pytest.mark.asyncio
    async def test_dispatch_no_matching_webhooks(self):
        mgr = WebhookManager()
        mgr.register("https://a.com", events=["other.event"])

        count = await mgr.dispatch("analysis.completed", {"data": "test"})
        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_matches_correct_events(self):
        mgr = WebhookManager()
        mgr.register("https://a.com", events=["analysis.completed"])
        mgr.register("https://b.com", events=["batch.completed"])

        # Dispatch will try HTTP delivery (will fail since no server),
        # but we can test that matching works by checking delivery records
        await mgr.dispatch("analysis.completed", {"data": "test"})

        deliveries = mgr.get_deliveries()
        assert len(deliveries) == 1
        assert deliveries[0]["event"] == "analysis.completed"

    @pytest.mark.asyncio
    async def test_dispatch_disabled_endpoint_ignored(self):
        mgr = WebhookManager()
        ep = mgr.register("https://a.com", events=["e1"])
        ep.enabled = False

        count = await mgr.dispatch("e1", {"data": "test"})
        assert count == 0

    @pytest.mark.asyncio
    async def test_delivery_records_stored(self):
        mgr = WebhookManager()
        mgr.register("https://a.com", events=["e1"])

        await mgr.dispatch("e1", {"key": "value"})

        deliveries = mgr.get_deliveries()
        assert len(deliveries) == 1
        assert deliveries[0]["event"] == "e1"
        assert deliveries[0]["status"] in ("success", "failed")
        assert deliveries[0]["attempt"] >= 1

    @pytest.mark.asyncio
    async def test_get_deliveries_filter_by_webhook_id(self):
        mgr = WebhookManager()
        ep1 = mgr.register("https://a.com", events=["e1"])
        mgr.register("https://b.com", events=["e1"])

        await mgr.dispatch("e1", {"data": "test"})

        all_deliveries = mgr.get_deliveries()
        assert len(all_deliveries) == 2

        filtered = mgr.get_deliveries(webhook_id=ep1.id)
        assert len(filtered) == 1
        assert filtered[0]["webhook_id"] == ep1.id

    @pytest.mark.asyncio
    async def test_get_deliveries_respects_limit(self):
        mgr = WebhookManager()
        mgr.register("https://a.com", events=["e1"])

        for _ in range(5):
            await mgr.dispatch("e1", {"data": "test"})

        limited = mgr.get_deliveries(limit=3)
        assert len(limited) == 3


# ---------------------------------------------------------------------------
# WebhookDelivery dataclass
# ---------------------------------------------------------------------------


class TestWebhookDeliveryModel:
    """Test WebhookDelivery data structure."""

    def test_delivery_default_values(self):
        d = WebhookDelivery(
            id="d1",
            webhook_id="w1",
            event="test",
            payload={"key": "val"},
            status="pending",
        )
        assert d.attempt == 0
        assert d.status_code is None
        assert d.error is None
        assert d.delivered_at is None
        assert d.created_at > 0
