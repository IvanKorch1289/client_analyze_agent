import os
from typing import Any, Dict, List, Optional

import httpx

from app.advanced_funcs.logging_client import logger


class TavilyClient:
    """Client for Tavily Search API."""

    BASE_URL = "https://api.tavily.com"

    _instance: Optional["TavilyClient"] = None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_TOKEN")
        self._client: Optional[httpx.AsyncClient] = None

    @classmethod
    def get_instance(cls) -> "TavilyClient":
        """Singleton pattern for client."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
            )
        return self._client

    def is_configured(self) -> bool:
        """Check if API key is available."""
        return bool(self.api_key)

    async def search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Search the web using Tavily API.
        
        Args:
            query: Search query
            search_depth: "basic" or "advanced" (more thorough but slower)
            max_results: Maximum number of results (1-10)
            include_answer: Include AI-generated answer
            include_raw_content: Include raw HTML content
            include_domains: Only search these domains
            exclude_domains: Exclude these domains
        
        Returns:
            Dict with search results
        """
        if not self.api_key:
            logger.error("Tavily API key not configured", component="tavily")
            return {
                "error": "Tavily API key not configured",
                "success": False
            }

        client = await self._get_client()

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
            response = await client.post(
                f"{self.BASE_URL}/search",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(
                f"Tavily search completed: {len(result.get('results', []))} results",
                component="tavily"
            )
            
            return {
                "success": True,
                "answer": result.get("answer", ""),
                "results": result.get("results", []),
                "query": query,
                "response_time": result.get("response_time", 0),
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Tavily API error: {e.response.status_code} - {e.response.text}",
                component="tavily"
            )
            return {
                "success": False,
                "error": f"API error: {e.response.status_code}"
            }
        except Exception as e:
            logger.error(f"Tavily request failed: {e}", component="tavily")
            return {
                "success": False,
                "error": str(e)
            }

    async def close(self):
        """Close the client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @classmethod
    async def close_global(cls):
        """Close the global instance."""
        if cls._instance:
            await cls._instance.close()
            cls._instance = None
