from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.http_client import AsyncHttpClient, TimeoutConfig
from app.services.service_status import status_error, status_not_configured, status_ready
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

    def is_configured(self) -> bool:
        return bool(self.api_key)

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
            http_client = await AsyncHttpClient.get_instance()
            response = await http_client.request_with_resilience(
                method="POST",
                url=f"{self.BASE_URL}/chat/completions",
                service="openrouter",
                timeout_config=TimeoutConfig(connect=5.0, read=120.0, write=10.0, pool=5.0),
                headers=headers,
                json=payload,
            )

            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "success": True,
                "content": content,
                "model": data.get("model", self.model),
                "usage": data.get("usage", {}),
            }

        except Exception as e:
            # Keep legacy return shape (success/error/content).
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
            return status_not_configured(error="API key not configured", integration="openrouter")

        try:
            http_client = await AsyncHttpClient.get_instance()
            response = await http_client.request_with_resilience(
                method="GET",
                url=f"{self.BASE_URL}/models",
                service="openrouter",
                timeout_config=TimeoutConfig(connect=5.0, read=10.0, write=5.0, pool=5.0),
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            # If we got here, it's 2xx.
            _ = response.json()
            return status_ready(integration="openrouter", model=self.model)
        except Exception as e:
            return status_error(error=str(e), integration="openrouter", model=self.model)


_openrouter_client: Optional[OpenRouterClient] = None


def get_openrouter_client() -> OpenRouterClient:
    """Get singleton OpenRouter client instance."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = OpenRouterClient()
    return _openrouter_client
