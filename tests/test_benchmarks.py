"""
Performance benchmarks using pytest-benchmark.

Run with:
    pytest tests/test_benchmarks.py -v --benchmark-only
    pytest tests/test_benchmarks.py -v --benchmark-json=benchmark.json
"""

import pytest
import time
import json
from unittest.mock import MagicMock, patch


class TestRiskCalculatorBenchmark:
    """Benchmark tests for risk score calculation."""

    @pytest.fixture
    def sample_source_data(self):
        """Sample source data for benchmarking."""
        return {
            "dadata": {
                "success": True,
                "data": {
                    "state": {"status": "ACTIVE"},
                    "name": {"full_with_opf": "ООО Тестовая Компания"},
                    "finance": {"balance": {"current_liquidity": 1.5}},
                },
            },
            "casebook": {
                "success": True,
                "data": [
                    {"caseNumber": f"A40-{i}", "category": "bankruptcy"}
                    for i in range(5)
                ],
            },
            "infosphere": {
                "success": True,
                "data": {"checks_passed": 10, "checks_failed": 2},
            },
            "perplexity": {
                "success": True,
                "intents": {
                    "reputation": {
                        "success": True,
                        "content": "Компания имеет хорошую репутацию на рынке.",
                    }
                },
            },
        }

    def test_risk_calculation_performance(self, sample_source_data, benchmark):
        """Benchmark risk score calculation speed."""
        from app.services.risk_calculator import calculate_normalized_risk

        def run_calculation():
            return calculate_normalized_risk(sample_source_data)

        result = benchmark(run_calculation)
        assert result is not None
        assert "total_score" in result

    def test_risk_calculation_large_dataset(self, benchmark):
        """Benchmark with large dataset (many court cases)."""
        from app.services.risk_calculator import calculate_normalized_risk

        large_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
            "casebook": {
                "success": True,
                "data": [
                    {"caseNumber": f"A40-{i}", "category": "civil"}
                    for i in range(100)
                ],
            },
            "infosphere": {"success": True, "data": {}},
        }

        result = benchmark(lambda: calculate_normalized_risk(large_data))
        assert result["total_score"] >= 0


class TestPIIMaskingBenchmark:
    """Benchmark tests for PII masking performance."""

    @pytest.fixture
    def sample_text_with_pii(self):
        """Sample text containing PII."""
        return """
        Директор компании Иванов Иван Иванович (ИНН 7707083893)
        зарегистрирован по адресу: г. Москва, ул. Ленина, д. 1.
        Контактный телефон: +7 (999) 123-45-67.
        Паспорт: 45 06 123456, СНИЛС: 123-456-789 01.
        ОГРН компании: 1027700132195.
        """

    def test_pii_masking_performance(self, sample_text_with_pii, benchmark):
        """Benchmark PII masking speed."""
        try:
            from app.shared.pii_protection import mask_pii

            result = benchmark(lambda: mask_pii(sample_text_with_pii))
            assert result is not None
        except ImportError:
            pytest.skip("PII protection module not available")

    def test_pii_masking_long_text(self, benchmark):
        """Benchmark PII masking with long text."""
        try:
            from app.shared.pii_protection import mask_pii

            # Generate long text with repeated PII patterns
            long_text = """
            Компания ООО "Тест" (ИНН 7707083893) работает с клиентами.
            Директор: Петров Пётр Петрович, тел: +7 (999) 111-22-33.
            """ * 50  # ~5000 characters

            result = benchmark(lambda: mask_pii(long_text))
            assert result is not None
        except ImportError:
            pytest.skip("PII protection module not available")


class TestSerializationBenchmark:
    """Benchmark tests for serialization operations."""

    @pytest.fixture
    def sample_report(self):
        """Sample report data for serialization."""
        return {
            "client_name": "ООО Тестовая Компания",
            "inn": "7707083893",
            "risk_score": 45.5,
            "risk_level": "medium",
            "categories": {
                "legal": {"score": 30, "factors": ["active_lawsuits"]},
                "financial": {"score": 50, "factors": ["low_liquidity"]},
                "reputation": {"score": 40, "factors": []},
                "regulatory": {"score": 60, "factors": ["tax_issues"]},
            },
            "sources": {
                "dadata": {"success": True},
                "casebook": {"success": True, "cases_count": 5},
                "infosphere": {"success": True},
            },
            "timestamp": "2024-01-15T10:00:00Z",
            "analysis_duration_ms": 45000,
        }

    def test_json_serialization(self, sample_report, benchmark):
        """Benchmark JSON serialization."""
        result = benchmark(lambda: json.dumps(sample_report, ensure_ascii=False))
        assert result is not None
        assert len(result) > 0

    def test_json_deserialization(self, sample_report, benchmark):
        """Benchmark JSON deserialization."""
        json_str = json.dumps(sample_report, ensure_ascii=False)
        result = benchmark(lambda: json.loads(json_str))
        assert result is not None
        assert result["client_name"] == sample_report["client_name"]


class TestCacheKeyGeneration:
    """Benchmark tests for cache key generation."""

    def test_hash_generation(self, benchmark):
        """Benchmark MD5 hash generation for cache keys."""
        import hashlib

        query = "ООО Газпром судебные дела 2024"

        def generate_key():
            return hashlib.md5(query.encode()).hexdigest()

        result = benchmark(generate_key)
        assert len(result) == 32

    def test_compound_key_generation(self, benchmark):
        """Benchmark compound cache key generation."""
        import hashlib

        def generate_compound_key():
            parts = [
                "company:ООО Газпром",
                "inn:7707083893",
                "query:судебные дела",
                "source:casebook",
            ]
            combined = "|".join(parts)
            return hashlib.sha256(combined.encode()).hexdigest()[:16]

        result = benchmark(generate_compound_key)
        assert len(result) == 16


class TestSentimentAnalysis:
    """Benchmark tests for sentiment analysis."""

    @pytest.fixture
    def sample_texts(self):
        """Sample texts for sentiment analysis."""
        return [
            "Компания демонстрирует стабильный рост и хорошие финансовые показатели.",
            "Обнаружены серьёзные проблемы с ликвидностью и риск банкротства.",
            "Судебных дел не обнаружено, репутация нейтральная.",
            "Компания ликвидирована, имеются долги перед кредиторами.",
            "Надёжный партнёр с позитивными отзывами клиентов.",
        ]

    def test_sentiment_analysis(self, sample_texts, benchmark):
        """Benchmark sentiment analysis."""
        from app.agents.data_collector import analyze_sentiment

        def analyze_all():
            return [analyze_sentiment(text) for text in sample_texts]

        results = benchmark(analyze_all)
        assert len(results) == len(sample_texts)
        for result in results:
            assert "label" in result
            assert "score" in result


# Pytest configuration for benchmarks
def pytest_configure(config):
    """Add benchmark markers."""
    config.addinivalue_line(
        "markers", "benchmark: mark test as a benchmark test"
    )
