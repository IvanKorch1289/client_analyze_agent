"""
Report Analyzer Agent: анализирует результаты поиска и создаёт итоговый отчёт через LLM.

P0 ИЗМЕНЕНИЯ:
- Убран ручной calculate_risk_score()
- Добавлен LLM анализ с системным промптом
- Добавлена документация API источников

Ключевой контракт: итоговый `report` соответствует модели
`app.schemas.report.ClientAnalysisReport`.
"""

import json
from datetime import datetime
from typing import Any, Dict, List

from app.services.llm_provider import llm_generate_json
from app.mcp_server.prompts.system_prompts import AnalyzerRole, get_system_prompt
from app.shared.pii_protection import mask_pii
from app.shared.utils import safe_dict_get
from app.shared.utils.formatters import truncate
from app.schemas.report import ClientAnalysisReport
from app.utility.logging_client import logger


def generate_summary(search_results: List[Dict[str, Any]], client_name: str) -> str:
    """Генерирует текстовое резюме на основе результатов поиска."""
    if not search_results:
        return f"Не удалось собрать информацию о клиенте {client_name}."

    successful = [r for r in search_results if r.get("success")]

    if not successful:
        return f"Все поисковые запросы завершились с ошибкой для клиента {client_name}."

    summary_parts = [f"## Анализ клиента: {client_name}\n"]
    summary_parts.append(f"*Дата анализа: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

    for result in successful:
        intent_id = result.get("intent_id", "")
        description = result.get("description", intent_id)
        content = result.get("content", "")
        sentiment = result.get("sentiment", {})

        sentiment_icon = {"positive": "+", "negative": "-", "neutral": "~"}.get(sentiment.get("label", "neutral"), "~")

        summary_parts.append(f"\n### {description} [{sentiment_icon}]\n")

        if content:
            truncated = content[:500] + "..." if len(content) > 500 else content
            summary_parts.append(truncated)

        citations = result.get("citations", [])
        if citations:
            summary_parts.append(f"\n*Источники: {len(citations)}*")

    return "\n".join(summary_parts)


def analyze_source_data(source_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализирует данные из разных источников (DaData, InfoSphere, Casebook)."""
    analysis = {
        "company_info": {},
        "legal_cases": [],
        "risk_signals": [],
        "positive_signals": [],
    }

    dadata = source_data.get("dadata", {})
    if dadata and dadata.get("success"):
        data = dadata.get("data", {})
        analysis["company_info"] = {
            "name": data.get("name", {}).get("full_with_opf", ""),
            "status": data.get("state", {}).get("status", ""),
            "registration_date": data.get("state", {}).get("registration_date"),
            "address": data.get("address", {}).get("value", ""),
            "management": data.get("management", {}).get("name", ""),
        }
        if data.get("state", {}).get("status") == "LIQUIDATED":
            analysis["risk_signals"].append("Компания ликвидирована")

    casebook = source_data.get("casebook", {})
    if casebook and casebook.get("success"):
        cases = casebook.get("data", [])
        if cases:
            analysis["legal_cases"] = cases[:10]
            if len(cases) > 5:
                analysis["risk_signals"].append(f"Найдено {len(cases)} судебных дел")

    infosphere = source_data.get("infosphere", {})
    if infosphere and infosphere.get("success"):
        data = infosphere.get("data", {})
        if data:
            analysis["infosphere_data"] = data

    return analysis


async def report_analyzer_agent(
    state: Dict[str, Any],
    verbose_reasoning: bool = True,  # Enable Chain-of-Thought by default
) -> Dict[str, Any]:
    """
    Агент-анализатор с поддержкой Chain-of-Thought рассуждений.

    ИЗМЕНЕНИЯ (Sprint 5):
    - Добавлен режим verbose_reasoning с пошаговым анализом
    - LLM показывает рассуждения перед оценкой
    - Сохранение reasoning_trace для аудита

    Входные данные:
        - search_results: List[Dict] - результаты поиска (Perplexity/Tavily)
        - source_data: Dict - данные от источников (DaData/InfoSphere/Casebook)
        - client_name: str - название клиента
        - inn: str - ИНН
        - verbose_reasoning: bool - включить Chain-of-Thought (default: True)

    Выходные данные:
        - report: Dict - структурированный отчёт
        - reasoning_trace: Dict - трассировка рассуждений (если verbose_reasoning=True)
        - current_step: str
    """
    search_results = state.get("search_results", [])
    source_data = state.get("source_data", {})
    client_name = state.get("client_name", "Неизвестный клиент")
    inn = state.get("inn", "")
    additional_notes = state.get("additional_notes", "")

    # Check if verbose_reasoning is passed in state (for workflow control)
    if "verbose_reasoning" in state:
        verbose_reasoning = state["verbose_reasoning"]

    logger.info(
        f"Report Analyzer: создание отчёта для '{client_name}' (CoT={'enabled' if verbose_reasoning else 'disabled'})",
        component="analyzer",
    )

    # Подготовка данных для LLM
    source_summary = _prepare_source_data_for_llm(source_data, search_results)

    # Генерация отчёта через LLM
    additional_context = ""
    if additional_notes and additional_notes.strip():
        additional_context = f"""

ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ И КОНТЕКСТ:
{additional_notes}

ВАЖНО: Внимательно изучи дополнительные инструкции выше и обязательно учти их при анализе!
"""

    user_message = f"""Проанализируй данные о компании и создай отчёт.

КОМПАНИЯ: {client_name}
ИНН: {inn if inn else "не указан"}

ДАННЫЕ ИЗ ИСТОЧНИКОВ:
{source_summary}
{additional_context}
Создай JSON отчёт с оценкой рисков по формату из системного промпта."""

    # Select prompt based on verbose_reasoning mode
    prompt_role = AnalyzerRole.REPORT_ANALYZER_COT if verbose_reasoning else AnalyzerRole.REPORT_ANALYZER

    llm_report = await llm_generate_json(
        system_prompt=get_system_prompt(prompt_role),
        user_message=user_message,
        temperature=0.1 if verbose_reasoning else 0.2,  # Lower temperature for CoT
        max_tokens=6000 if verbose_reasoning else 4000,  # More tokens for reasoning
        fallback_on_error=None,  # Используем fallback логику при ошибке
    )

    # Проверка результата LLM
    reasoning_trace = None

    if llm_report and "risk_assessment" in llm_report and not llm_report.get("error"):
        # LLM успешно сгенерировал отчёт
        logger.info("Report Analyzer: using LLM-generated report", component="analyzer")

        risk_assessment = llm_report.get("risk_assessment", {})

        # Extract reasoning trace if available (from CoT prompt)
        if verbose_reasoning and "reasoning" in llm_report:
            reasoning_trace = llm_report.get("reasoning")
            logger.info(
                f"Report Analyzer: reasoning trace captured (factors: {len(reasoning_trace.get('risk_factors', []))})",
                component="analyzer",
            )

        # Вычисляем качество данных и failed источники
        total_sources = len(search_results) + len([v for v in source_data.values() if v])
        successful_sources_count = sum(1 for r in search_results if r.get("success")) + sum(
            1 for v in source_data.values() if v and v.get("success")
        )
        data_quality_percent = round(
            ((successful_sources_count / total_sources * 100) if total_sources > 0 else 0),
            1,
        )

        # Список failed источников для диагностики
        failed_sources = []
        for r in search_results:
            if not r.get("success"):
                failed_sources.append(
                    {
                        "source": r.get("source", "unknown"),
                        "intent": r.get("intent_id", ""),
                        "error": r.get("error", "Unknown error"),
                    }
                )
        for source_name, source_result in source_data.items():
            if source_result and not source_result.get("success"):
                failed_sources.append(
                    {
                        "source": source_name,
                        "error": source_result.get("error", "Unknown error"),
                    }
                )

        # Предупреждения если качество данных низкое
        data_warnings = []
        if data_quality_percent < 50:
            data_warnings.append(
                f"⚠️ ВНИМАНИЕ: Доступно только {successful_sources_count}/{total_sources} источников ({data_quality_percent}%). "
                "Анализ может быть неполным."
            )
        elif data_quality_percent < 80:
            data_warnings.append(
                f"⚠️ Некоторые источники недоступны ({successful_sources_count}/{total_sources}, {data_quality_percent}%). "
                "Результаты основаны на доступных данных."
            )

        # Добавляем метаданные
        report = {
            "metadata": {
                "client_name": client_name,
                "inn": inn,
                "analysis_date": datetime.now().isoformat(),
                "data_sources_count": total_sources,
                "successful_sources": successful_sources_count,
                "failed_sources_count": len(failed_sources),
                "data_quality_percent": data_quality_percent,
                "data_warnings": data_warnings,
                "failed_sources": failed_sources,  # Для debugging
                "llm_generated": True,
                "verbose_reasoning": verbose_reasoning,
                "has_reasoning_trace": reasoning_trace is not None,
            },
            "risk_assessment": risk_assessment,
            "summary": llm_report.get("summary", ""),
            "findings": llm_report.get("findings", []),
            "recommendations": llm_report.get("recommendations", []),
            "company_info": safe_dict_get(source_data, "dadata", "data", default={}),
            "legal_cases_count": _count_legal_cases(source_data),
            "citations": _extract_citations(search_results),
        }

        # Include reasoning in report if available
        if reasoning_trace:
            report["reasoning"] = reasoning_trace

    else:
        # Fallback: используем старую логику если LLM недоступен
        logger.warning(
            f"Report Analyzer: LLM failed, using fallback logic. Error: {llm_report.get('error') if llm_report else 'No response'}",
            component="analyzer",
        )
        report = await _generate_report_fallback(search_results, source_data, client_name, inn)

    # Нормализуем/валидируем отчёт по канонической схеме
    try:
        report_obj = ClientAnalysisReport.model_validate(report)
        report = report_obj.model_dump(mode="json")
    except Exception as e:
        logger.error(f"Report validation failed: {e}, using raw report", component="analyzer")

    risk_level = report.get("risk_assessment", {}).get("level", "unknown")
    logger.info(
        f"Report Analyzer: отчёт создан, уровень риска: {risk_level}",
        component="analyzer",
    )

    result = {
        **state,
        "report": report,
        "analysis_result": report.get("summary", ""),
        "current_step": "completed",
    }

    # Add reasoning trace to state for audit/display purposes
    if reasoning_trace:
        result["reasoning_trace"] = reasoning_trace

    return result


def generate_recommendations(risk: Dict[str, Any]) -> List[str]:
    """Генерирует рекомендации на основе оценки риска."""
    level = risk.get("level", "medium")

    recommendations = {
        "low": [
            "Клиент имеет низкий уровень риска",
            "Рекомендуется стандартная процедура проверки",
            "Можно рассмотреть льготные условия сотрудничества",
        ],
        "medium": [
            "Рекомендуется дополнительная проверка документов",
            "Запросить финансовую отчётность за последний период",
            "Проверить актуальность лицензий и разрешений",
        ],
        "high": [
            "Требуется углублённая проверка контрагента",
            "Рекомендуется личная встреча с руководством",
            "Рассмотреть возможность обеспечения сделки",
            "Проверить аффилированные компании",
        ],
        "critical": [
            "ВНИМАНИЕ: Критический уровень риска",
            "Рекомендуется отказ от сотрудничества",
            "При необходимости работы - максимальное обеспечение",
            "Обязательная юридическая экспертиза",
            "Рассмотреть предоплату 100%",
        ],
    }

    return recommendations.get(level, recommendations["medium"])


# =============================================================================
# P0: NEW HELPER FUNCTIONS FOR LLM-BASED ANALYSIS
# =============================================================================


def _sanitize_tavily_content(content: str) -> str:
    """
    Маскирует PII в контенте Tavily перед передачей в LLM.

    Tavily full_texts содержат неструктурированный текст веб-страниц,
    который может включать персональные данные третьих лиц.

    Args:
        content: Сырой текст страницы

    Returns:
        Текст с замаскированными персональными данными
    """
    if not content:
        return ""
    result = mask_pii(content)
    return result.masked_text


def _prepare_source_data_for_llm(source_data: Dict[str, Any], search_results: List[Dict]) -> str:
    """
    P0 ENHANCED: Подготовка данных для LLM анализа с полными текстами страниц.

    Форматирует source_data и search_results в читаемый текст для промпта.
    Включает полные тексты из TOP-5 Tavily ссылок для глубокого анализа.
    """
    parts = []

    # DaData
    if dadata := source_data.get("dadata"):
        if dadata.get("success") and (data := dadata.get("data")):
            parts.append("=== DADATA (ЕГРЮЛ) ===")
            parts.append(f"Название: {safe_dict_get(data, 'name', 'full_with_opf', default='N/A')}")
            parts.append(f"Статус: {safe_dict_get(data, 'state', 'status', default='N/A')}")
            parts.append(f"Дата регистрации: {safe_dict_get(data, 'state', 'registration_date', default='N/A')}")
            parts.append(f"Адрес: {safe_dict_get(data, 'address', 'value', default='N/A')}")
            parts.append("")

    # Casebook
    if casebook := source_data.get("casebook"):
        if casebook.get("success") and (data := casebook.get("data")):
            parts.append("=== CASEBOOK (Судебные дела) ===")
            if isinstance(data, list) and data:
                parts.append(f"Найдено дел: {len(data)}")
                for case in data[:5]:  # Первые 5 дел
                    case_num = case.get("case_number", "N/A")
                    parts.append(f"- Дело {case_num}: {truncate(str(case), 200)}")
            else:
                parts.append("Судебные дела не найдены")
            parts.append("")

    # Infosphere
    if infosphere := source_data.get("infosphere"):
        if infosphere.get("success") and (data := infosphere.get("data")):
            parts.append("=== ИНФОСФЕРА (Финансы) ===")
            parts.append(truncate(json.dumps(data, ensure_ascii=False), 500))
            parts.append("")

    # Search results (Perplexity + Tavily snippets)
    perplexity_results = [r for r in search_results if r.get("source") == "perplexity" and r.get("success")]
    tavily_results = [r for r in search_results if r.get("source") == "tavily" and r.get("success")]

    if perplexity_results:
        parts.append("=== PERPLEXITY (Веб-поиск за год, 20+ источников) ===")
        for r in perplexity_results[:3]:  # Первые 3
            parts.append(f"Запрос: {r.get('intent_id', 'N/A')}")
            parts.append(truncate(r.get("content", ""), 800))  # Увеличено с 500
            parts.append("")

    if tavily_results:
        parts.append("=== TAVILY (Структурированный поиск, 20 результатов) ===")
        for r in tavily_results[:3]:  # Первые 3
            parts.append(f"Запрос: {r.get('intent_id', 'N/A')}")
            parts.append(f"Ответ: {truncate(r.get('answer', ''), 500)}")
            parts.append("")

    # P0: НОВОЕ - Полные тексты страниц из Tavily (критично для глубокого анализа)
    # P1: PII маскирование перед передачей в LLM
    tavily_full_texts = source_data.get("tavily_full_texts", [])
    if tavily_full_texts:
        parts.append("=== ПОЛНЫЕ ТЕКСТЫ СТРАНИЦ (TOP-5 Tavily) ===")
        parts.append(f"Скрейплено страниц: {len(tavily_full_texts)}")
        parts.append("")

        for idx, page in enumerate(tavily_full_texts, 1):
            raw_content = page.get("full_content", "")
            if raw_content:
                # Маскируем PII в контенте перед передачей в LLM
                sanitized_content = _sanitize_tavily_content(raw_content)
                parts.append(f"--- Страница {idx}: {page.get('title', 'N/A')} ---")
                parts.append(f"URL: {page.get('url', 'N/A')}")
                parts.append(f"Текст ({len(sanitized_content)} символов):")
                parts.append(sanitized_content)
                parts.append("")

        total_chars = sum(len(_sanitize_tavily_content(p.get("full_content", ""))) for p in tavily_full_texts)
        parts.append(f"ИТОГО: {len(tavily_full_texts)} страниц, {total_chars} символов полного текста")
        parts.append("")

    return "\n".join(parts) if parts else "Нет данных из источников"


def _count_legal_cases(source_data: Dict[str, Any]) -> int:
    """Подсчёт количества судебных дел из Casebook."""
    casebook = source_data.get("casebook", {})
    if casebook.get("success"):
        data = casebook.get("data", [])
        if isinstance(data, list):
            return len(data)
    return 0


def _extract_citations(search_results: List[Dict]) -> List[str]:
    """Извлечение всех цитат из результатов поиска."""
    all_citations = []
    for result in search_results:
        if result.get("success"):
            all_citations.extend(result.get("citations", []))
    return list(set(all_citations))[:20]  # Уникальные, первые 20


async def _generate_report_fallback(
    search_results: List[Dict],
    source_data: Dict[str, Any],
    client_name: str,
    inn: str,
) -> Dict[str, Any]:
    """
    Fallback: генерация отчёта по старой логике.

    Используется если LLM недоступен или вернул ошибку.
    """
    source_analysis = analyze_source_data(source_data) if source_data else {}

    # Используем старый ручной расчёт (временно, пока не перешли на LLM)
    risk_assessment = _calculate_risk_fallback(search_results, source_analysis)

    summary = generate_summary(search_results, client_name)

    findings = []
    if source_analysis.get("company_info"):
        findings.append(
            {
                "category": "Информация о компании (DaData)",
                "sentiment": "neutral",
                "key_points": str(source_analysis["company_info"])[:300],
            }
        )

    for result in search_results:
        if result.get("success"):
            findings.append(
                {
                    "category": result.get("description", result.get("intent_id")),
                    "sentiment": result.get("sentiment", {}).get("label", "neutral"),
                    "key_points": truncate(result.get("content", ""), 300),
                }
            )

    # Вычисляем качество данных (аналогично основному пути)
    total_sources = len(search_results) + len([v for v in source_data.values() if v])
    successful_sources_count = sum(1 for r in search_results if r.get("success")) + sum(
        1 for v in source_data.values() if v and v.get("success")
    )
    data_quality_percent = round((successful_sources_count / total_sources * 100) if total_sources > 0 else 0, 1)

    # Список failed источников
    failed_sources = []
    for r in search_results:
        if not r.get("success"):
            failed_sources.append(
                {
                    "source": r.get("source", "unknown"),
                    "error": r.get("error", "Unknown error"),
                }
            )
    for source_name, source_result in source_data.items():
        if source_result and not source_result.get("success"):
            failed_sources.append(
                {
                    "source": source_name,
                    "error": source_result.get("error", "Unknown error"),
                }
            )

    # Предупреждения
    data_warnings = []
    if data_quality_percent < 50:
        data_warnings.append(
            f"⚠️ ВНИМАНИЕ: Доступно только {successful_sources_count}/{total_sources} источников ({data_quality_percent}%). "
            "Анализ может быть неполным."
        )
    elif data_quality_percent < 80:
        data_warnings.append(
            f"⚠️ Некоторые источники недоступны ({successful_sources_count}/{total_sources}, {data_quality_percent}%). "
            "Результаты основаны на доступных данных."
        )

    return {
        "metadata": {
            "client_name": client_name,
            "inn": inn,
            "analysis_date": datetime.now().isoformat(),
            "data_sources_count": total_sources,
            "successful_sources": successful_sources_count,
            "failed_sources_count": len(failed_sources),
            "data_quality_percent": data_quality_percent,
            "data_warnings": data_warnings,
            "failed_sources": failed_sources,
            "llm_generated": False,
        },
        "company_info": source_analysis.get("company_info", {}),
        "legal_cases_count": len(source_analysis.get("legal_cases", [])),
        "risk_assessment": risk_assessment,
        "findings": findings,
        "summary": summary,
        "citations": _extract_citations(search_results),
        "recommendations": generate_recommendations(risk_assessment),
    }


def _calculate_risk_fallback(search_results: List[Dict], source_analysis: Dict) -> Dict[str, Any]:
    """Fallback: ручной расчёт риска (старая логика)."""
    if not search_results:
        return {"score": 50, "level": "medium", "factors": ["Нет данных для анализа"]}

    factors = []
    risk_points = 50

    successful_results = [r for r in search_results if r.get("success")]

    if not successful_results:
        return {
            "score": 50,
            "level": "medium",
            "factors": ["Не удалось получить данные из источников"],
        }

    # Анализ sentiment
    for result in successful_results:
        sentiment = result.get("sentiment", {})
        label = sentiment.get("label", "neutral")
        intent_id = result.get("intent_id", "")

        if intent_id == "lawsuits" and label == "negative":
            risk_points += 15
            factors.append("Обнаружены судебные разбирательства")
        elif intent_id == "financial" and label == "negative":
            risk_points += 25
            factors.append("Проблемы с финансовым состоянием")
        elif intent_id == "reputation" and label == "negative":
            risk_points += 10
            factors.append("Негативные отзывы")

    # Добавляем сигналы из source_analysis
    for signal in source_analysis.get("risk_signals", []):
        factors.append(signal)
        risk_points = min(100, risk_points + 10)

    risk_points = max(0, min(100, risk_points))

    if risk_points < 25:
        level = "low"
    elif risk_points < 50:
        level = "medium"
    elif risk_points < 75:
        level = "high"
    else:
        level = "critical"

    if not factors:
        factors.append("Стандартный уровень риска")

    return {"score": risk_points, "level": level, "factors": factors[:10]}
