"""
Adaptive Prompt Engine: автоматическая доработка промптов на основе истории фидбеков.

Система анализирует последние 10 фидбеков пользователя и автоматически
дорабатывает промпты для агентов, чтобы избежать повторения ошибок.
"""

from typing import Any, Dict, List, Optional

from app.agents.llm_manager import LLMManager, LLMProvider
from app.prompts.manager import PromptManager
from app.shared.pii_protection import mask_pii
from app.storage.feedback_repository import FeedbackRepository
from app.shared.toolkit.logging import logger


class AdaptivePromptEngine:
    """
    Движок адаптивных промптов на основе истории фидбеков.

    Анализирует паттерны ошибок в последних фидбеках и автоматически
    генерирует улучшенные версии промптов для предотвращения повторения ошибок.
    """

    _instance: Optional["AdaptivePromptEngine"] = None

    def __init__(
        self,
        feedback_repo: Optional[FeedbackRepository] = None,
        prompt_manager: Optional[PromptManager] = None,
        llm_manager: Optional[LLMManager] = None,
    ):
        self.feedback_repo = feedback_repo
        self.prompt_manager = prompt_manager or PromptManager.get_instance()
        self.llm_manager = llm_manager or LLMManager.get_instance()

        # Кэш адаптированных промптов (session-level)
        self._adaptive_cache: Dict[str, str] = {}

    def _sanitize_comments(self, comments: List[str]) -> List[str]:
        """
        Маскирует PII в комментариях пользователей перед передачей в LLM.

        Args:
            comments: Список комментариев пользователей

        Returns:
            Список комментариев с замаскированными персональными данными
        """
        sanitized = []
        for comment in comments:
            if not comment:
                continue
            result = mask_pii(comment)
            sanitized.append(result.masked_text)
        return sanitized

    @classmethod
    def get_instance(cls) -> "AdaptivePromptEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_adaptive_prompt(
        self,
        template_name: str,
        params: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        feedback_lookback: int = 10,
    ) -> str:
        """
        Получить адаптированный промпт с учетом истории фидбеков.

        Args:
            template_name: Имя базового шаблона (orchestrator, analyzer)
            params: Параметры для подстановки в промпт
            session_id: ID сессии для кэширования
            feedback_lookback: Количество последних фидбеков для анализа

        Returns:
            Адаптированный промпт с дополнительными инструкциями
        """
        # Проверка кэша
        cache_key = f"{template_name}:{session_id}" if session_id else None
        if cache_key and cache_key in self._adaptive_cache:
            logger.debug(
                f"Using cached adaptive prompt for {template_name}",
                component="adaptive_prompt",
            )
            base_prompt = self._adaptive_cache[cache_key]
        else:
            # Получить базовый промпт
            base_prompt = self.prompt_manager.get_template(
                template_name=template_name,
                version="latest",
                params=params or {},
            )

        # Если нет feedback_repo, вернуть базовый промпт
        if not self.feedback_repo:
            logger.debug(
                "FeedbackRepository not available, using base prompt",
                component="adaptive_prompt",
            )
            return base_prompt

        # Получить последние N фидбеков с негативными/частично точными оценками
        recent_feedbacks = await self.feedback_repo.get_recent_feedbacks(
            limit=feedback_lookback,
            rating_filter=None,  # Получаем все, фильтруем ниже
        )

        # Фильтровать только негативные и частично точные
        relevant_feedbacks = [fb for fb in recent_feedbacks if fb.get("rating") in ["inaccurate", "partially_accurate"]]

        if not relevant_feedbacks:
            logger.debug(
                "No relevant feedbacks found for adaptive prompting",
                component="adaptive_prompt",
            )
            return base_prompt

        # Анализировать паттерны ошибок
        patterns = await self.feedback_repo.analyze_feedback_patterns(limit=feedback_lookback)

        # Генерировать адаптивные инструкции
        adaptive_instructions = await self._generate_adaptive_instructions(
            template_name=template_name,
            feedback_patterns=patterns,
            recent_feedbacks=relevant_feedbacks[:5],  # Первые 5 для контекста
        )

        # Комбинировать базовый промпт с адаптивными инструкциями
        adaptive_prompt = self._combine_prompt_with_instructions(base_prompt, adaptive_instructions)

        # Сохранить в кэш
        if cache_key:
            self._adaptive_cache[cache_key] = adaptive_prompt

        logger.structured(
            "info",
            "adaptive_prompt_generated",
            component="adaptive_prompt",
            template_name=template_name,
            feedback_count=len(relevant_feedbacks),
            common_issues=patterns.get("common_issues", []),
        )

        return adaptive_prompt

    async def _generate_adaptive_instructions(
        self,
        template_name: str,
        feedback_patterns: Dict[str, Any],
        recent_feedbacks: List[Dict[str, Any]],
    ) -> str:
        """
        Генерировать адаптивные инструкции на основе паттернов фидбеков.

        Использует LLM для анализа истории ошибок и генерации
        конкретных инструкций по их предотвращению.
        """
        # Подготовить контекст для LLM
        meta_prompt = self._build_meta_prompt(template_name, feedback_patterns, recent_feedbacks)

        try:
            # Использовать LLM для генерации инструкций
            adaptive_instructions = await self.llm_manager.ainvoke(
                prompt=meta_prompt,
                provider=LLMProvider.OPENROUTER,
                temperature=0.3,  # Низкая температура для стабильности
                max_tokens=800,
            )

            return adaptive_instructions

        except Exception as e:
            logger.error(
                f"Failed to generate adaptive instructions: {e}",
                component="adaptive_prompt",
                exc_info=True,
            )
            # Fallback: сгенерировать простые инструкции из паттернов
            return self._fallback_instructions(feedback_patterns)

    def _build_meta_prompt(
        self,
        template_name: str,
        patterns: Dict[str, Any],
        feedbacks: List[Dict[str, Any]],
    ) -> str:
        """Построить мета-промпт для LLM анализа фидбеков."""
        # Маскируем PII в комментариях перед передачей в LLM
        raw_comments = patterns.get("sample_comments", [])[:3]
        sanitized_comments = self._sanitize_comments(raw_comments)

        meta_prompt = f"""Ты - эксперт по улучшению промптов для AI агентов.

КОНТЕКСТ: Агент "{template_name}" получил следующие фидбеки от пользователей:

СТАТИСТИКА ФИДБЕКОВ:
- Распределение оценок: {patterns.get("rating_distribution", {})}
- Частые проблемы: {", ".join(patterns.get("common_issues", []))}
- Области, требующие внимания: {patterns.get("focus_areas_frequency", {})}

ПОСЛЕДНИЕ КОММЕНТАРИИ ПОЛЬЗОВАТЕЛЕЙ:
{chr(10).join(f'- "{comment}"' for comment in sanitized_comments)}

ЗАДАЧА: Проанализируй эти фидбеки и сгенерируй КОНКРЕТНЫЕ, ДЕЙСТВЕННЫЕ инструкции
для промпта агента "{template_name}", чтобы предотвратить повторение этих ошибок.

ТРЕБОВАНИЯ К ИНСТРУКЦИЯМ:
1. Максимум 5 пунктов
2. Каждый пункт - конкретная директива (не общие фразы)
3. Фокус на исправлении выявленных проблем
4. Лаконичность (1-2 предложения на пункт)

ФОРМАТ ОТВЕТА (только инструкции, без дополнительного текста):
1. [Инструкция 1]
2. [Инструкция 2]
...
"""
        return meta_prompt

    def _fallback_instructions(self, patterns: Dict[str, Any]) -> str:
        """Простые инструкции на основе паттернов (fallback при ошибке LLM)."""
        instructions = ["ВАЖНЫЕ ИНСТРУКЦИИ НА ОСНОВЕ ПРЕДЫДУЩИХ ФИДБЕКОВ:", ""]

        common_issues = patterns.get("common_issues", [])
        if common_issues:
            instructions.append("ИЗБЕГАЙ СЛЕДУЮЩИХ ОШИБОК:")
            for issue in common_issues[:3]:
                instructions.append(f"- Уделяй особое внимание: {issue}")
            instructions.append("")

        sample_comments = patterns.get("sample_comments", [])
        if sample_comments:
            # Маскируем PII в комментариях
            sanitized = self._sanitize_comments(sample_comments[:2])
            instructions.append("УЧИТЫВАЙ ПРЕДЫДУЩИЕ ЗАМЕЧАНИЯ:")
            for comment in sanitized:
                instructions.append(f'- "{comment[:100]}..."')
            instructions.append("")

        return "\n".join(instructions)

    def _combine_prompt_with_instructions(self, base_prompt: str, adaptive_instructions: str) -> str:
        """Комбинировать базовый промпт с адаптивными инструкциями."""
        separator = "\n" + "=" * 80 + "\n"

        combined = f"""{base_prompt}

{separator}
🔄 АДАПТИВНЫЕ ИНСТРУКЦИИ (на основе анализа последних фидбеков):
{separator}

{adaptive_instructions}

{separator}
⚠️ КРИТИЧЕСКИ ВАЖНО: Эти инструкции основаны на реальных ошибках в предыдущих
анализах. Следуй им СТРОГО, чтобы избежать повторения тех же проблем.
{separator}
"""
        return combined

    def clear_cache(self, session_id: Optional[str] = None):
        """Очистить кэш адаптированных промптов."""
        if session_id:
            # Очистить кэш для конкретной сессии
            keys_to_remove = [k for k in self._adaptive_cache if session_id in k]
            for key in keys_to_remove:
                del self._adaptive_cache[key]
        else:
            # Очистить весь кэш
            self._adaptive_cache.clear()

        logger.debug(
            f"Adaptive prompt cache cleared for session: {session_id or 'all'}",
            component="adaptive_prompt",
        )
