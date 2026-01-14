"""
P0-2: Тесты для удаления asyncio.wait_for из длительных запросов.

Проверяем:
1. InfoSphere и Casebook не имеют дополнительных таймаутов
2. DaData сохраняет wait_for(30s)
3. Логирование длительных операций работает
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.data_collector import (
    _fetch_casebook_wrapper,
    _fetch_dadata_wrapper,
    _fetch_infosphere_wrapper,
)


class TestP0_2_WaitForRemoval:
    """Тесты удаления asyncio.wait_for."""

    @pytest.mark.asyncio
    async def test_dadata_still_has_wait_for(self):
        """
        Проверка что DaData сохраняет wait_for(30s).
        
        DaData - быстрый источник, не требует длительной обработки.
        """
        with patch("app.agents.data_collector.fetch_from_dadata") as mock_fetch:
            # Мокируем медленный ответ (35 секунд)
            async def slow_response(inn):
                await asyncio.sleep(35)
                return {"status": "success", "data": {}}
            
            mock_fetch.side_effect = slow_response
            
            # Должен упасть по таймауту 30s
            result = await _fetch_dadata_wrapper("7736050003")
            
            assert result["success"] is False, \
                "DaData должен упасть по таймауту 30s"
            assert result["error"] == "Timeout", \
                "Ошибка должна быть Timeout"

    @pytest.mark.asyncio
    async def test_infosphere_no_wait_for(self):
        """
        Проверка что InfoSphere НЕ имеет wait_for.
        
        InfoSphere может работать до 6 минут, wait_for убран.
        """
        with patch("app.agents.data_collector.fetch_from_infosphere") as mock_fetch:
            # Мокируем медленный ответ (2 минуты)
            async def slow_response(inn):
                await asyncio.sleep(120)
                return {"status": "success", "data": {"test": "data"}}
            
            mock_fetch.side_effect = slow_response
            
            # Запускаем с общим таймаутом 150s (больше чем имитация)
            try:
                result = await asyncio.wait_for(
                    _fetch_infosphere_wrapper("7736050003"),
                    timeout=150
                )
                
                # Должен успешно завершиться
                assert result["success"] is True, \
                    "InfoSphere должен успешно завершиться без wait_for"
                assert "test" in str(result.get("data")), \
                    "Данные должны быть получены"
                    
            except asyncio.TimeoutError:
                pytest.fail("InfoSphere не должен падать по таймауту (wait_for удалён)")

    @pytest.mark.asyncio
    async def test_casebook_no_wait_for(self):
        """
        Проверка что Casebook НЕ имеет wait_for.
        
        Casebook может работать до 6 минут (пагинация 100+ страниц).
        """
        with patch("app.agents.data_collector.fetch_from_casebook") as mock_fetch:
            # Мокируем медленный ответ (2 минуты)
            async def slow_response(inn):
                await asyncio.sleep(120)
                return {"status": "success", "data": [{"case": 1}, {"case": 2}]}
            
            mock_fetch.side_effect = slow_response
            
            # Запускаем с общим таймаутом 150s
            try:
                result = await asyncio.wait_for(
                    _fetch_casebook_wrapper("7736050003"),
                    timeout=150
                )
                
                # Должен успешно завершиться
                assert result["success"] is True, \
                    "Casebook должен успешно завершиться без wait_for"
                assert isinstance(result.get("data"), list), \
                    "Данные должны быть списком дел"
                    
            except asyncio.TimeoutError:
                pytest.fail("Casebook не должен падать по таймауту (wait_for удалён)")

    @pytest.mark.asyncio
    async def test_infosphere_logs_progress(self, caplog):
        """
        Проверка что InfoSphere логирует начало и завершение операции.
        """
        with patch("app.agents.data_collector.fetch_from_infosphere") as mock_fetch:
            mock_fetch.return_value = {"status": "success", "data": {}}
            
            await _fetch_infosphere_wrapper("7736050003")
            
            # Проверяем логи
            log_messages = [record.message for record in caplog.records]
            
            assert any("starting long fetch" in msg.lower() for msg in log_messages), \
                "Должно быть логирование начала операции"
            assert any("fetch completed" in msg.lower() for msg in log_messages), \
                "Должно быть логирование завершения операции"

    @pytest.mark.asyncio
    async def test_casebook_logs_cases_count(self, caplog):
        """
        Проверка что Casebook логирует количество найденных дел.
        """
        with patch("app.agents.data_collector.fetch_from_casebook") as mock_fetch:
            mock_fetch.return_value = {
                "status": "success",
                "data": [{"case": i} for i in range(50)]
            }
            
            await _fetch_casebook_wrapper("7736050003")
            
            # Проверяем логи
            log_messages = [record.message for record in caplog.records]
            
            assert any("found 50 cases" in msg.lower() for msg in log_messages), \
                "Должно быть логирование количества дел"

    @pytest.mark.asyncio
    async def test_error_handling_preserved(self):
        """
        Проверка что обработка ошибок сохранена после удаления wait_for.
        """
        with patch("app.agents.data_collector.fetch_from_infosphere") as mock_fetch:
            # Мокируем ошибку
            mock_fetch.side_effect = RuntimeError("API Error")
            
            result = await _fetch_infosphere_wrapper("7736050003")
            
            assert result["success"] is False, \
                "При ошибке success должен быть False"
            assert "API Error" in result["error"], \
                "Ошибка должна быть сохранена"


@pytest.mark.asyncio
class TestP0_2_Integration:
    """Интеграционные тесты (требуют реальных API ключей)."""

    @pytest.mark.skip(reason="Требует реальные API ключи и 6+ минут")
    async def test_casebook_can_handle_long_pagination(self):
        """
        Интеграционный тест: Casebook может обработать пагинацию без таймаута.
        
        Этот тест проверяет реальный сценарий с множеством страниц.
        """
        from app.agents.data_collector import _fetch_casebook_wrapper
        
        # ИНН компании с множеством дел (>100 страниц)
        test_inn = "7736050003"
        
        result = await _fetch_casebook_wrapper(test_inn)
        
        assert result["success"] is True, \
            f"Casebook должен успешно завершиться, error: {result.get('error')}"
        
        cases = result.get("data", [])
        print(f"✅ Casebook: найдено {len(cases)} дел")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

