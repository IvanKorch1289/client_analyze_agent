"""
Единая точка инициализации LLM для приложения.

Раньше в `llm_init.py` была отдельная (sync) реализация вызова OpenRouter через httpx,
а в `llm_manager.py` — полноценный менеджер с fallback на HuggingFace/GigaChat.

Это дублировало конфигурацию и ухудшало производительность (создавался новый httpx.Client
на каждый запрос, без keep-alive и без общего контроля).

Теперь `llm_init.py` — тонкий адаптер под LangChain, который делегирует всю логику
выбора провайдера и fallback в `LLMManager`.
"""

from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM

from app.agents.llm_manager import _run_coroutine_sync, get_llm_manager


class ManagerBackedLLM(LLM):
    """
    LangChain-compatible LLM, который использует `LLMManager`.

    Примечание по `stop`: в текущей реализации `LLMManager` не поддерживает stop-токены
    как отдельный параметр, поэтому здесь они игнорируются (fallback/маршрутизация
    не ломаются, а для большинства сценариев stop не критичен).
    """

    @property
    def _llm_type(self) -> str:
        return "llm_manager"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        _run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        return _run_coroutine_sync(get_llm_manager().ainvoke(prompt, **kwargs))

    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        _run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        return await get_llm_manager().ainvoke(prompt, **kwargs)


# Экспортируем единый экземпляр, как и раньше (для обратной совместимости).
llm = ManagerBackedLLM()

__all__ = ["llm", "ManagerBackedLLM"]
