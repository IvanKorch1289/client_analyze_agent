"""
LLM Manager с fallback стратегией.

Fallback последовательность:
1. OpenRouter (Primary) - anthropic/claude-3.5-sonnet
2. HuggingFace (Fallback #1) - Meta-Llama-3.1-70B-Instruct  
3. GigaChat (Fallback #2) - GigaChat-Pro

Автоматически переключается при ошибках или недоступности провайдера.
"""

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_community.llms import GigaChat
from langchain_core.language_models.llms import LLM
from langchain_huggingface import HuggingFaceEndpoint
from langchain_openai import ChatOpenAI

from app.config import settings
from app.utility.logging_client import logger


class LLMProvider(str, Enum):
    """Поддерживаемые LLM провайдеры."""
    
    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    GIGACHAT = "gigachat"


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
        self._openrouter_llm: Optional[ChatOpenAI] = None
        self._huggingface_llm: Optional[HuggingFaceEndpoint] = None
        self._gigachat_llm: Optional[GigaChat] = None
        
        self._provider_status: Dict[str, bool] = {
            LLMProvider.OPENROUTER: True,
            LLMProvider.HUGGINGFACE: True,
            LLMProvider.GIGACHAT: True,
        }
        
        self._fallback_order = [
            LLMProvider.OPENROUTER,
            LLMProvider.HUGGINGFACE,
            LLMProvider.GIGACHAT,
        ]
        
        logger.info("LLMManager initialized", component="llm_manager")
    
    def _get_openrouter_llm(self) -> ChatOpenAI:
        """
        Получить OpenRouter LLM (primary).
        
        Returns:
            ChatOpenAI: Настроенный LLM для OpenRouter
        """
        if self._openrouter_llm is None:
            if not settings.openrouter.api_key:
                raise ValueError("OpenRouter API key not configured")
            
            self._openrouter_llm = ChatOpenAI(
                api_key=settings.openrouter.api_key,
                base_url=settings.openrouter.api_url,
                model=settings.openrouter.model,
                temperature=settings.openrouter.temperature,
                max_tokens=settings.openrouter.max_tokens,
                timeout=settings.openrouter.timeout,
                # OpenRouter specific headers
                default_headers={
                    "HTTP-Referer": "https://client-analysis-system.com",
                    "X-Title": "Client Analysis System",
                },
            )
            
            logger.info(
                f"OpenRouter LLM initialized: {settings.openrouter.model}",
                component="llm_manager"
            )
        
        return self._openrouter_llm
    
    def _get_huggingface_llm(self) -> HuggingFaceEndpoint:
        """
        Получить HuggingFace LLM (fallback #1).
        
        Returns:
            HuggingFaceEndpoint: Настроенный LLM для HuggingFace
        """
        if self._huggingface_llm is None:
            if not settings.huggingface.api_key:
                raise ValueError("HuggingFace API key not configured")
            
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
                component="llm_manager"
            )
        
        return self._huggingface_llm
    
    def _get_gigachat_llm(self) -> GigaChat:
        """
        Получить GigaChat LLM (fallback #2).
        
        Returns:
            GigaChat: Настроенный LLM для GigaChat
        """
        if self._gigachat_llm is None:
            if not settings.gigachat.api_key:
                raise ValueError("GigaChat API key (credentials) not configured")
            
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
                component="llm_manager"
            )
        
        return self._gigachat_llm
    
    def _get_llm_by_provider(self, provider: LLMProvider) -> LLM:
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
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    async def ainvoke_with_provider(
        self,
        prompt: str,
        provider: LLMProvider,
        **kwargs
    ) -> str:
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
            component="llm_manager"
        )
        
        try:
            # ChatOpenAI возвращает AIMessage, нужно .content
            if provider == LLMProvider.OPENROUTER:
                response = await llm.ainvoke(prompt, **kwargs)
                return response.content if hasattr(response, 'content') else str(response)
            else:
                # HuggingFace и GigaChat возвращают строку
                response = await llm.ainvoke(prompt, **kwargs)
                return str(response)
                
        except Exception as e:
            logger.error(
                f"{provider} invocation failed: {e}",
                component="llm_manager",
                exc_info=True
            )
            self._provider_status[provider] = False
            raise
    
    async def ainvoke(
        self,
        prompt: str,
        **kwargs
    ) -> str:
        """
        Вызов LLM с автоматическим fallback.
        
        Пытается вызвать провайдеры в порядке:
        1. OpenRouter
        2. HuggingFace (если OpenRouter недоступен)
        3. GigaChat (если оба недоступны)
        
        Args:
            prompt: Запрос для LLM
            **kwargs: Дополнительные параметры для LLM
            
        Returns:
            str: Ответ от LLM
            
        Raises:
            Exception: Если все провайдеры недоступны
        """
        last_error = None
        
        for provider in self._fallback_order:
            # Пропускаем провайдеры, которые помечены как недоступные
            if not self._provider_status[provider]:
                logger.warning(
                    f"Skipping {provider} (marked as unavailable)",
                    component="llm_manager"
                )
                continue
            
            try:
                logger.info(
                    f"Attempting LLM call with {provider}",
                    component="llm_manager"
                )
                
                response = await self.ainvoke_with_provider(
                    prompt=prompt,
                    provider=provider,
                    **kwargs
                )
                
                logger.structured(
                    "info",
                    "llm_success",
                    component="llm_manager",
                    provider=provider.value,
                    prompt_length=len(prompt),
                    response_length=len(response),
                )
                
                # Помечаем провайдер как доступный при успехе
                self._provider_status[provider] = True
                
                return response
                
            except Exception as e:
                last_error = e
                logger.error(
                    f"LLM call failed with {provider}: {e}",
                    component="llm_manager"
                )
                self._provider_status[provider] = False
                continue
        
        # Все провайдеры недоступны
        logger.error(
            "All LLM providers failed",
            component="llm_manager",
            exc_info=True
        )
        raise Exception(
            f"All LLM providers failed. Last error: {last_error}"
        )
    
    def invoke(self, prompt: str, **kwargs) -> str:
        """
        Синхронная версия invoke с fallback.
        
        Args:
            prompt: Запрос для LLM
            **kwargs: Дополнительные параметры
            
        Returns:
            str: Ответ от LLM
        """
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.ainvoke(prompt, **kwargs))
    
    async def check_provider_health(self, provider: LLMProvider) -> bool:
        """
        Проверка здоровья провайдера.
        
        Args:
            provider: Провайдер для проверки
            
        Returns:
            bool: True если провайдер доступен
        """
        try:
            llm = self._get_llm_by_provider(provider)
            
            # Простой health check запрос
            test_prompt = "Hello"
            response = await self.ainvoke_with_provider(
                test_prompt,
                provider=provider
            )
            
            if response and len(response) > 0:
                self._provider_status[provider] = True
                logger.info(
                    f"{provider} health check: OK",
                    component="llm_manager"
                )
                return True
            else:
                self._provider_status[provider] = False
                return False
                
        except Exception as e:
            logger.error(
                f"{provider} health check failed: {e}",
                component="llm_manager"
            )
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
                logger.error(
                    f"Health check error for {provider}: {e}",
                    component="llm_manager"
                )
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
        return self._provider_status.copy()
    
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
                component="llm_manager"
            )
        else:
            for p in self._fallback_order:
                self._provider_status[p] = True
            logger.info(
                "All providers status reset to available",
                component="llm_manager"
            )


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
