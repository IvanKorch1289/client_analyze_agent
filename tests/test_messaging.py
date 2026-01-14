"""
Интеграционные тесты для RabbitMQ messaging.

Тестирует:
- RabbitPublisher: publish, connect, lazy connection
- Broker handlers: handle_client_analysis, handle_cache_invalidate
- DLQ: конфигурация очередей с dead letter routing
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.messaging.models import (
    ClientAnalysisRequest,
    ClientAnalysisResult,
    CacheInvalidateRequest,
)
from app.messaging.publisher import RabbitPublisher, get_rabbit_publisher


class TestRabbitPublisher:
    """Тесты для RabbitPublisher."""
    
    @pytest.mark.asyncio
    async def test_publisher_lazy_connection(self):
        """Publisher не подключается до первого publish."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker
            
            publisher = RabbitPublisher()
            
            assert publisher._connected is False
            mock_broker.connect.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_publisher_connects_on_first_publish(self):
        """Publisher подключается при первом publish."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker
            
            publisher = RabbitPublisher()
            
            await publisher.publish_client_analysis(
                client_name="ПАО Сбербанк",
                inn="7707083893",
            )
            
            mock_broker.connect.assert_called_once()
            mock_broker.publish.assert_called_once()
            assert publisher._connected is True
    
    @pytest.mark.asyncio
    async def test_publisher_reuses_connection(self):
        """Publisher переиспользует существующее соединение."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker
            
            publisher = RabbitPublisher()
            
            await publisher.publish_client_analysis(client_name="Test1", inn="1111111111")
            await publisher.publish_client_analysis(client_name="Test2", inn="2222222222")
            
            mock_broker.connect.assert_called_once()
            assert mock_broker.publish.call_count == 2
    
    @pytest.mark.asyncio
    async def test_publish_client_analysis_message_format(self):
        """Проверка формата сообщения для client analysis."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker
            
            publisher = RabbitPublisher()
            
            await publisher.publish_client_analysis(
                client_name="ООО Ромашка",
                inn="1234567890",
                additional_notes="Тестовые заметки",
                session_id="test-session-123",
                save_report=True,
            )
            
            call_args = mock_broker.publish.call_args
            message = call_args[0][0]
            
            assert isinstance(message, ClientAnalysisRequest)
            assert message.client_name == "ООО Ромашка"
            assert message.inn == "1234567890"
            assert message.additional_notes == "Тестовые заметки"
            assert message.session_id == "test-session-123"
            assert message.save_report is True
    
    @pytest.mark.asyncio
    async def test_publish_cache_invalidate(self):
        """Тест публикации сообщения инвалидации кэша."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker
            
            publisher = RabbitPublisher()
            
            await publisher.publish_cache_invalidate(prefix="dadata:", invalidate_all=False)
            
            call_args = mock_broker.publish.call_args
            message = call_args[0][0]
            
            assert isinstance(message, CacheInvalidateRequest)
            assert message.prefix == "dadata:"
            assert message.invalidate_all is False
    
    @pytest.mark.asyncio
    async def test_publish_cache_invalidate_all(self):
        """Тест полной инвалидации кэша."""
        with patch("app.messaging.publisher.RabbitBroker") as MockBroker:
            mock_broker = MagicMock()
            mock_broker.connect = AsyncMock()
            mock_broker.publish = AsyncMock()
            MockBroker.return_value = mock_broker
            
            publisher = RabbitPublisher()
            
            await publisher.publish_cache_invalidate(invalidate_all=True)
            
            call_args = mock_broker.publish.call_args
            message = call_args[0][0]
            
            assert message.invalidate_all is True


class TestPublisherSingleton:
    """Тесты для singleton get_rabbit_publisher."""
    
    def test_get_rabbit_publisher_returns_instance(self):
        """get_rabbit_publisher возвращает RabbitPublisher."""
        with patch("app.messaging.publisher.RabbitBroker"):
            import app.messaging.publisher as pub_module
            pub_module._publisher = None
            
            publisher = get_rabbit_publisher()
            assert isinstance(publisher, RabbitPublisher)
    
    def test_get_rabbit_publisher_returns_same_instance(self):
        """get_rabbit_publisher возвращает тот же экземпляр."""
        with patch("app.messaging.publisher.RabbitBroker"):
            import app.messaging.publisher as pub_module
            pub_module._publisher = None
            
            publisher1 = get_rabbit_publisher()
            publisher2 = get_rabbit_publisher()
            
            assert publisher1 is publisher2


class TestBrokerHandlers:
    """Тесты для обработчиков broker."""
    
    @pytest.mark.asyncio
    async def test_handle_client_analysis(self):
        """Тест обработчика анализа клиента."""
        from app.messaging.broker import handle_client_analysis
        
        msg = ClientAnalysisRequest(
            client_name="ПАО Сбербанк",
            inn="7707083893",
            additional_notes="Тест",
            save_report=False,
        )
        
        mock_result = {
            "status": "completed",
            "session_id": "test-session",
            "summary": "Риск низкий",
        }
        
        with patch("app.messaging.broker.execute_client_analysis", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            
            result = await handle_client_analysis(msg)
            
            assert isinstance(result, ClientAnalysisResult)
            assert result.status == "completed"
            assert result.session_id == "test-session"
            assert result.summary == "Риск низкий"
            
            mock_execute.assert_called_once_with(
                client_name="ПАО Сбербанк",
                inn="7707083893",
                additional_notes="Тест",
                save_report=False,
                session_id=None,
            )
    
    @pytest.mark.asyncio
    async def test_handle_cache_invalidate(self):
        """Тест обработчика инвалидации кэша."""
        from app.messaging.broker import handle_cache_invalidate
        
        msg = CacheInvalidateRequest(prefix="test:", invalidate_all=False)
        
        mock_result = {"status": "ok", "deleted": 5}
        
        with patch("app.messaging.broker.dispatch_cache_invalidate", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = mock_result
            
            result = await handle_cache_invalidate(msg)
            
            assert result["status"] == "ok"
            
            mock_dispatch.assert_called_once_with(
                prefix="test:",
                invalidate_all=False,
                prefer_queue=False,
            )
    
    @pytest.mark.asyncio
    async def test_handle_cache_invalidate_all(self):
        """Тест полной инвалидации через обработчик."""
        from app.messaging.broker import handle_cache_invalidate
        
        msg = CacheInvalidateRequest(invalidate_all=True)
        
        with patch("app.messaging.broker.dispatch_cache_invalidate", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = {"status": "ok", "deleted": 100}
            
            await handle_cache_invalidate(msg)
            
            mock_dispatch.assert_called_once_with(
                prefix=None,
                invalidate_all=True,
                prefer_queue=False,
            )


class TestDLQConfiguration:
    """Тесты конфигурации Dead Letter Queue."""
    
    def test_analysis_queue_has_dlq_config(self):
        """Очередь анализа настроена с DLQ."""
        from app.messaging.broker import _analysis_queue
        
        args = _analysis_queue.arguments or {}
        
        assert args.get("x-dead-letter-exchange") == "dlx"
        assert args.get("x-dead-letter-routing-key") == "dlq.analysis"
    
    def test_cache_queue_has_dlq_config(self):
        """Очередь кэша настроена с DLQ."""
        from app.messaging.broker import _cache_queue
        
        args = _cache_queue.arguments or {}
        
        assert args.get("x-dead-letter-exchange") == "dlx"
        assert args.get("x-dead-letter-routing-key") == "dlq.cache"
    
    def test_dlx_exchange_is_topic_type(self):
        """DLX exchange имеет тип TOPIC."""
        from app.messaging.broker import _dlx
        from faststream.rabbit import ExchangeType
        
        assert _dlx.type == ExchangeType.TOPIC
        assert _dlx.durable is True


class TestMessageModels:
    """Тесты для моделей сообщений."""
    
    def test_client_analysis_request_defaults(self):
        """Проверка дефолтных значений ClientAnalysisRequest."""
        msg = ClientAnalysisRequest(client_name="Test")
        
        assert msg.client_name == "Test"
        assert msg.inn == ""
        assert msg.additional_notes == ""
        assert msg.session_id is None
        assert msg.save_report is True
    
    def test_client_analysis_result_model(self):
        """Проверка ClientAnalysisResult."""
        result = ClientAnalysisResult(
            status="completed",
            session_id="sess-123",
            summary="Низкий риск",
            raw_result={"risk_score": 20},
        )
        
        assert result.status == "completed"
        assert result.session_id == "sess-123"
        assert result.summary == "Низкий риск"
        assert result.raw_result["risk_score"] == 20
    
    def test_cache_invalidate_request_defaults(self):
        """Проверка дефолтных значений CacheInvalidateRequest."""
        msg = CacheInvalidateRequest()
        
        assert msg.prefix is None
        assert msg.invalidate_all is False
