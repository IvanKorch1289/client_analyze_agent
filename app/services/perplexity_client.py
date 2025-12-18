import asyncio
import hashlib
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast

from dotenv import load_dotenv
from openai import AsyncOpenAI

from app.utility.logging_client import logger

load_dotenv('.env')


class PerplexityClient:
    DEFAULT_MODEL = "sonar-pro"
    BASE_URL = "https://api.perplexity.ai"

    _instance: Optional["PerplexityClient"] = None

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.model = model or os.getenv("PERPLEXITY_MODEL", self.DEFAULT_MODEL)
        self._client: Optional[AsyncOpenAI] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300

    @classmethod
    def get_instance(cls) -> "PerplexityClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.BASE_URL,
                timeout=300.0,
            )
        return self._client

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

        try:
            client = self._get_client()
            
            response = await client.chat.completions.create(
                model=use_model,
                messages=cast(Any, messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )

            logger.info(
                f"Perplexity response received via OpenAI SDK, model: {use_model}",
                component="perplexity",
            )

            content = response.choices[0].message.content if response.choices else ""
            
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            citations = []
            if hasattr(response, 'citations'):
                citations = getattr(response, 'citations', []) or []

            response_data = {
                "success": True,
                "content": content,
                "citations": citations,
                "model": use_model,
                "usage": usage,
                "raw_response": {"content": content},
                "cached": False,
            }

            if use_cache:
                self._cache[cache_key] = {**response_data, "cached": True}

            return response_data

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(
                f"Perplexity request failed: {type(e).__name__}: {error_msg}",
                component="perplexity",
            )
            
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                return {
                    "success": False,
                    "error": "Perplexity request timeout - сервис не ответил вовремя",
                    "timeout": True,
                }
            elif "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg.lower():
                return {"success": False, "error": "Invalid Perplexity API key"}
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                return {"success": False, "error": "Perplexity rate limit exceeded"}
            
            return {"success": False, "error": error_msg or "Неизвестная ошибка"}

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
        return {
            "configured": self.is_configured(),
            "model": self.model,
            "status": "ready" if self.is_configured() else "not_configured",
            "integration": "openai-sdk",
            "cache_stats": self.get_cache_stats(),
        }

    @classmethod
    async def close_global(cls):
        if cls._instance:
            cls._instance._cache.clear()
            if cls._instance._client:
                await cls._instance._client.close()
            cls._instance._client = None
            cls._instance = None
