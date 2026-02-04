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

        if final_score >= 75:
            level = "critical"
        elif final_score >= 50:
            level = "high"
        elif final_score >= 25:
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
                    bankruptcy_score = min(max_score, 30 + len(bankruptcy_cases) * 3)
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
                    defendant_score = 25
                    severity: Literal["critical", "high", "medium", "low"] = "high"
                elif defendant_count >= 50:
                    defendant_score = 20
                    severity = "high"
                elif defendant_count >= 20:
                    defendant_score = 15
                    severity = "medium"
                elif defendant_count >= 10:
                    defendant_score = 10
                    severity = "medium"
                elif defendant_count > 0:
                    defendant_score = 5
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
                    score = max(0, score - 3)
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
                    if liquidity < 0.5:
                        score += 28
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="🔴 КРИТИЧЕСКАЯ ликвидность",
                                severity="critical",
                                score_contribution=28,
                                source="infosphere",
                                evidence=f"Коэффициент ликвидности: {liquidity:.2f} (критически низко)",
                            )
                        )
                    elif liquidity < 1.0:
                        score += 18
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="⚠️ Низкая ликвидность",
                                severity="high",
                                score_contribution=18,
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
                    if debt_ratio > 0.8:
                        score += 20
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="⚠️ Высокая долговая нагрузка",
                                severity="high",
                                score_contribution=20,
                                source="infosphere",
                                evidence=f"Коэффициент долга: {debt_ratio:.2f} (высокий)",
                            )
                        )
                    elif debt_ratio > 0.6:
                        score += 10
                        factors.append(
                            RiskFactor(
                                category=RiskCategory.FINANCIAL,
                                description="⚠️ Повышенная долговая нагрузка",
                                severity="medium",
                                score_contribution=10,
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
                score += 25
                factors.append(
                    RiskFactor(
                        category=RiskCategory.FINANCIAL,
                        description="🔴 Низкий кредитный рейтинг",
                        severity="critical",
                        score_contribution=25,
                        source="infosphere",
                        evidence=f"Кредитный рейтинг: {credit_rating}",
                    )
                )
            elif any(r in credit_rating for r in medium_ratings):
                score += 15
                factors.append(
                    RiskFactor(
                        category=RiskCategory.FINANCIAL,
                        description="⚠️ Спекулятивный кредитный рейтинг",
                        severity="high",
                        score_contribution=15,
                        source="infosphere",
                        evidence=f"Кредитный рейтинг: {credit_rating}",
                    )
                )
        else:
            score += 10
            factors.append(
                RiskFactor(
                    category=RiskCategory.FINANCIAL,
                    description="⚠️ Финансовые данные недоступны",
                    severity="medium",
                    score_contribution=10,
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
            scandal_score = min(20, 10 + scandal_count * 3)
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
        elif negative_count > 3:
            score += 15
            factors.append(
                RiskFactor(
                    category=RiskCategory.REPUTATION,
                    description=f"⚠️ Множественные негативные отзывы ({negative_count})",
                    severity="medium",
                    score_contribution=15,
                    source="perplexity/tavily",
                    evidence=f"Найдено {negative_count} негативных результатов поиска",
                )
            )
        elif negative_count > 0:
            score += 5
            factors.append(
                RiskFactor(
                    category=RiskCategory.REPUTATION,
                    description=f"⚠️ Есть негативные отзывы ({negative_count})",
                    severity="low",
                    score_contribution=5,
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
                    score += 15
                    factors.append(
                        RiskFactor(
                            category=RiskCategory.REGULATORY,
                            description="🔴 Обнаружены санкционные ограничения",
                            severity="high",
                            score_contribution=15,
                            source="perplexity/tavily",
                            evidence=f"Найдено упоминание: {keyword}",
                        )
                    )
                    break

            for keyword in regulatory_keywords:
                if keyword in text:
                    score += 5
                    factors.append(
                        RiskFactor(
                            category=RiskCategory.REGULATORY,
                            description=f"⚠️ Регуляторные вопросы: {keyword}",
                            severity="medium",
                            score_contribution=5,
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
