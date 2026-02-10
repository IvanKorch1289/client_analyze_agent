"""
Tests for A/B testing infrastructure (Phase 5.5).

Run: pytest tests/test_ab_testing.py -v
"""

import pytest

from app.shared.ab_testing import (
    ABTestingManager,
    Experiment,
    ExperimentAssignment,
)


@pytest.fixture
def manager():
    """Fresh ABTestingManager for each test."""
    return ABTestingManager()


@pytest.fixture
def sample_experiment():
    """Standard 50/50 experiment."""
    return Experiment(
        name="model_comparison",
        variants={
            "control": {"model": "claude-3.5-sonnet", "temperature": 0.1},
            "treatment": {"model": "llama-3.1-70b", "temperature": 0.1},
        },
        traffic_split={"control": 0.5, "treatment": 0.5},
        description="Compare Claude vs Llama for risk analysis",
    )


@pytest.fixture
def three_way_experiment():
    """Three-way split experiment."""
    return Experiment(
        name="prompt_comparison",
        variants={
            "standard": {"prompt": "report_analyzer"},
            "cot": {"prompt": "report_analyzer_cot"},
            "risk_assessor": {"prompt": "risk_assessor"},
        },
        traffic_split={"standard": 0.34, "cot": 0.33, "risk_assessor": 0.33},
    )


class TestExperimentDefinition:
    """Test experiment creation and validation."""

    def test_valid_experiment(self, sample_experiment):
        assert sample_experiment.name == "model_comparison"
        assert len(sample_experiment.variants) == 2
        assert sample_experiment.enabled is True

    def test_mismatched_keys_raises(self):
        with pytest.raises(ValueError, match="variant keys must match"):
            Experiment(
                name="bad",
                variants={"a": {}, "b": {}},
                traffic_split={"a": 0.5, "c": 0.5},  # "c" not in variants
            )

    def test_traffic_split_not_summing_to_one(self):
        with pytest.raises(ValueError, match="must sum to 1.0"):
            Experiment(
                name="bad",
                variants={"a": {}, "b": {}},
                traffic_split={"a": 0.3, "b": 0.3},  # sum = 0.6
            )

    def test_three_way_experiment(self, three_way_experiment):
        assert len(three_way_experiment.variants) == 3
        total = sum(three_way_experiment.traffic_split.values())
        assert abs(total - 1.0) < 0.01


class TestVariantAssignment:
    """Test deterministic variant assignment."""

    def test_assignment_returns_result(self, manager, sample_experiment):
        manager.register_experiment(sample_experiment)
        result = manager.assign("model_comparison", "req-001")
        assert result is not None
        assert isinstance(result, ExperimentAssignment)
        assert result.variant in ("control", "treatment")
        assert result.experiment_name == "model_comparison"
        assert result.request_id == "req-001"

    def test_deterministic_assignment(self, manager, sample_experiment):
        """Same request_id always gets same variant."""
        manager.register_experiment(sample_experiment)
        results = [manager.assign("model_comparison", "req-stable") for _ in range(10)]
        variants = {r.variant for r in results}
        assert len(variants) == 1  # All same

    def test_different_requests_get_different_variants(self, manager, sample_experiment):
        """Different request IDs should distribute across variants."""
        manager.register_experiment(sample_experiment)
        variants = set()
        for i in range(100):
            result = manager.assign("model_comparison", f"req-{i}")
            variants.add(result.variant)
        # With 100 requests and 50/50 split, both variants should appear
        assert len(variants) == 2

    def test_assignment_config_matches_variant(self, manager, sample_experiment):
        manager.register_experiment(sample_experiment)
        result = manager.assign("model_comparison", "req-001")
        expected_config = sample_experiment.variants[result.variant]
        assert result.config == expected_config

    def test_disabled_experiment_returns_none(self, manager, sample_experiment):
        sample_experiment.enabled = False
        manager.register_experiment(sample_experiment)
        result = manager.assign("model_comparison", "req-001")
        assert result is None

    def test_nonexistent_experiment_returns_none(self, manager):
        result = manager.assign("does_not_exist", "req-001")
        assert result is None

    def test_deactivate_experiment(self, manager, sample_experiment):
        manager.register_experiment(sample_experiment)
        result1 = manager.assign("model_comparison", "req-001")
        assert result1 is not None

        manager.deactivate_experiment("model_comparison")
        result2 = manager.assign("model_comparison", "req-002")
        assert result2 is None


class TestOutcomeRecording:
    """Test outcome recording and aggregation."""

    def test_record_outcome(self, manager, sample_experiment):
        manager.register_experiment(sample_experiment)
        manager.assign("model_comparison", "req-001")
        manager.record_outcome(
            "model_comparison",
            "req-001",
            {"latency": 2.5, "risk_score": 45, "success": True},
        )
        results = manager.get_results("model_comparison")
        assert results["experiment"] == "model_comparison"
        # At least one variant should have outcomes
        total = sum(v.get("count", 0) for v in results["variants"].values())
        assert total == 1

    def test_aggregate_numeric_metrics(self, manager, sample_experiment):
        manager.register_experiment(sample_experiment)

        # Record multiple outcomes
        for i in range(10):
            req_id = f"req-{i}"
            manager.assign("model_comparison", req_id)
            manager.record_outcome(
                "model_comparison",
                req_id,
                {"latency": 1.0 + i * 0.1, "risk_score": 30 + i},
            )

        results = manager.get_results("model_comparison")
        total = sum(v.get("count", 0) for v in results["variants"].values())
        assert total == 10

        # Check aggregation structure
        for variant_data in results["variants"].values():
            if variant_data["count"] > 0:
                assert "latency" in variant_data
                assert "mean" in variant_data["latency"]
                assert "min" in variant_data["latency"]
                assert "max" in variant_data["latency"]

    def test_unassigned_outcome_is_logged(self, manager, sample_experiment):
        """Recording outcome for unassigned request should not crash."""
        manager.register_experiment(sample_experiment)
        # No assignment for req-999
        manager.record_outcome("model_comparison", "req-999", {"latency": 1.0})
        results = manager.get_results("model_comparison")
        total = sum(v.get("count", 0) for v in results["variants"].values())
        assert total == 0  # Outcome was discarded

    def test_nonexistent_experiment_results(self, manager):
        results = manager.get_results("does_not_exist")
        assert "error" in results


class TestExperimentListing:
    """Test experiment listing and status."""

    def test_list_experiments(self, manager, sample_experiment, three_way_experiment):
        manager.register_experiment(sample_experiment)
        manager.register_experiment(three_way_experiment)

        listing = manager.list_experiments()
        assert len(listing) == 2
        names = {e["name"] for e in listing}
        assert names == {"model_comparison", "prompt_comparison"}

    def test_listing_includes_counts(self, manager, sample_experiment):
        manager.register_experiment(sample_experiment)
        manager.assign("model_comparison", "req-001")
        manager.assign("model_comparison", "req-002")

        listing = manager.list_experiments()
        assert listing[0]["assignments"] == 2
        assert listing[0]["outcomes"] == 0


class TestTrafficDistribution:
    """Verify traffic split approximates configured ratios."""

    def test_50_50_split(self, manager):
        exp = Experiment(
            name="even_split",
            variants={"a": {}, "b": {}},
            traffic_split={"a": 0.5, "b": 0.5},
        )
        manager.register_experiment(exp)

        counts = {"a": 0, "b": 0}
        for i in range(1000):
            result = manager.assign("even_split", f"req-{i}")
            counts[result.variant] += 1

        # With 1000 samples, each should be roughly 500 ± 100
        assert 350 < counts["a"] < 650, f"Unexpected distribution: {counts}"
        assert 350 < counts["b"] < 650, f"Unexpected distribution: {counts}"

    def test_90_10_split(self, manager):
        exp = Experiment(
            name="skewed_split",
            variants={"majority": {}, "minority": {}},
            traffic_split={"majority": 0.9, "minority": 0.1},
        )
        manager.register_experiment(exp)

        counts = {"majority": 0, "minority": 0}
        for i in range(1000):
            result = manager.assign("skewed_split", f"req-{i}")
            counts[result.variant] += 1

        # Majority should be around 900 ± 100
        assert counts["majority"] > 750, f"Majority too low: {counts}"
        assert counts["minority"] > 30, f"Minority too low: {counts}"
