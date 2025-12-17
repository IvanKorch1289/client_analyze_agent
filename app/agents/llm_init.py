"""
LLM initialization module.
Provides both sync LangChain-compatible LLM and async OpenRouter client.
"""

from typing import Any, Dict, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM

from app.services.openrouter_client import OpenRouterClient, get_openrouter_client


class OpenRouterLLM(LLM):
    """
    LangChain-compatible LLM wrapper for OpenRouter API.
    Uses synchronous httpx calls for compatibility with LangChain.
    """

    model: str = "anthropic/claude-3.5-sonnet"
    temperature: float = 0.1
    max_tokens: int = 4096
    api_key: Optional[str] = None

    def __init__(self, **data: Any):
        super().__init__(**data)
        from app.settings import settings
        if not self.api_key:
            self.api_key = settings.openrouter_api_key
        if self.model == "anthropic/claude-3.5-sonnet" and settings.openrouter_model:
            self.model = settings.openrouter_model

    @property
    def _llm_type(self) -> str:
        return "openrouter"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Synchronous call to OpenRouter API."""
        import os

        import httpx

        api_key = self.api_key or os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise ValueError("OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://replit.com",
            "X-Title": "Client Analysis Agent",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if stop:
            payload["stop"] = stop

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return content
                else:
                    raise ValueError(f"OpenRouter API returned {response.status_code}: {response.text}")

        except httpx.TimeoutException as e:
            raise ValueError(f"OpenRouter request timeout: {e}")
        except Exception as e:
            raise ValueError(f"OpenRouter request failed: {e}")


llm = OpenRouterLLM()

openrouter_client = get_openrouter_client()
