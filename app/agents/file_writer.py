"""
File Writer Agent: сохраняет отчёт в файл.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict

from app.utility.logging_client import logger

REPORTS_DIR = "reports"


def ensure_reports_dir():
    """Создаёт директорию для отчётов если её нет."""
    if not os.path.exists(REPORTS_DIR):
        os.makedirs(REPORTS_DIR)
        logger.info(
            f"Created reports directory: {REPORTS_DIR}", component="file_writer"
        )


def generate_filename(client_name: str, inn: str, session_id: str) -> str:
    """Генерирует имя файла для отчёта."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in client_name if c.isalnum() or c in " _-")[
        :30
    ].strip()
    safe_name = safe_name.replace(" ", "_") or "unknown"

    if inn:
        return f"{timestamp}_{safe_name}_{inn}"
    return f"{timestamp}_{safe_name}_{session_id[:8]}"


async def file_writer_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Агент записи файлов: сохраняет отчёт в файл.

    Входные данные:
        - report: Dict - структурированный отчёт
        - analysis_result: str - текстовое резюме
        - client_name: str
        - inn: str
        - session_id: str

    Выходные данные:
        - saved_files: Dict - пути к сохранённым файлам
        - current_step: str
    """
    report = state.get("report", {})
    summary = state.get("analysis_result", "")
    client_name = state.get("client_name", "Неизвестный")
    inn = state.get("inn", "")
    session_id = state.get("session_id", str(int(time.time())))

    if not report and not summary:
        logger.warning("No report data to save", component="file_writer")
        return {**state, "saved_files": {}, "current_step": "completed"}

    ensure_reports_dir()
    base_filename = generate_filename(client_name, inn, session_id)

    saved_files = {}

    try:
        md_filename = f"{base_filename}.md"
        md_path = os.path.join(REPORTS_DIR, md_filename)

        md_content = generate_markdown_report(report, summary, client_name, inn)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        saved_files["markdown"] = md_path
        logger.info(f"Saved markdown report: {md_path}", component="file_writer")

    except Exception as e:
        logger.error(f"Failed to save markdown report: {e}", component="file_writer")

    try:
        json_filename = f"{base_filename}.json"
        json_path = os.path.join(REPORTS_DIR, json_filename)

        json_report = {
            "metadata": report.get("metadata", {}),
            "risk_assessment": report.get("risk_assessment", {}),
            "findings": report.get("findings", []),
            "recommendations": report.get("recommendations", []),
            "citations": report.get("citations", []),
            "source_data_summary": state.get("collection_stats", {}),
            "generated_at": datetime.now().isoformat(),
            "session_id": session_id,
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)

        saved_files["json"] = json_path
        logger.info(f"Saved JSON report: {json_path}", component="file_writer")

    except Exception as e:
        logger.error(f"Failed to save JSON report: {e}", component="file_writer")

    logger.structured(
        "info",
        "files_saved",
        component="file_writer",
        files=list(saved_files.keys()),
        client_name=client_name[:30],
    )

    return {**state, "saved_files": saved_files, "current_step": "completed"}


def generate_markdown_report(
    report: Dict, summary: str, client_name: str, inn: str
) -> str:
    """Генерирует markdown-отчёт."""
    lines = []

    lines.append(f"# Отчёт по анализу клиента: {client_name}")
    lines.append("")
    lines.append(f"**Дата анализа:** {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    if inn:
        lines.append(f"**ИНН:** {inn}")
    lines.append("")

    risk = report.get("risk_assessment", {})
    if risk:
        lines.append("## Оценка риска")
        lines.append("")

        level_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
        level = risk.get("level", "medium")
        emoji = level_emoji.get(level, "⚪")

        lines.append(
            f"**Уровень риска:** {emoji} {level.upper()} ({risk.get('score', 0)}/100)"
        )
        lines.append("")

        factors = risk.get("factors", [])
        if factors:
            lines.append("### Факторы риска:")
            for factor in factors:
                lines.append(f"- {factor}")
            lines.append("")

    if summary:
        lines.append("## Резюме")
        lines.append("")
        lines.append(summary)
        lines.append("")

    recommendations = report.get("recommendations", [])
    if recommendations:
        lines.append("## Рекомендации")
        lines.append("")
        for rec in recommendations:
            lines.append(f"- {rec}")
        lines.append("")

    findings = report.get("findings", [])
    if findings:
        lines.append("## Детальные находки")
        lines.append("")
        for finding in findings:
            category = finding.get("category", "Общая информация")
            sentiment = finding.get("sentiment", "neutral")
            sentiment_icon = {"positive": "✅", "negative": "⚠️", "neutral": "ℹ️"}.get(
                sentiment, "ℹ️"
            )

            lines.append(f"### {sentiment_icon} {category}")
            if finding.get("key_points"):
                lines.append(finding["key_points"])
            lines.append("")

    citations = report.get("citations", [])
    if citations:
        lines.append("## Источники")
        lines.append("")
        for i, citation in enumerate(citations[:10], 1):
            lines.append(f"{i}. {citation}")
        lines.append("")

    lines.append("---")
    lines.append("*Отчёт сгенерирован автоматически системой анализа клиентов*")

    return "\n".join(lines)
