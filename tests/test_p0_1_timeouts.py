"""
P0-1: Тесты для увеличенных таймаутов Casebook/InfoSphere.

Проверяем:
1. Константы обновлены правильно
2. HTTP клиент использует новые таймауты
3. Circuit breaker не открывается преждевременно
"""

import pytest
from app.config.constants import TimeoutConfig as AppTimeoutConfig
from app.services.http_client import AsyncHttpClient


class TestP0_1_TimeoutConstants:
    """Тесты констант таймаутов."""

    def test_infosphere_read_timeout_increased(self):
        """Проверка что таймаут InfoSphere увеличен до 360s."""
        assert AppTimeoutConfig.INFOSPHERE_READ == 360.0, \
            "InfoSphere READ timeout должен быть 360s (6 минут)"

    def test_casebook_read_timeout_increased(self):
        """Проверка что таймаут Casebook увеличен до 360s."""
        assert AppTimeoutConfig.CASEBOOK_READ == 360.0, \
            "Casebook READ timeout должен быть 360s (6 минут)"

    def test_dadata_timeout_unchanged(self):
        """Проверка что таймаут DaData не изменился (не требует длительной обработки)."""
        assert AppTimeoutConfig.DADATA_READ == 30.0, \
            "DaData READ timeout должен остаться 30s"

    def test_connect_timeouts_reasonable(self):
        """Проверка что connect таймауты остались быстрыми."""
        assert AppTimeoutConfig.INFOSPHERE_CONNECT == 5.0
        assert AppTimeoutConfig.CASEBOOK_CONNECT == 5.0
        # Connect должен быть быстрым, долго только read


@pytest.mark.asyncio
class TestP0_1_HttpClientConfig:
    """Тесты конфигурации HTTP клиента."""

    async def test_http_client_uses_new_timeouts(self):
        """Проверка что HTTP клиент использует обновлённые таймауты."""
        client = await AsyncHttpClient.get_instance()
        
        # Проверяем конфигурацию для InfoSphere
        infosphere_config = client._service_configs.get("infosphere")
        assert infosphere_config is not None, "InfoSphere конфигурация должна существовать"
        
        infosphere_timeout = infosphere_config["timeout"]
        assert infosphere_timeout.read == 360.0, \
            "InfoSphere должен использовать read timeout 360s"

        # Проверяем конфигурацию для Casebook
        casebook_config = client._service_configs.get("casebook")
        assert casebook_config is not None, "Casebook конфигурация должна существовать"
        
        casebook_timeout = casebook_config["timeout"]
        assert casebook_timeout.read == 360.0, \
            "Casebook должен использовать read timeout 360s"

    async def test_circuit_breaker_timeout_increased(self):
        """Проверка что circuit breaker timeout также увеличен."""
        client = await AsyncHttpClient.get_instance()
        
        # Для InfoSphere
        infosphere_cb = client._service_configs["infosphere"]["circuit_breaker"]
        assert infosphere_cb.timeout == 400.0, \
            "InfoSphere circuit breaker timeout должен быть 400s (больше read timeout)"
        
        # Для Casebook
        casebook_cb = client._service_configs["casebook"]["circuit_breaker"]
        assert casebook_cb.timeout == 400.0, \
            "Casebook circuit breaker timeout должен быть 400s (больше read timeout)"

    async def test_dadata_config_unchanged(self):
        """Проверка что конфигурация DaData не изменилась."""
        client = await AsyncHttpClient.get_instance()
        
        dadata_config = client._service_configs.get("dadata")
        assert dadata_config is not None
        
        dadata_timeout = dadata_config["timeout"]
        assert dadata_timeout.read == 30.0, \
            "DaData read timeout должен остаться 30s"
        
        dadata_cb = dadata_config["circuit_breaker"]
        assert dadata_cb.timeout == 30.0, \
            "DaData circuit breaker timeout должен остаться 30s"


@pytest.mark.asyncio
class TestP0_1_Integration:
    """Интеграционные тесты (требуют реальных API ключей)."""

    @pytest.mark.skip(reason="Требует реальные API ключи и длительное время выполнения")
    async def test_casebook_can_fetch_all_pages(self):
        """
        Интеграционный тест: Casebook может вычитать все страницы за 6 минут.
        
        Этот тест требует:
        - Реальный CASEBOOK_API_KEY
        - Валидный ИНН с большим количеством дел (>100 страниц)
        - Время выполнения: до 6 минут
        """
        from app.services.fetch_data import fetch_from_casebook
        
        # ИНН крупной компании с множеством дел
        test_inn = "7736050003"  # Газпром (пример)
        
        result = await fetch_from_casebook(test_inn)
        
        assert result.get("status") == "success", \
            f"Casebook должен успешно вычитать все страницы, error: {result.get('error')}"
        
        data = result.get("data", [])
        assert isinstance(data, list), "Casebook должен вернуть список дел"
        
        # Если дел больше 100, значит пагинация отработала
        if len(data) > 100:
            print(f"✅ Успешно вычитано {len(data)} дел из Casebook за 6 минут")

    @pytest.mark.skip(reason="Требует реальные API ключи")
    async def test_infosphere_long_request(self):
        """
        Интеграционный тест: InfoSphere может обработать длительный запрос.
        """
        from app.services.fetch_data import fetch_from_infosphere
        
        test_inn = "7736050003"
        
        result = await fetch_from_infosphere(test_inn)
        
        assert result.get("status") == "success", \
            f"InfoSphere должен успешно выполниться, error: {result.get('error')}"


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v", "--tb=short"])

