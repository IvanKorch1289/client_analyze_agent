"""
PromptManager: единая точка доступа к промптам с версионированием.

Обёртка над реестром SYSTEM_PROMPTS из system_prompts.py.
Поддерживает подстановку параметров и выбор версии.
"""

from typing import Any, Dict, Optional

from app.shared.toolkit.logging import logger


class PromptManager:
    """
    Менеджер промптов с поддержкой версионирования.

    Предоставляет единый интерфейс для получения промптов
    по имени шаблона (роли агента) с подстановкой параметров.
    """

    _instance: Optional["PromptManager"] = None

    def __init__(self):
        from app.mcp_server.prompts.system_prompts import SYSTEM_PROMPTS, AnalyzerRole

        self._system_prompts = SYSTEM_PROMPTS
        self._role_map: Dict[str, AnalyzerRole] = {role.value: role for role in AnalyzerRole}

    @classmethod
    def get_instance(cls) -> "PromptManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_template(
        self,
        template_name: str,
        version: str = "latest",
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Получить промпт по имени шаблона.

        Args:
            template_name: Имя шаблона (значение AnalyzerRole, напр. "orchestrator")
            version: Версия промпта ("latest" или конкретная, напр. "1.2")
            params: Параметры для подстановки в промпт ({client_name}, {inn} и т.д.)

        Returns:
            Текст промпта с подставленными параметрами

        Raises:
            KeyError: Если шаблон не найден
        """
        role = self._role_map.get(template_name)
        if role is None:
            raise KeyError(f"Prompt template '{template_name}' not found. Available: {list(self._role_map.keys())}")

        prompt_obj = self._system_prompts.get(role)
        if prompt_obj is None:
            raise KeyError(f"No prompt registered for role: {role}")

        if version != "latest" and prompt_obj.version != version:
            logger.warning(
                f"Requested prompt version {version} for {template_name}, but only {prompt_obj.version} is available",
                component="prompt_manager",
            )

        content = prompt_obj.content

        if params:
            try:
                content = content.format(**params)
            except KeyError:
                # Промпт может не содержать всех плейсхолдеров — не ошибка
                pass

        return content

    def get_version(self, template_name: str) -> str:
        """Получить текущую версию промпта."""
        role = self._role_map.get(template_name)
        if role is None:
            raise KeyError(f"Prompt template '{template_name}' not found")
        prompt_obj = self._system_prompts.get(role)
        if prompt_obj is None:
            raise KeyError(f"No prompt registered for role: {role}")
        return prompt_obj.version

    def list_templates(self) -> Dict[str, str]:
        """Получить список всех шаблонов с версиями."""
        return {role.value: self._system_prompts[role].version for role in self._system_prompts}
