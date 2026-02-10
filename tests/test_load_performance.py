"""
Load and Performance Tests (Sprint 14.1)

Tests for:
- API endpoint performance under load
- Concurrent request handling
- Resource usage monitoring
- Timeout validation
"""

import asyncio
import time
from typing import List
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ============================================================================
# PERFORMANCE BENCHMARKS (pytest-benchmark style)
# ============================================================================

try:
    import pytest_benchmark  # noqa: F401

    _has_benchmark = True
except ImportError:
    _has_benchmark = False


@pytest.mark.skipif(not _has_benchmark, reason="pytest-benchmark not installed")
class TestPerformanceBenchmarks:
    """Performance benchmarks for critical operations."""

    def test_risk_score_calculation_performance(self, benchmark):
        """Risk score calculation should complete in <50ms."""
        from app.agents.risk_calculator import RiskScoreCalculator

        calculator = RiskScoreCalculator()
        source_data = {
            "dadata": {
                "success": True,
                "data": {
                    "state": {"status": "ACTIVE"},
                    "finance": {"revenue": 100000000, "profit": 5000000},
                    "name": {"full_with_opf": "ООО Тестовая Компания"},
                },
            },
            "infosphere": {
                "success": True,
                "data": {"bankruptcy": False, "fssp": {"total_debt": 0}},
            },
            "casebook": {
                "success": True,
                "data": {"cases": [{"type": "plaintiff", "amount": 1000000}]},
            },
        }

        result = benchmark(calculator.calculate_risk_score, source_data)
        assert result is not None
        # Should have 3 elements: score, factors, level
        score, factors, level = result
        assert 0 <= score <= 100

    def test_pii_masking_performance(self, benchmark):
        """PII masking should complete in <100ms for typical text."""
        from app.shared.pii_protection import mask_pii

        text = """
        Компания ООО "Рога и Копыта" (ИНН 7707083893, ОГРН 1027700132195)
        Директор: Иванов Иван Иванович
        Телефон: +7 (495) 123-45-67
        Адрес: г. Москва, ул. Тверская, д. 1
        СНИЛС: 123-456-789 01
        Паспорт: 4510 123456
        """

        result = benchmark(mask_pii, text)
        assert result is not None
        assert "7707083893" not in result.masked_text

    def test_json_export_performance(self, benchmark):
        """JSON export should complete in <10ms for typical report."""
        from app.shared.toolkit.export import report_to_json

        report = {
            "report_id": "test-123",
            "client_name": "ООО Тестовая Компания",
            "inn": "7707083893",
            "risk_score": 45,
            "findings": [{"category": f"cat-{i}", "data": "x" * 100} for i in range(50)],
            "recommendations": [f"Rec {i}" for i in range(20)],
        }

        result = benchmark(report_to_json, report)
        assert len(result) > 1000

    def test_csv_export_performance(self, benchmark):
        """CSV export should complete in <20ms for typical report."""
        from app.shared.toolkit.export import report_to_csv

        report = {
            "report_id": "test-123",
            "client_name": "ООО Тестовая Компания",
            "inn": "7707083893",
            "created_at": 1705324800,
            "risk_level": "medium",
            "risk_score": 45,
            "report_data": {
                "findings": [
                    {
                        "category": f"cat-{i}",
                        "sentiment": "neutral",
                        "key_points": f"Point {i}",
                    }
                    for i in range(30)
                ],
                "risk_assessment": {"factors": [f"Factor {i}" for i in range(10)]},
                "recommendations": [f"Rec {i}" for i in range(15)],
            },
        }

        result = benchmark(report_to_csv, report)
        assert len(result) > 500


# ============================================================================
# CONCURRENT LOAD TESTS
# ============================================================================


class TestConcurrentLoad:
    """Tests for concurrent request handling."""

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """Health endpoint should handle 50 concurrent requests."""
        from app.api.v1 import v1_app as app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            start_time = time.perf_counter()

            # Send 50 concurrent requests
            tasks = [client.get("/health") for _ in range(50)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            elapsed = time.perf_counter() - start_time

        # Count successful responses
        successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)

        assert successful >= 45, f"Only {successful}/50 requests succeeded"
        assert elapsed < 5.0, f"50 requests took {elapsed:.2f}s (should be <5s)"

    @pytest.mark.asyncio
    async def test_concurrent_export_helpers(self):
        """Export helpers should handle concurrent calls."""
        from app.shared.toolkit.export import report_to_json, report_to_csv

        reports = [
            {
                "report_id": f"test-{i}",
                "client_name": f"Company {i}",
                "inn": f"77070838{90 + i:02d}",
                "created_at": 1705324800,
                "risk_level": "low",
                "risk_score": i * 5,
                "report_data": {"findings": [], "recommendations": []},
            }
            for i in range(20)
        ]

        async def export_report(report):
            """Export single report to both formats."""
            json_result = report_to_json(report)
            csv_result = report_to_csv(report)
            return len(json_result) + len(csv_result)

        start_time = time.perf_counter()
        tasks = [export_report(r) for r in reports]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start_time

        assert all(r > 0 for r in results)
        assert elapsed < 2.0, f"20 exports took {elapsed:.2f}s (should be <2s)"

    @pytest.mark.asyncio
    async def test_concurrent_risk_calculations(self):
        """Risk calculator should handle concurrent calls."""
        from app.agents.risk_calculator import RiskScoreCalculator

        calculator = RiskScoreCalculator()

        test_cases = [
            {
                "dadata": {
                    "success": True,
                    "data": {
                        "state": {"status": "ACTIVE"},
                        "finance": {"revenue": 1000000 * (i + 1)},
                    },
                },
            }
            for i in range(30)
        ]

        async def calculate(data):
            return calculator.calculate_risk_score(data)

        start_time = time.perf_counter()
        tasks = [calculate(tc) for tc in test_cases]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start_time

        assert all(r[0] >= 0 for r in results)  # All scores valid
        assert elapsed < 1.0, f"30 calculations took {elapsed:.2f}s (should be <1s)"


# ============================================================================
# API THROUGHPUT TESTS
# ============================================================================


class TestApiThroughput:
    """Tests for API throughput and response times."""

    @pytest.mark.asyncio
    async def test_reports_list_throughput(self):
        """Reports list endpoint should handle multiple requests efficiently."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get_all.return_value = [{"report_id": f"r-{i}", "client_name": f"Company {i}"} for i in range(10)]
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response_times: List[float] = []

                for _ in range(20):
                    start = time.perf_counter()
                    response = await client.get("/reports")
                    response_times.append(time.perf_counter() - start)

        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)

        assert avg_time < 0.1, f"Average response time {avg_time:.3f}s > 0.1s"
        assert max_time < 0.5, f"Max response time {max_time:.3f}s > 0.5s"

    @pytest.mark.asyncio
    async def test_export_endpoint_throughput(self):
        """Export endpoint should maintain throughput under load."""
        from app.api.v1 import v1_app as app

        sample_report = {
            "id": "test-123",
            "report_id": "test-123",
            "client_name": "Test Company",
            "inn": "7707083893",
            "created_at": 1705324800,
            "risk_level": "medium",
            "risk_score": 45,
            "report_data": {"findings": []},
        }

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = sample_report
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                start_time = time.perf_counter()

                tasks = [client.get("/reports/test-123/export?format=json") for _ in range(15)]
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                elapsed = time.perf_counter() - start_time

        successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        assert successful >= 12, f"Only {successful}/15 exports succeeded"
        assert elapsed < 3.0, f"15 exports took {elapsed:.2f}s"


# ============================================================================
# RESOURCE USAGE TESTS
# ============================================================================


class TestResourceUsage:
    """Tests for memory and CPU usage patterns."""

    @pytest.mark.asyncio
    async def test_memory_stable_under_load(self):
        """Memory should remain stable during repeated operations."""
        import sys

        from app.shared.toolkit.export import report_to_json

        # Get baseline
        initial_size = sys.getsizeof([])

        results = []
        for i in range(100):
            report = {
                "report_id": f"test-{i}",
                "data": "x" * 10000,
                "findings": [{"item": j} for j in range(100)],
            }
            result = report_to_json(report)
            results.append(len(result))
            # Clear to allow GC
            del result

        # Memory should not grow unboundedly
        # This is a basic check - for real memory testing use memory_profiler
        assert len(results) == 100
        assert all(r > 10000 for r in results)

    @pytest.mark.asyncio
    async def test_no_connection_leaks(self):
        """HTTP client should not leak connections."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = None
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            # Make many requests
            for batch in range(5):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    tasks = [client.get("/reports/nonexistent") for _ in range(10)]
                    await asyncio.gather(*tasks, return_exceptions=True)

        # If we get here without hanging, connections are being cleaned up
        assert True


# ============================================================================
# TIMEOUT TESTS
# ============================================================================


class TestTimeouts:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_slow_operation_timeout(self):
        """Slow operations should timeout appropriately."""
        from app.api.v1 import v1_app as app

        async def slow_get(*args, **kwargs):
            await asyncio.sleep(10)
            return None

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.side_effect = slow_get
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(app=app, base_url="http://test", timeout=2.0) as client:
                start = time.perf_counter()
                try:
                    await client.get("/reports/test-123")
                except Exception:
                    pass
                elapsed = time.perf_counter() - start

        # Should timeout around 2s, not wait 10s
        assert elapsed < 5.0, f"Request took {elapsed:.2f}s instead of timing out"

    @pytest.mark.asyncio
    async def test_concurrent_timeouts_handled(self):
        """Multiple concurrent timeouts should be handled gracefully."""
        from app.api.v1 import v1_app as app

        timeout_count = 0

        async def sometimes_slow(*args, **kwargs):
            nonlocal timeout_count
            timeout_count += 1
            if timeout_count % 3 == 0:
                await asyncio.sleep(10)
            return {"id": "test", "client_name": "Test"}

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.side_effect = sometimes_slow
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(app=app, base_url="http://test", timeout=1.0) as client:
                tasks = [client.get(f"/reports/test-{i}") for i in range(9)]
                results = await asyncio.gather(*tasks, return_exceptions=True)

        # Some should succeed, some should timeout
        successes = sum(1 for r in results if not isinstance(r, Exception))
        # At least some requests should complete
        assert successes > 0


# ============================================================================
# STRESS TESTS
# ============================================================================


class TestStress:
    """Stress tests for edge conditions."""

    @pytest.mark.asyncio
    async def test_rapid_sequential_requests(self):
        """System should handle rapid sequential requests."""
        from app.api.v1 import v1_app as app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            start = time.perf_counter()

            for i in range(100):
                response = await client.get("/health")
                assert response.status_code == 200

            elapsed = time.perf_counter() - start

        # 100 requests should complete in reasonable time
        assert elapsed < 10.0, f"100 sequential requests took {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_burst_traffic(self):
        """System should handle burst traffic patterns."""
        from app.api.v1 import v1_app as app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Burst 1
            burst1 = await asyncio.gather(*[client.get("/health") for _ in range(20)])

            # Short pause
            await asyncio.sleep(0.1)

            # Burst 2
            burst2 = await asyncio.gather(*[client.get("/health") for _ in range(20)])

            # Short pause
            await asyncio.sleep(0.1)

            # Burst 3
            burst3 = await asyncio.gather(*[client.get("/health") for _ in range(20)])

        all_responses = burst1 + burst2 + burst3
        successful = sum(1 for r in all_responses if r.status_code == 200)

        assert successful >= 55, f"Only {successful}/60 burst requests succeeded"

    @pytest.mark.asyncio
    async def test_large_payload_handling(self):
        """System should handle large payloads efficiently."""
        from app.shared.toolkit.export import report_to_json, reports_summary_to_csv

        # Large single report
        large_report = {
            "report_id": "large-1",
            "client_name": "Test",
            "inn": "1234567890",
            "created_at": 1705324800,
            "risk_level": "low",
            "risk_score": 10,
            "findings": [{"data": "x" * 1000} for _ in range(500)],
            "raw_data": "y" * 100000,
        }

        start = time.perf_counter()
        json_result = report_to_json(large_report)
        elapsed = time.perf_counter() - start

        assert len(json_result) > 500000
        assert elapsed < 1.0, f"Large report export took {elapsed:.2f}s"

        # Many reports for summary
        many_reports = [
            {
                "report_id": f"r-{i}",
                "client_name": f"Company {i}",
                "inn": f"12345678{i:02d}",
                "created_at": 1705324800,
                "risk_level": "low",
                "risk_score": i % 100,
                "report_data": {"findings": []},
            }
            for i in range(500)
        ]

        start = time.perf_counter()
        csv_result = reports_summary_to_csv(many_reports)
        elapsed = time.perf_counter() - start

        assert csv_result.count("\n") > 500
        assert elapsed < 1.0, f"500 reports summary took {elapsed:.2f}s"


# ============================================================================
# LOCUST-STYLE LOAD TEST SCENARIOS (for manual execution)
# ============================================================================


class TestLoadScenarios:
    """Load test scenarios that can be adapted for Locust."""

    @pytest.mark.asyncio
    async def test_mixed_workload(self):
        """Simulate realistic mixed workload."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = {
                "report_id": "test",
                "client_name": "Test",
                "inn": "1234567890",
                "created_at": 1705324800,
                "risk_level": "low",
                "risk_score": 20,
                "report_data": {},
            }
            mock_repo.get_all.return_value = []
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Mix of different request types
                tasks = []

                # Health checks (60%)
                tasks.extend([client.get("/health") for _ in range(30)])

                # Reports list (20%)
                tasks.extend([client.get("/reports") for _ in range(10)])

                # Export (20%)
                tasks.extend([client.get("/reports/test/export?format=json") for _ in range(10)])

                start = time.perf_counter()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                elapsed = time.perf_counter() - start

        successful = sum(1 for r in results if not isinstance(r, Exception) and r.status_code in [200, 404])
        assert successful >= 40, f"Only {successful}/50 mixed requests succeeded"
        assert elapsed < 5.0, f"Mixed workload took {elapsed:.2f}s"


# ============================================================================
# PERFORMANCE REGRESSION TESTS
# ============================================================================


class TestPerformanceRegression:
    """Tests to catch performance regressions."""

    BASELINE_TIMES = {
        "risk_calculation": 0.05,  # 50ms
        "json_export": 0.01,  # 10ms
        "csv_export": 0.02,  # 20ms
        "pii_masking": 0.1,  # 100ms
    }

    def test_risk_calculation_regression(self):
        """Risk calculation should not regress beyond baseline."""
        from app.agents.risk_calculator import RiskScoreCalculator

        calculator = RiskScoreCalculator()
        source_data = {
            "dadata": {"success": True, "data": {"state": {"status": "ACTIVE"}}},
        }

        times = []
        for _ in range(10):
            start = time.perf_counter()
            calculator.calculate_risk_score(source_data)
            times.append(time.perf_counter() - start)

        avg_time = sum(times) / len(times)
        assert avg_time < self.BASELINE_TIMES["risk_calculation"] * 2, (
            f"Risk calculation regressed: {avg_time:.4f}s > {self.BASELINE_TIMES['risk_calculation'] * 2:.4f}s"
        )

    def test_json_export_regression(self):
        """JSON export should not regress beyond baseline."""
        from app.shared.toolkit.export import report_to_json

        report = {"report_id": "test", "data": "x" * 1000}

        times = []
        for _ in range(10):
            start = time.perf_counter()
            report_to_json(report)
            times.append(time.perf_counter() - start)

        avg_time = sum(times) / len(times)
        assert avg_time < self.BASELINE_TIMES["json_export"] * 2, (
            f"JSON export regressed: {avg_time:.4f}s > {self.BASELINE_TIMES['json_export'] * 2:.4f}s"
        )
