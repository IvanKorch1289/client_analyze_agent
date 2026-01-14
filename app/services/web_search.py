"""
Web Search Service - унифицированный интерфейс для поисковых провайдеров.

Абстрагирует Perplexity и Tavily за общим интерфейсом.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.services.perplexity_client import PerplexityClient
from app.services.tavily_client import TavilyClient


class WebSearchProvider(ABC):
    """Абстрактный интерфейс для веб-поиска."""

    @abstractmethod
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        Выполнить поисковый запрос.

        Args:
            query: Поисковый запрос
            **kwargs: Дополнительные параметры провайдера

        Returns:
            Dict с ключами:
            - success: bool
            - content/answer: str (результат поиска)
            - results: List[Dict] (список результатов, опционально)
            - cached: bool
            - error: str (при ошибке)
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Проверить наличие конфигурации."""
        pass

    @abstractmethod
    async def healthcheck(self, timeout_s: float = 8.0) -> Dict[str, Any]:
        """
        Проверить доступность сервиса.

        Returns:
            Dict с ключами: configured, available, status, latency_ms, error
        """
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Получить статус провайдера (без внешнего вызова)."""
        pass


class PerplexitySearchProvider(WebSearchProvider):
    """Perplexity AI адаптер."""

    def __init__(self, client: Optional[PerplexityClient] = None):
        self._client = client or PerplexityClient.get_instance()

    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """Поиск через Perplexity AI."""
        system_prompt = kwargs.pop(
            "system_prompt",
            "Be precise and concise. Answer in Russian if the question is in Russian.",
        )
        return await self._client.ask(
            question=query,
            system_prompt=system_prompt,
            use_cache=kwargs.pop("use_cache", True),
            **kwargs,
        )

    def is_configured(self) -> bool:
        return self._client.is_configured()

    async def healthcheck(self, timeout_s: float = 8.0) -> Dict[str, Any]:
        return await self._client.healthcheck(timeout_s)

    async def get_status(self) -> Dict[str, Any]:
        return await self._client.get_status()


class TavilySearchProvider(WebSearchProvider):
    """Tavily адаптер."""

    def __init__(self, client: Optional[TavilyClient] = None):
        self._client = client or TavilyClient.get_instance()

    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """Поиск через Tavily."""
        return await self._client.search(
            query=query,
            search_depth=kwargs.pop("search_depth", "basic"),
            max_results=kwargs.pop("max_results", 5),
            include_answer=kwargs.pop("include_answer", True),
            use_cache=kwargs.pop("use_cache", True),
            **kwargs,
        )

    def is_configured(self) -> bool:
        return self._client.is_configured()

    async def healthcheck(self, timeout_s: float = 8.0) -> Dict[str, Any]:
        return await self._client.healthcheck(timeout_s)

    async def get_status(self) -> Dict[str, Any]:
        return await self._client.get_status()


class WebSearchService:
    """
    Унифицированный сервис веб-поиска.

    Позволяет использовать несколько провайдеров с fallback.

    Example:
        service = WebSearchService()
        result = await service.search("company reputation", provider="perplexity")
        # или с fallback
        result = await service.search_with_fallback("company info")
    """

    def __init__(self):
        self._providers: Dict[str, WebSearchProvider] = {
            "perplexity": PerplexitySearchProvider(),
            "tavily": TavilySearchProvider(),
        }

    def get_provider(self, name: str) -> Optional[WebSearchProvider]:
        """Получить провайдер по имени."""
        return self._providers.get(name)

    def available_providers(self) -> List[str]:
        """Список доступных (сконфигурированных) провайдеров."""
        return [name for name, p in self._providers.items() if p.is_configured()]

    async def search(
        self,
        query: str,
        provider: str = "perplexity",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Поиск через указанный провайдер.

        Args:
            query: Поисковый запрос
            provider: "perplexity" или "tavily"
            **kwargs: Параметры провайдера

        Returns:
            Результат поиска
        """
        p = self._providers.get(provider)
        if not p:
            return {"success": False, "error": f"Unknown provider: {provider}"}
        if not p.is_configured():
            return {"success": False, "error": f"Provider {provider} not configured"}
        return await p.search(query, **kwargs)

    async def search_with_fallback(
        self,
        query: str,
        primary: str = "perplexity",
        fallback: str = "tavily",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Поиск с fallback на другой провайдер при ошибке.

        Args:
            query: Поисковый запрос
            primary: Основной провайдер
            fallback: Резервный провайдер
            **kwargs: Параметры провайдера

        Returns:
            Результат поиска (добавляет "provider" в ответ)
        """
        result = await self.search(query, provider=primary, **kwargs)
        if result.get("success"):
            result["provider"] = primary
            return result

        result = await self.search(query, provider=fallback, **kwargs)
        result["provider"] = fallback
        return result

    async def healthcheck_all(self, timeout_s: float = 8.0) -> Dict[str, Dict[str, Any]]:
        """Проверить все провайдеры."""
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.healthcheck(timeout_s)
        return results

    async def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Получить статусы всех провайдеров."""
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.get_status()
        return results


_service_instance: Optional[WebSearchService] = None


def get_web_search_service() -> WebSearchService:
    """Singleton для WebSearchService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = WebSearchService()
    return _service_instance


__all__ = [
    "WebSearchProvider",
    "PerplexitySearchProvider",
    "TavilySearchProvider",
    "WebSearchService",
    "get_web_search_service",
]
