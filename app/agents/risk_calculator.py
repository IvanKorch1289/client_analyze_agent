"""
Калькулятор риск-скора с нормализацией.

ПРОБЛЕМА: 100 судебных дел = 75 баллов - это завышено.
РЕШЕНИЕ: Нормализованный расчёт с категориями и весами.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple

from app.shared.toolkit.logging import logger


class RiskCategory(str, Enum):
    """Категории риска."""

    LEGAL = "legal"
    FINANCIAL = "financial"
    REPUTATION = "reputation"
    REGULATORY = "regulatory"


@dataclass
class RiskFactor:
    """
    Один риск-фактор.

    Attributes:
        category: Категория риска
        description: Описание фактора
        severity: Уровень серьёзности (critical/high/medium/low)
        score_contribution: Сколько баллов добавляет (0-40)
        source: Источник данных (dadata/casebook/infosphere/perplexity/tavily)
        evidence: Доказательство (опционально)
    """

    category: RiskCategory
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    score_contribution: int
    source: str
    evidence: Optional[str] = None


@dataclass(frozen=True)
class RiskThresholds:
    """Configurable risk score thresholds (extracted from magic numbers)."""

    # Risk level boundaries (final score 0-100)
    critical_level: int = 75
    high_level: int = 50
    medium_level: int = 25

    # Legal: defendant case counts → scores
    bankruptcy_base: int = 30
    bankruptcy_per_case: int = 3
    defendant_100_plus: int = 25
    defendant_50_plus: int = 20
    defendant_20_plus: int = 15
    defendant_10_plus: int = 10
    defendant_any: int = 5
    plaintiff_discount: int = 3

    # Financial thresholds
    critical_liquidity: float = 0.5
    critical_liquidity_score: int = 28
    low_liquidity: float = 1.0
    low_liquidity_score: int = 18
    high_debt_ratio: float = 0.8
    high_debt_score: int = 20
    medium_debt_ratio: float = 0.6
    medium_debt_score: int = 10
    low_credit_score: int = 25
    medium_credit_score: int = 15
    no_financial_data_score: int = 10

    # Reputation
    scandal_base: int = 10
    scandal_per_count: int = 3
    scandal_max: int = 20
    multiple_negative_score: int = 15
    few_negative_score: int = 5
    negative_count_threshold: int = 3

    # Regulatory
    sanction_score: int = 15
    regulatory_issue_score: int = 5


# Default thresholds (can be overridden for testing or per-deployment tuning)
DEFAULT_THRESHOLDS = RiskThresholds()


class RiskScoreCalculator:
    """
    Калькулятор итогового риск-скора (0-100).

    Формула расчёта:
    1. Собрать факторы риска из ВСЕХ источников
    2. Нормализовать counts (относительные, не абсолютные)
    3. Расставить severity (крит > высокий > средний > низкий)
    4. Рассчитать total_score с весами
    5. Привести к шкале 0-100

    Примеры нормализации:
    - 100 судебных дел с severity=HIGH → 25 баллов (не 75!)
    - 1 дело о банкротстве severity=CRITICAL → 40 баллов
    - Ликвидация status=LIQUIDATING → 45+ баллов (критично)
    """

    WEIGHTS = {
        RiskCategory.LEGAL: 0.35,
        RiskCategory.FINANCIAL: 0.30,
        RiskCategory.REPUTATION: 0.20,
        RiskCategory.REGULATORY: 0.15,
    }

    MAX_SCORE_PER_CATEGORY = {
        RiskCategory.LEGAL: 40,
        RiskCategory.FINANCIAL: 30,
        RiskCategory.REPUTATION: 20,
        RiskCategory.REGULATORY: 15,
    }

    def __init__(self, thresholds: Optional[RiskThresholds] = None):
        self.t = thresholds or DEFAULT_THRESHOLDS

    def calculate_risk_score(
        self,
        source_data: Dict[str, Any],
        search_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[int, List[RiskFactor], str]:
        """
        Рассчитать итоговый риск-скор на основе данных из всех источников.

        Args:
            source_data: Данные из источников (dadata, casebook, infosphere)
            search_results: Результаты веб-поиска (perplexity, tavily)

        Returns:
            Tuple[int, List[RiskFactor], str]:
                - risk_score: 0-100
                - factors: Список факторов риска с объяснением
                - level: Уровень риска (low/medium/high/critical)
        """
        factors: List[RiskFactor] = []
        search_results = search_results or []

        logger.info("Расчёт риск-скора с нормализацией", component="risk_calculator")

        legal_score = self._calculate_legal_risk(source_data, factors)
        financial_score = self._calculate_financial_risk(source_data, factors)
        reputation_score = self._calculate_reputation_risk(search_results, factors)
        regulatory_score = self._calculate_regulatory_risk(source_data, search_results, factors)

        max_possible = sum(self.MAX_SCORE_PER_CATEGORY.values())
        raw_score = legal_score + financial_score + reputation_score + regulatory_score

        normalized_score = (raw_score / max_possible) * 100 if max_possible > 0 else 0

        final_score = min(100, max(0, int(normalized_score)))

        if final_score >= self.t.critical_level:
            level = "critical"
        elif final_score >= self.t.high_level:
            level = "high"
        elif final_score >= self.t.medium_level:
            level = "medium"
        else:
            level = "low"

        logger.info(
            f"Риск-скор: {final_score}/100, уровень: {level}, факторов: {len(factors)}",
            component="risk_calculator",
        )

        return final_score, factors, level

    def _calculate_legal_risk(
        self,
        source_data: Dict[str, Any],
        factors: List[RiskFactor],
    ) -> int:
        """
        Рассчитать правовой риск на основе судебных дел и статуса компании.

        КРИТЕРИИ:
        - Статус LIQUIDATING/BANKRUPT → +40 (критично!)
        - Банкротные дела → +35-40
        - Ответчик в 100+ делах → +25 (нормализованно!)
        - Ответчик в 50+ делах → +20
        - Ответчик в 10-50 делах → +15
        - Ответчик в <10 делах → +5-10
        - Истец → -3 (хороший знак)
        """
        score = 0
        max_score = self.MAX_SCORE_PER_CATEGORY[RiskCategory.LEGAL]

        dadata = source_data.get("dadata", {})
        casebook = source_data.get("casebook", {})

        if dadata.get("success") or dadata.get("status") == "success":
            data = dadata.get("data", {})
            company_status = data.get("state", {}).get("status", "").upper()

            if company_status in ["LIQUIDATING", "LIQUIDATED", "BANKRUPT"]:
                score = max_score
                factors.append(
                    RiskFactor(
                        category=RiskCategory.LEGAL,
                        description="⚠️ КРИТИЧЕСКИЙ СТАТУС: Компания в процессе ликвидации/банкротства",
                        severity="critical",
                        score_contribution=max_score,
                        source="dadata",
                        evidence=f"Статус компании: {company_status}",
                    )
                )
                return score
            elif company_status == "ACTIVE":
                factors.append(
                    RiskFactor(
                        category=RiskCategory.LEGAL,
                        description="✅ Компания активна и зарегистрирована",
                        severity="low",
                        score_contribution=0,
                        source="dadata",
                        evidence=f"Статус: {company_status}",
                    )
                )

        if casebook.get("success") or casebook.get("status") == "success":
            cases = casebook.get("data", [])
            if isinstance(cases, list):
                total_cases = len(cases)

                bankruptcy_cases = [
                    c
                    for c in cases
                    if "банкротство" in str(c.get("category", "")).lower()
                    or "банкротство" in str(c.get("case_name", "")).lower()
                ]
                defendant_cases = [c for c in cases if c.get("role") == "defendant"]
                plaintiff_cases = [c for c in cases if c.get("role") == "plaintiff"]

                if bankruptcy_cases:
                    bankruptcy_score = min(max_score, self.t.bankruptcy_base + len(bankruptcy_cases) * self.t.bankruptcy_per_case)
                    score += bankruptcy_score
                    factors.append(
                        RiskFactor(
                            category=RiskCategory.LEGAL,
                            description=f"🔴 Банкротные дела: {len(bankruptcy_cases)} дел(о/а)",
                            severity="critical",
                            score_contribution=bankruptcy_score,
                            source="casebook",
                            evidence=f"Обнаружено {len(bankruptcy_cases)} дел о банкротстве",
                        )
                    )

                defendant_count = len(defendant_cases) if defendant_cases else total_cases

                if defendant_count >= 100:
                    defendant_score = self.t.defendant_100_plus
                    severity: Literal["critical", "high", "medium", "low"] = "high"
                elif defendant_count >= 50:
                    defendant_score = self.t.defendant_50_plus
                    severity = "high"
                elif defendant_count >= 20:
                    defendant_score = self.t.defendant_20_plus
                    severity = "medium"
                elif defendant_count >= 10:
                    defendant_score = self.t.defendant_10_plus
                    severity = "medium"
                elif defendant_count > 0:
                    defendant_score = self.t.defendant_any
                    severity = "low"
                else:
                    defendant_score = 0
                    severity = "low"

                if defendant_score > 0 and not bankruptcy_cases:
                    score += defendant_score
                    factors.append(
                        RiskFactor(
                            category=RiskCategory.LEGAL,
                            description=f"⚖️ Судебные дела: {defendant_count} дел",
                            severity=severity,
                            score_contribution=defendant_score,
                            source="casebook",
                            evidence=f"Компания участвует в {defendant_count} судебных делах",
                        )
                    )

                if plaintiff_cases and not bankruptcy_cases:
                    score = max(0, score - self.t.plaintiff_discount)
                    factors.append(
                        RiskFactor(
                            category=RiskCategory.LEGAL,
                            description=f"✅ Инициирует судебные дела: {len(plaintiff_cases)} исков",
                            severity="low",
                            score_contribution=-3,
                            source="casebook",
                            evidence=f"Компания защищает свои интересы ({len(plaintiff_cases)} исков)",
                        )
                    )

        return min(max_score, score)

    def _calculate_financial_risk(
        self,
        source_data: Dict[str, Any],
        factors: List[RiskFactor],
    ) -> int:
        """
        Рассчитать финансовый риск на основе данных InfoSphere и DaData.

        КРИТЕРИИ:
        - Ликвидность < 0.5 → +28 (критически низко)
        - Ликвидность 0.5-1.0 → +18 (ниже нормы)
        - Долг > 0.8 → +20 (перелевериджид)
        - Кредитный рейтинг < BBB → +15-25
        - Отсутствие финансовых данных → +10
        """
        score = 0
        max_score = self.MAX_SCORE_PER_CATEGORY[RiskCategory.FINANCIAL]

        infosphere = source_data.get("infosphere", {})

        if infosphere.get("success") or infosphere.get("status") == "success":
            data = infosphere.get("data", {})

            liquidity = data.get("liquidity_ratio")
            if liquidity is not None:
                try:
                    liquidity = float(liquidity)
                    if liquidity < self.t.critical_liquidity:
                        score += self.t.critical_liquidity_score
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="🔴 КРИТИЧЕСКАЯ ликвидность",
                                severity="critical",
                                score_contribution=self.t.critical_liquidity_score,
                                source="infosphere",
                                evidence=f"Коэффициент ликвидности: {liquidity:.2f} (критически низко)",
                            )
                        )
                    elif liquidity < self.t.low_liquidity:
                        score += self.t.low_liquidity_score
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="⚠️ Низкая ликвидность",
                                severity="high",
                                score_contribution=self.t.low_liquidity_score,
                                source="infosphere",
                                evidence=f"Коэффициент ликвидности: {liquidity:.2f} (ниже нормы)",
                            )
                        )
                    else:
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="✅ Здоровая ликвидность",
                                severity="low",
                                score_contribution=0,
                                source="infosphere",
                                evidence=f"Коэффициент ликвидности: {liquidity:.2f}",
                            )
                        )
                except (ValueError, TypeError):
                    pass

            debt_ratio = data.get("debt_ratio")
            if debt_ratio is not None:
                try:
                    debt_ratio = float(debt_ratio)
                    if debt_ratio > self.t.high_debt_ratio:
                        score += self.t.high_debt_score
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="⚠️ Высокая долговая нагрузка",
                                severity="high",
                                score_contribution=self.t.high_debt_score,
                                source="infosphere",
                                evidence=f"Коэффициент долга: {debt_ratio:.2f} (высокий)",
                            )
                        )
                    elif debt_ratio > self.t.medium_debt_ratio:
                        score += self.t.medium_debt_score
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="⚠️ Повышенная долговая нагрузка",
                                severity="medium",
                                score_contribution=self.t.medium_debt_score,
                                source="infosphere",
                                evidence=f"Коэффициент долга: {debt_ratio:.2f}",
                            )
                        )
                except (ValueError, TypeError):
                    pass

            credit_rating = data.get("credit_rating", "").upper()
            low_ratings = ["CCC", "CC", "C", "D", "NR"]
            medium_ratings = ["BB", "BB+", "BB-", "B", "B+", "B-"]

            if any(r in credit_rating for r in low_ratings):
                score += self.t.low_credit_score
                factors.append(
                    RiskFactor(
                        category=RiskCategory.FINANCIAL,
                        description="🔴 Низкий кредитный рейтинг",
                        severity="critical",
                        score_contribution=self.t.low_credit_score,
                        source="infosphere",
                        evidence=f"Кредитный рейтинг: {credit_rating}",
                    )
                )
            elif any(r in credit_rating for r in medium_ratings):
                score += self.t.medium_credit_score
                factors.append(
                    RiskFactor(
                        category=RiskCategory.FINANCIAL,
                        description="⚠️ Спекулятивный кредитный рейтинг",
                        severity="high",
                        score_contribution=self.t.medium_credit_score,
                        source="infosphere",
                        evidence=f"Кредитный рейтинг: {credit_rating}",
                    )
                )
        else:
            score += self.t.no_financial_data_score
            factors.append(
                RiskFactor(
                    category=RiskCategory.FINANCIAL,
                    description="⚠️ Финансовые данные недоступны",
                    severity="medium",
                    score_contribution=self.t.no_financial_data_score,
                    source="infosphere",
                    evidence="Нет данных из InfoSphere",
                )
            )

        return min(max_score, score)

    def _calculate_reputation_risk(
        self,
        search_results: List[Dict[str, Any]],
        factors: List[RiskFactor],
    ) -> int:
        """
        Рассчитать репутационный риск на основе веб-поиска.

        КРИТЕРИИ:
        - Скандалы, уголовные дела → +20
        - Множественные негативные отзывы → +15
        - Негативные упоминания в СМИ → +10
        - Нейтральные/позитивные отзывы → +0
        """
        score = 0
        max_score = self.MAX_SCORE_PER_CATEGORY[RiskCategory.REPUTATION]

        negative_keywords = [
            "скандал",
            "мошенничество",
            "обман",
            "уголовное дело",
            "банкротство",
            "ликвидация",
            "долги",
            "неплатежи",
            "жалоб",
            "претензий",
            "обманут",
            "кинули",
        ]

        negative_count = 0
        scandal_count = 0

        for result in search_results:
            if not result.get("success"):
                continue

            content = str(result.get("content", "")).lower()
            answer = str(result.get("answer", "")).lower()
            text = content + " " + answer

            sentiment = result.get("sentiment", {})
            if sentiment.get("label") == "negative":
                negative_count += 1

            for keyword in negative_keywords[:4]:
                if keyword in text:
                    scandal_count += 1
                    break

        if scandal_count > 0:
            scandal_score = min(self.t.scandal_max, self.t.scandal_base + scandal_count * self.t.scandal_per_count)
            score += scandal_score
            factors.append(
                RiskFactor(
                    category=RiskCategory.REPUTATION,
                    description=f"🔴 Обнаружены негативные упоминания ({scandal_count})",
                    severity="high" if scandal_count >= 2 else "medium",
                    score_contribution=scandal_score,
                    source="perplexity/tavily",
                    evidence=f"Найдено {scandal_count} упоминаний скандалов/проблем",
                )
            )
        elif negative_count > self.t.negative_count_threshold:
            score += self.t.multiple_negative_score
            factors.append(
                RiskFactor(
                    category=RiskCategory.REPUTATION,
                    description=f"⚠️ Множественные негативные отзывы ({negative_count})",
                    severity="medium",
                    score_contribution=self.t.multiple_negative_score,
                    source="perplexity/tavily",
                    evidence=f"Найдено {negative_count} негативных результатов поиска",
                )
            )
        elif negative_count > 0:
            score += self.t.few_negative_score
            factors.append(
                RiskFactor(
                    category=RiskCategory.REPUTATION,
                    description=f"⚠️ Есть негативные отзывы ({negative_count})",
                    severity="low",
                    score_contribution=self.t.few_negative_score,
                    source="perplexity/tavily",
                    evidence=f"Найдено {negative_count} негативных результатов",
                )
            )
        else:
            factors.append(
                RiskFactor(
                    category=RiskCategory.REPUTATION,
                    description="✅ Репутация нейтральная или положительная",
                    severity="low",
                    score_contribution=0,
                    source="perplexity/tavily",
                    evidence="Негативных упоминаний не обнаружено",
                )
            )

        return min(max_score, score)

    def _calculate_regulatory_risk(
        self,
        source_data: Dict[str, Any],
        search_results: List[Dict[str, Any]],
        factors: List[RiskFactor],
    ) -> int:
        """
        Рассчитать регуляторный риск.

        КРИТЕРИИ:
        - Санкции → +15
        - Отсутствие лицензий → +10
        - Штрафы от ФНС/ФАС → +10
        - Регуляторные проверки → +5
        """
        score = 0
        max_score = self.MAX_SCORE_PER_CATEGORY[RiskCategory.REGULATORY]

        sanction_keywords = [
            "санкции",
            "санкций",
            "санкциями",
            "санкционный",
            "санкционные",
            "ограничения",
            "запрет",
        ]
        regulatory_keywords = ["штраф", "нарушение", "проверка фнс", "проверка фас"]

        for result in search_results:
            if not result.get("success"):
                continue

            text = str(result.get("content", "") + result.get("answer", "")).lower()

            for keyword in sanction_keywords:
                if keyword in text:
                    score += self.t.sanction_score
                    factors.append(
                        RiskFactor(
                            category=RiskCategory.REGULATORY,
                            description="🔴 Обнаружены санкционные ограничения",
                            severity="high",
                            score_contribution=self.t.sanction_score,
                            source="perplexity/tavily",
                            evidence=f"Найдено упоминание: {keyword}",
                        )
                    )
                    break

            for keyword in regulatory_keywords:
                if keyword in text:
                    score += self.t.regulatory_issue_score
                    factors.append(
                        RiskFactor(
                            category=RiskCategory.REGULATORY,
                            description=f"⚠️ Регуляторные вопросы: {keyword}",
                            severity="medium",
                            score_contribution=self.t.regulatory_issue_score,
                            source="perplexity/tavily",
                            evidence=f"Найдено упоминание: {keyword}",
                        )
                    )
                    break

        if score == 0:
            factors.append(
                RiskFactor(
                    category=RiskCategory.REGULATORY,
                    description="✅ Регуляторных проблем не обнаружено",
                    severity="low",
                    score_contribution=0,
                    source="combined",
                    evidence="Нет санкций или штрафов",
                )
            )

        return min(max_score, score)


risk_calculator = RiskScoreCalculator()


def calculate_normalized_risk(
    source_data: Dict[str, Any],
    search_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Удобная функция для расчёта нормализованного риск-скора.

    Args:
        source_data: Данные из источников
        search_results: Результаты веб-поиска

    Returns:
        Dict с полями: score, level, factors
    """
    score, factors, level = risk_calculator.calculate_risk_score(source_data, search_results)

    return {
        "score": score,
        "level": level,
        "factors": [f.description for f in factors],
        "factors_detailed": [
            {
                "category": f.category.value,
                "description": f.description,
                "severity": f.severity,
                "score_contribution": f.score_contribution,
                "source": f.source,
                "evidence": f.evidence,
            }
            for f in factors
        ],
    }
