"""
LLM Evaluation Framework scaffold (Phase 5.2).

Provides deterministic checks for LLM output quality without calling real LLMs.
Tests validate:
- JSON schema compliance of LLM responses
- Risk level consistency (score ↔ level mapping)
- Required fields presence
- Reasoning quality heuristics

Future: integrate with RAGAS/DeepEval for embedding-based metrics.

Run: pytest tests/test_llm_evaluation.py -v
"""

import json
from typing import Any, Dict, List, Optional

import pytest


# ============================================================================
# Sample LLM outputs for evaluation (mock responses)
# ============================================================================

VALID_COT_RESPONSE = {
    "reasoning": {
        "sources_analyzed": ["dadata", "casebook", "infosphere", "perplexity", "tavily"],
        "data_quality": {
            "complete_sources": 4,
            "partial_sources": 1,
            "failed_sources": 0,
        },
        "risk_factors": [
            {
                "factor": "15 судебных дел в качестве ответчика",
                "category": "legal",
                "severity": "high",
                "impact": 25,
                "source": "casebook",
                "evidence": "Casebook data: 15 defendant cases",
            }
        ],
        "positive_factors": [
            {"factor": "Длительная история работы (12 лет)", "impact": -5, "source": "dadata"}
        ],
        "calculation": "0 + 25 + 20 - 5 = 40",
        "confidence": 0.8,
    },
    "risk_assessment": {
        "score": 40,
        "level": "medium",
        "factors": [
            "15 судебных дел в качестве ответчика",
            "Высокая долговая нагрузка",
        ],
        "categories": {
            "legal_risk": 25,
            "financial_risk": 20,
            "reputation_risk": 5,
            "operational_risk": 0,
            "affiliation_risk": 0,
            "sanctions_risk": 0,
        },
    },
    "summary": "Компания имеет повышенный правовой риск из-за множества судебных дел.",
    "findings": [
        {
            "category": "legal",
            "severity": "high",
            "description": "15 судебных дел в качестве ответчика",
            "source": "casebook",
            "recommendation": "Запросить справку об отсутствии задолженности",
        }
    ],
    "recommendations": [
        "Запросить справку об отсутствии задолженности",
        "Рассмотреть банковскую гарантию",
    ],
}

VALID_SIMPLE_RESPONSE = {
    "risk_assessment": {
        "score": 15,
        "level": "low",
        "factors": ["Нет существенных рисков"],
    },
    "summary": "Компания не имеет существенных рисков.",
    "findings": [],
    "recommendations": ["Стандартная проверка"],
}

INVALID_SCORE_LEVEL_RESPONSE = {
    "risk_assessment": {
        "score": 80,
        "level": "low",  # Mismatch: score 80 should be "critical"
        "factors": [],
    },
    "summary": "test",
    "findings": [],
    "recommendations": [],
}

MISSING_FIELDS_RESPONSE = {
    "risk_assessment": {"score": 50},
    # Missing: summary, findings, recommendations
}


# ============================================================================
# Evaluation functions
# ============================================================================


def _level_for_score(score: int) -> str:
    """Expected risk level for a given score."""
    if score < 25:
        return "low"
    elif score < 50:
        return "medium"
    elif score < 75:
        return "high"
    return "critical"


def evaluate_schema_compliance(response: Dict[str, Any]) -> List[str]:
    """Check if the LLM response has all required fields.

    Returns list of missing/invalid fields.
    """
    errors: List[str] = []

    if "risk_assessment" not in response:
        errors.append("missing risk_assessment")
    else:
        ra = response["risk_assessment"]
        if "score" not in ra:
            errors.append("missing risk_assessment.score")
        elif not isinstance(ra["score"], (int, float)):
            errors.append("risk_assessment.score is not numeric")
        elif not (0 <= ra["score"] <= 100):
            errors.append(f"risk_assessment.score out of range: {ra['score']}")
        if "level" not in ra:
            errors.append("missing risk_assessment.level")
        elif ra["level"] not in ("low", "medium", "high", "critical"):
            errors.append(f"invalid risk_assessment.level: {ra['level']}")

    if "summary" not in response:
        errors.append("missing summary")
    elif not response["summary"] or len(response["summary"]) < 10:
        errors.append("summary too short")

    if "findings" not in response:
        errors.append("missing findings")

    if "recommendations" not in response:
        errors.append("missing recommendations")

    return errors


def evaluate_score_level_consistency(response: Dict[str, Any]) -> Optional[str]:
    """Check if score and level are consistent.

    Returns error message or None if consistent.
    """
    ra = response.get("risk_assessment", {})
    score = ra.get("score")
    level = ra.get("level")

    if score is None or level is None:
        return "score or level missing"

    expected = _level_for_score(int(score))
    if level != expected:
        return f"score {score} → expected '{expected}', got '{level}'"
    return None


def evaluate_reasoning_quality(response: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate CoT reasoning quality (if present).

    Returns dict with quality metrics.
    """
    reasoning = response.get("reasoning")
    if not reasoning:
        return {"has_reasoning": False}

    quality: Dict[str, Any] = {"has_reasoning": True}

    # Sources coverage
    sources = reasoning.get("sources_analyzed", [])
    quality["sources_count"] = len(sources)
    quality["has_all_sources"] = len(sources) >= 3

    # Risk factors
    factors = reasoning.get("risk_factors", [])
    quality["risk_factors_count"] = len(factors)
    quality["factors_have_evidence"] = all(
        f.get("evidence") or f.get("source") for f in factors
    )
    quality["factors_have_impact"] = all(
        isinstance(f.get("impact"), (int, float)) for f in factors
    )

    # Calculation present
    quality["has_calculation"] = bool(reasoning.get("calculation"))

    # Confidence
    confidence = reasoning.get("confidence")
    quality["has_confidence"] = confidence is not None
    quality["confidence_reasonable"] = (
        isinstance(confidence, (int, float)) and 0 <= confidence <= 1
    ) if confidence is not None else False

    return quality


def evaluate_findings_quality(response: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate findings quality.

    Returns dict with quality metrics.
    """
    findings = response.get("findings", [])
    if not findings:
        return {"findings_count": 0, "all_have_category": True, "all_have_source": True}

    return {
        "findings_count": len(findings),
        "all_have_category": all(f.get("category") for f in findings),
        "all_have_source": all(f.get("source") for f in findings),
        "all_have_severity": all(f.get("severity") for f in findings),
        "all_have_description": all(f.get("description") for f in findings),
    }


# ============================================================================
# Tests
# ============================================================================


class TestSchemaCompliance:
    """Validate LLM response schema compliance."""

    def test_valid_cot_response_passes(self):
        errors = evaluate_schema_compliance(VALID_COT_RESPONSE)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_simple_response_passes(self):
        errors = evaluate_schema_compliance(VALID_SIMPLE_RESPONSE)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_fields_detected(self):
        errors = evaluate_schema_compliance(MISSING_FIELDS_RESPONSE)
        assert "missing summary" in errors
        assert "missing findings" in errors
        assert "missing recommendations" in errors

    def test_empty_response_detected(self):
        errors = evaluate_schema_compliance({})
        assert len(errors) >= 4  # All top-level fields missing

    def test_score_out_of_range(self):
        response = {
            "risk_assessment": {"score": 150, "level": "critical"},
            "summary": "Test summary text",
            "findings": [],
            "recommendations": [],
        }
        errors = evaluate_schema_compliance(response)
        assert any("out of range" in e for e in errors)


class TestScoreLevelConsistency:
    """Validate score ↔ level mapping."""

    def test_valid_cot_is_consistent(self):
        error = evaluate_score_level_consistency(VALID_COT_RESPONSE)
        assert error is None

    def test_valid_simple_is_consistent(self):
        error = evaluate_score_level_consistency(VALID_SIMPLE_RESPONSE)
        assert error is None

    def test_mismatch_detected(self):
        error = evaluate_score_level_consistency(INVALID_SCORE_LEVEL_RESPONSE)
        assert error is not None
        assert "expected 'critical'" in error

    @pytest.mark.parametrize(
        "score,level",
        [
            (0, "low"),
            (24, "low"),
            (25, "medium"),
            (49, "medium"),
            (50, "high"),
            (74, "high"),
            (75, "critical"),
            (100, "critical"),
        ],
    )
    def test_boundary_scores(self, score, level):
        response = {"risk_assessment": {"score": score, "level": level}}
        error = evaluate_score_level_consistency(response)
        assert error is None, f"Score {score} should be '{level}': {error}"


class TestReasoningQuality:
    """Evaluate Chain-of-Thought reasoning quality."""

    def test_cot_response_quality(self):
        quality = evaluate_reasoning_quality(VALID_COT_RESPONSE)
        assert quality["has_reasoning"] is True
        assert quality["sources_count"] == 5
        assert quality["has_all_sources"] is True
        assert quality["risk_factors_count"] >= 1
        assert quality["factors_have_evidence"] is True
        assert quality["factors_have_impact"] is True
        assert quality["has_calculation"] is True
        assert quality["has_confidence"] is True
        assert quality["confidence_reasonable"] is True

    def test_simple_response_has_no_reasoning(self):
        quality = evaluate_reasoning_quality(VALID_SIMPLE_RESPONSE)
        assert quality["has_reasoning"] is False

    def test_partial_reasoning(self):
        response = {
            "reasoning": {
                "sources_analyzed": ["dadata"],
                "risk_factors": [{"factor": "test", "impact": 10}],
            }
        }
        quality = evaluate_reasoning_quality(response)
        assert quality["has_reasoning"] is True
        assert quality["sources_count"] == 1
        assert quality["has_all_sources"] is False
        assert quality["has_calculation"] is False
        assert quality["has_confidence"] is False


class TestFindingsQuality:
    """Evaluate findings quality metrics."""

    def test_cot_findings_quality(self):
        quality = evaluate_findings_quality(VALID_COT_RESPONSE)
        assert quality["findings_count"] >= 1
        assert quality["all_have_category"] is True
        assert quality["all_have_source"] is True
        assert quality["all_have_severity"] is True

    def test_empty_findings(self):
        quality = evaluate_findings_quality(VALID_SIMPLE_RESPONSE)
        assert quality["findings_count"] == 0

    def test_incomplete_findings(self):
        response = {
            "findings": [
                {"category": "legal"},  # Missing severity, source, description
            ]
        }
        quality = evaluate_findings_quality(response)
        assert quality["findings_count"] == 1
        assert quality["all_have_severity"] is False
        assert quality["all_have_source"] is False


class TestEvaluationFrameworkIntegrity:
    """Meta-tests for the evaluation framework itself."""

    def test_level_for_score_boundaries(self):
        assert _level_for_score(0) == "low"
        assert _level_for_score(24) == "low"
        assert _level_for_score(25) == "medium"
        assert _level_for_score(49) == "medium"
        assert _level_for_score(50) == "high"
        assert _level_for_score(74) == "high"
        assert _level_for_score(75) == "critical"
        assert _level_for_score(100) == "critical"

    def test_all_evaluators_return_expected_types(self):
        assert isinstance(evaluate_schema_compliance(VALID_COT_RESPONSE), list)
        assert isinstance(evaluate_reasoning_quality(VALID_COT_RESPONSE), dict)
        assert isinstance(evaluate_findings_quality(VALID_COT_RESPONSE), dict)
        result = evaluate_score_level_consistency(VALID_COT_RESPONSE)
        assert result is None or isinstance(result, str)

    def test_sample_responses_are_valid_json(self):
        """Ensure sample responses can round-trip through JSON."""
        for response in [VALID_COT_RESPONSE, VALID_SIMPLE_RESPONSE]:
            serialized = json.dumps(response, ensure_ascii=False)
            deserialized = json.loads(serialized)
            assert deserialized == response
