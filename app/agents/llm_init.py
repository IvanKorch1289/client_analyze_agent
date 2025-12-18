"""
LLM initialization module.
Provides both sync LangChain-compatible LLM and async OpenRouter client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM

from app.config import settings
from app.services.openrouter_client import get_openrouter_client
from app.utility.logging_client import logger


@dataclass(frozen=True)
class _ProviderResult:
    provider: str
    content: str


class _OpenRouterProvider:
    name = "openrouter"

    def __init__(self):
        self.api_key = settings.openrouter.api_key
        self.model = settings.openrouter.model or "anthropic/claude-3.5-sonnet"
        self.temperature = settings.openrouter.temperature
        self.max_tokens = settings.openrouter.max_tokens or 4096

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, stop: Optional[List[str]] = None) -> _ProviderResult:
        import httpx

        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://replit.com",
            "X-Title": "Client Analysis Agent",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stop:
            payload["stop"] = stop

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise ValueError(f"OpenRouter API returned {resp.status_code}: {resp.text}")
            data = resp.json()
            content = (
                data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            )
            return _ProviderResult(provider=self.name, content=content)


class FallbackLLM(LLM):
    """
    LangChain-compatible LLM using OpenRouter.
    """

    def __init__(self, **data: Any):
        super().__init__(**data)
        self._providers = [
            _OpenRouterProvider(),
        ]

    @property
    def _llm_type(self) -> str:
        return "fallback_llm"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        _run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Synchronous call with provider fallback."""
        errors: List[str] = []
        for provider in self._providers:
            if not provider.is_configured():
                errors.append(f"{provider.name}:not_configured")
                continue
            try:
                result = provider.generate(prompt=prompt, stop=stop)
                logger.structured(
                    "info",
                    "llm_provider_selected",
                    component="llm",
                    provider=result.provider,
                )
                return result.content
            except Exception as e:
                err = str(e) or type(e).__name__
                errors.append(f"{provider.name}:{err}")
                logger.structured(
                    "warning",
                    "llm_provider_failed",
                    component="llm",
                    provider=provider.name,
                    error=err,
                )
                continue

        raise ValueError(f"All LLM providers failed: {errors}")


llm = FallbackLLM()

openrouter_client = get_openrouter_client()
