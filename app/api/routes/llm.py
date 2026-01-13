"""
LLM API endpoints for async processing with webhook callback.

Provides:
- POST /llm/async - Submit async LLM request
- GET /llm/providers - List available providers
"""

import asyncio
import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.schemas.llm import (
    AsyncLLMAccepted,
    AsyncLLMRequest,
    LLMCallbackPayload,
    LLMProviderEnum,
    LLMProvidersResponse,
)
from app.utility.logging_client import logger

llm_router = APIRouter(prefix="/llm", tags=["LLM"])


def _generate_request_id() -> str:
    """Generate unique request ID."""
    return f"llm_{uuid.uuid4().hex[:16]}_{int(time.time())}"


def _is_provider_available(provider: LLMProviderEnum) -> bool:
    """Check if a provider is configured and available."""
    provider_configs = {
        LLMProviderEnum.OPENROUTER: bool(settings.openrouter.api_key),
        LLMProviderEnum.HUGGINGFACE: bool(settings.huggingface.api_key),
        LLMProviderEnum.GIGACHAT: bool(settings.gigachat.api_key),
        LLMProviderEnum.YANDEXGPT: bool(settings.yandexgpt.api_key),
        LLMProviderEnum.OPENLLAMA: True,  # Local, always "available" if requested
    }
    return provider_configs.get(provider, False)


async def _process_llm_request_background(
    request_id: str,
    data: AsyncLLMRequest,
) -> None:
    """
    Process LLM request in background and send callback.

    Used as fallback when RabbitMQ is not enabled.
    """
    import httpx

    start_time = time.perf_counter()
    callback_payload: Dict[str, Any]

    try:
        from app.agents.llm_manager import LLMProvider, get_llm_manager

        manager = get_llm_manager()

        # Map enum to LLMProvider
        provider_map = {
            LLMProviderEnum.OPENROUTER: LLMProvider.OPENROUTER,
            LLMProviderEnum.HUGGINGFACE: LLMProvider.HUGGINGFACE,
            LLMProviderEnum.GIGACHAT: LLMProvider.GIGACHAT,
            LLMProviderEnum.YANDEXGPT: LLMProvider.YANDEXGPT,
            LLMProviderEnum.OPENLLAMA: LLMProvider.OPENROUTER,  # Fallback
        }

        llm_provider = provider_map.get(data.provider, LLMProvider.OPENROUTER)

        # Build full prompt
        full_prompt = data.prompt
        if data.system_prompt:
            full_prompt = f"{data.system_prompt}\n\n{data.prompt}"

        # Call LLM with specific provider
        response = await manager.ainvoke_with_provider(
            prompt=full_prompt,
            provider=llm_provider,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )

        processing_time = (time.perf_counter() - start_time) * 1000

        callback_payload = LLMCallbackPayload(
            request_id=request_id,
            status="success",
            provider_used=data.provider.value,
            response=response,
            processing_time_ms=processing_time,
            request_metadata=data.request_metadata,
        ).model_dump()

        logger.structured(
            "info",
            "async_llm_completed",
            request_id=request_id,
            provider=data.provider.value,
            processing_time_ms=round(processing_time, 2),
        )

    except Exception as e:
        processing_time = (time.perf_counter() - start_time) * 1000

        callback_payload = LLMCallbackPayload(
            request_id=request_id,
            status="error",
            provider_used=data.provider.value,
            error=str(e),
            processing_time_ms=processing_time,
            request_metadata=data.request_metadata,
        ).model_dump()

        logger.error(
            f"Async LLM request failed: {e}",
            component="llm_api",
            request_id=request_id,
        )

    # Send callback
    try:
        headers = dict(data.callback_headers) if data.callback_headers else {}
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            callback_response = await client.post(
                str(data.callback_url),
                json=callback_payload,
                headers=headers,
                timeout=30.0,
            )
            logger.info(
                f"Callback sent for {request_id}: status {callback_response.status_code}",
                component="llm_api",
            )
    except Exception as e:
        logger.error(
            f"Callback failed for {request_id}: {e}",
            component="llm_api",
        )


@llm_router.post("/async", response_model=AsyncLLMAccepted, status_code=202)
async def submit_async_llm_request(
    request: Request,
    data: AsyncLLMRequest,
) -> AsyncLLMAccepted:
    """
    Submit async LLM request with webhook callback.

    Returns 202 Accepted immediately. Result is delivered via callback URL.

    The request is either:
    1. Published to RabbitMQ queue for worker processing (if enabled)
    2. Processed in background task (fallback)
    """
    request_id = _generate_request_id()

    # Validate provider availability
    if not _is_provider_available(data.provider):
        raise HTTPException(
            status_code=400,
            detail=f"Provider {data.provider.value} is not configured",
        )

    # Queue message for processing
    if settings.queue.enabled:
        try:
            from app.messaging.publisher import get_rabbit_publisher

            publisher = await get_rabbit_publisher()
            await publisher.publish_async_llm_request(
                request_id=request_id,
                prompt=data.prompt,
                system_prompt=data.system_prompt,
                provider=data.provider.value,
                callback_url=str(data.callback_url),
                callback_headers=data.callback_headers,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
                request_metadata=data.request_metadata,
            )
            logger.structured(
                "info",
                "async_llm_queued",
                request_id=request_id,
                provider=data.provider.value,
                callback_url=str(data.callback_url),
            )
        except Exception as e:
            logger.warning(
                f"Queue publish failed, falling back to background task: {e}",
                component="llm_api",
            )
            # Fallback to background task
            asyncio.create_task(_process_llm_request_background(request_id, data))
    else:
        # Process in background task
        asyncio.create_task(_process_llm_request_background(request_id, data))
        logger.structured(
            "info",
            "async_llm_background",
            request_id=request_id,
            provider=data.provider.value,
            callback_url=str(data.callback_url),
        )

    return AsyncLLMAccepted(
        request_id=request_id,
        estimated_time_seconds=30,
    )


@llm_router.get("/providers", response_model=LLMProvidersResponse)
async def list_llm_providers() -> LLMProvidersResponse:
    """
    List available LLM providers and their status.

    Returns all supported providers and whether they are configured.
    """
    from app.agents.llm_manager import get_llm_manager

    manager = get_llm_manager()

    providers = [p.value for p in LLMProviderEnum]
    status = manager.get_provider_status()

    # Add OpenLlama status (always potentially available as internal)
    status["openllama"] = True

    return LLMProvidersResponse(
        providers=providers,
        status=status,
    )


__all__ = ["llm_router"]
