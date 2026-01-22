"""
LLM Manager с fallback стратегией и поддержкой Jay Guard прокси.

Fallback последовательность:
1. OpenRouter (Primary) - anthropic/claude-3.5-sonnet
2. HuggingFace (Fallback #1) - Meta-Llama-3.1-70B-Instruct
3. GigaChat (Fallback #2) - GigaChat-Pro
4. YandexGPT (Fallback #3) - YandexGPT-Lite

Jay Guard Proxy:
- Если включен (JAYGUARD_ENABLED=true), все запросы к OpenRouter идут через Jay Guard
- Jay Guard обеспечивает PII маскирование и защиту данных

Автоматически переключается при ошибках или недоступности провайдера.
"""

import asyncio
import threading
import time
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.utility.logging_client import logger

# Lazy imports для PII, audit, cache и metrics
_pii_protection = None
_llm_audit = None
_llm_cache = None
_prometheus_metrics = None


def _get_pii_protection():
    """Lazy import PII protection module."""
    global _pii_protection
    if _pii_protection is None:
        from app.shared import pii_protection as pii_mod

        _pii_protection = pii_mod
    return _pii_protection


def _get_llm_audit():
    """Lazy import LLM audit module."""
    global _llm_audit
    if _llm_audit is None:
        from app.shared import llm_audit as audit_mod

        _llm_audit = audit_mod
    return _llm_audit


def _get_llm_cache():
    """Lazy import LLM cache module."""
    global _llm_cache
    if _llm_cache is None:
        from app.shared import llm_cache as cache_mod

        _llm_cache = cache_mod
    return _llm_cache


def _get_metrics():
    """Lazy import Prometheus metrics."""
    global _prometheus_metrics
    if _prometheus_metrics is None:
        try:
            from app.shared.prometheus_metrics import metrics

            _prometheus_metrics = metrics
        except ImportError:
            _prometheus_metrics = None
    return _prometheus_metrics


def _run_coroutine_sync(coro):
    """
    Безопасно выполнить coroutine из sync-кода.

    - Если event loop уже запущен (например, мы в async-контексте), выполняем coroutine
      в отдельном потоке с отдельным loop. Это блокирует текущий поток (как и любой
      sync I/O), но не приводит к ошибке "asyncio.run() cannot be called...".
    - Если loop не запущен — используем asyncio.run().
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box: Dict[str, Any] = {}

    def _runner():
        try:
            result_box["value"] = asyncio.run(coro)
        except Exception as e:
            result_box["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("value")


class LLMProvider(str, Enum):
    """Поддерживаемые LLM провайдеры."""

    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    GIGACHAT = "gigachat"
    YANDEXGPT = "yandexgpt"


class LLMManager:
    """
    Менеджер LLM с автоматическим fallback.

    Управляет доступом к множественным LLM провайдерам с резервированием.
    При недоступности primary провайдера автоматически переключается на fallback.

    Использование:
        manager = LLMManager()

        # Автоматический fallback
        response = await manager.ainvoke("Analyze this company...")

        # Принудительное использование конкретного провайдера
        response = await manager.ainvoke_with_provider(
            "Analyze...",
            provider=LLMProvider.HUGGINGFACE
        )

        # Health check всех провайдеров
        health = await manager.check_all_providers_health()
    """

    def __init__(self):
        """Инициализация LLM Manager."""
        # Lazy-init провайдеров. Импорты тяжёлых зависимостей делаем внутри геттеров,
        # чтобы ускорить холодный старт и не тянуть лишнее, если провайдер не используется.
        self._openrouter_llm: Any = None
        self._huggingface_llm: Any = None
        self._gigachat_llm: Any = None
        self._yandexgpt_llm: Any = None

        self._provider_status: Dict[LLMProvider, bool] = {
            LLMProvider.OPENROUTER: True,
            LLMProvider.HUGGINGFACE: True,
            LLMProvider.GIGACHAT: True,
            LLMProvider.YANDEXGPT: True,
        }

        self._fallback_order = [
            LLMProvider.OPENROUTER,
            LLMProvider.HUGGINGFACE,
            LLMProvider.GIGACHAT,
            LLMProvider.YANDEXGPT,
        ]

        logger.info("LLMManager initialized", component="llm_manager")

    def _get_openrouter_llm(self) -> Any:
        """
        Получить OpenRouter LLM (primary).

        Если включен Jay Guard прокси (JAYGUARD_ENABLED=true), запросы идут через него.

        Returns:
            LLM: Настроенный LLM для OpenRouter (через Jay Guard если включен)
        """
        if self._openrouter_llm is None:
            from langchain_openai import ChatOpenAI

            jayguard_enabled = settings.jayguard.enabled
            jayguard_url = settings.jayguard.api_url
            jayguard_key = settings.jayguard.api_key

            if jayguard_enabled and jayguard_url and jayguard_key:
                self._openrouter_llm = ChatOpenAI(
                    api_key=jayguard_key,
                    base_url=jayguard_url,
                    model=settings.openrouter.model,
                    temperature=settings.openrouter.temperature,
                    max_tokens=settings.openrouter.max_tokens,
                    timeout=settings.jayguard.timeout,
                    default_headers={
                        "HTTP-Referer": "https://client-analysis-system.com",
                        "X-Title": "Client Analysis System",
                    },
                )

                logger.info(
                    f"OpenRouter LLM via Jay Guard proxy: {settings.openrouter.model}",
                    component="llm_manager",
                )
            else:
                if not settings.openrouter.api_key:
                    raise ValueError("OpenRouter API key not configured")

                self._openrouter_llm = ChatOpenAI(
                    api_key=settings.openrouter.api_key,
                    base_url=settings.openrouter.api_url,
                    model=settings.openrouter.model,
                    temperature=settings.openrouter.temperature,
                    max_tokens=settings.openrouter.max_tokens,
                    timeout=settings.openrouter.timeout,
                    default_headers={
                        "HTTP-Referer": "https://client-analysis-system.com",
                        "X-Title": "Client Analysis System",
                    },
                )

                logger.info(
                    f"OpenRouter LLM initialized: {settings.openrouter.model}",
                    component="llm_manager",
                )

        return self._openrouter_llm

    def _get_huggingface_llm(self) -> Any:
        """
        Получить HuggingFace LLM (fallback #1).

        Returns:
            LLM: Настроенный LLM для HuggingFace
        """
        if self._huggingface_llm is None:
            if not settings.huggingface.api_key:
                raise ValueError("HuggingFace API key not configured")
            from langchain_huggingface import HuggingFaceEndpoint

            self._huggingface_llm = HuggingFaceEndpoint(
                endpoint_url=None,  # Will use inference API
                repo_id=settings.huggingface.model,
                huggingfacehub_api_token=settings.huggingface.api_key,
                temperature=settings.huggingface.temperature,
                max_new_tokens=settings.huggingface.max_tokens,
                top_p=settings.huggingface.top_p,
                timeout=settings.huggingface.timeout,
            )

            logger.info(
                f"HuggingFace LLM initialized: {settings.huggingface.model}",
                component="llm_manager",
            )

        return self._huggingface_llm

    def _get_gigachat_llm(self) -> Any:
        """
        Получить GigaChat LLM (fallback #2).

        Returns:
            LLM: Настроенный LLM для GigaChat
        """
        if self._gigachat_llm is None:
            if not settings.gigachat.api_key:
                raise ValueError("GigaChat API key (credentials) not configured")
            from langchain_community.llms import GigaChat

            self._gigachat_llm = GigaChat(
                credentials=settings.gigachat.api_key,
                model=settings.gigachat.model,
                temperature=settings.gigachat.temperature,
                max_tokens=settings.gigachat.max_tokens,
                timeout=settings.gigachat.timeout,
                verify_ssl_certs=settings.gigachat.verify_ssl_certs,
                scope="GIGACHAT_API_PERS",  # Personal scope
            )

            logger.info(
                f"GigaChat LLM initialized: {settings.gigachat.model}",
                component="llm_manager",
            )

        return self._gigachat_llm

    def _get_yandexgpt_llm(self) -> Any:
        """
        Получить YandexGPT LLM (fallback #3).

        Returns:
            LLM: Настроенный LLM для YandexGPT
        """
        if self._yandexgpt_llm is None:
            if not settings.yandexgpt.api_key:
                raise ValueError("YandexGPT IAM token not configured")
            from langchain_community.llms import YandexGPT

            self._yandexgpt_llm = YandexGPT(
                iam_token=settings.yandexgpt.api_key,
                folder_id=settings.yandexgpt.folder_id,
                model_uri=settings.yandexgpt.model_uri,
                temperature=settings.yandexgpt.temperature,
                max_tokens=settings.yandexgpt.max_tokens,
            )

            logger.info("YandexGPT LLM initialized", component="llm_manager")

        return self._yandexgpt_llm

    def _get_llm_by_provider(self, provider: LLMProvider) -> Any:
        """
        Получить LLM по имени провайдера.

        Args:
            provider: Имя провайдера

        Returns:
            LLM: Настроенный LLM

        Raises:
            ValueError: Если провайдер не поддерживается или не сконфигурирован
        """
        if provider == LLMProvider.OPENROUTER:
            return self._get_openrouter_llm()
        elif provider == LLMProvider.HUGGINGFACE:
            return self._get_huggingface_llm()
        elif provider == LLMProvider.GIGACHAT:
            return self._get_gigachat_llm()
        elif provider == LLMProvider.YANDEXGPT:
            return self._get_yandexgpt_llm()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def ainvoke_with_provider(self, prompt: str, provider: LLMProvider, **kwargs) -> str:
        """
        Вызов LLM с явным указанием провайдера.

        Args:
            prompt: Запрос для LLM
            provider: Провайдер для использования
            **kwargs: Дополнительные параметры для LLM

        Returns:
            str: Ответ от LLM

        Raises:
            Exception: При ошибке вызова LLM
        """
        llm = self._get_llm_by_provider(provider)

        logger.debug(
            f"Invoking {provider} with prompt length: {len(prompt)}",
            component="llm_manager",
        )

        try:
            # ChatOpenAI возвращает AIMessage, нужно .content
            if provider == LLMProvider.OPENROUTER:
                response = await llm.ainvoke(prompt, **kwargs)
                return response.content if hasattr(response, "content") else str(response)
            else:
                # HuggingFace, GigaChat и YandexGPT возвращают строку
                response = await llm.ainvoke(prompt, **kwargs)
                return str(response)

        except Exception as e:
            logger.error(
                f"{provider} invocation failed: {e}",
                component="llm_manager",
                exc_info=True,
            )
            self._provider_status[provider] = False
            raise

    # ============================================================
    # HELPER METHODS for ainvoke() - extracted for lower complexity
    # ============================================================

    async def _try_cache_lookup(self, prompt: str, start_time: float, **kwargs) -> Optional[str]:
        """
        Try to get response from LLM cache.

        Returns:
            Cached response if hit, None if miss or error.
        """
        try:
            cache = _get_llm_cache()
            cache_result = await cache.get_cached_response(
                prompt=prompt,
                provider=self._fallback_order[0].value,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4000),
            )

            if cache_result.hit:
                total_duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.info(
                    f"LLM Cache HIT - saved {total_duration_ms}ms",
                    component="llm_manager",
                )

                # Log cache hit to audit
                if settings.secure.llm_audit_enabled:
                    await self._log_cache_hit_audit(
                        prompt,
                        cache_result.response,
                        cache_result.cache_key,
                        total_duration_ms,
                    )

                return cache_result.response
        except Exception as e:
            logger.error(f"LLM Cache check failed: {e}", component="llm_manager")

        return None

    async def _log_cache_hit_audit(self, prompt: str, response: str, cache_key: str, duration_ms: int) -> None:
        """Log cache hit to audit trail."""
        try:
            audit = _get_llm_audit()
            audit_logger = audit.get_audit_logger()
            await audit_logger.log_llm_call(
                provider="cache",
                model="cached",
                operation="ainvoke_cached",
                prompt=prompt,
                response=response,
                duration_ms=duration_ms,
                success=True,
                pii_detected=False,
                metadata={"cache_key": cache_key, "cache_hit": True},
            )
        except Exception as e:
            logger.error(f"Audit logging failed: {e}", component="llm_manager")

    def _mask_prompt_pii(self, prompt: str) -> Tuple[str, Optional[Any]]:
        """
        Mask PII in prompt before sending to LLM.

        Returns:
            Tuple of (masked_prompt, pii_result or None)
        """
        if not settings.secure.llm_audit_enabled:
            return prompt, None

        try:
            pii = _get_pii_protection()
            pii_result = pii.mask_pii(text=prompt, language="ru", mask_level="high")

            if pii_result.pii_detected:
                logger.warning(
                    f"PII detected and masked: {pii_result.pii_count} items",
                    component="llm_manager",
                )

            return pii_result.masked_text, pii_result
        except Exception as e:
            logger.error(f"PII masking failed: {e}", component="llm_manager")
            return prompt, None

    async def _call_providers_with_fallback(
        self, masked_prompt: str, pii_result: Optional[Any], start_time: float, **kwargs
    ) -> Tuple[bool, str, Optional["LLMProvider"], int, Optional[Exception]]:
        """
        Try calling LLM providers in fallback order.

        Returns:
            Tuple of (success, response_text, used_provider, attempts, last_error)
        """
        last_error = None
        attempts = 0
        response_text = ""
        used_provider = None

        for provider in self._fallback_order:
            attempts += 1

            if not self._provider_status[provider]:
                logger.warning(f"Skipping {provider} (unavailable)", component="llm_manager")
                continue

            try:
                logger.info(f"Attempting LLM call with {provider}", component="llm_manager")
                provider_start = time.perf_counter()

                response_text = await self.ainvoke_with_provider(prompt=masked_prompt, provider=provider, **kwargs)

                provider_duration = time.perf_counter() - provider_start
                self._log_provider_success(
                    provider,
                    masked_prompt,
                    response_text,
                    provider_duration,
                    start_time,
                    attempts,
                    pii_result,
                )

                self._provider_status[provider] = True
                used_provider = provider
                return True, response_text, used_provider, attempts, None

            except Exception as e:
                last_error = e
                logger.error(f"LLM call failed with {provider}: {e}", component="llm_manager")
                self._provider_status[provider] = False
                self._record_provider_failure(provider, provider_start, attempts)

        return False, response_text, used_provider, attempts, last_error

    def _log_provider_success(
        self,
        provider: "LLMProvider",
        prompt: str,
        response: str,
        provider_duration: float,
        start_time: float,
        attempts: int,
        pii_result: Optional[Any],
    ) -> None:
        """Log successful provider call."""
        total_duration = time.perf_counter() - start_time
        logger.structured(
            "info",
            "llm_success",
            component="llm_manager",
            provider=provider.value,
            prompt_length=len(prompt),
            response_length=len(response),
            duration_ms=round(provider_duration * 1000, 2),
            total_duration_ms=round(total_duration * 1000, 2),
            fallback_used=(provider != LLMProvider.OPENROUTER),
            attempts=attempts,
            pii_masked=bool(pii_result and pii_result.pii_detected),
        )

        # Record Prometheus metrics
        prom = _get_metrics()
        if prom and prom.enabled:
            prom.record_llm_request(provider=provider.value, success=True, latency=provider_duration)

    def _record_provider_failure(self, provider: "LLMProvider", provider_start: float, attempts: int) -> None:
        """Record provider failure in metrics."""
        prom = _get_metrics()
        if prom and prom.enabled:
            prom.record_llm_request(
                provider=provider.value,
                success=False,
                latency=time.perf_counter() - provider_start,
            )
            if attempts < len(self._fallback_order):
                next_provider = self._fallback_order[attempts] if attempts < len(self._fallback_order) else None
                if next_provider:
                    prom.record_llm_fallback(provider.value, next_provider.value)

    def _unmask_response_pii(self, response: str, pii_result: Optional[Any]) -> str:
        """Unmask PII in response if masking was applied."""
        if not pii_result or not pii_result.replacements:
            return response

        try:
            pii = _get_pii_protection()
            return pii.unmask_pii(masked_text=response, replacements=pii_result.replacements)
        except Exception as e:
            logger.error(f"PII unmasking failed: {e}", component="llm_manager")
            return response

    async def _log_llm_audit(
        self,
        prompt: str,
        response: Optional[str],
        used_provider: Optional["LLMProvider"],
        success: bool,
        start_time: float,
        attempts: int,
        last_error: Optional[Exception],
        pii_result: Optional[Any],
        **kwargs,
    ) -> None:
        """Log LLM call to audit trail."""
        if not settings.secure.llm_audit_enabled:
            return

        try:
            audit = _get_llm_audit()
            audit_logger = audit.get_audit_logger()
            total_duration_ms = int((time.perf_counter() - start_time) * 1000)

            await audit_logger.log_llm_call(
                provider=used_provider.value if used_provider else "unknown",
                model=(self._get_model_name(used_provider) if used_provider else "unknown"),
                operation="ainvoke",
                prompt=prompt,
                response=response if success else None,
                duration_ms=total_duration_ms,
                success=success,
                error=str(last_error) if not success else None,
                pii_detected=bool(pii_result and pii_result.pii_detected),
                pii_types=pii_result.detected_pii_types if pii_result else [],
                temperature=kwargs.get("temperature"),
                max_tokens=kwargs.get("max_tokens"),
                fallback_used=(used_provider != LLMProvider.OPENROUTER if used_provider else False),
                metadata={
                    "attempts": attempts,
                    "prompt_masked": bool(pii_result and pii_result.pii_detected),
                },
            )
        except Exception as e:
            logger.error(f"Audit logging failed: {e}", component="llm_manager")

    async def _save_to_cache(
        self,
        prompt: str,
        response: str,
        used_provider: Optional["LLMProvider"],
        **kwargs,
    ) -> None:
        """Save successful response to cache."""
        try:
            cache = _get_llm_cache()
            await cache.set_cached_response(
                prompt=prompt,
                response=response,
                provider=used_provider.value if used_provider else "default",
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4000),
                ttl=3600,
            )
        except Exception as e:
            logger.error(f"LLM Cache save failed: {e}", component="llm_manager")

    # ============================================================
    # MAIN AINVOKE METHOD (refactored to use helpers)
    # ============================================================

    async def ainvoke(self, prompt: str, cache_enabled: bool = True, **kwargs) -> str:
        """
        Вызов LLM с автоматическим fallback, кэшированием, PII защитой и аудитом.

        Пытается вызвать провайдеры в порядке:
        1. OpenRouter
        2. HuggingFace (если OpenRouter недоступен)
        3. GigaChat (если оба недоступны)

        LLM Cache:
        - Проверяет кэш перед вызовом LLM (экономия 30-40 сек)
        - Кэширует успешные ответы с TTL 1 час

        PII Protection:
        - Маскирует PII перед отправкой в LLM
        - Восстанавливает PII в ответе

        Audit Logging:
        - Логирует все запросы и ответы для compliance (152-ФЗ)

        Args:
            prompt: Запрос для LLM
            cache_enabled: Использовать кэш (default: True)
            **kwargs: Дополнительные параметры для LLM
                - temperature: float
                - max_tokens: int

        Returns:
            str: Ответ от LLM

        Raises:
            Exception: Если все провайдеры недоступны
        """
        start_time = time.perf_counter()

        # Step 1: Check cache
        if cache_enabled:
            cached_response = await self._try_cache_lookup(prompt, start_time, **kwargs)
            if cached_response is not None:
                return cached_response

        # Step 2: Mask PII in prompt
        masked_prompt, pii_result = self._mask_prompt_pii(prompt)

        # Step 3: Try providers with fallback
        success, response_text, used_provider, attempts, last_error = await self._call_providers_with_fallback(
            masked_prompt, pii_result, start_time, **kwargs
        )

        # Step 4: Unmask PII in response
        final_response = self._unmask_response_pii(response_text, pii_result) if success else response_text

        # Step 5: Log to audit trail
        await self._log_llm_audit(
            prompt,
            final_response,
            used_provider,
            success,
            start_time,
            attempts,
            last_error,
            pii_result,
            **kwargs,
        )

        # Step 6: Save to cache
        if success and cache_enabled and final_response:
            await self._save_to_cache(prompt, final_response, used_provider, **kwargs)

        # Step 7: Return result or raise error
        if not success:
            total_duration = time.perf_counter() - start_time
            logger.error(
                f"All LLM providers failed (duration: {total_duration * 1000:.2f}ms, attempts: {attempts})",
                component="llm_manager",
            )
            raise Exception(f"All LLM providers failed after {attempts} attempts. Last error: {last_error}")

        return final_response

    def _get_model_name(self, provider: "LLMProvider") -> str:
        """Получает название модели для провайдера."""
        model_map = {
            LLMProvider.OPENROUTER: "claude-3.5-sonnet",
            LLMProvider.HUGGINGFACE: "Meta-Llama-3.1-70B",
            LLMProvider.GIGACHAT: "GigaChat-Pro",
            LLMProvider.YANDEXGPT: "YandexGPT-Lite",
        }
        return model_map.get(provider, "unknown")

    def invoke(self, prompt: str, **kwargs) -> str:
        """
        Синхронная версия invoke с fallback.

        Args:
            prompt: Запрос для LLM
            **kwargs: Дополнительные параметры

        Returns:
            str: Ответ от LLM
        """
        return _run_coroutine_sync(self.ainvoke(prompt, **kwargs))

    async def check_provider_health(self, provider: LLMProvider) -> bool:
        """
        Проверка здоровья провайдера.

        Args:
            provider: Провайдер для проверки

        Returns:
            bool: True если провайдер доступен
        """
        try:
            _ = self._get_llm_by_provider(provider)  # Проверяем что провайдер доступен

            # Простой health check запрос
            test_prompt = "Hello"
            response = await self.ainvoke_with_provider(test_prompt, provider=provider)

            if response and len(response) > 0:
                self._provider_status[provider] = True
                logger.info(f"{provider} health check: OK", component="llm_manager")
                return True
            else:
                self._provider_status[provider] = False
                return False

        except Exception as e:
            logger.error(f"{provider} health check failed: {e}", component="llm_manager")
            self._provider_status[provider] = False
            return False

    async def check_all_providers_health(self) -> Dict[str, bool]:
        """
        Проверка здоровья всех провайдеров.

        Returns:
            Dict[str, bool]: Статус каждого провайдера
        """
        logger.info("Starting health check for all providers", component="llm_manager")

        health_results = {}

        for provider in self._fallback_order:
            try:
                is_healthy = await self.check_provider_health(provider)
                health_results[provider.value] = is_healthy
            except Exception as e:
                logger.error(f"Health check error for {provider}: {e}", component="llm_manager")
                health_results[provider.value] = False

        logger.structured(
            "info",
            "providers_health_check",
            component="llm_manager",
            results=health_results,
        )

        return health_results

    def get_provider_status(self) -> Dict[str, bool]:
        """
        Получить текущий статус провайдеров.

        Returns:
            Dict[str, bool]: Статус каждого провайдера
        """
        return {p.value: v for p, v in self._provider_status.items()}

    def reset_provider_status(self, provider: Optional[LLMProvider] = None):
        """
        Сбросить статус провайдера (вернуть как доступный).

        Args:
            provider: Провайдер для сброса. Если None - сбросить все.
        """
        if provider:
            self._provider_status[provider] = True
            logger.info(
                f"Provider {provider} status reset to available",
                component="llm_manager",
            )
        else:
            for p in self._fallback_order:
                self._provider_status[p] = True
            logger.info("All providers status reset to available", component="llm_manager")


# Singleton экземпляр
_llm_manager_instance: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """
    Получить singleton экземпляр LLMManager.

    Returns:
        LLMManager: Единственный экземпляр менеджера
    """
    global _llm_manager_instance

    if _llm_manager_instance is None:
        _llm_manager_instance = LLMManager()

    return _llm_manager_instance


__all__ = [
    "LLMManager",
    "LLMProvider",
    "get_llm_manager",
]
