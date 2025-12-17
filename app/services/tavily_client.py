import hashlib
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from app.services.http_client import (
    AsyncHttpClient,
    CircuitBreakerOpenError,
)
from app.utility.logging_client import logger

load_dotenv('.env')


class TavilyClient:
    BASE_URL = "https://api.tavily.com"

    _instance: Optional["TavilyClient"] = None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self._http_client: Optional[AsyncHttpClient] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300

    @classmethod
    def get_instance(cls) -> "TavilyClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _get_http_client(self) -> AsyncHttpClient:
        if self._http_client is None:
            self._http_client = await AsyncHttpClient.get_instance()
        return self._http_client

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_cache_key(
        self,
        query: str,
        search_depth: str,
        max_results: int,
        include_answer: bool = True,
        include_raw_content: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> str:
        key_parts = [
            query,
            search_depth,
            str(max_results),
            str(include_answer),
            str(include_raw_content),
            ",".join(sorted(include_domains or [])),
            ",".join(sorted(exclude_domains or [])),
        ]
        key_str = ":".join(key_parts)
        return (
            f"tavily:{hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()}"
        )

    async def search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        if not self.api_key:
            logger.error("Tavily API key not configured", component="tavily")
            return {"error": "Tavily API key not configured", "success": False}

        cache_key = self._get_cache_key(
            query,
            search_depth,
            max_results,
            include_answer,
            include_raw_content,
            include_domains,
            exclude_domains,
        )
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.info(f"Tavily cache hit for query: {query[:50]}", component="tavily")
            return cached

        http_client = await self._get_http_client()

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": min(max_results, 10),
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }

        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        try:
            response = await http_client.request_with_resilience(
                method="POST",
                url=f"{self.BASE_URL}/search",
                service="tavily",
                json=payload,
            )
            result = response.json()

            logger.info(
                f"Tavily search completed: {len(result.get('results', []))} results",
                component="tavily",
            )

            response_data = {
                "success": True,
                "answer": result.get("answer", ""),
                "results": result.get("results", []),
                "query": query,
                "response_time": result.get("response_time", 0),
                "cached": False,
            }

            if use_cache:
                self._cache[cache_key] = {**response_data, "cached": True}

            return response_data

        except CircuitBreakerOpenError:
            logger.warning(
                "Tavily circuit breaker is open, service temporarily unavailable",
                component="tavily",
            )
            return {
                "success": False,
                "error": "Tavily service temporarily unavailable (circuit breaker open)",
                "circuit_breaker": True,
            }

        except httpx.TimeoutException as e:
            logger.error(
                f"Tavily request timeout: {type(e).__name__}",
                component="tavily",
            )
            return {
                "success": False,
                "error": "Tavily request timeout - сервис не ответил вовремя",
                "timeout": True,
            }

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(
                f"Tavily HTTP error: {status_code}",
                component="tavily",
            )
            if status_code in (401, 403):
                return {"success": False, "error": "Invalid Tavily API key"}
            elif status_code == 429:
                return {"success": False, "error": "Tavily rate limit exceeded"}
            return {"success": False, "error": f"HTTP {status_code}"}

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(
                f"Tavily request failed: {type(e).__name__}: {error_msg}",
                component="tavily",
            )
            return {"success": False, "error": error_msg or "Неизвестная ошибка"}

    async def search_with_fallback(
        self,
        query: str,
        fallback_handler: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        result = await self.search(query, **kwargs)

        if not result.get("success") and fallback_handler:
            logger.info(
                f"Tavily search failed, trying fallback for: {query[:50]}",
                component="tavily",
            )
            return await fallback_handler(query, **kwargs)

        return result

    def clear_cache(self):
        self._cache.clear()
        logger.info("Tavily cache cleared", component="tavily")

    def get_cache_stats(self) -> Dict[str, int]:
        return {
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl,
        }

    async def get_status(self) -> Dict[str, Any]:
        http_client = await self._get_http_client()
        circuit_status = http_client.get_circuit_breaker_status("tavily")
        metrics = http_client.get_metrics("tavily")

        return {
            "configured": self.is_configured(),
            "circuit_breaker": circuit_status,
            "metrics": metrics,
            "cache_stats": self.get_cache_stats(),
        }

    @classmethod
    async def close_global(cls):
        if cls._instance:
            cls._instance._cache.clear()
            cls._instance = None
