from app.utility.pdf_generator import normalize_report_for_pdf


def test_normalize_report_for_pdf_supports_current_report_shape():
    report = {
        "risk_assessment": {"score": 77, "level": "critical", "factors": ["x"]},
        "summary": "SUMMARY",
        "findings": [{"category": "Cat", "key_points": "KP"}],
        "recommendations": ["R1", "R2"],
        "citations": ["https://example.com"],
    }

    normalized = normalize_report_for_pdf(report)
    assert normalized["risk_score"] == 77
    assert normalized["risk_level"] == "critical"
    assert normalized["summary"] == "SUMMARY"
    assert normalized["findings"] and isinstance(normalized["findings"][0], str)
    assert normalized["recommendations"] == ["R1", "R2"]
    assert normalized["citations"] == ["https://example.com"]


def test_normalize_report_for_pdf_supports_legacy_shape():
    report = {
        "risk_score": 12,
        "risk_level": "low",
        "findings": ["F1"],
        "recommendations": ["R1"],
        "citations": [],
    }
    normalized = normalize_report_for_pdf(report)
    assert normalized["risk_score"] == 12
    assert normalized["risk_level"] == "low"
    assert normalized["findings"] == ["F1"]

