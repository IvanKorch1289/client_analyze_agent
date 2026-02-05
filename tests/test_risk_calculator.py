"""
Tests for risk_calculator.py - Core business logic testing.

Sprint 12: P0 Critical Tests
Coverage: Risk scoring algorithm, category calculations, normalization
"""


from app.agents.risk_calculator import (
    RiskScoreCalculator,
    RiskCategory,
    RiskFactor,
    calculate_normalized_risk,
)


class TestRiskScoreCalculator:
    """Test suite for RiskScoreCalculator class."""

    def setup_method(self):
        """Initialize calculator for each test."""
        self.calculator = RiskScoreCalculator()

    # ==================== EDGE CASES ====================

    def test_empty_source_data_returns_low_risk(self):
        """Empty source data should return low risk with some factors."""
        score, factors, level = self.calculator.calculate_risk_score({})

        assert 0 <= score <= 100
        assert level in ["low", "medium", "high", "critical"]
        assert isinstance(factors, list)

    def test_all_sources_failed_returns_medium_risk(self):
        """When all sources fail, should add risk for missing data."""
        source_data = {
            "dadata": {"success": False, "error": "timeout"},
            "casebook": {"success": False, "error": "timeout"},
            "infosphere": {"success": False, "error": "timeout"},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        # Should have factor for missing financial data
        assert any("недоступны" in f.description for f in factors)
        assert score >= 9  # At least penalty for missing data (normalized: 10/105*100=9.5)

    def test_score_bounded_0_to_100(self):
        """Score should always be in 0-100 range."""
        # Extreme negative case
        minimal_data = {}
        score1, _, _ = self.calculator.calculate_risk_score(minimal_data)
        assert 0 <= score1 <= 100

        # Extreme positive case (all risks)
        extreme_data = {
            "dadata": {"success": True, "data": {"state": {"status": "LIQUIDATING"}}},
            "casebook": {"success": True, "data": [{"category": "банкротство"}] * 50},
            "infosphere": {
                "success": True,
                "data": {"liquidity_ratio": 0.1, "debt_ratio": 0.95},
            },
        }
        search = [{"success": True, "content": "скандал мошенничество санкции штраф"}]
        score2, _, _ = self.calculator.calculate_risk_score(extreme_data, search)
        assert 0 <= score2 <= 100

    # ==================== LEGAL RISK ====================

    def test_liquidating_company_max_legal_score(self):
        """Company in LIQUIDATING status should get max legal score."""
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "LIQUIDATING"}}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        legal_factors = [f for f in factors if f.category == RiskCategory.LEGAL]
        assert len(legal_factors) > 0
        assert any("КРИТИЧЕСКИЙ" in f.description or "ликвидаци" in f.description.lower() for f in legal_factors)
        assert any(f.severity == "critical" for f in legal_factors)

    def test_bankrupt_company_max_legal_score(self):
        """Company in BANKRUPT status should get max legal score."""
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "BANKRUPT"}}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        legal_factors = [f for f in factors if f.category == RiskCategory.LEGAL]
        assert any(f.severity == "critical" for f in legal_factors)

    def test_active_company_low_legal_score(self):
        """Active company with no cases should have low legal score."""
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {"success": True, "data": []},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        legal_factors = [f for f in factors if f.category == RiskCategory.LEGAL]
        assert any("Компания активна" in f.description for f in legal_factors)
        assert all(f.severity == "low" for f in legal_factors)

    def test_bankruptcy_cases_high_legal_score(self):
        """Bankruptcy cases should significantly increase legal score."""
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {
                "success": True,
                "data": [
                    {"category": "банкротство", "case_name": "Дело о банкротстве"},
                    {"category": "банкротство", "case_name": "Дело о банкротстве 2"},
                ],
            },
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        assert any("Банкротные дела" in f.description for f in factors)
        assert score >= 30  # Bankruptcy should add significant score

    def test_defendant_cases_normalized_scores(self):
        """Defendant cases should be normalized (100 cases != 75 points)."""
        # 5 cases
        source_data_5 = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {"success": True, "data": [{"role": "defendant"}] * 5},
        }
        score_5, _, _ = self.calculator.calculate_risk_score(source_data_5)

        # 100 cases
        source_data_100 = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {"success": True, "data": [{"role": "defendant"}] * 100},
        }
        score_100, _, _ = self.calculator.calculate_risk_score(source_data_100)

        # 100 cases should NOT be 20x more than 5 cases (normalization)
        assert score_100 < score_5 * 10  # Should be normalized
        assert score_100 <= 50  # Should not exceed reasonable bounds

    def test_plaintiff_cases_reduce_score(self):
        """Being a plaintiff (suing others) should slightly reduce risk."""
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {
                "success": True,
                "data": [
                    {"role": "plaintiff"},
                    {"role": "plaintiff"},
                ],
            },
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        assert any("Инициирует судебные дела" in f.description for f in factors)
        plaintiff_factor = [f for f in factors if "Инициирует" in f.description][0]
        assert plaintiff_factor.score_contribution < 0  # Should reduce score

    # ==================== FINANCIAL RISK ====================

    def test_critical_liquidity_high_financial_score(self):
        """Liquidity < 0.5 should be critical."""
        source_data = {
            "infosphere": {"success": True, "data": {"liquidity_ratio": 0.3}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        financial_factors = [f for f in factors if f.category == RiskCategory.FINANCIAL]
        assert any("КРИТИЧЕСКАЯ ликвидность" in f.description for f in financial_factors)
        assert any(f.score_contribution >= 25 for f in financial_factors)

    def test_low_liquidity_medium_financial_score(self):
        """Liquidity 0.5-1.0 should be concerning but not critical."""
        source_data = {
            "infosphere": {"success": True, "data": {"liquidity_ratio": 0.7}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        financial_factors = [f for f in factors if f.category == RiskCategory.FINANCIAL]
        assert any("Низкая ликвидность" in f.description for f in financial_factors)

    def test_healthy_liquidity_no_penalty(self):
        """Liquidity >= 1.0 should be healthy."""
        source_data = {
            "infosphere": {"success": True, "data": {"liquidity_ratio": 1.5}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        financial_factors = [f for f in factors if f.category == RiskCategory.FINANCIAL]
        assert any("Здоровая ликвидность" in f.description for f in financial_factors)

    def test_high_debt_increases_financial_risk(self):
        """Debt ratio > 0.8 should increase financial risk."""
        source_data = {
            "infosphere": {"success": True, "data": {"debt_ratio": 0.9}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        assert any("долговая нагрузка" in f.description.lower() for f in factors)

    def test_low_credit_rating_high_risk(self):
        """Low credit ratings (CCC, D) should be critical."""
        source_data = {
            "infosphere": {"success": True, "data": {"credit_rating": "CCC"}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        assert any("Низкий кредитный рейтинг" in f.description for f in factors)

    def test_speculative_credit_rating_medium_risk(self):
        """Speculative ratings (BB) should be high but not critical."""
        source_data = {
            "infosphere": {"success": True, "data": {"credit_rating": "BB+"}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        assert any("Спекулятивный кредитный рейтинг" in f.description for f in factors)

    # ==================== REPUTATION RISK ====================

    def test_scandal_mentions_high_reputation_risk(self):
        """Scandal mentions should increase reputation risk."""
        search_results = [
            {"success": True, "content": "компания скандал мошенничество"},
            {"success": True, "content": "уголовное дело против директора"},
        ]
        score, factors, level = self.calculator.calculate_risk_score({}, search_results)

        reputation_factors = [f for f in factors if f.category == RiskCategory.REPUTATION]
        assert any("негативные упоминания" in f.description.lower() for f in reputation_factors)

    def test_negative_sentiment_increases_risk(self):
        """Negative sentiment in search results should increase risk."""
        search_results = [
            {"success": True, "content": "отзыв", "sentiment": {"label": "negative"}},
            {"success": True, "content": "отзыв", "sentiment": {"label": "negative"}},
            {"success": True, "content": "отзыв", "sentiment": {"label": "negative"}},
            {"success": True, "content": "отзыв", "sentiment": {"label": "negative"}},
        ]
        score, factors, level = self.calculator.calculate_risk_score({}, search_results)

        reputation_factors = [f for f in factors if f.category == RiskCategory.REPUTATION]
        assert any("негативные отзывы" in f.description.lower() for f in reputation_factors)

    def test_neutral_search_results_low_reputation_risk(self):
        """Neutral/positive search results should have low reputation risk."""
        search_results = [
            {"success": True, "content": "компания работает стабильно"},
            {"success": True, "content": "положительные отзывы клиентов"},
        ]
        score, factors, level = self.calculator.calculate_risk_score({}, search_results)

        reputation_factors = [f for f in factors if f.category == RiskCategory.REPUTATION]
        assert any("нейтральная или положительная" in f.description.lower() for f in reputation_factors)

    # ==================== REGULATORY RISK ====================

    def test_sanctions_high_regulatory_risk(self):
        """Sanction mentions should increase regulatory risk."""
        search_results = [
            {"success": True, "content": "компания под санкциями США"},
        ]
        score, factors, level = self.calculator.calculate_risk_score({}, search_results)

        regulatory_factors = [f for f in factors if f.category == RiskCategory.REGULATORY]
        assert any("санкционные ограничения" in f.description.lower() for f in regulatory_factors)

    def test_regulatory_issues_medium_risk(self):
        """Regulatory fines/checks should add medium risk."""
        search_results = [
            {"success": True, "content": "штраф от ФНС за нарушения"},
        ]
        score, factors, level = self.calculator.calculate_risk_score({}, search_results)

        regulatory_factors = [f for f in factors if f.category == RiskCategory.REGULATORY]
        assert any("Регуляторные вопросы" in f.description for f in regulatory_factors)

    def test_no_regulatory_issues_clean(self):
        """No regulatory issues should result in clean status."""
        search_results = [
            {"success": True, "content": "компания работает законно"},
        ]
        score, factors, level = self.calculator.calculate_risk_score({}, search_results)

        regulatory_factors = [f for f in factors if f.category == RiskCategory.REGULATORY]
        assert any("проблем не обнаружено" in f.description.lower() for f in regulatory_factors)

    # ==================== LEVEL THRESHOLDS ====================

    def test_score_level_low(self):
        """Score 0-24 should be 'low' level."""
        # Minimal risk scenario
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {"success": True, "data": []},
            "infosphere": {"success": True, "data": {"liquidity_ratio": 2.0}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        if score < 25:
            assert level == "low"

    def test_score_level_medium(self):
        """Score 25-49 should be 'medium' level."""
        # Medium risk scenario
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {"success": True, "data": [{"role": "defendant"}] * 30},
            "infosphere": {"success": True, "data": {"liquidity_ratio": 0.8}},
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        if 25 <= score < 50:
            assert level == "medium"

    def test_score_level_high(self):
        """Score 50-74 should be 'high' level."""
        # High risk scenario
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {"success": True, "data": [{"category": "банкротство"}]},
            "infosphere": {
                "success": True,
                "data": {"liquidity_ratio": 0.4, "debt_ratio": 0.85},
            },
        }
        score, factors, level = self.calculator.calculate_risk_score(source_data)

        if 50 <= score < 75:
            assert level == "high"

    def test_score_level_critical(self):
        """Score 75+ should be 'critical' level."""
        # Critical risk scenario
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "LIQUIDATING"}}},
            "casebook": {"success": True, "data": [{"category": "банкротство"}] * 5},
            "infosphere": {
                "success": True,
                "data": {"liquidity_ratio": 0.2, "credit_rating": "D"},
            },
        }
        search = [{"success": True, "content": "скандал санкции мошенничество"}]
        score, factors, level = self.calculator.calculate_risk_score(source_data, search)

        if score >= 75:
            assert level == "critical"

    # ==================== WEIGHTS ====================

    def test_category_weights_sum_to_one(self):
        """Category weights should sum to 1.0."""
        total_weight = sum(self.calculator.WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.001

    def test_max_scores_are_reasonable(self):
        """Max scores per category should be reasonable."""
        for category, max_score in self.calculator.MAX_SCORE_PER_CATEGORY.items():
            assert 10 <= max_score <= 50
            assert category in RiskCategory


class TestCalculateNormalizedRisk:
    """Test the convenience function calculate_normalized_risk."""

    def test_returns_dict_with_required_keys(self):
        """Should return dict with score, level, factors, factors_detailed."""
        result = calculate_normalized_risk({})

        assert "score" in result
        assert "level" in result
        assert "factors" in result
        assert "factors_detailed" in result

    def test_score_is_integer(self):
        """Score should be an integer."""
        result = calculate_normalized_risk({})
        assert isinstance(result["score"], int)

    def test_level_is_valid(self):
        """Level should be one of low/medium/high/critical."""
        result = calculate_normalized_risk({})
        assert result["level"] in ["low", "medium", "high", "critical"]

    def test_factors_is_list_of_strings(self):
        """Factors should be list of description strings."""
        result = calculate_normalized_risk({})
        assert isinstance(result["factors"], list)
        for f in result["factors"]:
            assert isinstance(f, str)

    def test_factors_detailed_has_all_fields(self):
        """factors_detailed should have all required fields."""
        # Create scenario that generates factors
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
        }
        result = calculate_normalized_risk(source_data)

        for factor in result["factors_detailed"]:
            assert "category" in factor
            assert "description" in factor
            assert "severity" in factor
            assert "score_contribution" in factor
            assert "source" in factor
            assert "evidence" in factor


class TestRiskFactor:
    """Test RiskFactor dataclass."""

    def test_risk_factor_creation(self):
        """Should create RiskFactor with all fields."""
        factor = RiskFactor(
            category=RiskCategory.LEGAL,
            description="Test factor",
            severity="high",
            score_contribution=20,
            source="dadata",
            evidence="Test evidence",
        )

        assert factor.category == RiskCategory.LEGAL
        assert factor.description == "Test factor"
        assert factor.severity == "high"
        assert factor.score_contribution == 20
        assert factor.source == "dadata"
        assert factor.evidence == "Test evidence"

    def test_risk_factor_optional_evidence(self):
        """Evidence field should be optional."""
        factor = RiskFactor(
            category=RiskCategory.FINANCIAL,
            description="Test",
            severity="low",
            score_contribution=5,
            source="infosphere",
        )
        assert factor.evidence is None


class TestRiskCategory:
    """Test RiskCategory enum."""

    def test_all_categories_exist(self):
        """All expected categories should exist."""
        assert RiskCategory.LEGAL
        assert RiskCategory.FINANCIAL
        assert RiskCategory.REPUTATION
        assert RiskCategory.REGULATORY

    def test_categories_are_strings(self):
        """Categories should have string values."""
        assert RiskCategory.LEGAL.value == "legal"
        assert RiskCategory.FINANCIAL.value == "financial"
        assert RiskCategory.REPUTATION.value == "reputation"
        assert RiskCategory.REGULATORY.value == "regulatory"


class TestIntegration:
    """Integration tests for complete risk calculation scenarios."""

    def test_real_company_scenario_gazprom_like(self):
        """Simulate a large stable company (like Gazprom)."""
        source_data = {
            "dadata": {
                "success": True,
                "data": {
                    "state": {"status": "ACTIVE"},
                    "name": {"full_with_opf": 'ПАО "Газпром"'},
                },
            },
            "casebook": {
                "success": True,
                "data": [{"role": "plaintiff"}] * 50 + [{"role": "defendant"}] * 10,
            },
            "infosphere": {
                "success": True,
                "data": {
                    "liquidity_ratio": 1.8,
                    "debt_ratio": 0.4,
                    "credit_rating": "BBB+",
                },
            },
        }
        search_results = [
            {"success": True, "content": "крупнейшая газовая компания России"},
        ]

        result = calculate_normalized_risk(source_data, search_results)

        # Large stable company should have low-medium risk
        assert result["score"] < 50
        assert result["level"] in ["low", "medium"]

    def test_real_company_scenario_bankrupt(self):
        """Simulate a company going bankrupt."""
        source_data = {
            "dadata": {
                "success": True,
                "data": {
                    "state": {"status": "LIQUIDATING"},
                    "name": {"full_with_opf": 'ООО "Банкрот"'},
                },
            },
            "casebook": {
                "success": True,
                "data": [{"category": "банкротство"}] * 3,
            },
            "infosphere": {
                "success": True,
                "data": {
                    "liquidity_ratio": 0.1,
                    "debt_ratio": 0.95,
                    "credit_rating": "D",
                },
            },
        }
        search_results = [
            {
                "success": True,
                "content": "компания объявила о банкротстве скандал с долгами",
            },
        ]

        result = calculate_normalized_risk(source_data, search_results)

        # Bankrupt company should have critical risk
        assert result["score"] >= 60
        assert result["level"] in ["high", "critical"]

    def test_real_company_scenario_startup(self):
        """Simulate a new startup with limited data."""
        source_data = {
            "dadata": {
                "success": True,
                "data": {
                    "state": {"status": "ACTIVE"},
                    "name": {"full_with_opf": 'ООО "Стартап"'},
                },
            },
            "casebook": {"success": True, "data": []},
            "infosphere": {"success": False, "error": "Нет финансовых данных"},
        }
        search_results = [
            {"success": True, "content": "молодая IT-компания"},
        ]

        result = calculate_normalized_risk(source_data, search_results)

        # Startup with missing data should have low-medium risk
        assert result["score"] < 40
        assert result["level"] in ["low", "medium"]

    def test_real_company_scenario_sanctioned(self):
        """Simulate a sanctioned company."""
        source_data = {
            "dadata": {
                "success": True,
                "data": {"state": {"status": "ACTIVE"}},
            },
        }
        search_results = [
            {"success": True, "content": "компания под санкциями США и ЕС ограничения"},
            {"success": True, "content": "санкционный список SDN"},
        ]

        result = calculate_normalized_risk(source_data, search_results)

        # Sanctioned company should have elevated risk
        assert result["score"] >= 20
        assert any("санкционные" in f.lower() for f in result["factors"])
