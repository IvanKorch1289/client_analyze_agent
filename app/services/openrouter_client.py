from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.utility.logging_client import logger


class OpenRouterClient:
    """
    Client for OpenRouter API - provides access to multiple LLM models.
    Uses httpx for HTTP requests.
    """

    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key or settings.openrouter.api_key
        self.model = model or settings.openrouter.model or self.DEFAULT_MODEL
        self.temperature = temperature or settings.openrouter.temperature
        self.max_tokens = max_tokens or settings.openrouter.max_tokens

        if not self.api_key:
            logger.warning(
                "[OPENROUTER] API key not configured",
                component="openrouter"
            )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request to OpenRouter.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Dict with response content and metadata
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "OpenRouter API key not configured",
                "content": "",
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://replit.com",
            "X-Title": "Client Analysis Agent",
        }

        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {
                        "success": True,
                        "content": content,
                        "model": data.get("model", self.model),
                        "usage": data.get("usage", {}),
                    }
                else:
                    error_msg = response.text
                    logger.error(
                        f"[OPENROUTER] API error: {response.status_code} - {error_msg}",
                        component="openrouter"
                    )
                    return {
                        "success": False,
                        "error": f"API error: {response.status_code}",
                        "content": "",
                    }

        except httpx.TimeoutException:
            logger.error("[OPENROUTER] Request timeout", component="openrouter")
            return {
                "success": False,
                "error": "Request timeout",
                "content": "",
            }
        except Exception as e:
            logger.error(f"[OPENROUTER] Request failed: {e}", component="openrouter")
            return {
                "success": False,
                "error": str(e),
                "content": "",
            }

    async def analyze_text(self, text: str, prompt: str) -> Dict[str, Any]:
        """
        Analyze text using the LLM.

        Args:
            text: Text to analyze
            prompt: Analysis instructions

        Returns:
            Analysis result
        """
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]
        return await self.chat(messages)

    async def check_status(self) -> Dict[str, Any]:
        """Check OpenRouter API status."""
        if not self.api_key:
            return {
                "available": False,
                "error": "API key not configured",
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )

                if response.status_code == 200:
                    return {
                        "available": True,
                        "model": self.model,
                    }
                else:
                    return {
                        "available": False,
                        "error": f"API error: {response.status_code}",
                    }

        except Exception as e:
            return {
                "available": False,
                "error": str(e),
            }


_openrouter_client: Optional[OpenRouterClient] = None


def get_openrouter_client() -> OpenRouterClient:
    """Get singleton OpenRouter client instance."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = OpenRouterClient()
    return _openrouter_client
