"""
Shared LLM utilities for agents.

Wrapper для LLMManager с retry логикой, fallback и защитой данных через LLM Guard.

Безопасность:
- Все данные перед отправкой во внешнюю LLM проходят через LLMGuardService
- PII (ИНН, телефоны, email, ФИО) анонимизируются
- Ответ LLM деанонимизируется перед возвратом
"""

import json
from typing import Any, Dict, Optional

from app.agents.llm_manager import LLMManager
from app.services.llm_guard import get_llm_guard
from app.utility.logging_client import logger

_llm_manager_instance: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """
    Получить singleton instance LLMManager.

    Returns:
        LLMManager instance
    """
    global _llm_manager_instance
    if _llm_manager_instance is None:
        _llm_manager_instance = LLMManager()
    return _llm_manager_instance


def _sanitize_for_llm(text: str) -> tuple[str, bool]:
    """
    Анонимизировать PII перед отправкой в LLM.

    Returns:
        (sanitized_text, has_pii)
    """
    try:
        guard = get_llm_guard()
        result = guard.sanitize_input(text)
        if result.has_pii:
            logger.debug(
                f"LLM Guard: sanitized {len(result.matches)} PII matches",
                component="llm_provider",
            )
        return result.sanitized_text, result.has_pii
    except Exception as e:
        logger.warning(f"LLM Guard sanitize error: {e}", component="llm_provider")
        return text, False


def _restore_from_llm(text: str, had_pii: bool) -> str:
    """
    Восстановить PII после получения ответа от LLM.
    """
    if not had_pii:
        return text
    try:
        guard = get_llm_guard()
        return guard.restore_output(text)
    except Exception as e:
        logger.warning(f"LLM Guard restore error: {e}", component="llm_provider")
        return text


async def llm_generate_json(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 4000,
    fallback_on_error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Генерация JSON через LLM с обработкой ошибок.

    Args:
        system_prompt: Системный промпт
        user_message: Сообщение пользователя
        temperature: Температура (default: 0.2 для точности)
        max_tokens: Макс токенов (default: 4000)
        fallback_on_error: Fallback ответ при ошибке

    Returns:
        Parsed JSON dict или fallback

    Examples:
        >>> result = await llm_generate_json(
        ...     system_prompt="You are a risk analyst",
        ...     user_message="Analyze this company: ...",
        ...     fallback_on_error={"score": 50, "level": "medium"}
        ... )
    """
    llm = get_llm_manager()

    try:
        full_prompt = f"{system_prompt}\n\n{user_message}"

        sanitized_prompt, had_pii = _sanitize_for_llm(full_prompt)

        content = await llm.ainvoke(
            prompt=sanitized_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if not content or not isinstance(content, str):
            logger.error("LLM returned empty or invalid response", component="llm_helper")
            return fallback_on_error or {"error": "Empty response"}

        content = _restore_from_llm(content, had_pii)

        # Try to parse JSON from response
        try:
            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}", component="llm_helper")
            # Try to extract JSON from text
            import re

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

            logger.warning(
                f"Using fallback due to JSON parse error. Raw content: {content[:200]}",
                component="llm_helper",
            )
            return fallback_on_error or {
                "error": "JSON parse failed",
                "raw_content": content,
            }

    except Exception as e:
        logger.error(f"LLM generation error: {e}", component="llm_helper", exc_info=True)
        return fallback_on_error or {"error": str(e)}


async def llm_generate_text(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> str:
    """
    Генерация текста через LLM.

    Args:
        system_prompt: Системный промпт
        user_message: Сообщение пользователя
        temperature: Температура (default: 0.7 для креативности)
        max_tokens: Макс токенов

    Returns:
        Generated text или error message
    """
    llm = get_llm_manager()

    try:
        full_prompt = f"{system_prompt}\n\n{user_message}"

        sanitized_prompt, had_pii = _sanitize_for_llm(full_prompt)

        content = await llm.ainvoke(
            prompt=sanitized_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        result = content if isinstance(content, str) else str(content)
        return _restore_from_llm(result, had_pii)

    except Exception as e:
        logger.error(f"LLM text generation error: {e}", component="llm_helper")
        return f"[Ошибка: {str(e)}]"


__all__ = [
    "get_llm_manager",
    "llm_generate_json",
    "llm_generate_text",
]
