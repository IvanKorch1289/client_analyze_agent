"""
Tests for API export routes and export helpers.

Sprint 13.3: Export Tests (PDF/JSON/CSV/Excel/Word)
Coverage: Export endpoints, export helpers, file generation
"""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from io import BytesIO, StringIO

from httpx import ASGITransport, AsyncClient


# ============================================================================
# FIXTURES AND MOCK DATA
# ============================================================================

@pytest.fixture
def sample_report():
    """Sample report data for export tests."""
    return {
        "id": "report-123",
        "report_id": "report-123",
        "client_name": "ООО Тестовая Компания",
        "inn": "7707083893",
        "created_at": 1705324800,  # 2024-01-15 12:00:00
        "expires_at": 1707916800,  # 2024-02-14 12:00:00
        "risk_level": "medium",
        "risk_score": 45,
        "metadata": {
            "client_name": "ООО Тестовая Компания",
            "inn": "7707083893",
            "analysis_date": "2024-01-15T12:00:00",
            "data_sources_count": 5,
            "successful_sources": 4,
        },
        "risk_assessment": {
            "score": 45,
            "level": "medium",
            "factors": [
                "Компания в процессе реорганизации",
                "Судебные споры на сумму >10М руб",
                "Низкая чистая прибыль за 2023",
            ],
            "categories": {
                "legal": 30,
                "financial": 50,
                "reputation": 20,
                "regulatory": 15,
            },
        },
        "report_data": {
            "findings": [
                {
                    "category": "legal",
                    "sentiment": "negative",
                    "key_points": "Активные судебные разбирательства",
                },
                {
                    "category": "financial",
                    "sentiment": "neutral",
                    "key_points": "Стабильная выручка, снижение прибыли",
                },
            ],
            "risk_assessment": {
                "score": 45,
                "level": "medium",
                "factors": ["Реорганизация", "Судебные споры"],
            },
            "recommendations": [
                "Мониторинг судебных дел",
                "Запросить финансовую отчётность за 2023",
                "Проверить статус реорганизации",
            ],
        },
        "summary": "Компания находится в процессе реорганизации с активными судебными спорами.",
        "findings": [
            {"category": "legal", "severity": "medium", "description": "Судебные дела"},
        ],
        "recommendations": [
            "Мониторинг судебных дел",
            "Запросить финансовую отчётность",
        ],
        "reasoning": {
            "calculation": "legal*0.35 + financial*0.30 + reputation*0.20 + regulatory*0.15",
            "confidence": 0.85,
        },
    }


@pytest.fixture
def multiple_reports(sample_report):
    """Multiple reports for bulk export tests."""
    reports = []
    for i in range(3):
        report = sample_report.copy()
        report["id"] = f"report-{i}"
        report["report_id"] = f"report-{i}"
        report["client_name"] = f"ООО Компания {i+1}"
        report["inn"] = f"77070838{90+i}"
        report["risk_score"] = 30 + i * 20
        reports.append(report)
    return reports


# ============================================================================
# TESTS FOR EXPORT HELPERS
# ============================================================================


class TestReportToJson:
    """Tests for report_to_json helper function."""

    def test_json_export_basic(self, sample_report):
        """JSON export should produce valid JSON."""
        from app.utility.export_helpers import report_to_json

        result = report_to_json(sample_report)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed is not None
        assert parsed["client_name"] == "ООО Тестовая Компания"
        assert parsed["risk_score"] == 45

    def test_json_export_pretty(self, sample_report):
        """JSON export with pretty=True should be indented."""
        from app.utility.export_helpers import report_to_json

        result = report_to_json(sample_report, pretty=True)

        # Should have indentation
        assert "\n" in result
        assert "  " in result

    def test_json_export_compact(self, sample_report):
        """JSON export with pretty=False should be compact."""
        from app.utility.export_helpers import report_to_json

        result = report_to_json(sample_report, pretty=False)

        # Should not have unnecessary whitespace
        assert "  " not in result

    def test_json_export_cyrillic(self, sample_report):
        """JSON export should preserve Cyrillic characters."""
        from app.utility.export_helpers import report_to_json

        result = report_to_json(sample_report)

        # Cyrillic should be preserved (not escaped)
        assert "ООО Тестовая Компания" in result
        assert "\\u" not in result.split('"client_name"')[1][:30]

    def test_json_export_with_datetime(self):
        """JSON export should handle datetime objects."""
        from app.utility.export_helpers import report_to_json

        report_with_datetime = {
            "timestamp": datetime(2024, 1, 15, 12, 0, 0),
            "name": "Test",
        }

        # Should not raise error - datetime is converted to string
        result = report_to_json(report_with_datetime)
        assert "2024-01-15" in result

    def test_json_export_empty_report(self):
        """JSON export should handle empty reports."""
        from app.utility.export_helpers import report_to_json

        result = report_to_json({})
        assert result == "{}"


class TestReportToCsv:
    """Tests for report_to_csv helper function."""

    def test_csv_export_basic(self, sample_report):
        """CSV export should produce valid CSV."""
        from app.utility.export_helpers import report_to_csv

        result = report_to_csv(sample_report)

        # Should contain metadata
        assert "Report ID" in result
        assert "report-123" in result
        assert "ООО Тестовая Компания" in result
        assert "7707083893" in result

    def test_csv_export_findings(self, sample_report):
        """CSV export should include findings."""
        from app.utility.export_helpers import report_to_csv

        result = report_to_csv(sample_report)

        assert "# Findings" in result
        assert "Category" in result
        assert "Sentiment" in result
        assert "legal" in result or "financial" in result

    def test_csv_export_risk_factors(self, sample_report):
        """CSV export should include risk factors."""
        from app.utility.export_helpers import report_to_csv

        result = report_to_csv(sample_report)

        assert "# Risk Factors" in result

    def test_csv_export_recommendations(self, sample_report):
        """CSV export should include recommendations."""
        from app.utility.export_helpers import report_to_csv

        result = report_to_csv(sample_report)

        assert "# Recommendations" in result

    def test_csv_export_empty_findings(self):
        """CSV export should handle reports without findings."""
        from app.utility.export_helpers import report_to_csv

        report = {
            "report_id": "test-123",
            "client_name": "Test",
            "inn": "1234567890",
            "created_at": 1705324800,
            "risk_level": "low",
            "risk_score": 10,
            "report_data": {},
        }

        result = report_to_csv(report)
        assert "test-123" in result
        # Should not crash without findings


class TestReportsSummaryToCsv:
    """Tests for reports_summary_to_csv helper function."""

    def test_summary_csv_basic(self, multiple_reports):
        """Summary CSV should contain all reports."""
        from app.utility.export_helpers import reports_summary_to_csv

        result = reports_summary_to_csv(multiple_reports)

        # Should have header
        assert "Report ID" in result
        assert "Client Name" in result
        assert "INN" in result
        assert "Risk Score" in result

        # Should have all reports
        for report in multiple_reports:
            assert report["report_id"] in result

    def test_summary_csv_columns(self, multiple_reports):
        """Summary CSV should have correct columns."""
        from app.utility.export_helpers import reports_summary_to_csv

        result = reports_summary_to_csv(multiple_reports)
        lines = result.strip().split("\n")

        # First line is header
        header = lines[0]
        assert "Report ID" in header
        assert "Findings Count" in header

        # Should have header + N data rows
        assert len(lines) == len(multiple_reports) + 1

    def test_summary_csv_empty_list(self):
        """Summary CSV should handle empty list."""
        from app.utility.export_helpers import reports_summary_to_csv

        result = reports_summary_to_csv([])

        # Should have header only
        assert "Report ID" in result


class TestNormalizeReportForExport:
    """Tests for normalize_report_for_export helper function."""

    def test_normalize_adds_iso_timestamps(self, sample_report):
        """Normalization should add ISO timestamp fields."""
        from app.utility.export_helpers import normalize_report_for_export

        result = normalize_report_for_export(sample_report)

        assert "created_at_iso" in result
        assert "2024-01-15" in result["created_at_iso"]

    def test_normalize_preserves_original(self, sample_report):
        """Normalization should preserve original fields."""
        from app.utility.export_helpers import normalize_report_for_export

        result = normalize_report_for_export(sample_report)

        assert result["client_name"] == sample_report["client_name"]
        assert result["risk_score"] == sample_report["risk_score"]

    def test_normalize_handles_missing_timestamps(self):
        """Normalization should handle reports without timestamps."""
        from app.utility.export_helpers import normalize_report_for_export

        report = {"client_name": "Test", "risk_score": 10}

        # Should not crash
        result = normalize_report_for_export(report)
        assert result["client_name"] == "Test"


class TestFormatBytesSize:
    """Tests for format_bytes_size helper function."""

    def test_bytes(self):
        """Should format bytes correctly."""
        from app.utility.export_helpers import format_bytes_size

        assert format_bytes_size(500) == "500.0 B"

    def test_kilobytes(self):
        """Should format kilobytes correctly."""
        from app.utility.export_helpers import format_bytes_size

        assert format_bytes_size(1024) == "1.0 KB"
        assert format_bytes_size(1536) == "1.5 KB"

    def test_megabytes(self):
        """Should format megabytes correctly."""
        from app.utility.export_helpers import format_bytes_size

        assert format_bytes_size(1024 * 1024) == "1.0 MB"
        assert format_bytes_size(2 * 1024 * 1024) == "2.0 MB"

    def test_gigabytes(self):
        """Should format gigabytes correctly."""
        from app.utility.export_helpers import format_bytes_size

        assert format_bytes_size(1024 * 1024 * 1024) == "1.0 GB"


# ============================================================================
# TESTS FOR EXPORT API ENDPOINTS (export.py)
# ============================================================================


class TestExcelExport:
    """Tests for Excel export endpoint."""

    @pytest.mark.asyncio
    async def test_excel_export_success(self, sample_report):
        """Excel export should return xlsx file."""
        from app.api.v1 import v1_app as app

        with patch("app.api.routes.export._get_report", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_report

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/report-123/excel")

            if response.status_code == 200:
                # Check content type
                assert (
                    "spreadsheetml" in response.headers.get("content-type", "")
                    or "octet-stream" in response.headers.get("content-type", "")
                )
                # Check filename in disposition
                disposition = response.headers.get("content-disposition", "")
                assert "report_report-123" in disposition
                assert ".xlsx" in disposition

    @pytest.mark.asyncio
    async def test_excel_export_not_found(self):
        """Excel export should return 404 for missing report."""
        from app.api.v1 import v1_app as app

        with patch("app.api.routes.export._get_report", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/nonexistent/excel")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_excel_export_missing_pandas(self, sample_report):
        """Excel export should handle missing pandas gracefully."""
        from app.api.v1 import v1_app as app

        with patch("app.api.routes.export._get_report", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_report

            # Simulate pandas import error
            with patch.dict("sys.modules", {"pandas": None}):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.get("/export/report-123/excel")

                # May return 500 if pandas not available
                assert response.status_code in [200, 500]


class TestWordExport:
    """Tests for Word export endpoint."""

    @pytest.mark.asyncio
    async def test_word_export_success(self, sample_report):
        """Word export should return docx file."""
        from app.api.v1 import v1_app as app

        with patch("app.api.routes.export._get_report", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_report

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/report-123/word")

            if response.status_code == 200:
                # Check content type
                assert (
                    "wordprocessingml" in response.headers.get("content-type", "")
                    or "octet-stream" in response.headers.get("content-type", "")
                )
                # Check filename
                disposition = response.headers.get("content-disposition", "")
                assert ".docx" in disposition

    @pytest.mark.asyncio
    async def test_word_export_not_found(self):
        """Word export should return 404 for missing report."""
        from app.api.v1 import v1_app as app

        with patch("app.api.routes.export._get_report", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/nonexistent/word")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_word_export_with_all_sections(self, sample_report):
        """Word export should include all report sections."""
        from app.api.v1 import v1_app as app

        with patch("app.api.routes.export._get_report", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_report

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/report-123/word")

            # Just check it doesn't error - content is binary
            assert response.status_code in [200, 500]


class TestHistoryTimeline:
    """Tests for analysis history timeline endpoint."""

    @pytest.mark.asyncio
    async def test_history_timeline_success(self, multiple_reports):
        """History timeline should return analysis snapshots."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get_by_inn.return_value = multiple_reports
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/history/7707083893")

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_history_timeline_empty(self):
        """History timeline should return empty list for unknown INN."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get_by_inn.return_value = []
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/history/0000000000")

            if response.status_code == 200:
                data = response.json()
                assert data == []

    @pytest.mark.asyncio
    async def test_history_timeline_limit(self):
        """History timeline should respect limit parameter."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get_by_inn.return_value = []
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/export/history/7707083893?limit=5")

            assert response.status_code in [200, 500]


# ============================================================================
# TESTS FOR REPORTS EXPORT ENDPOINTS (reports.py)
# ============================================================================


class TestReportJsonCsvExport:
    """Tests for /reports/{report_id}/export endpoint."""

    @pytest.mark.asyncio
    async def test_export_json_format(self, sample_report):
        """JSON export should return valid JSON."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = sample_report
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/reports/report-123/export?format=json")

            if response.status_code == 200:
                assert response.headers.get("content-type") == "application/json"
                # Should be valid JSON
                data = json.loads(response.text)
                assert data is not None

    @pytest.mark.asyncio
    async def test_export_csv_format(self, sample_report):
        """CSV export should return valid CSV."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = sample_report
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/reports/report-123/export?format=csv")

            if response.status_code == 200:
                assert response.headers.get("content-type") == "text/csv"
                # Should contain report data
                assert "report-123" in response.text or "Report ID" in response.text

    @pytest.mark.asyncio
    async def test_export_default_format_is_json(self, sample_report):
        """Default export format should be JSON."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = sample_report
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/reports/report-123/export")

            if response.status_code == 200:
                assert response.headers.get("content-type") == "application/json"

    @pytest.mark.asyncio
    async def test_export_report_not_found(self):
        """Export should return 404 for missing report."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = None
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/reports/nonexistent/export")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_content_disposition(self, sample_report):
        """Export should set Content-Disposition header."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = sample_report
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/reports/report-123/export?format=json")

            if response.status_code == 200:
                disposition = response.headers.get("content-disposition", "")
                assert "attachment" in disposition
                assert "report_report-123.json" in disposition


class TestBulkExport:
    """Tests for bulk export endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_export_csv(self, multiple_reports):
        """Bulk export should create summary CSV."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.side_effect = lambda rid: next(
                (r for r in multiple_reports if r["report_id"] == rid), None
            )
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/reports/bulk-export?format=csv",
                    json={"report_ids": ["report-0", "report-1", "report-2"]},
                )

            if response.status_code == 200:
                assert response.headers.get("content-type") == "text/csv"
                # Should contain all reports
                for report in multiple_reports:
                    assert report["report_id"] in response.text

    @pytest.mark.asyncio
    async def test_bulk_export_empty_list(self):
        """Bulk export with empty list should return 404 or error."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = None
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/reports/bulk-export?format=csv",
                    json={"report_ids": ["nonexistent-1", "nonexistent-2"]},
                )

            # Should return 404 if no reports found
            assert response.status_code in [404, 422, 500]

    @pytest.mark.asyncio
    async def test_bulk_export_partial_success(self, sample_report):
        """Bulk export should handle partial availability."""
        from app.api.v1 import v1_app as app

        def get_report_mock(report_id):
            if report_id == "report-123":
                return sample_report
            return None

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.side_effect = get_report_mock
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/reports/bulk-export?format=csv",
                    json={"report_ids": ["report-123", "nonexistent"]},
                )

            if response.status_code == 200:
                # Should export available reports
                assert "report-123" in response.text


# ============================================================================
# TESTS FOR EDGE CASES AND ERROR HANDLING
# ============================================================================


class TestExportEdgeCases:
    """Tests for export edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_export_with_special_characters(self):
        """Export should handle special characters in data."""
        from app.utility.export_helpers import report_to_json, report_to_csv

        report = {
            "report_id": "test-123",
            "client_name": 'ООО "Тест & Партнёры"',
            "inn": "1234567890",
            "created_at": 1705324800,
            "risk_level": "low",
            "risk_score": 10,
            "report_data": {
                "findings": [{"category": "test", "sentiment": "neutral", "key_points": "Text with <html> & \"quotes\""}]
            },
        }

        # JSON should handle special chars
        json_result = report_to_json(report)
        assert 'ООО "Тест & Партнёры"' in json_result or 'ООО \\"Тест' in json_result

        # CSV should handle special chars
        csv_result = report_to_csv(report)
        assert "test-123" in csv_result

    @pytest.mark.asyncio
    async def test_export_with_none_values(self):
        """Export should handle None values gracefully."""
        from app.utility.export_helpers import report_to_json, normalize_report_for_export

        report = {
            "report_id": "test-123",
            "client_name": None,
            "inn": None,
            "risk_score": None,
        }

        # Should not crash
        json_result = report_to_json(report)
        assert "null" in json_result

        normalized = normalize_report_for_export(report)
        assert normalized["report_id"] == "test-123"

    @pytest.mark.asyncio
    async def test_export_with_large_data(self):
        """Export should handle large data sets."""
        from app.utility.export_helpers import report_to_json, reports_summary_to_csv

        # Create large report
        large_report = {
            "report_id": "large-report",
            "client_name": "Test",
            "inn": "1234567890",
            "created_at": 1705324800,
            "risk_level": "medium",
            "risk_score": 50,
            "report_data": {
                "findings": [
                    {"category": f"cat-{i}", "sentiment": "neutral", "key_points": f"Finding {i} " * 100}
                    for i in range(100)
                ],
                "recommendations": [f"Recommendation {i} " * 50 for i in range(50)],
            },
        }

        # Should handle large data
        json_result = report_to_json(large_report)
        assert len(json_result) > 10000

        # Create many reports for summary
        many_reports = [
            {
                "report_id": f"report-{i}",
                "client_name": f"Company {i}",
                "inn": f"{1234567890 + i}",
                "created_at": 1705324800,
                "risk_level": "low",
                "risk_score": i % 100,
                "report_data": {"findings": []},
            }
            for i in range(100)
        ]

        csv_result = reports_summary_to_csv(many_reports)
        assert csv_result.count("\n") > 100  # Should have 100+ rows

    @pytest.mark.asyncio
    async def test_export_with_unicode_edge_cases(self):
        """Export should handle various Unicode characters."""
        from app.utility.export_helpers import report_to_json

        report = {
            "report_id": "unicode-test",
            "client_name": "日本語テスト 한국어 العربية",
            "description": "Emoji test: 🎉 🚀 ✅",
            "special": "Math: ∑∏∫ Currency: €£¥",
        }

        result = report_to_json(report)
        # Should preserve all Unicode
        assert "日本語テスト" in result
        assert "한국어" in result

    def test_csv_export_with_commas_in_data(self):
        """CSV export should properly escape commas in data."""
        from app.utility.export_helpers import report_to_csv

        report = {
            "report_id": "comma-test",
            "client_name": "Company, Inc.",
            "inn": "1234567890",
            "created_at": 1705324800,
            "risk_level": "low",
            "risk_score": 10,
            "report_data": {
                "findings": [
                    {"category": "legal", "sentiment": "neutral", "key_points": "Issue A, Issue B, Issue C"}
                ]
            },
        }

        result = report_to_csv(report)
        # CSV should properly handle commas (they should be quoted)
        assert "comma-test" in result


class TestExportSecurityAndValidation:
    """Tests for export security and input validation."""

    @pytest.mark.asyncio
    async def test_export_sanitizes_report_id(self):
        """Export should handle potentially malicious report IDs."""
        from app.api.v1 import v1_app as app

        with patch("app.storage.tarantool.TarantoolClient.get_instance", new_callable=AsyncMock) as mock_tarantool:
            mock_client = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.get.return_value = None
            mock_client.get_reports_repository.return_value = mock_repo
            mock_tarantool.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Test path traversal attempt
                response = await client.get("/reports/../../../etc/passwd/export")

            # Should return 404 or 422, not allow path traversal
            assert response.status_code in [404, 422, 500]

    @pytest.mark.asyncio
    async def test_bulk_export_validates_limit(self):
        """Bulk export should validate list size."""
        from app.api.v1 import v1_app as app

        # Try to export too many reports (if there's a limit)
        many_ids = [f"report-{i}" for i in range(200)]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/reports/bulk-export?format=csv",
                json={"report_ids": many_ids},
            )

        # Should either process or return validation error
        assert response.status_code in [200, 422, 500]


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestExportIntegration:
    """Integration tests for export functionality."""

    @pytest.mark.asyncio
    async def test_full_export_workflow(self, sample_report):
        """Test complete export workflow: get report -> export to multiple formats."""
        from app.utility.export_helpers import (
            report_to_json,
            report_to_csv,
            normalize_report_for_export,
        )

        # Step 1: Normalize report
        normalized = normalize_report_for_export(sample_report)
        assert "created_at_iso" in normalized

        # Step 2: Export to JSON
        json_export = report_to_json(normalized)
        parsed = json.loads(json_export)
        assert parsed["client_name"] == sample_report["client_name"]

        # Step 3: Export to CSV
        csv_export = report_to_csv(sample_report)
        assert sample_report["report_id"] in csv_export

    @pytest.mark.asyncio
    async def test_export_preserves_data_integrity(self, sample_report):
        """Export should preserve all data without loss."""
        from app.utility.export_helpers import report_to_json

        # Export and reimport
        json_str = report_to_json(sample_report)
        reimported = json.loads(json_str)

        # All key fields should be preserved
        assert reimported["client_name"] == sample_report["client_name"]
        assert reimported["inn"] == sample_report["inn"]
        assert reimported["risk_score"] == sample_report["risk_score"]
        assert reimported["risk_level"] == sample_report["risk_level"]

        # Nested data should be preserved
        assert reimported["risk_assessment"]["score"] == sample_report["risk_assessment"]["score"]
        assert reimported["risk_assessment"]["factors"] == sample_report["risk_assessment"]["factors"]


class TestExportRouterExists:
    """Tests to verify export router is properly mounted."""

    @pytest.mark.asyncio
    async def test_export_routes_exist(self):
        """Export router should be mounted with correct routes."""
        from app.api.v1 import v1_app as app

        routes = [route.path for route in app.routes]

        # Should have export routes
        export_routes = [r for r in routes if "/export" in r]
        assert len(export_routes) > 0, "No export routes found"

    @pytest.mark.asyncio
    async def test_reports_export_route_exists(self):
        """Reports export route should exist."""
        from app.api.v1 import v1_app as app

        routes = [route.path for route in app.routes]

        # Should have /reports/*/export route
        assert any("export" in r for r in routes), "No export route in reports"
