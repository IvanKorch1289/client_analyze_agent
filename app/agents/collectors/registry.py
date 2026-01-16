"""
Registry data collectors (DaData, Casebook, InfoSphere).

These collectors fetch data from government and commercial registries using INN.
"""

from typing import Any, Dict, Optional

from app.agents.collectors.base import BaseCollector, CollectorResult
from app.services.fetch_data import (
    fetch_from_casebook,
    fetch_from_dadata,
    fetch_from_infosphere,
)
from app.utility.logging_client import logger


class DaDataCollector(BaseCollector):
    """
    Collector for DaData EGRUL registry.

    Fetches company registration data from Russian unified state register.
    Fast response time (~1-5 seconds).
    """

    source_name = "dadata"
    default_timeout = 30

    async def _collect(self, inn: str = "", **kwargs) -> CollectorResult:
        """
        Fetch data from DaData.

        Args:
            inn: Company INN (10 or 12 digits)

        Returns:
            CollectorResult with EGRUL data
        """
        if not inn or not inn.isdigit() or len(inn) not in (10, 12):
            return CollectorResult(
                source=self.source_name,
                success=False,
                error="Invalid INN format",
            )

        result = await fetch_from_dadata(inn)

        if "error" in result:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=result.get("error"),
            )

        return CollectorResult(
            source=self.source_name,
            success=True,
            data=result.get("data", {}),
        )


class InfoSphereCollector(BaseCollector):
    """
    Collector for InfoSphere multi-database check.

    Checks company against 12+ databases:
    - FSSP (bailiffs)
    - Bankruptcy registry
    - Central Bank data
    - Federal Tax Service
    - And more

    Long response time (up to 6 minutes due to multi-page processing).
    """

    source_name = "infosphere"
    default_timeout = 360  # 6 minutes

    async def _collect(self, inn: str = "", **kwargs) -> CollectorResult:
        """
        Fetch data from InfoSphere.

        Args:
            inn: Company INN

        Returns:
            CollectorResult with multi-database check results
        """
        if not inn or not inn.isdigit():
            return CollectorResult(
                source=self.source_name,
                success=False,
                error="Invalid INN format",
            )

        logger.info(
            f"InfoSphere: starting fetch for INN {inn} (may take up to 6 min)",
            component="collector",
        )

        result = await fetch_from_infosphere(inn)

        logger.info(
            f"InfoSphere: fetch completed for INN {inn}",
            component="collector",
        )

        if "error" in result:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=result.get("error"),
            )

        return CollectorResult(
            source=self.source_name,
            success=True,
            data=result.get("data", {}),
        )


class CasebookCollector(BaseCollector):
    """
    Collector for Casebook arbitration court cases.

    Fetches all arbitration cases for a company.
    Long response time (up to 6 minutes for companies with 100+ cases).
    """

    source_name = "casebook"
    default_timeout = 360  # 6 minutes

    async def _collect(self, inn: str = "", **kwargs) -> CollectorResult:
        """
        Fetch court cases from Casebook.

        Args:
            inn: Company INN

        Returns:
            CollectorResult with list of court cases
        """
        if not inn or not inn.isdigit():
            return CollectorResult(
                source=self.source_name,
                success=False,
                error="Invalid INN format",
            )

        logger.info(
            f"Casebook: starting fetch for INN {inn} (may take up to 6 min)",
            component="collector",
        )

        result = await fetch_from_casebook(inn)

        cases = result.get("data", [])
        cases_count = len(cases) if cases else 0

        logger.info(
            f"Casebook: fetch completed for INN {inn}, found {cases_count} cases",
            component="collector",
        )

        if "error" in result:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=result.get("error"),
            )

        return CollectorResult(
            source=self.source_name,
            success=True,
            data=cases,
            metadata={"cases_count": cases_count},
        )


def convert_registry_to_search_result(
    source: str,
    data: Any,
) -> Optional[Dict[str, Any]]:
    """
    Convert registry collector result to search_results format.

    Args:
        source: Source name (dadata, casebook, infosphere)
        data: Raw data from collector

    Returns:
        Dictionary in search_results format or None
    """
    if source == "dadata" and data:
        content = f"Компания: {data.get('name', {}).get('full_with_opf', 'Н/Д')}\n"
        content += f"Статус: {data.get('state', {}).get('status', 'Н/Д')}\n"
        content += f"Адрес: {data.get('address', {}).get('value', 'Н/Д')}"

        status = data.get("state", {}).get("status", "")
        sentiment = (
            {"label": "negative", "score": -0.5}
            if status == "LIQUIDATED"
            else {"label": "neutral", "score": 0}
        )

        return {
            "intent_id": "dadata_info",
            "description": "Реестровые данные (DaData)",
            "query": "Информация из ЕГРЮЛ",
            "success": True,
            "content": content,
            "citations": [],
            "sentiment": sentiment,
        }

    if source == "casebook" and isinstance(data, list):
        case_count = len(data)
        content = f"Найдено судебных дел: {case_count}"
        if case_count > 0:
            content += f"\nПоследние дела: {', '.join([str(c.get('caseNumber', '')) for c in data[:5]])}"

        if case_count > 10:
            sentiment = {"label": "negative", "score": -0.7}
        elif case_count > 3:
            sentiment = {"label": "negative", "score": -0.3}
        else:
            sentiment = {"label": "neutral", "score": 0}

        return {
            "intent_id": "lawsuits",
            "description": "Судебные дела (Casebook)",
            "query": "Арбитражные дела",
            "success": True,
            "content": content,
            "citations": [],
            "sentiment": sentiment,
        }

    if source == "infosphere" and data:
        content = f"Проверка по базам: {len(data) if isinstance(data, list) else 'выполнена'}"
        return {
            "intent_id": "infosphere_check",
            "description": "Проверка контрагента (InfoSphere)",
            "query": "Проверка по базам данных",
            "success": True,
            "content": content,
            "citations": [],
            "sentiment": {"label": "neutral", "score": 0},
        }

    return None
