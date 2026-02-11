"""
Схемы запросов/ответов LLM для асинхронной обработки.

Поддерживает несколько LLM провайдеров с доставкой через webhook callback.
"""

import ipaddress
import socket
from enum import Enum
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator


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
    system_prompt: Optional[str] = Field(None, max_length=10000, description="Системный промпт (опционально)")
    provider: LLMProviderEnum = Field(
        default=LLMProviderEnum.OPENROUTER,
        description="LLM провайдер для использования",
    )
    callback_url: HttpUrl = Field(..., description="URL для отправки результатов POST запросом")
    callback_headers: Optional[Dict[str, str]] = Field(
        default=None, description="Заголовки для включения в callback запрос"
    )

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url_not_internal(cls, v: HttpUrl) -> HttpUrl:
        """Блокировка SSRF: запрет callback на внутренние адреса."""
        url_str = str(v)
        parsed = urlparse(url_str)
        hostname = parsed.hostname or ""

        # Блокировка Docker-хостнеймов внутренних сервисов
        blocked_hosts = {
            "localhost", "tarantool", "rabbitmq", "chroma", "chromadb",
            "prometheus", "alertmanager", "grafana", "tempo", "jayguard",
            "app", "worker", "mcp", "redis", "postgres", "mongodb",
        }
        if hostname.lower() in blocked_hosts:
            raise ValueError(f"callback_url не может указывать на внутренний сервис: {hostname}")

        # Блокировка приватных IP-адресов (RFC 1918, loopback, link-local)
        try:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, addr in resolved:
                ip = ipaddress.ip_address(addr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    raise ValueError(
                        f"callback_url не может указывать на приватный/локальный адрес: {addr[0]}"
                    )
        except socket.gaierror:
            # DNS-резолв не удался — разрешаем (будет ошибка при фактическом вызове)
            pass

        return v

    @field_validator("callback_headers")
    @classmethod
    def sanitize_callback_headers(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Удаление потенциально опасных заголовков из callback."""
        if not v:
            return v
        blocked_header_prefixes = ("x-auth", "cookie", "x-api-key", "x-admin")
        return {
            k: val for k, val in v.items()
            if not k.lower().startswith(blocked_header_prefixes)
        }

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
    estimated_time_seconds: Optional[int] = Field(None, description="Примерное время обработки")


class LLMCallbackPayload(BaseModel):
    """Payload, отправляемый на callback URL после обработки LLM."""

    request_id: str = Field(..., description="Оригинальный ID запроса")
    status: str = Field(..., description="Статус обработки: success или error")
    provider_used: str = Field(..., description="Провайдер, обработавший запрос")
    response: Optional[str] = Field(None, description="Текст ответа LLM")
    error: Optional[str] = Field(None, description="Сообщение об ошибке при неудаче")
    usage: Optional[Dict[str, int]] = Field(None, description="Статистика использования токенов")
    processing_time_ms: float = Field(..., description="Время обработки в миллисекундах")
    request_metadata: Optional[Dict[str, Any]] = Field(None, description="Оригинальные метаданные запроса")


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


class MaskTextRequest(BaseModel):
    """
    Запрос на маскирование PII данных в тексте.

    Используется для тестирования и preview маскирования перед отправкой в LLM.
    """

    text: str = Field(..., min_length=1, max_length=100000, description="Текст для маскирования")
    language: str = Field(default="ru", description="Язык текста (ru, en)")
    mask_level: str = Field(
        default="high",
        description="Уровень маскирования: low (только ИНН/ОГРН), medium (+ контакты), high (все PII)",
    )


class MaskTextResponse(BaseModel):
    """Ответ с замаскированным текстом и метаданными."""

    original_text: str = Field(..., description="Оригинальный текст")
    masked_text: str = Field(..., description="Текст с замаскированными PII данными")
    pii_detected: bool = Field(..., description="Обнаружены ли PII данные")
    pii_count: int = Field(..., description="Количество обнаруженных PII сущностей")
    detected_pii_types: list[str] = Field(..., description="Типы обнаруженных PII")
    replacements: list[Dict[str, Any]] = Field(..., description="Маппинг для размаскирования")


__all__ = [
    "LLMProviderEnum",
    "AsyncLLMRequest",
    "AsyncLLMAccepted",
    "LLMCallbackPayload",
    "LLMProviderStatus",
    "LLMProvidersResponse",
    "MaskTextRequest",
    "MaskTextResponse",
]
