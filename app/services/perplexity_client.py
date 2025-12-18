import asyncio
import hashlib
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from app.utility.logging_client import logger

load_dotenv('.env')


class PerplexityClient:
    DEFAULT_MODEL = "sonar-pro"
    BASE_URL = "https://api.perplexity.ai"

    _instance: Optional["PerplexityClient"] = None

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.model = model or os.getenv("PERPLEXITY_MODEL", self.DEFAULT_MODEL)
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300

    @classmethod
    def get_instance(cls) -> "PerplexityClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(300.0, connect=30.0),
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
            
            payload: Dict[str, Any] = {
                "model": use_model,
                "messages": messages,
                "temperature": temperature,
                # Perplexity extension (OpenAI-compatible)
                "search_recency_filter": search_recency_filter,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            data = response.json()

            logger.info(
                f"Perplexity response received via httpx, model: {use_model}",
                component="perplexity",
            )

            content = ""
            if data.get("choices") and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
            
            usage = {}
            if data.get("usage"):
                usage = {
                    "prompt_tokens": data["usage"].get("prompt_tokens", 0),
                    "completion_tokens": data["usage"].get("completion_tokens", 0),
                    "total_tokens": data["usage"].get("total_tokens", 0),
                }

            citations = data.get("citations", []) or []

            response_data = {
                "success": True,
                "content": content,
                "citations": citations,
                "model": use_model,
                "usage": usage,
                "raw_response": {"content": content},
                "cached": False,
                "integration": "httpx-direct",
            }

            if use_cache:
                self._cache[cache_key] = {**response_data, "cached": True}

            return response_data

        except httpx.TimeoutException:
            logger.error("Perplexity request timeout", component="perplexity")
            return {
                "success": False,
                "error": "Perplexity request timeout - сервис не ответил вовремя",
                "timeout": True,
            }
        except httpx.HTTPStatusError as e:
            error_msg = str(e)
            logger.error(
                f"Perplexity HTTP error: {e.response.status_code}: {error_msg}",
                component="perplexity",
            )
            if e.response.status_code in (401, 403):
                return {"success": False, "error": "Invalid Perplexity API key"}
            elif e.response.status_code == 429:
                return {"success": False, "error": "Perplexity rate limit exceeded"}
            return {"success": False, "error": f"HTTP {e.response.status_code}: {error_msg}"}
        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(
                f"Perplexity request failed: {type(e).__name__}: {error_msg}",
                component="perplexity",
            )
            return {"success": False, "error": error_msg or "Неизвестная ошибка"}

    async def ask_langchain(
        self,
        question: str,
        system_prompt: str = "Be precise and concise. Answer in Russian if the question is in Russian.",
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        search_recency_filter: str = "month",
    ) -> Dict[str, Any]:
        """
        Perplexity запрос через LangChain (ChatOpenAI-compatible).

        Важно: Perplexity API является OpenAI-compatible, но отдача `citations`
        может не прокидываться через LangChain-обёртку. В таком случае `citations`
        будут пустыми.
        """
        if not self.api_key:
            logger.error("Perplexity API key not configured", component="perplexity")
            return {"error": "Perplexity API key not configured", "success": False}

        use_model = model or self.model

        try:
            # Lazy import: dependency is optional at runtime for non-search flows.
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                api_key=self.api_key,
                model=use_model,
                base_url=self.BASE_URL,
                temperature=temperature,
                max_tokens=max_tokens,
                # Pass-through Perplexity params (best-effort)
                model_kwargs={"search_recency_filter": search_recency_filter},
            )

            msg = await llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=question)]
            )

            content = getattr(msg, "content", "") or ""
            citations = []

            # Best-effort extraction: some providers put extra fields here.
            additional = getattr(msg, "additional_kwargs", None) or {}
            if isinstance(additional, dict):
                citations = additional.get("citations", []) or []

            response_metadata = getattr(msg, "response_metadata", None) or {}
            if not citations and isinstance(response_metadata, dict):
                citations = response_metadata.get("citations", []) or []

            return {
                "success": True,
                "content": content,
                "citations": citations,
                "model": use_model,
                "raw_response": {"content": content},
                "cached": False,
                "integration": "langchain-openai",
            }

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(
                f"Perplexity LangChain request failed: {type(e).__name__}: {error_msg}",
                component="perplexity",
            )
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
            "integration": "httpx-direct",
            "cache_stats": self.get_cache_stats(),
        }

    @classmethod
    async def close_global(cls):
        if cls._instance:
            cls._instance._cache.clear()
            if cls._instance._client:
                await cls._instance._client.aclose()
            cls._instance._client = None
            cls._instance = None
