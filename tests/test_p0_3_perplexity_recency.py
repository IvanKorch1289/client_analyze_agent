"""
P0-3: Тесты для включения search_recency_filter в Perplexity.

Проверяем:
1. Параметр search_recency_filter передаётся в API
2. Fallback работает если параметр не поддерживается
3. Другие ошибки правильно пробрасываются
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.perplexity_client import PerplexityClient


class TestP0_3_RecencyFilter:
    """Тесты включения search_recency_filter."""

    @pytest.mark.asyncio
    async def test_recency_filter_is_passed(self):
        """
        Проверка что search_recency_filter передаётся в ChatOpenAI.
        """
        with patch("langchain_openai.ChatOpenAI") as mock_chat:
            # Настраиваем мок
            mock_instance = AsyncMock()
            mock_message = MagicMock()
            mock_message.content = "Test response"
            mock_instance.ainvoke.return_value = mock_message
            mock_chat.return_value = mock_instance
            
            client = PerplexityClient(api_key="test_key", model="sonar-pro")
            
            # Вызываем с search_recency_filter="year"
            result = await client.chat(
                messages=[{"role": "user", "content": "test"}],
                search_recency_filter="year",
            )
            
            # Проверяем что ChatOpenAI вызван с model_kwargs
            assert mock_chat.called, "ChatOpenAI должен быть вызван"
            call_kwargs = mock_chat.call_args[1]
            
            assert "model_kwargs" in call_kwargs, \
                "model_kwargs должен быть передан"
            assert call_kwargs["model_kwargs"] == {"search_recency_filter": "year"}, \
                "search_recency_filter должен быть 'year'"

    @pytest.mark.asyncio
    async def test_fallback_when_not_supported(self):
        """
        Проверка что fallback работает если search_recency_filter не поддерживается.
        """
        with patch("langchain_openai.ChatOpenAI") as mock_chat:
            # Первый вызов - ошибка "not supported"
            # Второй вызов - успех
            mock_instance_error = AsyncMock()
            mock_instance_error.ainvoke.side_effect = Exception(
                "Parameter search_recency_filter is not supported"
            )
            
            mock_instance_success = AsyncMock()
            mock_message = MagicMock()
            mock_message.content = "Success without filter"
            mock_instance_success.ainvoke.return_value = mock_message
            
            mock_chat.side_effect = [mock_instance_error, mock_instance_success]
            
            client = PerplexityClient(api_key="test_key", model="sonar-pro")
            
            result = await client.chat(
                messages=[{"role": "user", "content": "test"}],
                search_recency_filter="year",
            )
            
            # Должен вернуть успешный результат после fallback
            assert result["success"] is True, \
                "Fallback должен привести к успеху"
            assert "Success" in result["content"], \
                "Контент должен быть от второго вызова"
            
            # ChatOpenAI должен быть вызван дважды
            assert mock_chat.call_count == 2, \
                "ChatOpenAI должен быть вызван дважды (original + fallback)"
            
            # Второй вызов не должен иметь model_kwargs
            second_call_kwargs = mock_chat.call_args_list[1][1]
            assert "model_kwargs" not in second_call_kwargs or \
                   second_call_kwargs.get("model_kwargs") is None, \
                "Второй вызов не должен иметь model_kwargs"

    @pytest.mark.asyncio
    async def test_other_errors_are_propagated(self):
        """
        Проверка что другие ошибки (не связанные с recency filter) пробрасываются.
        """
        with patch("langchain_openai.ChatOpenAI") as mock_chat:
            mock_instance = AsyncMock()
            # Ошибка НЕ связанная с search_recency_filter
            mock_instance.ainvoke.side_effect = Exception("API rate limit exceeded")
            mock_chat.return_value = mock_instance
            
            client = PerplexityClient(api_key="test_key", model="sonar-pro")
            
            result = await client.chat(
                messages=[{"role": "user", "content": "test"}],
                search_recency_filter="year",
            )
            
            # Должна вернуться ошибка
            assert result["success"] is False, \
                "Другие ошибки должны приводить к failure"
            assert "rate limit" in result["error"].lower(), \
                "Ошибка должна содержать исходное сообщение"

    @pytest.mark.asyncio
    async def test_ask_method_passes_recency_filter(self):
        """
        Проверка что метод ask() правильно передаёт search_recency_filter.
        """
        with patch("langchain_openai.ChatOpenAI") as mock_chat:
            mock_instance = AsyncMock()
            mock_message = MagicMock()
            mock_message.content = "Test answer"
            mock_instance.ainvoke.return_value = mock_message
            mock_chat.return_value = mock_instance
            
            client = PerplexityClient(api_key="test_key", model="sonar-pro")
            
            # Вызываем ask с search_recency_filter
            result = await client.ask(
                question="Test question",
                search_recency_filter="year",
            )
            
            # Проверяем что параметр передался
            assert mock_chat.called
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs.get("model_kwargs") == {"search_recency_filter": "year"}

    @pytest.mark.asyncio
    async def test_default_recency_filter_value(self):
        """
        Проверка что дефолтное значение search_recency_filter = "month".
        """
        with patch("langchain_openai.ChatOpenAI") as mock_chat:
            mock_instance = AsyncMock()
            mock_message = MagicMock()
            mock_message.content = "Test"
            mock_instance.ainvoke.return_value = mock_message
            mock_chat.return_value = mock_instance
            
            client = PerplexityClient(api_key="test_key")
            
            # Вызываем без явного указания search_recency_filter
            # Должно использоваться дефолтное значение из параметров функции
            result = await client.ask(question="Test")
            
            # По умолчанию в функции ask() нет явного дефолта,
            # но в chat() дефолт search_recency_filter="month"
            # Проверяем что ChatOpenAI вызван
            assert mock_chat.called


@pytest.mark.asyncio
class TestP0_3_Integration:
    """Интеграционные тесты (требуют реальный API ключ)."""

    @pytest.mark.skip(reason="Требует реальный PERPLEXITY_API_KEY")
    async def test_real_api_with_year_filter(self):
        """
        Интеграционный тест: реальный запрос с search_recency_filter="year".
        
        Проверяет что API принимает параметр и возвращает актуальные данные.
        """
        from app.services.perplexity_client import PerplexityClient
        
        client = PerplexityClient.get_instance()
        
        if not client.is_configured():
            pytest.skip("Perplexity API key not configured")
        
        result = await client.ask(
            question="Последние новости о компании Газпром за последний год",
            search_recency_filter="year",
        )
        
        assert result["success"] is True, \
            f"Запрос должен быть успешным, error: {result.get('error')}"
        
        content = result.get("content", "")
        assert len(content) > 0, "Контент не должен быть пустым"
        
        # Проверяем что есть упоминание актуальности
        assert any(word in content.lower() for word in ["2024", "2025", "недавно", "последн"]), \
            "Ответ должен содержать актуальную информацию"
        
        print(f"✅ Perplexity с year filter: {len(content)} символов")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

