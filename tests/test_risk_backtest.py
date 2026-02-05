"""
Tests for risk score backtesting against ground truth dataset.

Phase 5.1: Ground truth dataset validation.
Ensures risk_calculator produces scores consistent with expert-labeled expectations.
"""

import json
import os

import pytest

from app.agents.risk_calculator import calculate_normalized_risk

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
GROUND_TRUTH_FILE = os.path.join(FIXTURES_DIR, "ground_truth_risk_scores.json")


def _load_ground_truth():
    with open(GROUND_TRUTH_FILE) as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


@pytest.mark.parametrize(
    "case",
    GROUND_TRUTH,
    ids=[c["id"] for c in GROUND_TRUTH],
)
class TestRiskScoreBacktest:
    """Backtesting risk scores against expert-labeled ground truth."""

    def test_score_in_expected_range(self, case):
        """Calculated score must fall within the expert-labeled range."""
        result = calculate_normalized_risk(
            case["source_data"],
            case.get("search_results", []),
        )
        lo, hi = case["expected_score_range"]
        assert lo <= result["score"] <= hi, (
            f"[{case['id']}] {case['description']}: "
            f"score={result['score']} not in [{lo}, {hi}]. "
            f"Level={result['level']}. Factors: {result['factors']}"
        )

    def test_level_matches_expected(self, case):
        """Risk level must match the expert-labeled level."""
        result = calculate_normalized_risk(
            case["source_data"],
            case.get("search_results", []),
        )
        assert result["level"] == case["expected_level"], (
            f"[{case['id']}] {case['description']}: "
            f"level={result['level']} != expected={case['expected_level']}. "
            f"Score={result['score']}"
        )


class TestGroundTruthDatasetIntegrity:
    """Validate the ground truth dataset itself."""

    def test_dataset_not_empty(self):
        assert len(GROUND_TRUTH) >= 10

    def test_all_cases_have_required_fields(self):
        required = {
            "id",
            "description",
            "source_data",
            "expected_level",
            "expected_score_range",
        }
        for case in GROUND_TRUTH:
            missing = required - set(case.keys())
            assert not missing, f"Case {case.get('id')}: missing fields {missing}"

    def test_all_ids_unique(self):
        ids = [c["id"] for c in GROUND_TRUTH]
        assert len(ids) == len(set(ids))

    def test_score_ranges_valid(self):
        for case in GROUND_TRUTH:
            lo, hi = case["expected_score_range"]
            assert 0 <= lo <= hi <= 100, f"Case {case['id']}: invalid range [{lo}, {hi}]"

    def test_levels_valid(self):
        valid_levels = {"low", "medium", "high", "critical"}
        for case in GROUND_TRUTH:
            assert case["expected_level"] in valid_levels, (
                f"Case {case['id']}: invalid level '{case['expected_level']}'"
            )

    def test_coverage_all_risk_levels(self):
        """Ground truth should cover all 4 risk levels."""
        levels = {c["expected_level"] for c in GROUND_TRUTH}
        assert levels == {"low", "medium", "high", "critical"}
