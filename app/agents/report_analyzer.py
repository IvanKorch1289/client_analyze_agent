"""
Report Analyzer Agent: анализирует результаты поиска и создаёт итоговый отчёт.

Ключевой контракт: итоговый `report` соответствует модели
`app.schemas.report.ClientAnalysisReport`.
"""

from datetime import datetime
from typing import Any, Dict, List

from app.utility.logging_client import logger
from app.schemas.report import ClientAnalysisReport


def calculate_risk_score(search_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Рассчитывает общую оценку риска на основе результатов поиска.
    Returns: {"score": 0-100, "level": "low"|"medium"|"high"|"critical", "factors": [...]}
    """
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

    sentiment_scores = []
    for result in successful_results:
        sentiment = result.get("sentiment", {})
        score = sentiment.get("score", 0)
        sentiment_scores.append(score)

        intent_id = result.get("intent_id", "")
        label = sentiment.get("label", "neutral")

        if intent_id == "lawsuits" and label == "negative":
            risk_points += 15
            factors.append("Обнаружены судебные разбирательства")
        elif intent_id == "negative" and label == "negative":
            risk_points += 20
            factors.append("Найдена негативная информация в СМИ")
        elif intent_id == "financial" and label == "negative":
            risk_points += 25
            factors.append("Проблемы с финансовым состоянием")
        elif intent_id == "reputation" and label == "negative":
            risk_points += 10
            factors.append("Негативные отзывы клиентов")

        if label == "positive":
            if intent_id == "reputation":
                risk_points -= 10
                factors.append("Положительная репутация")
            elif intent_id == "financial":
                risk_points -= 15
                factors.append("Стабильное финансовое положение")

    avg_sentiment = (
        sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
    )
    risk_points -= int(avg_sentiment * 10)

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

    return {"score": risk_points, "level": level, "factors": factors[:5]}


def generate_summary(search_results: List[Dict[str, Any]], client_name: str) -> str:
    """Генерирует текстовое резюме на основе результатов поиска."""
    if not search_results:
        return f"Не удалось собрать информацию о клиенте {client_name}."

    successful = [r for r in search_results if r.get("success")]

    if not successful:
        return f"Все поисковые запросы завершились с ошибкой для клиента {client_name}."

    summary_parts = [f"## Анализ клиента: {client_name}\n"]
    summary_parts.append(
        f"*Дата анализа: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
    )

    for result in successful:
        intent_id = result.get("intent_id", "")
        description = result.get("description", intent_id)
        content = result.get("content", "")
        sentiment = result.get("sentiment", {})

        sentiment_icon = {"positive": "+", "negative": "-", "neutral": "~"}.get(
            sentiment.get("label", "neutral"), "~"
        )

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


async def report_analyzer_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Агент-анализатор: создаёт итоговый отчёт с оценкой рисков.

    Входные данные:
        - search_results: List[Dict] - результаты поиска (Perplexity/Tavily)
        - source_data: Dict - данные от источников (DaData/InfoSphere/Casebook)
        - client_name: str - название клиента
        - inn: str - ИНН

    Выходные данные:
        - report: Dict - структурированный отчёт
        - current_step: str
    """
    search_results = state.get("search_results", [])
    source_data = state.get("source_data", {})
    client_name = state.get("client_name", "Неизвестный клиент")
    inn = state.get("inn", "")

    logger.info(
        f"Report Analyzer: создание отчёта для '{client_name}'", component="analyzer"
    )

    source_analysis = analyze_source_data(source_data) if source_data else {}

    risk_assessment = calculate_risk_score(search_results)

    for signal in source_analysis.get("risk_signals", []):
        risk_assessment["factors"].append(signal)
        risk_assessment["score"] = min(100, risk_assessment["score"] + 10)

    if risk_assessment["score"] >= 75:
        risk_assessment["level"] = "critical"
    elif risk_assessment["score"] >= 50:
        risk_assessment["level"] = "high"
    elif risk_assessment["score"] >= 25:
        risk_assessment["level"] = "medium"

    summary = generate_summary(search_results, client_name)

    all_citations = []
    findings = []

    if source_analysis.get("company_info"):
        findings.append(
            {
                "category": "Информация о компании (DaData)",
                "sentiment": "neutral",
                "key_points": str(source_analysis["company_info"])[:300],
            }
        )

    if source_analysis.get("legal_cases"):
        case_count = len(source_analysis["legal_cases"])
        findings.append(
            {
                "category": f"Судебные дела (Casebook): {case_count}",
                "sentiment": "negative" if case_count > 3 else "neutral",
                "key_points": f"Найдено {case_count} судебных дел",
            }
        )

    for result in search_results:
        if result.get("success"):
            all_citations.extend(result.get("citations", []))
            findings.append(
                {
                    "category": result.get("description", result.get("intent_id")),
                    "sentiment": result.get("sentiment", {}).get("label", "neutral"),
                    "key_points": (
                        result.get("content", "")[:300] if result.get("content") else ""
                    ),
                }
            )

    successful_sources = sum(1 for v in source_data.values() if v and v.get("success"))

    report = {
        "metadata": {
            "client_name": client_name,
            "inn": inn,
            "analysis_date": datetime.now().isoformat(),
            "data_sources_count": len(search_results)
            + len([v for v in source_data.values() if v]),
            "successful_sources": sum(1 for r in search_results if r.get("success"))
            + successful_sources,
        },
        "company_info": source_analysis.get("company_info", {}),
        "legal_cases_count": len(source_analysis.get("legal_cases", [])),
        "risk_assessment": risk_assessment,
        "findings": findings,
        "summary": summary,
        "citations": list(set(all_citations))[:20],
        "recommendations": generate_recommendations(risk_assessment),
    }

    # Нормализуем/валидируем отчёт по канонической схеме.
    # Если схема не сходится — это ошибка разработки (лучше упасть, чем писать неконсистентный report).
    report_obj = ClientAnalysisReport.model_validate(report)
    report = report_obj.model_dump(mode="json")

    logger.info(
        f"Report Analyzer: отчёт создан, уровень риска: {risk_assessment['level']}",
        component="analyzer",
    )

    return {
        **state,
        "report": report,
        "analysis_result": summary,
        "current_step": "completed",
    }


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
