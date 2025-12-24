"""
P0-3.5: Тесты для рефакторинга MCP-сервера.

Проверяем:
1. Дубликат prompts.py удалён
2. Агенты используют импорты из MCP
3. Системные промпты доступны через get_system_prompt()
4. MCP экспортирует все промпты и resources
"""

import pytest
from pathlib import Path


class TestP0_3_5_DuplicateRemoval:
    """Тесты удаления дубликатов."""

    def test_shared_prompts_deleted(self):
        """
        Проверка что app/agents/shared/prompts.py удалён.
        """
        file_path = Path("app/agents/shared/prompts.py")
        
        assert not file_path.exists(), \
            "Дубликат app/agents/shared/prompts.py должен быть удалён"

    def test_agents_import_from_mcp(self):
        """
        Проверка что агенты импортируют промпты из MCP.
        """
        # Читаем orchestrator.py
        orchestrator_content = Path("app/agents/orchestrator.py").read_text()
        
        assert "from app.mcp_server.prompts.system_prompts import" in orchestrator_content, \
            "Orchestrator должен импортировать из MCP"
        
        assert "get_system_prompt" in orchestrator_content or "format_dadata_for_prompt" in orchestrator_content, \
            "Orchestrator должен использовать функции из MCP"
        
        # Читаем report_analyzer.py
        analyzer_content = Path("app/agents/report_analyzer.py").read_text()
        
        assert "from app.mcp_server.prompts.system_prompts import" in analyzer_content, \
            "Analyzer должен импортировать из MCP"
        
        assert "get_system_prompt" in analyzer_content, \
            "Analyzer должен использовать get_system_prompt"


class TestP0_3_5_SystemPrompts:
    """Тесты системных промптов в MCP."""

    def test_get_system_prompt_exists(self):
        """Проверка что функция get_system_prompt() доступна."""
        from app.mcp_server.prompts.system_prompts import get_system_prompt, AnalyzerRole
        
        # Должна быть вызываема
        assert callable(get_system_prompt), \
            "get_system_prompt должна быть функцией"

    def test_all_roles_have_prompts(self):
        """Проверка что все роли имеют системные промпты."""
        from app.mcp_server.prompts.system_prompts import (
            get_system_prompt,
            AnalyzerRole,
            SYSTEM_PROMPTS,
        )
        
        # Проверяем основные роли
        required_roles = [
            AnalyzerRole.ORCHESTRATOR,
            AnalyzerRole.REPORT_ANALYZER,
            AnalyzerRole.REGISTRY_ANALYZER,
            AnalyzerRole.WEB_ANALYZER,
        ]
        
        for role in required_roles:
            assert role in SYSTEM_PROMPTS, \
                f"Роль {role} должна иметь системный промпт"
            
            prompt = get_system_prompt(role)
            assert len(prompt) > 100, \
                f"Промпт для {role} не должен быть пустым"

    def test_prompts_are_in_russian(self):
        """Проверка что промпты на русском языке."""
        from app.mcp_server.prompts.system_prompts import get_system_prompt, AnalyzerRole
        
        prompt = get_system_prompt(AnalyzerRole.ORCHESTRATOR)
        
        # Проверяем наличие русских символов
        assert any(ord(c) > 1000 for c in prompt), \
            "Промпт должен содержать русские символы"

    def test_format_dadata_helper(self):
        """Проверка вспомогательной функции format_dadata_for_prompt."""
        from app.mcp_server.prompts.system_prompts import format_dadata_for_prompt
        
        test_data = {
            "name": {"full_with_opf": "ПАО ГАЗПРОМ"},
            "state": {"status": "ACTIVE", "registration_date": "1993-11-15"},
        }
        
        formatted = format_dadata_for_prompt(test_data)
        
        assert "ГАЗПРОМ" in formatted, \
            "Должно содержать название компании"
        assert "ACTIVE" in formatted, \
            "Должно содержать статус"


class TestP0_3_5_MCPPrompts:
    """Тесты экспорта промптов через MCP."""

    def test_mcp_has_system_prompts(self):
        """Проверка что MCP main.py экспортирует системные промпты."""
        mcp_main_content = Path("app/mcp_server/main.py").read_text()
        
        # Проверяем что добавлены декораторы @mcp.prompt
        assert "system_prompt_orchestrator" in mcp_main_content, \
            "MCP должен экспортировать промпт оркестратора"
        
        assert "system_prompt_report_analyzer" in mcp_main_content, \
            "MCP должен экспортировать промпт анализатора"
        
        assert "system_prompt_registry_analyzer" in mcp_main_content, \
            "MCP должен экспортировать промпт реестрового анализатора"
        
        assert "system_prompt_web_analyzer" in mcp_main_content, \
            "MCP должен экспортировать промпт веб-аналитика"

    def test_mcp_imports_from_prompts_module(self):
        """Проверка что MCP импортирует из prompts module."""
        mcp_main_content = Path("app/mcp_server/main.py").read_text()
        
        assert "from app.mcp_server.prompts.system_prompts import" in mcp_main_content, \
            "MCP должен импортировать из своего prompts модуля"


class TestP0_3_5_BestPractices:
    """Тесты Best Practices resources."""

    def test_best_practices_file_created(self):
        """Проверка что best_practices.py создан."""
        file_path = Path("app/mcp_server/resources/best_practices.py")
        
        assert file_path.exists(), \
            "best_practices.py должен существовать"

    def test_best_practices_content(self):
        """Проверка содержимого best practices."""
        from app.mcp_server.resources.best_practices import ANALYSIS_BEST_PRACTICES
        
        # Проверяем ключевые разделы
        assert "ОБЯЗАТЕЛЬНЫЕ ПРОВЕРКИ" in ANALYSIS_BEST_PRACTICES, \
            "Должен содержать раздел обязательных проверок"
        
        assert "ЕГРЮЛ" in ANALYSIS_BEST_PRACTICES, \
            "Должен упоминать ЕГРЮЛ"
        
        assert "ФОРМУЛА РАСЧЁТА" in ANALYSIS_BEST_PRACTICES.upper(), \
            "Должен содержать формулы расчёта"
        
        assert "КРИТИЧЕСКИЕ ФЛАГИ" in ANALYSIS_BEST_PRACTICES.upper(), \
            "Должен описывать критические флаги"
        
        # Проверяем длину (должен быть comprehensive)
        assert len(ANALYSIS_BEST_PRACTICES) > 5000, \
            "Best practices должны быть подробными (>5000 символов)"

    def test_api_examples_content(self):
        """Проверка содержимого API examples."""
        from app.mcp_server.resources.best_practices import API_USAGE_EXAMPLES
        
        # Проверяем наличие примеров для всех API
        assert "DaData" in API_USAGE_EXAMPLES, \
            "Должны быть примеры DaData"
        
        assert "Casebook" in API_USAGE_EXAMPLES, \
            "Должны быть примеры Casebook"
        
        assert "InfoSphere" in API_USAGE_EXAMPLES, \
            "Должны быть примеры InfoSphere"
        
        assert "Perplexity" in API_USAGE_EXAMPLES, \
            "Должны быть примеры Perplexity"
        
        assert "Tavily" in API_USAGE_EXAMPLES, \
            "Должны быть примеры Tavily"
        
        # Проверяем наличие кода
        assert "```python" in API_USAGE_EXAMPLES or "```xml" in API_USAGE_EXAMPLES, \
            "Должны быть code examples"

    def test_mcp_exports_best_practices(self):
        """Проверка что MCP экспортирует best practices как resource."""
        mcp_main_content = Path("app/mcp_server/main.py").read_text()
        
        assert "best_practices_resource" in mcp_main_content, \
            "MCP должен экспортировать best_practices resource"
        
        assert 'app://best-practices' in mcp_main_content, \
            "MCP должен иметь URI app://best-practices"
        
        assert "api_examples_resource" in mcp_main_content, \
            "MCP должен экспортировать api_examples resource"
        
        assert "api_specs_resource" in mcp_main_content, \
            "MCP должен экспортировать api_specs resource"


@pytest.mark.asyncio
class TestP0_3_5_Integration:
    """Интеграционные тесты MCP-сервера."""

    @pytest.mark.skip(reason="Требует запущенный MCP сервер")
    async def test_mcp_server_lists_prompts(self):
        """
        Интеграционный тест: MCP сервер возвращает список промптов.
        
        Запустить MCP:
            python -m app.mcp_server.main
        
        Проверить:
            GET http://localhost:8011/mcp/prompts
        """
        import httpx
        
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8011/mcp/prompts")
            assert resp.status_code == 200
            
            data = resp.json()
            prompt_names = [p["name"] for p in data.get("prompts", [])]
            
            # Проверяем что все системные промпты присутствуют
            assert "system_prompt_orchestrator" in prompt_names
            assert "system_prompt_report_analyzer" in prompt_names
            assert "system_prompt_registry_analyzer" in prompt_names

    @pytest.mark.skip(reason="Требует запущенный MCP сервер")
    async def test_mcp_server_lists_resources(self):
        """
        Интеграционный тест: MCP сервер возвращает список resources.
        """
        import httpx
        
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8011/mcp/resources")
            assert resp.status_code == 200
            
            data = resp.json()
            resource_uris = [r["uri"] for r in data.get("resources", [])]
            
            # Проверяем новые resources
            assert "app://best-practices" in resource_uris
            assert "app://api-usage-examples" in resource_uris
            assert "app://api-specs" in resource_uris


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

