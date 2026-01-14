"""
Схемы запросов/ответов LLM для асинхронной обработки.

Поддерживает несколько LLM провайдеров с доставкой через webhook callback.
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, HttpUrl


class LLMProviderEnum(str, Enum):
    """Поддерживаемые LLM провайдеры."""

    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    GIGACHAT = "gigachat"
    YANDEXGPT = "yandexgpt"
    OPENLLAMA = "openllama"  # Внутренний LLM через локальное развёртывание


class AsyncLLMRequest(BaseModel):
    """
    Запрос на асинхронную обработку LLM.

    Запрос немедленно ставится в очередь, результат доставляется
    через webhook callback на указанный URL.
    """

    prompt: str = Field(..., min_length=1, max_length=50000, description="Пользовательский промпт")
    system_prompt: Optional[str] = Field(
        None, max_length=10000, description="Системный промпт (опционально)"
    )
    provider: LLMProviderEnum = Field(
        default=LLMProviderEnum.OPENROUTER, description="LLM провайдер для использования"
    )
    callback_url: HttpUrl = Field(..., description="URL для отправки результатов POST запросом")
    callback_headers: Optional[Dict[str, str]] = Field(
        default=None, description="Заголовки для включения в callback запрос"
    )

    # Параметры LLM
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Температура семплирования")
    max_tokens: int = Field(default=4096, ge=1, le=32000, description="Максимальное количество токенов")

    # Метаданные для отслеживания
    request_metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Пользовательские метаданные, возвращаемые с callback"
    )


class AsyncLLMAccepted(BaseModel):
    """Ответ при принятии асинхронного LLM запроса."""

    status: str = "accepted"
    request_id: str = Field(..., description="Уникальный ID запроса для отслеживания")
    message: str = "Запрос поставлен в очередь на обработку"
    estimated_time_seconds: Optional[int] = Field(
        None, description="Примерное время обработки"
    )


class LLMCallbackPayload(BaseModel):
    """Payload, отправляемый на callback URL после обработки LLM."""

    request_id: str = Field(..., description="Оригинальный ID запроса")
    status: str = Field(..., description="Статус обработки: success или error")
    provider_used: str = Field(..., description="Провайдер, обработавший запрос")
    response: Optional[str] = Field(None, description="Текст ответа LLM")
    error: Optional[str] = Field(None, description="Сообщение об ошибке при неудаче")
    usage: Optional[Dict[str, int]] = Field(None, description="Статистика использования токенов")
    processing_time_ms: float = Field(..., description="Время обработки в миллисекундах")
    request_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Оригинальные метаданные запроса"
    )


class LLMProviderStatus(BaseModel):
    """Статус LLM провайдера."""

    provider: str
    available: bool
    model: Optional[str] = None
    error: Optional[str] = None


class LLMProvidersResponse(BaseModel):
    """Ответ со списком доступных LLM провайдеров."""

    providers: list[str] = Field(..., description="Список имён провайдеров")
    status: Dict[str, bool] = Field(..., description="Статус доступности провайдеров")


__all__ = [
    "LLMProviderEnum",
    "AsyncLLMRequest",
    "AsyncLLMAccepted",
    "LLMCallbackPayload",
    "LLMProviderStatus",
    "LLMProvidersResponse",
]
