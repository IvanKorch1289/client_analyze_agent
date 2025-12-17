import hashlib
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.utility.logging_client import logger
from app.services.http_client import (
    AsyncHttpClient,
    CircuitBreakerOpenError,
)
from dotenv import load_dotenv


load_dotenv('.env')


class PerplexityClient:
    BASE_URL = "https://api.perplexity.ai/chat/completions"
    DEFAULT_MODEL = "sonar"

    _instance: Optional["PerplexityClient"] = None

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.model = model or os.getenv("PERPLEXITY_MODEL", self.DEFAULT_MODEL)
        self._http_client: Optional[AsyncHttpClient] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300

    @classmethod
    def get_instance(cls) -> "PerplexityClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _get_http_client(self) -> AsyncHttpClient:
        if self._http_client is None:
            self._http_client = await AsyncHttpClient.get_instance()
        return self._http_client

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_cache_key(self, messages: List[Dict[str, str]], model: str) -> str:
        messages_str = str(messages)
        key_str = f"{messages_str}:{model}"
        return f"perplexity:{hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()}"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        search_recency_filter: str = "month",
        use_cache: bool = False,
    ) -> Dict[str, Any]:
        if not self.api_key:
            logger.error("Perplexity API key not configured", component="perplexity")
            return {"error": "Perplexity API key not configured", "success": False}

        use_model = model or self.model

        cache_key = self._get_cache_key(messages, use_model)
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.info("Perplexity cache hit", component="perplexity")
            return cached

        http_client = await self._get_http_client()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.9,
            "return_images": False,
            "return_related_questions": False,
            "search_recency_filter": search_recency_filter,
            "stream": False,
            "presence_penalty": 0,
            "frequency_penalty": 1,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            response = await http_client.request_with_resilience(
                method="POST",
                url=self.BASE_URL,
                service="perplexity",
                headers=headers,
                json=payload,
            )
            result = response.json()

            logger.info(
                f"Perplexity response received, model: {use_model}",
                component="perplexity",
            )

            response_data = {
                "success": True,
                "content": result.get("choices", [{}])[0]
                .get("message", {})
                .get("content", ""),
                "citations": result.get("citations", []),
                "model": result.get("model"),
                "usage": result.get("usage", {}),
                "raw_response": result,
                "cached": False,
            }

            if use_cache:
                self._cache[cache_key] = {**response_data, "cached": True}

            return response_data

        except CircuitBreakerOpenError:
            logger.warning(
                "Perplexity circuit breaker is open, service temporarily unavailable",
                component="perplexity",
            )
            return {
                "success": False,
                "error": "Perplexity service temporarily unavailable (circuit breaker open)",
                "circuit_breaker": True,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Perplexity request failed: {error_msg}", component="perplexity"
            )

            if "status_code" in error_msg:
                if "401" in error_msg or "403" in error_msg:
                    return {"success": False, "error": "Invalid Perplexity API key"}
                elif "429" in error_msg:
                    return {"success": False, "error": "Perplexity rate limit exceeded"}

            return {"success": False, "error": error_msg}

    async def ask(
        self,
        question: str,
        system_prompt: str = "Be precise and concise. Answer in Russian if the question is in Russian.",
        use_cache: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
        return await self.chat(messages, use_cache=use_cache, **kwargs)

    async def ask_with_fallback(
        self,
        question: str,
        fallback_handler: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        result = await self.ask(question, **kwargs)

        if not result.get("success") and fallback_handler:
            logger.info(
                f"Perplexity ask failed, trying fallback for: {question[:50]}",
                component="perplexity",
            )
            return await fallback_handler(question, **kwargs)

        return result

    def clear_cache(self):
        self._cache.clear()
        logger.info("Perplexity cache cleared", component="perplexity")

    def get_cache_stats(self) -> Dict[str, int]:
        return {
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl,
        }

    async def get_status(self) -> Dict[str, Any]:
        http_client = await self._get_http_client()
        circuit_status = http_client.get_circuit_breaker_status("perplexity")
        metrics = http_client.get_metrics("perplexity")

        return {
            "configured": self.is_configured(),
            "model": self.model,
            "circuit_breaker": circuit_status,
            "metrics": metrics,
            "cache_stats": self.get_cache_stats(),
        }

    @classmethod
    async def close_global(cls):
        if cls._instance:
            cls._instance._cache.clear()
            cls._instance = None
