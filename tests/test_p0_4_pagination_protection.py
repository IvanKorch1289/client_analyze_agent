"""P0-4: Тесты защиты от бесконечной пагинации."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.http_client import AsyncHttpClient

@pytest.mark.asyncio
async def test_max_pages_limit_enforced():
    """Тест что MAX_PAGES_LIMIT останавливает пагинацию."""
    with patch("app.config.constants.MAX_PAGES_LIMIT", 5):
        client = await AsyncHttpClient.get_instance()
        
        # Мок бесконечной пагинации
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"item": 1}],
            "total_pages": 1000  # Много страниц
        }
        
        with patch.object(client, 'request', return_value=mock_response):
            result = await client.fetch_all_pages(
                url="http://test.com/api",
                params={"page": 1}
            )
            
            # Должно остановиться на 5 страницах
            assert len(result) == 5, "Должно остановиться на MAX_PAGES_LIMIT"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

