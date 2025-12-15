import os
from typing import Any, Dict, List, Optional

import httpx

from app.advanced_funcs.logging_client import logger


class PerplexityClient:
    """Client for Perplexity AI API."""

    BASE_URL = "https://api.perplexity.ai/chat/completions"
    DEFAULT_MODEL = "llama-3.1-sonar-small-128k-online"

    _instance: Optional["PerplexityClient"] = None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self._client: Optional[httpx.AsyncClient] = None

    @classmethod
    def get_instance(cls) -> "PerplexityClient":
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

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        search_recency_filter: str = "month",
    ) -> Dict[str, Any]:
        """
        Send a chat request to Perplexity API.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (default: llama-3.1-sonar-small-128k-online)
            temperature: Temperature for generation (0.0 - 1.0)
            max_tokens: Maximum tokens in response
            search_recency_filter: Filter for search results (day, week, month, year)
        
        Returns:
            API response dict
        """
        if not self.api_key:
            logger.error("Perplexity API key not configured", component="perplexity")
            return {
                "error": "Perplexity API key not configured",
                "success": False
            }

        client = await self._get_client()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.9,
            "return_images": False,
            "return_related_questions": False,
            "search_recency_filter": search_recency_filter,
            "stream": False,
            "presence_penalty": 0,
            "frequency_penalty": 1
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            response = await client.post(
                self.BASE_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(
                f"Perplexity response received, model: {model}",
                component="perplexity"
            )
            
            return {
                "success": True,
                "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "citations": result.get("citations", []),
                "model": result.get("model"),
                "usage": result.get("usage", {}),
                "raw_response": result
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Perplexity API error: {e.response.status_code} - {e.response.text}",
                component="perplexity"
            )
            return {
                "success": False,
                "error": f"API error: {e.response.status_code}"
            }
        except Exception as e:
            logger.error(f"Perplexity request failed: {e}", component="perplexity")
            return {
                "success": False,
                "error": str(e)
            }

    async def ask(
        self,
        question: str,
        system_prompt: str = "Be precise and concise. Answer in Russian if the question is in Russian.",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Simple interface to ask a question.
        
        Args:
            question: The question to ask
            system_prompt: System prompt for context
            **kwargs: Additional parameters passed to chat()
        
        Returns:
            API response dict
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ]
        return await self.chat(messages, **kwargs)

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
