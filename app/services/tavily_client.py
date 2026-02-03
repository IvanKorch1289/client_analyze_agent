import asyncio
import hashlib
import os
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from langchain_community.tools.tavily_search import TavilySearchResults

from app.config import settings
from app.utility.logging_client import logger

# Constants for content extraction
MAX_CONTENT_CHARS = 10000
MAX_URLS_TO_EXTRACT = 10
EXTRACTION_TIMEOUT = 15.0


class TavilyClient:
    _instance: Optional["TavilyClient"] = None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.tavily.api_key
        if self.api_key:
            os.environ["TAVILY_API_KEY"] = self.api_key
        # L1 кэш в памяти процесса (быстрый, но не разделяется между воркерами)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = settings.tavily.cache_ttl or 300
        # Коалесинг (аналогично Perplexity): один внешний вызов на cache_key
        self._inflight: Dict[str, asyncio.Future] = {}

    @classmethod
    def get_instance(cls) -> "TavilyClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_tool(
        self,
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = True,  # Changed: extract full content by default
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
        include_raw_content: bool = True,
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
        return f"tavily:{hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()}"

    async def search(
        self,
        query: str,
        search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "basic",
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = True,  # Changed: extract full content by default
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
        if use_cache:
            # 1) L1 cache
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                logger.info(f"Tavily cache hit (L1) for query: {query[:50]}", component="tavily")
                return cached

            # 2) L2 cache (Tarantool)
            if settings.tavily.cache_enabled:
                try:
                    from app.storage.tarantool import TarantoolClient

                    t = await TarantoolClient.get_instance()
                    repo = t.get_cache_repository()
                    l2 = await repo.get(cache_key)
                    if l2:
                        self._cache[cache_key] = l2
                        logger.info(
                            f"Tavily cache hit (L2/Tarantool) for query: {query[:50]}",
                            component="tavily",
                        )
                        return l2
                except Exception:
                    pass

            # 3) Coalescing
            inflight = self._inflight.get(cache_key)
            if inflight is not None:
                return await inflight

        try:
            if use_cache:
                loop = asyncio.get_event_loop()
                fut: asyncio.Future = loop.create_future()
                self._inflight[cache_key] = fut

            tool = self._get_tool(
                max_results=max_results,
                include_answer=include_answer,
                include_raw_content=include_raw_content,
            )

            loop = asyncio.get_event_loop()
            payload: Dict[str, Any] = {"query": query}
            if include_domains:
                payload["include_domains"] = include_domains
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains

            # `search_depth` is not guaranteed to be supported by all LangChain wrappers,
            # but if supported, it's safe to pass through.
            if search_depth:
                payload["search_depth"] = search_depth

            results = await loop.run_in_executor(None, tool.invoke, payload)

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
                        raw_content = item.get("raw_content", "")
                        formatted_results.append(
                            {
                                "title": item.get("title", ""),
                                "url": item.get("url", ""),
                                "content": content,
                                "raw_content": raw_content,  # Full page content
                                "snippet": content[:500] if content else "",
                                "score": item.get("score", 0),
                                "char_count": (len(raw_content) if raw_content else len(content)),
                            }
                        )
                    else:
                        formatted_results.append(
                            {
                                "content": str(item),
                                "url": "",
                                "snippet": str(item)[:500],
                                "char_count": len(str(item)),
                            }
                        )

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
                "integration": "langchain-community",
            }

            if use_cache:
                self._cache[cache_key] = {**response_data, "cached": True}
                # L2 запись в Tarantool (best-effort)
                if settings.tavily.cache_enabled:
                    try:
                        from app.storage.tarantool import TarantoolClient

                        t = await TarantoolClient.get_instance()
                        repo = t.get_cache_repository()
                        await repo.set_with_ttl(
                            cache_key,
                            {**response_data, "cached": True},
                            ttl=self._cache_ttl,
                            source="tavily",
                        )
                    except Exception:
                        pass

                inflight = self._inflight.pop(cache_key, None)
                if inflight is not None and not inflight.done():
                    inflight.set_result({**response_data, "cached": True})

            return response_data

        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(
                f"Tavily LangChain request failed: {type(e).__name__}: {error_msg}",
                component="tavily",
            )
            inflight = self._inflight.pop(cache_key, None) if use_cache else None
            if inflight is not None and not inflight.done():
                inflight.set_result({"success": False, "error": error_msg})

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

    async def extract_content(
        self,
        urls: List[str],
        max_chars_per_page: int = MAX_CONTENT_CHARS,
        timeout_per_url: float = EXTRACTION_TIMEOUT,
    ) -> List[Dict[str, Any]]:
        """
        Extract full content from a list of URLs.

        Similar to what Perplexity AI does when analyzing pages.
        Uses aiohttp for async fetching and BeautifulSoup for HTML parsing.

        Args:
            urls: List of URLs to extract content from
            max_chars_per_page: Maximum characters to extract per page
            timeout_per_url: Timeout in seconds for each URL

        Returns:
            List of extraction results with url, title, content, char_count, success
        """
        import aiohttp

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning(
                "BeautifulSoup not installed, skipping content extraction",
                component="tavily",
            )
            return []

        async def fetch_url(url: str) -> Dict[str, Any]:
            """Fetch and parse a single URL."""
            start_time = time.perf_counter()
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=timeout_per_url),
                        headers={
                            "User-Agent": "Mozilla/5.0 (compatible; ClientAnalyzer/1.0; +https://example.com/bot)",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                        },
                        allow_redirects=True,
                        ssl=False,  # Skip SSL verification for problematic sites
                    ) as response:
                        if response.status != 200:
                            return {
                                "url": url,
                                "success": False,
                                "error": f"HTTP {response.status}",
                                "elapsed_ms": round((time.perf_counter() - start_time) * 1000, 2),
                            }

                        html = await response.text()
                        soup = BeautifulSoup(html, "html.parser")

                        # Remove non-content elements
                        for tag in soup(
                            [
                                "script",
                                "style",
                                "nav",
                                "footer",
                                "header",
                                "aside",
                                "noscript",
                                "iframe",
                            ]
                        ):
                            tag.decompose()

                        # Extract title
                        title = ""
                        if soup.title and soup.title.string:
                            title = soup.title.string.strip()

                        # Extract main content text
                        text = soup.get_text(separator=" ", strip=True)
                        text = " ".join(text.split())  # Normalize whitespace

                        # Truncate if needed
                        full_length = len(text)
                        text = text[:max_chars_per_page]

                        return {
                            "url": url,
                            "title": title,
                            "content": text,
                            "full_content": text,  # Alias for compatibility
                            "char_count": full_length,
                            "truncated": full_length > max_chars_per_page,
                            "success": True,
                            "extracted_at": datetime.now().isoformat(),
                            "elapsed_ms": round((time.perf_counter() - start_time) * 1000, 2),
                        }

            except asyncio.TimeoutError:
                return {
                    "url": url,
                    "success": False,
                    "error": "Timeout",
                    "elapsed_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }
            except Exception as e:
                return {
                    "url": url,
                    "success": False,
                    "error": str(e)[:200],
                    "elapsed_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

        # Limit URLs and run in parallel
        urls_to_fetch = urls[:MAX_URLS_TO_EXTRACT]
        tasks = [fetch_url(url) for url in urls_to_fetch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter and log results
        extracted = []
        for result in results:
            if isinstance(result, dict):
                extracted.append(result)
            elif isinstance(result, Exception):
                extracted.append(
                    {
                        "url": "unknown",
                        "success": False,
                        "error": str(result)[:200],
                    }
                )

        success_count = sum(1 for r in extracted if r.get("success"))
        total_chars = sum(r.get("char_count", 0) for r in extracted if r.get("success"))

        logger.info(
            f"Content extraction completed: {success_count}/{len(urls_to_fetch)} URLs, {total_chars} chars",
            component="tavily",
        )

        return extracted

    async def search_with_extraction(
        self,
        query: str,
        max_results: int = 10,
        extract_top_n: int = 5,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Perform search and automatically extract content from top results.

        Combines search() and extract_content() for convenience.

        Args:
            query: Search query
            max_results: Maximum search results
            extract_top_n: Number of top results to extract full content from
            **kwargs: Additional arguments for search()

        Returns:
            Search result with additional 'extracted_content' field
        """
        # 1. Perform search
        search_result = await self.search(
            query=query,
            max_results=max_results,
            include_raw_content=True,
            **kwargs,
        )

        if not search_result.get("success"):
            return search_result

        # 2. Extract content from top URLs (if raw_content not available)
        results = search_result.get("results", [])
        urls_to_extract = []

        for r in results[:extract_top_n]:
            url = r.get("url")
            raw_content = r.get("raw_content", "")
            # Only extract if raw_content is missing or too short
            if url and (not raw_content or len(raw_content) < 500):
                urls_to_extract.append(url)

        if urls_to_extract:
            extracted = await self.extract_content(urls_to_extract)
            search_result["extracted_content"] = extracted
            search_result["total_extracted_chars"] = sum(e.get("char_count", 0) for e in extracted if e.get("success"))
        else:
            search_result["extracted_content"] = []
            search_result["total_extracted_chars"] = sum(r.get("char_count", 0) for r in results[:extract_top_n])

        return search_result

    def clear_cache(self):
        """
        Очистка L1 кэша процесса.

        Примечание: L2 кэш в Tarantool очищается через админ-эндпоинт `/utility/cache/prefix/tavily:`.
        """
        self._cache.clear()
        logger.info("Tavily cache cleared (L1)", component="tavily")

    def get_cache_stats(self) -> Dict[str, int]:
        return {
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl,
        }

    async def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured(),
            # Additive: normalize to the same minimal shape as other clients.
            "available": self.is_configured(),
            "status": "ready" if self.is_configured() else "not_configured",
            "integration": "langchain-community",
            "cache_stats": self.get_cache_stats(),
        }

    async def healthcheck(self, timeout_s: float = 8.0) -> Dict[str, Any]:
        """
        Реальная проверка доступности сервиса (не только конфигурации):
        выполняет простой поисковый запрос и проверяет, что есть результаты/ответ.
        """
        import time

        if not self.is_configured():
            return {
                "configured": False,
                "available": False,
                "status": "not_configured",
                "error": "Tavily API key not configured",
                "integration": "langchain-community",
            }

        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.search(
                    query="site:example.com example",
                    search_depth="basic",
                    max_results=3,
                    include_answer=True,
                    use_cache=False,
                ),
                timeout=timeout_s,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            ok = bool(result.get("success")) and (bool(result.get("answer")) or bool(result.get("results")))
            return {
                "configured": True,
                "available": ok,
                "status": "ready" if ok else "error",
                "latency_ms": round(latency_ms, 2),
                "error": None if ok else (result.get("error") or "Unexpected response"),
                "integration": "langchain-community",
            }
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "configured": True,
                "available": False,
                "status": "error",
                "latency_ms": round(latency_ms, 2),
                "error": str(e) or type(e).__name__,
                "integration": "langchain-community",
            }

    @classmethod
    async def close_global(cls):
        if cls._instance:
            cls._instance._cache.clear()
            cls._instance = None
