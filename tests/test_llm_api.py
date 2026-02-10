"""
Tests for async LLM API endpoint and related functionality.

Tests:
- LLM schema validation (AsyncLLMRequest, AsyncLLMAccepted, LLMCallbackPayload)
- API endpoints (/llm/async, /llm/providers)
- Publisher: publish_async_llm_request
- Broker handler: handle_async_llm_request
- DLQ configuration for LLM queue
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from pydantic import ValidationError

from app.schemas.llm import (
    AsyncLLMRequest,
    AsyncLLMAccepted,
    LLMCallbackPayload,
    LLMProviderEnum,
    LLMProvidersResponse,
)
from app.messaging.models import AsyncLLMQueueMessage
from app.messaging.publisher import RabbitPublisher


class TestLLMSchemas:
    """Tests for LLM Pydantic schemas."""

    def test_async_llm_request_valid(self):
        """Valid AsyncLLMRequest with all fields."""
        request = AsyncLLMRequest(
            prompt="Hello, how are you?",
            system_prompt="You are a helpful assistant.",
            provider=LLMProviderEnum.OPENROUTER,
            callback_url="https://example.com/callback",
            callback_headers={"Authorization": "Bearer token"},
            temperature=0.7,
            max_tokens=4096,
            request_metadata={"user_id": "123"},
        )

        assert request.prompt == "Hello, how are you?"
        assert request.system_prompt == "You are a helpful assistant."
        assert request.provider == LLMProviderEnum.OPENROUTER
        assert str(request.callback_url) == "https://example.com/callback"
        assert request.callback_headers == {"Authorization": "Bearer token"}
        assert request.temperature == 0.7
        assert request.max_tokens == 4096
        assert request.request_metadata == {"user_id": "123"}

    def test_async_llm_request_minimal(self):
        """Minimal AsyncLLMRequest with only required fields."""
        request = AsyncLLMRequest(
            prompt="Test prompt",
            callback_url="https://example.com/webhook",
        )

        assert request.prompt == "Test prompt"
        assert request.system_prompt is None
        assert request.provider == LLMProviderEnum.OPENROUTER  # default
        assert request.temperature == 0.7  # default
        assert request.max_tokens == 4096  # default
        assert request.callback_headers is None
        assert request.request_metadata is None

    def test_async_llm_request_empty_prompt_fails(self):
        """Empty prompt should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            AsyncLLMRequest(
                prompt="",
                callback_url="https://example.com/callback",
            )
        assert "string_too_short" in str(exc_info.value).lower()

    def test_async_llm_request_invalid_url_fails(self):
        """Invalid callback URL should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            AsyncLLMRequest(
                prompt="Test",
                callback_url="not-a-valid-url",
            )
        assert "url" in str(exc_info.value).lower()

    def test_async_llm_request_temperature_bounds(self):
        """Temperature must be between 0.0 and 2.0."""
        # Valid boundary values
        request_min = AsyncLLMRequest(
            prompt="Test",
            callback_url="https://example.com/cb",
            temperature=0.0,
        )
        assert request_min.temperature == 0.0

        request_max = AsyncLLMRequest(
            prompt="Test",
            callback_url="https://example.com/cb",
            temperature=2.0,
        )
        assert request_max.temperature == 2.0

        # Invalid: below minimum
        with pytest.raises(ValidationError):
            AsyncLLMRequest(
                prompt="Test",
                callback_url="https://example.com/cb",
                temperature=-0.1,
            )

        # Invalid: above maximum
        with pytest.raises(ValidationError):
            AsyncLLMRequest(
                prompt="Test",
                callback_url="https://example.com/cb",
                temperature=2.1,
            )

    def test_async_llm_request_max_tokens_bounds(self):
        """Max tokens must be between 1 and 32000."""
        # Valid boundary values
        request_min = AsyncLLMRequest(
            prompt="Test",
            callback_url="https://example.com/cb",
            max_tokens=1,
        )
        assert request_min.max_tokens == 1

        request_max = AsyncLLMRequest(
            prompt="Test",
            callback_url="https://example.com/cb",
            max_tokens=32000,
        )
        assert request_max.max_tokens == 32000

        # Invalid: below minimum
        with pytest.raises(ValidationError):
            AsyncLLMRequest(
                prompt="Test",
                callback_url="https://example.com/cb",
                max_tokens=0,
            )

    def test_async_llm_request_all_providers(self):
        """Test all provider enum values."""
        for provider in LLMProviderEnum:
            request = AsyncLLMRequest(
                prompt="Test",
                callback_url="https://example.com/cb",
                provider=provider,
            )
            assert request.provider == provider

    def test_async_llm_accepted_model(self):
        """Test AsyncLLMAccepted response model."""
        response = AsyncLLMAccepted(
            request_id="llm_abc123_1234567890",
            estimated_time_seconds=30,
        )

        assert response.status == "accepted"
        assert response.request_id == "llm_abc123_1234567890"
        assert response.message == "Запрос поставлен в очередь на обработку"
        assert response.estimated_time_seconds == 30

    def test_llm_callback_payload_success(self):
        """Test LLMCallbackPayload for successful response."""
        payload = LLMCallbackPayload(
            request_id="llm_123",
            status="success",
            provider_used="openrouter",
            response="This is the LLM response.",
            processing_time_ms=1500.5,
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            request_metadata={"source": "test"},
        )

        assert payload.request_id == "llm_123"
        assert payload.status == "success"
        assert payload.provider_used == "openrouter"
        assert payload.response == "This is the LLM response."
        assert payload.error is None
        assert payload.processing_time_ms == 1500.5
        assert payload.usage == {"prompt_tokens": 100, "completion_tokens": 50}

    def test_llm_callback_payload_error(self):
        """Test LLMCallbackPayload for error response."""
        payload = LLMCallbackPayload(
            request_id="llm_456",
            status="error",
            provider_used="huggingface",
            error="Provider unavailable",
            processing_time_ms=500.0,
        )

        assert payload.status == "error"
        assert payload.error == "Provider unavailable"
        assert payload.response is None

    def test_llm_providers_response(self):
        """Test LLMProvidersResponse model."""
        response = LLMProvidersResponse(
            providers=["openrouter", "huggingface", "gigachat"],
            status={"openrouter": True, "huggingface": False, "gigachat": True},
        )

        assert len(response.providers) == 3
        assert response.status["openrouter"] is True
        assert response.status["huggingface"] is False


class TestAsyncLLMQueueMessage:
    """Tests for AsyncLLMQueueMessage model."""

    def test_async_llm_queue_message_valid(self):
        """Valid AsyncLLMQueueMessage with all fields."""
        msg = AsyncLLMQueueMessage(
            request_id="llm_test_123",
            prompt="Hello world",
            system_prompt="Be helpful",
            provider="openrouter",
            callback_url="https://example.com/cb",
            callback_headers={"Auth": "Bearer xyz"},
            temperature=0.5,
            max_tokens=2000,
            request_metadata={"key": "value"},
            created_at=time.time(),
        )

        assert msg.request_id == "llm_test_123"
        assert msg.prompt == "Hello world"
        assert msg.system_prompt == "Be helpful"
        assert msg.provider == "openrouter"
        assert msg.callback_url == "https://example.com/cb"
        assert msg.temperature == 0.5
        assert msg.max_tokens == 2000

    def test_async_llm_queue_message_defaults(self):
        """Test default values for AsyncLLMQueueMessage."""
        msg = AsyncLLMQueueMessage(
            request_id="test",
            prompt="Test prompt",
            provider="gigachat",
            callback_url="https://example.com/hook",
            created_at=1234567890.0,
        )

        assert msg.system_prompt is None
        assert msg.callback_headers is None
        assert msg.temperature == 0.7
        assert msg.max_tokens == 4096
        assert msg.request_metadata is None


class TestRabbitPublisherLLM:
    """Tests for RabbitPublisher async LLM methods."""

    @pytest.mark.asyncio
    async def test_publish_async_llm_request(self):
        """Test publishing async LLM request to queue."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker

            publisher = RabbitPublisher()

            await publisher.publish_async_llm_request(
                request_id="llm_test_abc",
                prompt="Analyze this company",
                system_prompt="You are an analyst",
                provider="openrouter",
                callback_url="https://my-service.com/webhook",
                callback_headers={"Authorization": "Bearer secret"},
                temperature=0.8,
                max_tokens=8000,
                request_metadata={"user": "test_user"},
            )

            mock_broker.connect.assert_called_once()
            mock_broker.publish.assert_called_once()

            call_args = mock_broker.publish.call_args
            message = call_args[0][0]

            assert isinstance(message, AsyncLLMQueueMessage)
            assert message.request_id == "llm_test_abc"
            assert message.prompt == "Analyze this company"
            assert message.system_prompt == "You are an analyst"
            assert message.provider == "openrouter"
            assert message.callback_url == "https://my-service.com/webhook"
            assert message.callback_headers == {"Authorization": "Bearer secret"}
            assert message.temperature == 0.8
            assert message.max_tokens == 8000
            assert message.request_metadata == {"user": "test_user"}
            assert message.created_at > 0

    @pytest.mark.asyncio
    async def test_publish_async_llm_request_minimal(self):
        """Test publishing async LLM request with minimal params."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker

            publisher = RabbitPublisher()

            await publisher.publish_async_llm_request(
                request_id="llm_min",
                prompt="Simple question",
                provider="huggingface",
                callback_url="https://callback.test",
            )

            call_args = mock_broker.publish.call_args
            message = call_args[0][0]

            assert message.system_prompt is None
            assert message.callback_headers is None
            assert message.temperature == 0.7
            assert message.max_tokens == 4096
            assert message.request_metadata is None


class TestBrokerHandlerLLM:
    """Tests for LLM broker handler."""

    @pytest.mark.asyncio
    async def test_handle_async_llm_request_success(self):
        """Test successful LLM request handling."""
        from app.messaging.broker import handle_async_llm_request

        msg = AsyncLLMQueueMessage(
            request_id="llm_success_test",
            prompt="What is 2+2?",
            system_prompt="Answer briefly",
            provider="openrouter",
            callback_url="https://callback.example.com/llm",
            temperature=0.5,
            max_tokens=100,
            created_at=time.time(),
        )

        mock_manager = MagicMock()
        mock_manager.ainvoke_with_provider = AsyncMock(return_value="The answer is 4.")

        with patch("app.agents.llm_manager.get_llm_manager", return_value=mock_manager):
            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(return_value=MagicMock(status_code=200))
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await handle_async_llm_request(msg)

        assert result["status"] == "success"
        assert result["request_id"] == "llm_success_test"
        assert result["provider_used"] == "openrouter"
        assert result["response"] == "The answer is 4."
        assert "processing_time_ms" in result

    @pytest.mark.asyncio
    async def test_handle_async_llm_request_error(self):
        """Test LLM request handling when LLM fails."""
        from app.messaging.broker import handle_async_llm_request

        msg = AsyncLLMQueueMessage(
            request_id="llm_error_test",
            prompt="This will fail",
            provider="gigachat",
            callback_url="https://callback.example.com/error",
            created_at=time.time(),
        )

        mock_manager = MagicMock()
        mock_manager.ainvoke_with_provider = AsyncMock(side_effect=Exception("Provider unavailable"))

        with patch("app.agents.llm_manager.get_llm_manager", return_value=mock_manager):
            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(return_value=MagicMock(status_code=200))
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await handle_async_llm_request(msg)

        assert result["status"] == "error"
        assert result["request_id"] == "llm_error_test"
        assert "Provider unavailable" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_async_llm_request_with_metadata(self):
        """Test that request metadata is passed through."""
        from app.messaging.broker import handle_async_llm_request

        msg = AsyncLLMQueueMessage(
            request_id="llm_meta_test",
            prompt="Test with metadata",
            provider="yandexgpt",
            callback_url="https://callback.example.com/meta",
            request_metadata={"correlation_id": "xyz789", "source": "api"},
            created_at=time.time(),
        )

        mock_manager = MagicMock()
        mock_manager.ainvoke_with_provider = AsyncMock(return_value="Response")

        with patch("app.agents.llm_manager.get_llm_manager", return_value=mock_manager):
            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(return_value=MagicMock(status_code=200))
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await handle_async_llm_request(msg)

        assert result["request_metadata"] == {
            "correlation_id": "xyz789",
            "source": "api",
        }


class TestLLMQueueConfiguration:
    """Tests for LLM queue DLQ configuration."""

    def test_llm_queue_has_dlq_config(self):
        """LLM queue is configured with DLQ."""
        from app.messaging.broker import _llm_queue

        args = _llm_queue.arguments or {}

        assert args.get("x-dead-letter-exchange") == "dlx"
        assert args.get("x-dead-letter-routing-key") == "dlq.llm"
        assert args.get("x-message-ttl") == 300000  # 5 min TTL

    def test_llm_queue_is_durable(self):
        """LLM queue is durable."""
        from app.messaging.broker import _llm_queue

        assert _llm_queue.durable is True


class TestLLMAPIEndpoint:
    """Tests for LLM API endpoints."""

    @pytest.mark.asyncio
    async def test_submit_async_llm_request_returns_202(self):
        """POST /llm/async returns 202 Accepted."""
        from fastapi.testclient import TestClient
        from app.api.v1 import v1_app

        client = TestClient(v1_app)

        with patch("app.api.routes.llm._is_provider_available", return_value=True):
            with patch("app.api.routes.llm.settings") as mock_settings:
                mock_settings.queue.enabled = False

                with patch(
                    "app.api.routes.llm._process_llm_request_background",
                    new_callable=AsyncMock,
                ):
                    response = client.post(
                        "/llm/async",
                        json={
                            "prompt": "Test prompt",
                            "callback_url": "https://example.com/callback",
                            "provider": "openrouter",
                        },
                    )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert "request_id" in data
        assert data["request_id"].startswith("llm_")

    @pytest.mark.asyncio
    async def test_submit_async_llm_request_invalid_provider(self):
        """POST /llm/async returns 400 for unconfigured provider."""
        from fastapi.testclient import TestClient
        from app.api.v1 import v1_app

        client = TestClient(v1_app)

        with patch("app.api.routes.llm._is_provider_available", return_value=False):
            response = client.post(
                "/llm/async",
                json={
                    "prompt": "Test prompt",
                    "callback_url": "https://example.com/callback",
                    "provider": "gigachat",
                },
            )

        assert response.status_code == 400
        # Check error response - could be "detail" or in response body
        resp_data = response.json()
        error_text = str(resp_data).lower()
        assert "not configured" in error_text or "error" in error_text

    def test_list_llm_providers(self):
        """GET /llm/providers returns provider list."""
        from fastapi.testclient import TestClient
        from app.api.v1 import v1_app

        client = TestClient(v1_app)

        mock_manager = MagicMock()
        mock_manager.get_provider_status.return_value = {
            "openrouter": True,
            "huggingface": False,
            "gigachat": True,
            "yandexgpt": False,
        }

        with patch("app.agents.llm_manager.get_llm_manager", return_value=mock_manager):
            response = client.get("/llm/providers")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "status" in data
        assert "openrouter" in data["providers"]
        assert "openllama" in data["providers"]  # Internal provider always listed


class TestLLMProviderEnum:
    """Tests for LLMProviderEnum."""

    def test_provider_enum_values(self):
        """Test all provider enum values."""
        assert LLMProviderEnum.OPENROUTER.value == "openrouter"
        assert LLMProviderEnum.HUGGINGFACE.value == "huggingface"
        assert LLMProviderEnum.GIGACHAT.value == "gigachat"
        assert LLMProviderEnum.YANDEXGPT.value == "yandexgpt"
        assert LLMProviderEnum.OPENLLAMA.value == "openllama"

    def test_provider_enum_count(self):
        """There should be 5 providers."""
        assert len(LLMProviderEnum) == 5
