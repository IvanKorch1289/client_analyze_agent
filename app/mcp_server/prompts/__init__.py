"""
Типизированные системные промпты для агентов.

Централизованное управление промптами с версионированием и метаданными.
"""

from app.mcp_server.prompts.system_prompts import (
    AnalyzerRole,
    SystemPrompt,
    SYSTEM_PROMPTS,
    get_prompt_metadata,
    get_system_prompt,
    format_dadata_for_prompt,
    REGISTRY_ANALYZER_PROMPT_CONTENT,
    WEB_ANALYZER_PROMPT_CONTENT,
    MASTER_SYNTHESIZER_PROMPT_CONTENT,
)

__all__ = [
    "AnalyzerRole",
    "SystemPrompt",
    "SYSTEM_PROMPTS",
    "get_system_prompt",
    "get_prompt_metadata",
    "format_dadata_for_prompt",
    "REGISTRY_ANALYZER_PROMPT_CONTENT",
    "WEB_ANALYZER_PROMPT_CONTENT",
    "MASTER_SYNTHESIZER_PROMPT_CONTENT",
]
