"""
E2E тесты полного workflow анализа клиента.

Тестирует:
- Полный цикл: INN → Data Collection → Analysis → Report → Storage
- Сохранение отчёта в Tarantool
- Обработку ошибок на разных этапах
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestE2EWorkflow:
    """E2E тесты для полного workflow."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_with_mocked_llm(self):
        """Полный workflow с мокированным LLM."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "completed",
            "session_id": "e2e-test-session-123",
            "client_name": "ПАО Сбербанк",
            "inn": "7707083893",
            "report": {
                "risk_score": 25,
                "summary": "Низкий уровень риска. Компания имеет стабильные финансовые показатели.",
                "findings": [
                    {"source": "dadata", "status": "ok", "data": {"company": "ПАО Сбербанк"}},
                    {"source": "casebook", "status": "ok", "data": {"cases": 0}},
                ],
                "recommendations": ["Продолжить сотрудничество"],
            },
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            with patch("app.storage.tarantool.TarantoolClient") as mock_tarantool:
                mock_client = MagicMock()
                mock_tarantool.get_instance = AsyncMock(return_value=mock_client)
                
                mock_reports_repo = AsyncMock()
                mock_reports_repo.create_from_workflow_result = AsyncMock(return_value="report-12345")
                mock_client.get_reports_repository.return_value = mock_reports_repo
                
                result = await execute_client_analysis(
                    client_name="ПАО Сбербанк",
                    inn="7707083893",
                    additional_notes="Тестовый анализ",
                    save_report=True,
                )
                
                assert result["status"] == "completed"
                assert result["session_id"] == "e2e-test-session-123"
                assert result["report"]["risk_score"] == 25
                
                mock_run.assert_called_once_with(
                    client_name="ПАО Сбербанк",
                    inn="7707083893",
                    additional_notes="Тестовый анализ",
                    session_id=None,
                )
                
                mock_reports_repo.create_from_workflow_result.assert_called_once_with(mock_workflow_result)
    
    @pytest.mark.asyncio
    async def test_workflow_without_saving_report(self):
        """Workflow без сохранения отчёта."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "completed",
            "session_id": "e2e-no-save",
            "report": {"risk_score": 50},
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            result = await execute_client_analysis(
                client_name="ООО Тест",
                inn="1234567890",
                save_report=False,
            )
            
            assert result["status"] == "completed"
            assert result["session_id"] == "e2e-no-save"
    
    @pytest.mark.asyncio
    async def test_workflow_with_external_session_id(self):
        """Workflow с внешним session_id."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "completed",
            "session_id": "external-session-xyz",
            "report": {"risk_score": 30},
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            with patch("app.storage.tarantool.TarantoolClient") as mock_tarantool:
                mock_client = MagicMock()
                mock_tarantool.get_instance = AsyncMock(return_value=mock_client)
                mock_reports_repo = AsyncMock()
                mock_reports_repo.create_from_workflow_result = AsyncMock(return_value="r-123")
                mock_client.get_reports_repository.return_value = mock_reports_repo
                
                result = await execute_client_analysis(
                    client_name="Test",
                    inn="1111111111",
                    session_id="external-session-xyz",
                    save_report=True,
                )
                
                assert result["session_id"] == "external-session-xyz"
                
                mock_run.assert_called_once_with(
                    client_name="Test",
                    inn="1111111111",
                    additional_notes="",
                    session_id="external-session-xyz",
                )
    
    @pytest.mark.asyncio
    async def test_workflow_handles_tarantool_error_gracefully(self):
        """Workflow продолжает работать при ошибке Tarantool."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "completed",
            "session_id": "tarantool-error-test",
            "report": {"risk_score": 45},
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            with patch("app.storage.tarantool.TarantoolClient") as mock_tarantool:
                mock_tarantool.get_instance = AsyncMock(side_effect=Exception("Tarantool unavailable"))
                
                result = await execute_client_analysis(
                    client_name="Test Error",
                    inn="2222222222",
                    save_report=True,
                )
                
                assert result["status"] == "completed"
                assert result["session_id"] == "tarantool-error-test"
    
    @pytest.mark.asyncio
    async def test_workflow_incomplete_status_not_saved(self):
        """Неуспешный workflow не сохраняет отчёт."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "error",
            "session_id": "error-session",
            "error": "LLM timeout",
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            with patch("app.storage.tarantool.TarantoolClient") as mock_tarantool:
                mock_client = MagicMock()
                mock_tarantool.get_instance = AsyncMock(return_value=mock_client)
                mock_reports_repo = AsyncMock()
                mock_client.get_reports_repository.return_value = mock_reports_repo
                
                result = await execute_client_analysis(
                    client_name="Error Test",
                    inn="3333333333",
                    save_report=True,
                )
                
                assert result["status"] == "error"
                
                mock_reports_repo.create_from_workflow_result.assert_not_called()


class TestE2EDataCollection:
    """E2E тесты для сбора данных."""
    
    @pytest.mark.asyncio
    async def test_workflow_aggregates_multiple_sources(self):
        """Workflow агрегирует данные из нескольких источников."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "completed",
            "session_id": "multi-source-test",
            "report": {
                "risk_score": 35,
                "sources": {
                    "dadata": {"status": "ok", "company": "ООО Тест"},
                    "casebook": {"status": "ok", "cases": 2},
                    "infosphere": {"status": "timeout", "error": "Service unavailable"},
                    "perplexity": {"status": "ok", "summary": "Стабильная компания"},
                    "tavily": {"status": "ok", "news": []},
                },
            },
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            with patch("app.storage.tarantool.TarantoolClient") as mock_tarantool:
                mock_client = MagicMock()
                mock_tarantool.get_instance = AsyncMock(return_value=mock_client)
                mock_reports_repo = AsyncMock()
                mock_reports_repo.create_from_workflow_result = AsyncMock(return_value="r-multi")
                mock_client.get_reports_repository.return_value = mock_reports_repo
                
                result = await execute_client_analysis(
                    client_name="ООО Тест",
                    inn="4444444444",
                    save_report=True,
                )
                
                assert result["status"] == "completed"
                assert "sources" in result["report"]
                sources = result["report"]["sources"]
                assert sources["dadata"]["status"] == "ok"
                assert sources["infosphere"]["status"] == "timeout"


class TestE2EReportGeneration:
    """E2E тесты для генерации отчётов."""
    
    @pytest.mark.asyncio
    async def test_report_contains_required_fields(self):
        """Отчёт содержит все обязательные поля."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "completed",
            "session_id": "report-fields-test",
            "client_name": "ПАО Газпром",
            "inn": "7736050003",
            "report": {
                "risk_score": 15,
                "risk_level": "low",
                "summary": "Крупнейшая энергетическая компания России",
                "findings": [
                    {"category": "financial", "description": "Стабильные финансы"},
                    {"category": "legal", "description": "Нет судебных исков"},
                ],
                "recommendations": [
                    "Рекомендовано к сотрудничеству",
                ],
                "metadata": {
                    "analysis_date": datetime.now(timezone.utc).isoformat(),
                    "sources_used": ["dadata", "casebook", "perplexity"],
                },
            },
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            with patch("app.storage.tarantool.TarantoolClient") as mock_tarantool:
                mock_client = MagicMock()
                mock_tarantool.get_instance = AsyncMock(return_value=mock_client)
                mock_reports_repo = AsyncMock()
                mock_reports_repo.create_from_workflow_result = AsyncMock(return_value="report-id")
                mock_client.get_reports_repository.return_value = mock_reports_repo
                
                result = await execute_client_analysis(
                    client_name="ПАО Газпром",
                    inn="7736050003",
                    save_report=True,
                )
                
                report = result["report"]
                
                assert "risk_score" in report
                assert isinstance(report["risk_score"], (int, float))
                assert 0 <= report["risk_score"] <= 100
                
                assert "summary" in report
                assert len(report["summary"]) > 0
                
                assert "findings" in report
                assert isinstance(report["findings"], list)
                
                assert "recommendations" in report
                assert isinstance(report["recommendations"], list)


class TestE2EWithAdditionalNotes:
    """E2E тесты с дополнительными заметками."""
    
    @pytest.mark.asyncio
    async def test_additional_notes_passed_to_workflow(self):
        """Дополнительные заметки передаются в workflow."""
        from app.services.analysis_executor import execute_client_analysis
        
        mock_workflow_result = {
            "status": "completed",
            "session_id": "notes-test",
            "report": {"risk_score": 40},
        }
        
        with patch("app.agents.client_workflow.run_client_analysis_batch", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_workflow_result
            
            with patch("app.storage.tarantool.TarantoolClient") as mock_tarantool:
                mock_client = MagicMock()
                mock_tarantool.get_instance = AsyncMock(return_value=mock_client)
                mock_reports_repo = AsyncMock()
                mock_reports_repo.create_from_workflow_result = AsyncMock(return_value="r-1")
                mock_client.get_reports_repository.return_value = mock_reports_repo
                
                await execute_client_analysis(
                    client_name="Test Notes",
                    inn="5555555555",
                    additional_notes="Обратить внимание на судебные дела за последний год",
                    save_report=True,
                )
                
                mock_run.assert_called_once()
                call_kwargs = mock_run.call_args.kwargs
                assert call_kwargs["additional_notes"] == "Обратить внимание на судебные дела за последний год"
