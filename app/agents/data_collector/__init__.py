"""
Data Collector Agent Package.

Модульная структура для сбора данных из различных источников:
- fetchers.py - Функции получения данных из API
- builders.py - Построение и преобразование результатов
- agent.py - Основной агент сбора данных

Usage:
    from app.agents.data_collector import data_collector_agent

    result = await data_collector_agent(state)
"""

from app.agents.data_collector.agent import data_collector_agent
from app.agents.data_collector.builders import (
    analyze_sentiment,
    build_search_results,
    convert_registry_sources_to_search_results,
)
from app.agents.data_collector.fetchers import (
    cascade_perplexity_analysis,
    fetch_casebook,
    fetch_dadata,
    fetch_infosphere,
    fetch_perplexity,
    fetch_tavily,
)

# Legacy private function names (with underscore prefix) for backward compatibility
_fetch_perplexity = fetch_perplexity
_cascade_perplexity_analysis = cascade_perplexity_analysis
_fetch_tavily = fetch_tavily
_fetch_dadata_wrapper = fetch_dadata
_fetch_infosphere_wrapper = fetch_infosphere
_fetch_casebook_wrapper = fetch_casebook
_build_search_results = build_search_results
_convert_registry_sources_to_search_results = convert_registry_sources_to_search_results
_analyze_sentiment = analyze_sentiment

__all__ = [
    # Main agent
    "data_collector_agent",
    # Fetchers
    "fetch_perplexity",
    "cascade_perplexity_analysis",
    "fetch_tavily",
    "fetch_dadata",
    "fetch_infosphere",
    "fetch_casebook",
    # Builders
    "build_search_results",
    "convert_registry_sources_to_search_results",
    "analyze_sentiment",
    # Legacy names (backward compatibility)
    "_fetch_perplexity",
    "_cascade_perplexity_analysis",
    "_fetch_tavily",
    "_fetch_dadata_wrapper",
    "_fetch_infosphere_wrapper",
    "_fetch_casebook_wrapper",
    "_build_search_results",
    "_convert_registry_sources_to_search_results",
    "_analyze_sentiment",
]
