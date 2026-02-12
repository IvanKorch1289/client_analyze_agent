"""
LLM Audit Logging Module

Логирует все запросы и ответы LLM для:
- Compliance и аудита (152-ФЗ)
- Отладки и анализа качества
- Cost tracking и оптимизации
- Security monitoring (PII leakage detection)
"""

import hashlib
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.shared.toolkit.logging import logger

# Lazy imports
_audit_storage = None

# Regex для определения PII маркеров вида [ENTITY_TYPE_N], например [INN_1], [CLIENT_NAME_2]
_PII_MARKER_PATTERN = re.compile(r"\[([A-Z_]+)_\d+\]")


def detect_pii_markers(text: str) -> Tuple[bool, List[str]]:
    """
    Определяет наличие PII маркеров в тексте.

    PII маркеры создаются модулем pii_protection при маскировании
    персональных данных и имеют вид [ENTITY_TYPE_N], например:
    - [INN_1], [INN_2] - ИНН
    - [CLIENT_NAME_1] - ФИО клиента
    - [PHONE_1] - телефон

    Args:
        text: Текст для проверки

    Returns:
        Tuple[bool, List[str]]: (обнаружены ли маркеры, список типов PII)
    """
    if not text:
        return False, []

    matches = _PII_MARKER_PATTERN.findall(text)
    if not matches:
        return False, []

    # Уникальные типы PII (без номеров)
    pii_types = sorted(set(matches))
    return True, pii_types


class PrivacyMode(str, Enum):
    """Режимы приватности для логирования."""

    FULL = "full"  # Полное логирование (dev/debug)
    HASH_ONLY = "hash_only"  # Только хэши (production default)
    MINIMAL = "minimal"  # Только метаданные


@dataclass
class LLMAuditRecord:
    """Запись аудита LLM вызова."""

    # Временные метки
    timestamp: str  # ISO format
    duration_ms: int  # Время выполнения

    # Идентификация
    request_id: str  # Уникальный ID запроса
    provider: str  # openrouter, huggingface, gigachat, yandex
    model: str  # Название модели
    operation: str  # generate_text, generate_json, cascade, etc.

    # Приватность
    privacy_mode: str  # full, hash_only, minimal
    pii_detected: bool  # Обнаружена ли PII в prompt
    pii_types: List[str]  # Типы PII если обнаружена

    # Контент (зависит от privacy_mode)
    prompt_hash: str  # SHA256 hash промпта (всегда)
    prompt_text: Optional[str]  # Полный текст (только в FULL mode)
    response_hash: str  # SHA256 hash ответа (всегда)
    response_text: Optional[str]  # Полный текст (только в FULL mode)

    # Метаданные
    prompt_tokens: Optional[int]  # Количество токенов в промпте
    response_tokens: Optional[int]  # Количество токенов в ответе
    total_tokens: Optional[int]  # Всего токенов
    temperature: Optional[float]  # Температура генерации
    max_tokens: Optional[int]  # Максимум токенов

    # Статус
    success: bool  # Успешно ли выполнен запрос
    error: Optional[str]  # Текст ошибки если есть
    fallback_used: bool  # Был ли использован fallback provider

    # Дополнительная информация
    metadata: Dict[str, Any]  # Произвольные метаданные


@dataclass
class LLMCallParams:
    """
    Parameter object для log_llm_call.

    Группирует 17 параметров вызова для удобной передачи:
        params = LLMCallParams(provider="openrouter", model="claude-3.5", ...)
        await audit_logger.log_llm_call(**asdict(params))
    """

    provider: str
    model: str
    operation: str
    prompt: str
    response: Optional[str]
    duration_ms: int
    success: bool
    error: Optional[str] = None
    pii_detected: bool = False
    pii_types: Optional[List[str]] = None
    prompt_tokens: Optional[int] = None
    response_tokens: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    fallback_used: bool = False
    metadata: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


class LLMAuditLogger:
    """
    Логгер аудита LLM вызовов.

    Сохраняет записи в Tarantool persistent space для долгосрочного хранения.
    Поддерживает различные режимы приватности.
    """

    def __init__(self, privacy_mode: PrivacyMode = PrivacyMode.HASH_ONLY):
        """
        Args:
            privacy_mode: Режим приватности (по умолчанию hash_only для production)
        """
        self.privacy_mode = privacy_mode
        self._storage = None

    async def _get_storage(self):
        """Lazy initialization Tarantool storage."""
        if self._storage is None:
            try:
                from app.storage.tarantool import get_tarantool_client

                client = await get_tarantool_client()
                self._storage = client
            except Exception as e:
                logger.error(
                    f"LLM Audit: Failed to initialize storage: {e}",
                    component="llm_audit",
                )
                # Fallback to no storage (logs only)
                self._storage = False
        return self._storage if self._storage is not False else None

    @staticmethod
    def compute_hash(text: str) -> str:
        """
        Вычисляет SHA256 хэш текста.

        Args:
            text: Текст для хэширования

        Returns:
            Hex digest (первые 16 символов)
        """
        if not text:
            return ""
        return hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]

    async def log_llm_call(
        self,
        provider: str,
        model: str,
        operation: str,
        prompt: str,
        response: Optional[str],
        duration_ms: int,
        success: bool,
        error: Optional[str] = None,
        pii_detected: bool = False,
        pii_types: Optional[List[str]] = None,
        prompt_tokens: Optional[int] = None,
        response_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        fallback_used: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> LLMAuditRecord:
        """
        Логирует LLM вызов.

        Принимает параметры напрямую для обратной совместимости.
        Также поддерживает передачу через LLMCallParams:
            params = LLMCallParams(provider="openrouter", ...)
            await logger.log_llm_call(**asdict(params))
        """
        if request_id is None:
            request_id = f"{provider}_{int(time.time() * 1000)}"

        # Вычисляем хэши
        prompt_hash = self.compute_hash(prompt)
        response_hash = self.compute_hash(response) if response else ""

        # Определяем что сохранять в зависимости от privacy_mode
        prompt_text = None
        response_text = None

        if self.privacy_mode == PrivacyMode.FULL:
            prompt_text = prompt
            response_text = response
        # В HASH_ONLY и MINIMAL режимах текст не сохраняется

        # Создаём запись
        record = LLMAuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            request_id=request_id,
            provider=provider,
            model=model,
            operation=operation,
            privacy_mode=self.privacy_mode.value,
            pii_detected=pii_detected,
            pii_types=pii_types or [],
            prompt_hash=prompt_hash,
            prompt_text=prompt_text,
            response_hash=response_hash,
            response_text=response_text,
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            total_tokens=((prompt_tokens or 0) + (response_tokens or 0) if prompt_tokens and response_tokens else None),
            temperature=temperature,
            max_tokens=max_tokens,
            success=success,
            error=error,
            fallback_used=fallback_used,
            metadata=metadata or {},
        )

        # Логируем в stdout
        log_message = (
            f"LLM Call: {provider}/{model} | "
            f"op={operation} | "
            f"duration={duration_ms}ms | "
            f"tokens={record.total_tokens} | "
            f"pii={pii_detected} | "
            f"success={success}"
        )

        if success:
            logger.info(log_message, component="llm_audit")
        else:
            logger.error(f"{log_message} | error={error}", component="llm_audit")

        # Сохраняем в Tarantool
        await self._save_to_storage(record)

        return record

    async def _save_to_storage(self, record: LLMAuditRecord):
        """
        Сохраняет запись в Tarantool persistent space.

        Args:
            record: Запись для сохранения
        """
        storage = await self._get_storage()
        if storage is None:
            logger.warning(
                "LLM Audit: Storage not available, skipping persist",
                component="llm_audit",
            )
            return

        try:
            # Сохраняем в persistent space с TTL 90 дней
            # Space: llm_audit (создастся автоматически в Tarantool init)
            await storage.call(
                "box.space.llm_audit:insert",
                (
                    record.request_id,  # Primary key
                    record.timestamp,
                    record.provider,
                    record.model,
                    record.operation,
                    record.duration_ms,
                    record.success,
                    record.pii_detected,
                    record.prompt_hash,
                    record.response_hash,
                    record.total_tokens or 0,
                    # Сохраняем full record как JSON для гибкости
                    asdict(record),
                ),
            )

            logger.debug(f"LLM Audit: Saved record {record.request_id}", component="llm_audit")

        except Exception as e:
            logger.error(
                f"LLM Audit: Failed to save record: {e}",
                component="llm_audit",
                exc_info=True,
            )

    async def get_recent_calls(self, limit: int = 100) -> List[LLMAuditRecord]:
        """
        Получает последние N вызовов LLM.

        Args:
            limit: Количество записей

        Returns:
            Список LLMAuditRecord
        """
        storage = await self._get_storage()
        if storage is None:
            return []

        try:
            result = await storage.call(
                "box.space.llm_audit:select",
                (None, {"limit": limit, "iterator": "REQ"}),
            )

            records = []
            for row in result:
                # row[-1] содержит full record dict
                record_dict = row[-1]
                records.append(LLMAuditRecord(**record_dict))

            return records

        except Exception as e:
            logger.error(f"LLM Audit: Failed to get recent calls: {e}", component="llm_audit")
            return []

    async def get_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Получает статистику по LLM вызовам за последние N часов.

        Args:
            hours: Количество часов для анализа

        Returns:
            Словарь со статистикой
        """
        # Получаем недавние вызовы
        records = await self.get_recent_calls(limit=1000)

        # Фильтруем по времени
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = [r for r in records if datetime.fromisoformat(r.timestamp) >= cutoff]

        # Считаем статистику
        total_calls = len(recent)
        successful = sum(1 for r in recent if r.success)
        failed = total_calls - successful

        total_tokens = sum(r.total_tokens for r in recent if r.total_tokens)
        avg_duration = sum(r.duration_ms for r in recent) / total_calls if total_calls > 0 else 0

        pii_detected_count = sum(1 for r in recent if r.pii_detected)
        fallback_used_count = sum(1 for r in recent if r.fallback_used)

        # По провайдерам
        providers = {}
        for r in recent:
            if r.provider not in providers:
                providers[r.provider] = {"calls": 0, "tokens": 0, "errors": 0}
            providers[r.provider]["calls"] += 1
            providers[r.provider]["tokens"] += r.total_tokens or 0
            if not r.success:
                providers[r.provider]["errors"] += 1

        return {
            "period_hours": hours,
            "total_calls": total_calls,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total_calls if total_calls > 0 else 0,
            "total_tokens": total_tokens,
            "avg_duration_ms": avg_duration,
            "pii_detected_count": pii_detected_count,
            "pii_detection_rate": (pii_detected_count / total_calls if total_calls > 0 else 0),
            "fallback_used_count": fallback_used_count,
            "providers": providers,
        }


# Singleton instance
_audit_logger: Optional[LLMAuditLogger] = None


def get_audit_logger(privacy_mode: Optional[PrivacyMode] = None) -> LLMAuditLogger:
    """
    Получает singleton instance LLMAuditLogger.

    Args:
        privacy_mode: Режим приватности (используется только при первой инициализации)

    Returns:
        LLMAuditLogger instance
    """
    global _audit_logger

    if _audit_logger is None:
        # Читаем privacy_mode из конфига если не указан
        if privacy_mode is None:
            try:
                from app.config.settings import settings

                privacy_mode_str = settings.secure.llm_audit_privacy_mode
                privacy_mode = PrivacyMode(privacy_mode_str)
            except Exception:
                privacy_mode = PrivacyMode.HASH_ONLY  # Safe default

        _audit_logger = LLMAuditLogger(privacy_mode=privacy_mode)

    return _audit_logger


def audit_llm_call(operation: str):
    """
    Декоратор для автоматического логирования LLM вызовов.

    Usage:
        @audit_llm_call(operation="generate_json")
        async def my_llm_function(prompt: str, ...) -> str:
            # LLM call logic
            return response

    Args:
        operation: Тип операции (для идентификации в логах)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            logger_instance = get_audit_logger()

            # Извлекаем параметры из args/kwargs
            prompt = kwargs.get("prompt") or kwargs.get("user_message") or kwargs.get("messages", "")
            provider = kwargs.get("provider", "unknown")
            model = kwargs.get("model", "unknown")

            response = None
            error = None
            success = False

            try:
                # Выполняем функцию
                response = await func(*args, **kwargs)
                success = True
                return response

            except Exception as e:
                error = str(e)
                raise

            finally:
                # Вычисляем длительность
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Определяем наличие PII маркеров в промпте
                prompt_str = str(prompt)
                pii_detected, pii_types = detect_pii_markers(prompt_str)

                # Логируем
                await logger_instance.log_llm_call(
                    provider=provider,
                    model=model,
                    operation=operation,
                    prompt=prompt_str,
                    response=str(response) if response else None,
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                    pii_detected=pii_detected,
                    pii_types=pii_types,
                    metadata={
                        "function": func.__name__,
                        "args_count": len(args),
                        "kwargs_count": len(kwargs),
                    },
                )

        return wrapper

    return decorator


__all__ = [
    "LLMAuditRecord",
    "LLMCallParams",
    "LLMAuditLogger",
    "PrivacyMode",
    "get_audit_logger",
    "audit_llm_call",
    "detect_pii_markers",
]
