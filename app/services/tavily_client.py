import asyncio
import hashlib
import os
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults

from app.utility.logging_client import logger

load_dotenv('.env')


class TavilyClient:
    _instance: Optional["TavilyClient"] = None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY") or os.getenv("TAVILY_TOKEN")
        if self.api_key:
            os.environ["TAVILY_API_KEY"] = self.api_key
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300

    @classmethod
    def get_instance(cls) -> "TavilyClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_tool(
        self,
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = False,
    ) -> TavilySearchResults:
        return TavilySearchResults(
            max_results=max_results,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
        )

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
        search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "basic",
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

        try:
            tool = self._get_tool(
                max_results=max_results,
                include_answer=include_answer,
                include_raw_content=include_raw_content,
            )

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, tool.invoke, {"query": query})

            answer = ""
            if isinstance(results, str):
                import json
                try:
                    results = json.loads(results)
                except json.JSONDecodeError:
                    results = [{"content": results, "url": ""}]

            # LangChain tool output can be either:
            # - list[dict] (results only)
            # - dict {"answer": str, "results": list[dict], ...}
            if isinstance(results, dict):
                answer = results.get("answer", "") or ""
                results = results.get("results", []) or []

            formatted_results = []
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        content = item.get("content", "")
                        formatted_results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "content": content,
                            "snippet": content[:500] if content else "",
                            "score": item.get("score", 0),
                        })
                    else:
                        formatted_results.append({"content": str(item), "url": "", "snippet": str(item)[:500]})

            logger.info(
                f"Tavily LangChain search completed: {len(formatted_results)} results",
                component="tavily",
            )

            response_data = {
                "success": True,
                "answer": answer,
                "results": formatted_results,
                "query": query,
                "response_time": 0,
                "cached": False,
            }

            if use_cache:
                self._cache[cache_key] = {**response_data, "cached": True}

            return response_data

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(
                f"Tavily LangChain request failed: {type(e).__name__}: {error_msg}",
                component="tavily",
            )
            
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                return {
                    "success": False,
                    "error": "Tavily request timeout - сервис не ответил вовремя",
                    "timeout": True,
                }
            elif "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg.lower():
                return {"success": False, "error": "Invalid Tavily API key"}
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                return {"success": False, "error": "Tavily rate limit exceeded"}
            
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
        return {
            "configured": self.is_configured(),
            "status": "ready" if self.is_configured() else "not_configured",
            "integration": "langchain-community",
            "cache_stats": self.get_cache_stats(),
        }

    @classmethod
    async def close_global(cls):
        if cls._instance:
            cls._instance._cache.clear()
            cls._instance = None
