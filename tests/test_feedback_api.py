"""
Интеграционные тесты для feedback API.

Тестирует:
- Отправку фидбека без перезапуска анализа
- Отправку фидбека с rerun_analysis=True
- Валидацию входных данных
- Обработку ошибок (несуществующий отчёт)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

from app.api.v1 import v1_app
from app.schemas.requests import FeedbackRequest


@pytest.fixture
def client():
    """Создать тестовый клиент с отключённым rate limiting."""
    import app.api.routes.agent as agent_module
    
    agent_module.limiter._enabled = False
    agent_module.limiter._storage.reset()
    
    test_client = TestClient(v1_app)
    
    yield test_client
    
    agent_module.limiter._enabled = True


@pytest.fixture
def mock_tarantool():
    """Мок для TarantoolClient."""
    with patch("app.storage.tarantool.TarantoolClient") as mock:
        mock_instance = MagicMock()
        mock.get_instance = AsyncMock(return_value=mock_instance)
        
        mock_reports_repo = AsyncMock()
        mock_instance.get_reports_repository = MagicMock(return_value=mock_reports_repo)
        
        yield {
            "client": mock,
            "instance": mock_instance,
            "reports_repo": mock_reports_repo,
        }


@pytest.fixture
def sample_report():
    """Примерный отчёт для тестов."""
    return {
        "id": "test-report-123",
        "inn": "7707083893",
        "client_name": "ПАО Сбербанк",
        "status": "completed",
        "report_data": {
            "risk_score": 25,
            "summary": "Низкий риск",
            "metadata": {
                "additional_notes": "Предыдущие заметки"
            }
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


class TestFeedbackAPIValidation:
    """Тесты валидации входных данных."""
    
    def test_feedback_missing_report_id(self, client):
        """Проверка обязательности report_id."""
        response = client.post(
            "/agent/feedback",
            json={
                "rating": "accurate",
                "comment": "Отличный отчёт",
            }
        )
        assert response.status_code == 422
    
    def test_feedback_invalid_rating(self, client):
        """Проверка валидации rating."""
        response = client.post(
            "/agent/feedback",
            json={
                "report_id": "test-123",
                "rating": "invalid_rating",
                "comment": "Тест",
            }
        )
        assert response.status_code == 422
    
    def test_feedback_valid_ratings(self, client, mock_tarantool, sample_report):
        """Проверка всех допустимых значений rating."""
        mock_tarantool["reports_repo"].get.return_value = sample_report
        
        valid_ratings = ["accurate", "partially_accurate", "inaccurate"]
        
        for rating in valid_ratings:
            response = client.post(
                "/agent/feedback",
                json={
                    "report_id": "test-123",
                    "rating": rating,
                    "rerun_analysis": False,
                }
            )
            assert response.status_code == 200, f"Rating '{rating}' should be valid"


class TestFeedbackWithoutRerun:
    """Тесты фидбека без перезапуска анализа."""
    
    def test_feedback_saved_without_rerun(self, client, mock_tarantool, sample_report):
        """Фидбек сохраняется без перезапуска анализа."""
        mock_tarantool["reports_repo"].get.return_value = sample_report
        
        response = client.post(
            "/agent/feedback",
            json={
                "report_id": "test-report-123",
                "rating": "accurate",
                "comment": "Отличный отчёт, все данные корректны",
                "rerun_analysis": False,
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "feedback_saved"
        assert "feedback" in data
        assert data["feedback"]["rating"] == "accurate"
        assert data["feedback"]["comment"] == "Отличный отчёт, все данные корректны"
    
    def test_feedback_with_focus_areas(self, client, mock_tarantool, sample_report):
        """Фидбек с указанием областей внимания."""
        mock_tarantool["reports_repo"].get.return_value = sample_report
        
        response = client.post(
            "/agent/feedback",
            json={
                "report_id": "test-report-123",
                "rating": "partially_accurate",
                "comment": "Нужно больше внимания к судебным делам",
                "focus_areas": ["судебные дела", "финансовые показатели"],
                "rerun_analysis": False,
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["feedback"]["focus_areas"] == ["судебные дела", "финансовые показатели"]


class TestFeedbackWithRerun:
    """Тесты фидбека с перезапуском анализа."""
    
    def test_feedback_triggers_reanalysis(self, client, mock_tarantool, sample_report):
        """Фидбек с rerun=True запускает переанализ."""
        mock_tarantool["reports_repo"].get.return_value = sample_report
        
        mock_result = {
            "session_id": "new-session-456",
            "status": "completed",
            "report": {"risk_score": 30},
        }
        
        with patch("app.api.routes.agent.execute_client_analysis", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            
            response = client.post(
                "/agent/feedback",
                json={
                    "report_id": "test-report-123",
                    "rating": "inaccurate",
                    "comment": "Данные по судебным делам неполные",
                    "focus_areas": ["casebook"],
                    "rerun_analysis": True,
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "reanalysis_complete"
            assert data["new_session_id"] == "new-session-456"
            assert data["original_report_id"] == "test-report-123"
            
            mock_execute.assert_called_once()
            call_kwargs = mock_execute.call_args.kwargs
            assert call_kwargs["inn"] == "7707083893"
            assert call_kwargs["client_name"] == "ПАО Сбербанк"
            assert call_kwargs["save_report"] is True
            assert "ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ" in call_kwargs["additional_notes"] or \
                   "неполные" in call_kwargs["additional_notes"]
    
    def test_feedback_reanalysis_includes_previous_context(self, client, mock_tarantool, sample_report):
        """Переанализ включает контекст предыдущего отчёта."""
        mock_tarantool["reports_repo"].get.return_value = sample_report
        
        with patch("app.api.routes.agent.execute_client_analysis", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"session_id": "new-session"}
            
            response = client.post(
                "/agent/feedback",
                json={
                    "report_id": "test-report-123",
                    "rating": "inaccurate",
                    "comment": "Риск-скор занижен",
                    "rerun_analysis": True,
                }
            )
            
            assert response.status_code == 200
            
            call_kwargs = mock_execute.call_args.kwargs
            notes = call_kwargs.get("additional_notes", "")
            assert "Предыдущие заметки" in notes or len(notes) > 0


class TestFeedbackErrorHandling:
    """Тесты обработки ошибок."""
    
    def test_feedback_report_not_found(self, client, mock_tarantool):
        """Ошибка при отсутствии отчёта."""
        mock_tarantool["reports_repo"].get.return_value = None
        
        response = client.post(
            "/agent/feedback",
            json={
                "report_id": "nonexistent-report",
                "rating": "accurate",
                "rerun_analysis": False,
            }
        )
        
        assert response.status_code == 404
    
    def test_feedback_reanalysis_error(self, client, mock_tarantool, sample_report):
        """Обработка ошибки при переанализе."""
        mock_tarantool["reports_repo"].get.return_value = sample_report
        
        with patch("app.api.routes.agent.execute_client_analysis", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("LLM unavailable")
            
            response = client.post(
                "/agent/feedback",
                json={
                    "report_id": "test-report-123",
                    "rating": "inaccurate",
                    "comment": "Нужен переанализ",
                    "rerun_analysis": True,
                }
            )
            
            assert response.status_code == 500
            data = response.json()
            error_text = data.get("detail", "") or data.get("message", "") or str(data)
            assert "Ошибка" in error_text or "error" in error_text.lower() or "LLM" in error_text


class TestFeedbackInstructionBuilder:
    """Тесты построения инструкций для LLM."""
    
    def test_build_instructions_includes_rating(self):
        """Инструкции включают рейтинг."""
        from app.api.routes.agent import _build_feedback_instructions
        
        request = FeedbackRequest(
            report_id="test-123",
            rating="inaccurate",
            comment="Данные устарели",
        )
        
        original_report = {
            "report_data": {
                "risk_score": 50,
                "summary": "Средний риск",
            }
        }
        
        instructions = _build_feedback_instructions(request, original_report)
        
        assert "inaccurate" in instructions.lower() or "неточн" in instructions.lower()
    
    def test_build_instructions_includes_focus_areas(self):
        """Инструкции включают области внимания."""
        from app.api.routes.agent import _build_feedback_instructions
        
        request = FeedbackRequest(
            report_id="test-123",
            rating="partially_accurate",
            comment="Проверьте судебные дела",
            focus_areas=["casebook", "infosphere"],
        )
        
        original_report = {"report_data": {}}
        
        instructions = _build_feedback_instructions(request, original_report)
        
        assert "casebook" in instructions.lower() or "infosphere" in instructions.lower() or \
               "внимание" in instructions.lower()
    
    def test_build_instructions_includes_previous_score(self):
        """Инструкции включают предыдущий риск-скор."""
        from app.api.routes.agent import _build_feedback_instructions
        
        request = FeedbackRequest(
            report_id="test-123",
            rating="inaccurate",
            comment="Риск занижен",
        )
        
        original_report = {
            "report_data": {
                "risk_score": 25,
                "summary": "Низкий риск",
            }
        }
        
        instructions = _build_feedback_instructions(request, original_report)
        
        assert "25" in instructions or "риск" in instructions.lower()
