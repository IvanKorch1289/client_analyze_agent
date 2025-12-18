import asyncio
import hashlib
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from app.utility.logging_client import logger

load_dotenv(".env")


class PerplexityClient:
    """
    Perplexity client via LangChain (OpenAI-compatible).

    Важное требование: реальный вызов Perplexity выполняется через LangChain,
    без "прямого httpx" в рабочем коде.
    """

    DEFAULT_MODEL = "sonar-pro"
    BASE_URL = "https://api.perplexity.ai"

    _instance: Optional["PerplexityClient"] = None

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.model = model or os.getenv("PERPLEXITY_MODEL", self.DEFAULT_MODEL)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl_s = 300

    @classmethod
    def get_instance(cls) -> "PerplexityClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_cache_key(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        search_recency_filter: str,
    ) -> str:
        key_str = f"{messages}:{model}:{temperature}:{max_tokens}:{search_recency_filter}"
        return (
            f"perplexity:{hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()}"
        )

    def _cache_get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cached = self._cache.get(cache_key)
        if not cached:
            return None
        created_at = cached.get("_created_at", 0.0)
        if created_at and (time.time() - float(created_at)) > self._cache_ttl_s:
            self._cache.pop(cache_key, None)
            return None
        return cached

    def _cache_set(self, cache_key: str, value: Dict[str, Any]) -> None:
        self._cache[cache_key] = {**value, "_created_at": time.time()}

    @staticmethod
    def _to_lc_messages(messages: List[Dict[str, str]]) -> Tuple[list, list]:
        errors = []
        lc_messages = []

        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        for msg in messages:
            if not isinstance(msg, dict):
                errors.append(f"invalid_message:{type(msg).__name__}")
                continue
            role = (msg.get("role") or "").strip()
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                errors.append(f"unsupported_role:{role or 'missing'}")
        return lc_messages, errors

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
            return {"success": False, "error": "Perplexity API key not configured"}

        use_model = model or self.model

        cache_key = self._get_cache_key(
            messages=messages,
            model=use_model,
            temperature=temperature,
            max_tokens=max_tokens,
            search_recency_filter=search_recency_filter,
        )
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                logger.info("Perplexity cache hit", component="perplexity")
                return cached

        try:
            from langchain_openai import ChatOpenAI

            lc_messages, conversion_errors = self._to_lc_messages(messages)
            if conversion_errors:
                logger.warning(
                    f"Perplexity message conversion issues: {conversion_errors}",
                    component="perplexity",
                )

            llm = ChatOpenAI(
                api_key=self.api_key,
                model=use_model,
                base_url=self.BASE_URL,
                temperature=temperature,
                max_tokens=max_tokens,
                model_kwargs={"search_recency_filter": search_recency_filter},
            )

            msg = await llm.ainvoke(lc_messages)
            content = getattr(msg, "content", "") or ""

            citations: List[str] = []
            additional = getattr(msg, "additional_kwargs", None) or {}
            if isinstance(additional, dict):
                citations = additional.get("citations", []) or []

            response_metadata = getattr(msg, "response_metadata", None) or {}
            if not citations and isinstance(response_metadata, dict):
                citations = response_metadata.get("citations", []) or []

            response_data = {
                "success": True,
                "content": content,
                "citations": citations,
                "model": use_model,
                "raw_response": {"content": content},
                "cached": False,
                "integration": "langchain-openai",
            }

            if use_cache:
                self._cache_set(cache_key, {**response_data, "cached": True})

            return response_data

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(
                f"Perplexity LangChain request failed: {type(e).__name__}: {error_msg}",
                component="perplexity",
            )
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

    async def ask_langchain(self, *args, **kwargs) -> Dict[str, Any]:
        """Back-compat alias: теперь Perplexity работает только через LangChain."""
        return await self.ask(*args, **kwargs)

    async def ask_with_fallback(
        self,
        question: str,
        fallback_handler: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        result = await self.ask(question, **kwargs)
        if not result.get("success") and fallback_handler:
            return await fallback_handler(question, **kwargs)
        return result

    async def healthcheck(self, timeout_s: float = 8.0) -> Dict[str, Any]:
        """
        Реальная проверка доступности сервиса: тестовый запрос и проверка результата.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "available": False,
                "status": "not_configured",
                "error": "Perplexity API key not configured",
            }

        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.ask(
                    question="Ответь строго одним словом: OK",
                    system_prompt="Ты тест доступности. Отвечай строго 'OK'.",
                    temperature=0,
                    max_tokens=8,
                    use_cache=False,
                ),
                timeout=timeout_s,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            ok = bool(result.get("success")) and "OK" in (result.get("content") or "")
            return {
                "configured": True,
                "available": ok,
                "status": "ready" if ok else "error",
                "latency_ms": round(latency_ms, 2),
                "model": result.get("model", self.model),
                "error": None if ok else (result.get("error") or "Unexpected response"),
                "integration": result.get("integration", "langchain-openai"),
            }
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "configured": True,
                "available": False,
                "status": "error",
                "latency_ms": round(latency_ms, 2),
                "model": self.model,
                "error": str(e) or type(e).__name__,
                "integration": "langchain-openai",
            }

    def clear_cache(self) -> None:
        self._cache.clear()
        logger.info("Perplexity cache cleared", component="perplexity")

    def get_cache_stats(self) -> Dict[str, int]:
        return {"cache_size": len(self._cache), "cache_ttl": self._cache_ttl_s}

    async def get_status(self) -> Dict[str, Any]:
        # Status != healthcheck; does not call external service.
        return {
            "configured": self.is_configured(),
            "model": self.model,
            "status": "ready" if self.is_configured() else "not_configured",
            "integration": "langchain-openai",
            "cache_stats": self.get_cache_stats(),
        }

    @classmethod
    async def close_global(cls):
        if cls._instance:
            cls._instance._cache.clear()
            cls._instance = None
