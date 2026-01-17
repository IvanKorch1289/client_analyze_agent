"""
Government API collectors for Russian company data.

Provides collectors for free public APIs:
- FNS (ФНС) - EGRUL/EGRIP data from nalog.ru
- FSSP (ФССП) - Enforcement proceedings data
- Bankrot (ЕФРСБ) - Bankruptcy registry data
"""

import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from app.agents.collectors.base import BaseCollector, CollectorResult
from app.config import settings
from app.utility.logging_client import logger


class FNSCollector(BaseCollector):
    """
    Collector for FNS (ФНС) data from egrul.nalog.ru.

    Free API for:
    - EGRUL/EGRIP extracts
    - Company status
    - Registration information

    Note: This is a public web API, not an official REST API.
    Rate limiting and availability may vary.
    """

    source_name = "fns"
    default_timeout = 30

    BASE_URL = "https://egrul.nalog.ru"

    async def _collect(
        self,
        inn: str,
        **kwargs,
    ) -> CollectorResult:
        """
        Fetch company data from FNS by INN.

        Args:
            inn: Company INN (10 digits) or individual INN (12 digits)

        Returns:
            CollectorResult with EGRUL data
        """
        if not inn or not inn.isdigit() or len(inn) not in (10, 12):
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=f"Invalid INN format: {inn}",
            )

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Initiate search
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json, text/javascript, */*",
                    "Content-Type": "application/x-www-form-urlencoded",
                }

                # FNS uses a specific search endpoint
                search_data = {"vyession": "1", "query": inn, "region": ""}

                async with session.post(
                    f"{self.BASE_URL}/",
                    data=search_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=False,
                ) as resp:
                    if resp.status != 200:
                        return CollectorResult(
                            source=self.source_name,
                            success=False,
                            error=f"FNS search failed: HTTP {resp.status}",
                        )

                    search_result = await resp.json()
                    token = search_result.get("t")

                    if not token:
                        # No token means no results found
                        return CollectorResult(
                            source=self.source_name,
                            success=True,
                            data={
                                "found": False,
                                "inn": inn,
                                "message": "Компания не найдена в ЕГРЮЛ/ЕГРИП",
                            },
                        )

                # Step 2: Wait for processing
                await asyncio.sleep(1.5)

                # Step 3: Get results
                results_url = f"{self.BASE_URL}/search-result/{token}"
                async with session.get(
                    results_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as resp:
                    if resp.status != 200:
                        return CollectorResult(
                            source=self.source_name,
                            success=False,
                            error=f"FNS results failed: HTTP {resp.status}",
                        )

                    results = await resp.json()
                    rows = results.get("rows", [])

                    if not rows:
                        return CollectorResult(
                            source=self.source_name,
                            success=True,
                            data={
                                "found": False,
                                "inn": inn,
                                "message": "Компания не найдена",
                            },
                        )

                    # Extract relevant data
                    company_data = rows[0] if rows else {}
                    return CollectorResult(
                        source=self.source_name,
                        success=True,
                        data={
                            "found": True,
                            "inn": inn,
                            "total_found": results.get("cnt", 1),
                            "company": {
                                "name": company_data.get("n", ""),
                                "full_name": company_data.get("c", ""),
                                "ogrn": company_data.get("o", ""),
                                "inn": company_data.get("i", ""),
                                "kpp": company_data.get("p", ""),
                                "address": company_data.get("a", ""),
                                "status": company_data.get("s", ""),
                                "registration_date": company_data.get("r", ""),
                                "termination_date": company_data.get("e", ""),
                            },
                            "source_url": f"{self.BASE_URL}",
                        },
                    )

        except aiohttp.ClientError as e:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=f"Network error: {str(e)[:200]}",
            )
        except Exception as e:
            logger.error(f"FNS collector error: {e}", component="collector")
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=str(e)[:200],
            )


class FSSPCollector(BaseCollector):
    """
    Collector for FSSP (ФССП) enforcement proceedings.

    Uses the official FSSP API (requires free registration for token).
    API docs: https://api-ip.fssprus.ru/api/swagger/index.html

    Note: If no token configured, attempts fallback to public search.
    """

    source_name = "fssp"
    default_timeout = 30

    BASE_URL = "https://api-ip.fssprus.ru/api/v1.0"
    PUBLIC_URL = "https://fssp.gov.ru/iss/ip"

    def __init__(self, api_token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._api_token = api_token or getattr(getattr(settings, "fssp", None), "api_token", None)

    def is_configured(self) -> bool:
        """FSSP requires API token for full functionality."""
        return bool(self._api_token)

    async def _collect(
        self,
        inn: Optional[str] = None,
        client_name: Optional[str] = None,
        region: Optional[str] = None,
        **kwargs,
    ) -> CollectorResult:
        """
        Search for enforcement proceedings.

        Args:
            inn: Company INN
            client_name: Company name (fallback if no INN)
            region: Region code (optional)

        Returns:
            CollectorResult with enforcement proceedings data
        """
        if not inn and not client_name:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error="Either INN or company name is required",
            )

        # If no API token, return info about configuration
        if not self._api_token:
            return CollectorResult(
                source=self.source_name,
                success=True,
                data={
                    "configured": False,
                    "message": "FSSP API token not configured. Get free token at fssp.gov.ru",
                    "manual_check_url": f"{self.PUBLIC_URL}",
                    "search_query": inn or client_name,
                },
                metadata={"requires_configuration": True},
            )

        try:
            headers = {"Authorization": f"Bearer {self._api_token}"}
            params: Dict[str, Any] = {}

            # Build search parameters
            if inn:
                params["inn"] = inn
            else:
                params["name"] = client_name

            if region:
                params["region"] = region

            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/search/legal"
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    if resp.status == 401:
                        return CollectorResult(
                            source=self.source_name,
                            success=False,
                            error="Invalid FSSP API token",
                        )
                    elif resp.status == 429:
                        return CollectorResult(
                            source=self.source_name,
                            success=False,
                            error="FSSP API rate limit exceeded",
                        )
                    elif resp.status != 200:
                        return CollectorResult(
                            source=self.source_name,
                            success=False,
                            error=f"FSSP API error: HTTP {resp.status}",
                        )

                    data = await resp.json()
                    proceedings = data.get("result", [])

                    # Calculate statistics
                    total_debt = sum(float(p.get("ip_sum", 0) or 0) for p in proceedings)
                    active_count = sum(1 for p in proceedings if p.get("ip_end") is None)

                    return CollectorResult(
                        source=self.source_name,
                        success=True,
                        data={
                            "found": len(proceedings) > 0,
                            "proceedings": proceedings[:50],  # Limit to 50
                            "total_count": len(proceedings),
                            "active_count": active_count,
                            "closed_count": len(proceedings) - active_count,
                            "total_debt": round(total_debt, 2),
                            "has_active_proceedings": active_count > 0,
                            "risk_signal": (
                                f"Найдено {active_count} активных исполнительных производств "
                                f"на сумму {total_debt:,.2f} руб."
                                if active_count > 0
                                else None
                            ),
                        },
                    )

        except aiohttp.ClientError as e:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=f"Network error: {str(e)[:200]}",
            )
        except Exception as e:
            logger.error(f"FSSP collector error: {e}", component="collector")
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=str(e)[:200],
            )


class BankrotCollector(BaseCollector):
    """
    Collector for EFRSB (ЕФРСБ) bankruptcy registry.

    Uses the Fedresurs public API for bankruptcy information.
    API docs: https://bankrot.fedresurs.ru/

    Free to use, no registration required.
    """

    source_name = "bankrot"
    default_timeout = 45

    BASE_URL = "https://bankrot.fedresurs.ru"
    API_URL = "https://bankrot.fedresurs.ru/api"

    async def _collect(
        self,
        inn: str,
        client_name: Optional[str] = None,
        **kwargs,
    ) -> CollectorResult:
        """
        Search for bankruptcy records by INN.

        Args:
            inn: Company INN
            client_name: Company name (optional, for logging)

        Returns:
            CollectorResult with bankruptcy data
        """
        if not inn:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error="INN is required for bankruptcy search",
            )

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                }

                # Search for debtor by INN via API endpoint
                api_url = f"{self.API_URL}/Search"
                async with session.get(
                    api_url,
                    params={"searchString": inn, "type": "Debtor"},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                    ssl=False,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        debtors = data.get("pageData", [])
                    else:
                        # Fallback: return manual check info
                        return CollectorResult(
                            source=self.source_name,
                            success=True,
                            data={
                                "found": False,
                                "is_bankrupt": False,
                                "manual_check_required": True,
                                "manual_check_url": f"{self.BASE_URL}/DebtorsSearch.aspx",
                                "search_inn": inn,
                                "message": "Автоматический поиск недоступен. Проверьте вручную.",
                            },
                        )

                if not debtors:
                    return CollectorResult(
                        source=self.source_name,
                        success=True,
                        data={
                            "found": False,
                            "is_bankrupt": False,
                            "inn": inn,
                            "messages": [],
                            "stage": None,
                            "message": "Компания не найдена в реестре банкротств",
                        },
                    )

                # Found debtor - get details
                debtor = debtors[0]
                debtor_id = debtor.get("id")
                debtor_name = debtor.get("name", "")

                # Try to get messages/stages
                messages: List[Dict[str, Any]] = []
                latest_stage = None

                if debtor_id:
                    try:
                        messages_url = f"{self.API_URL}/Debtors/{debtor_id}/Messages"
                        async with session.get(
                            messages_url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=15),
                            ssl=False,
                        ) as msg_resp:
                            if msg_resp.status == 200:
                                msg_data = await msg_resp.json()
                                messages = msg_data.get("pageData", [])[:20]
                                if messages:
                                    latest_stage = messages[0].get("type")
                    except Exception:
                        pass  # Continue without messages

                # Determine bankruptcy stage
                stage_mapping = {
                    "Наблюдение": "observation",
                    "Финансовое оздоровление": "financial_recovery",
                    "Внешнее управление": "external_management",
                    "Конкурсное производство": "bankruptcy_proceedings",
                    "Мировое соглашение": "settlement",
                }

                normalized_stage = stage_mapping.get(latest_stage, latest_stage)

                return CollectorResult(
                    source=self.source_name,
                    success=True,
                    data={
                        "found": True,
                        "is_bankrupt": True,
                        "inn": inn,
                        "debtor_info": {
                            "id": debtor_id,
                            "name": debtor_name,
                            "inn": debtor.get("inn", inn),
                            "ogrn": debtor.get("ogrn", ""),
                            "address": debtor.get("address", ""),
                            "region": debtor.get("region", ""),
                        },
                        "messages_count": len(messages),
                        "latest_stage": latest_stage,
                        "normalized_stage": normalized_stage,
                        "risk_signal": f"CRITICAL: Компания в процедуре банкротства ({latest_stage or 'неизвестная стадия'})",
                        "risk_level": "critical",
                        "detail_url": (f"{self.BASE_URL}/Debtor?id={debtor_id}" if debtor_id else None),
                    },
                )

        except aiohttp.ClientError as e:
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=f"Network error: {str(e)[:200]}",
            )
        except Exception as e:
            logger.error(f"Bankrot collector error: {e}", component="collector")
            return CollectorResult(
                source=self.source_name,
                success=False,
                error=str(e)[:200],
            )


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


async def collect_government_data(
    inn: str,
    client_name: Optional[str] = None,
    include_fns: bool = True,
    include_fssp: bool = True,
    include_bankrot: bool = True,
) -> Dict[str, CollectorResult]:
    """
    Collect data from all government sources in parallel.

    Args:
        inn: Company INN
        client_name: Company name (optional)
        include_fns: Include FNS (EGRUL) data
        include_fssp: Include FSSP (enforcement) data
        include_bankrot: Include bankruptcy data

    Returns:
        Dict mapping source name to CollectorResult
    """
    tasks = {}

    if include_fns:
        fns = FNSCollector()
        tasks["fns"] = fns.collect(inn=inn)

    if include_fssp:
        fssp = FSSPCollector()
        tasks["fssp"] = fssp.collect(inn=inn, client_name=client_name)

    if include_bankrot:
        bankrot = BankrotCollector()
        tasks["bankrot"] = bankrot.collect(inn=inn, client_name=client_name)

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    output = {}
    for name, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            output[name] = CollectorResult(
                source=name,
                success=False,
                error=str(result)[:200],
            )
        else:
            output[name] = result

    return output


__all__ = [
    "FNSCollector",
    "FSSPCollector",
    "BankrotCollector",
    "collect_government_data",
]
