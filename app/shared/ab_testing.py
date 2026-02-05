"""
A/B Testing Infrastructure for LLM experiments (Phase 5.5).

Supports running experiments that compare different LLM configurations:
- Different providers (e.g., OpenRouter vs GigaChat)
- Different models (e.g., Claude 3.5 vs Llama 3.1)
- Different prompts (e.g., standard vs CoT)
- Different temperatures or other parameters

Usage:
    from app.shared.ab_testing import ab_manager

    # Register experiment
    ab_manager.register_experiment(Experiment(
        name="cot_vs_standard",
        variants={"control": {"prompt": "standard"}, "treatment": {"prompt": "cot"}},
        traffic_split={"control": 0.5, "treatment": 0.5},
    ))

    # Assign variant for a request
    variant = ab_manager.assign("cot_vs_standard", request_id="req-123")
    # variant = "control" or "treatment"

    # Record outcome
    ab_manager.record_outcome("cot_vs_standard", request_id="req-123",
                               metrics={"latency": 2.5, "risk_score": 45})
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.shared.toolkit.logging import logger


@dataclass
class Experiment:
    """Defines an A/B test experiment.

    Attributes:
        name: Unique experiment name (e.g., "cot_vs_standard")
        variants: Dict of variant_name → config overrides
        traffic_split: Dict of variant_name → traffic fraction (must sum to 1.0)
        enabled: Whether this experiment is active
        description: Human-readable description
    """

    name: str
    variants: Dict[str, Dict[str, Any]]
    traffic_split: Dict[str, float]
    enabled: bool = True
    description: str = ""

    def __post_init__(self):
        if set(self.variants.keys()) != set(self.traffic_split.keys()):
            raise ValueError(
                f"Experiment '{self.name}': variant keys must match traffic_split keys. "
                f"variants={set(self.variants.keys())}, split={set(self.traffic_split.keys())}"
            )
        total = sum(self.traffic_split.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Experiment '{self.name}': traffic_split must sum to 1.0, got {total}"
            )


@dataclass
class ExperimentAssignment:
    """Records a variant assignment for a request."""

    experiment_name: str
    variant: str
    request_id: str
    config: Dict[str, Any]
    assigned_at: float = field(default_factory=time.time)


@dataclass
class ExperimentOutcome:
    """Records outcome metrics for an assigned variant."""

    experiment_name: str
    variant: str
    request_id: str
    metrics: Dict[str, Any]
    recorded_at: float = field(default_factory=time.time)


class ABTestingManager:
    """Manages A/B testing experiments.

    Thread-safe via immutable experiment configs and append-only result logs.
    Variant assignment is deterministic based on request_id hash
    (same request always gets same variant).
    """

    def __init__(self):
        self._experiments: Dict[str, Experiment] = {}
        self._assignments: List[ExperimentAssignment] = []
        self._outcomes: List[ExperimentOutcome] = []

    def register_experiment(self, experiment: Experiment) -> None:
        """Register a new experiment."""
        self._experiments[experiment.name] = experiment
        logger.info(
            f"A/B experiment registered: {experiment.name} "
            f"variants={list(experiment.variants.keys())}",
            component="ab_testing",
        )

    def deactivate_experiment(self, name: str) -> None:
        """Deactivate an experiment (stops new assignments)."""
        if name in self._experiments:
            self._experiments[name].enabled = False
            logger.info(f"A/B experiment deactivated: {name}", component="ab_testing")

    def get_experiment(self, name: str) -> Optional[Experiment]:
        """Get experiment by name."""
        return self._experiments.get(name)

    def list_experiments(self) -> List[Dict[str, Any]]:
        """List all registered experiments with status."""
        return [
            {
                "name": exp.name,
                "enabled": exp.enabled,
                "variants": list(exp.variants.keys()),
                "traffic_split": exp.traffic_split,
                "description": exp.description,
                "assignments": sum(
                    1 for a in self._assignments if a.experiment_name == exp.name
                ),
                "outcomes": sum(
                    1 for o in self._outcomes if o.experiment_name == exp.name
                ),
            }
            for exp in self._experiments.values()
        ]

    def assign(
        self,
        experiment_name: str,
        request_id: str,
    ) -> Optional[ExperimentAssignment]:
        """Assign a variant to a request.

        Assignment is deterministic: same (experiment_name, request_id) always
        yields the same variant. This ensures consistency across retries.

        Returns:
            ExperimentAssignment with variant config, or None if experiment
            doesn't exist or is disabled.
        """
        experiment = self._experiments.get(experiment_name)
        if not experiment or not experiment.enabled:
            return None

        # Deterministic hash-based assignment
        hash_input = f"{experiment_name}:{request_id}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        bucket = (hash_value % 10000) / 10000.0  # 0.0 to 0.9999

        cumulative = 0.0
        assigned_variant = None
        for variant_name, fraction in experiment.traffic_split.items():
            cumulative += fraction
            if bucket < cumulative:
                assigned_variant = variant_name
                break

        if assigned_variant is None:
            assigned_variant = list(experiment.traffic_split.keys())[-1]

        config = experiment.variants[assigned_variant]
        assignment = ExperimentAssignment(
            experiment_name=experiment_name,
            variant=assigned_variant,
            request_id=request_id,
            config=config,
        )
        self._assignments.append(assignment)

        # Record to prometheus if available
        try:
            from app.shared.prometheus_metrics import metrics as prom_metrics

            prom_metrics.record_error(
                error_type=f"ab_assign:{experiment_name}:{assigned_variant}",
                component="ab_testing",
            )
        except Exception:
            pass

        logger.debug(
            f"A/B assigned: {experiment_name} → {assigned_variant} "
            f"(request={request_id})",
            component="ab_testing",
        )

        return assignment

    def record_outcome(
        self,
        experiment_name: str,
        request_id: str,
        outcome_metrics: Dict[str, Any],
    ) -> None:
        """Record outcome metrics for an assigned request.

        Args:
            experiment_name: Experiment name
            request_id: Request ID (must match a previous assignment)
            outcome_metrics: Dict of metric_name → value (e.g. latency, score, quality)
        """
        # Find matching assignment
        matching = [
            a
            for a in self._assignments
            if a.experiment_name == experiment_name and a.request_id == request_id
        ]
        if not matching:
            logger.warning(
                f"A/B outcome for unassigned request: {experiment_name}/{request_id}",
                component="ab_testing",
            )
            return

        variant = matching[-1].variant

        outcome = ExperimentOutcome(
            experiment_name=experiment_name,
            variant=variant,
            request_id=request_id,
            metrics=outcome_metrics,
        )
        self._outcomes.append(outcome)

        logger.debug(
            f"A/B outcome: {experiment_name}/{variant} metrics={outcome_metrics}",
            component="ab_testing",
        )

    def get_results(self, experiment_name: str) -> Dict[str, Any]:
        """Get aggregated results for an experiment.

        Returns per-variant statistics for numeric metrics.
        """
        experiment = self._experiments.get(experiment_name)
        if not experiment:
            return {"error": f"Experiment '{experiment_name}' not found"}

        outcomes_by_variant: Dict[str, List[Dict[str, Any]]] = {
            v: [] for v in experiment.variants
        }
        for o in self._outcomes:
            if o.experiment_name == experiment_name:
                outcomes_by_variant.setdefault(o.variant, []).append(o.metrics)

        results: Dict[str, Any] = {
            "experiment": experiment_name,
            "enabled": experiment.enabled,
            "variants": {},
        }

        for variant_name, outcomes in outcomes_by_variant.items():
            n = len(outcomes)
            if n == 0:
                results["variants"][variant_name] = {"count": 0}
                continue

            # Aggregate numeric metrics
            aggregated: Dict[str, Any] = {"count": n}
            all_keys = set()
            for o in outcomes:
                all_keys.update(o.keys())

            for key in all_keys:
                values = [o[key] for o in outcomes if key in o and isinstance(o[key], (int, float))]
                if values:
                    aggregated[key] = {
                        "mean": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "count": len(values),
                    }

            results["variants"][variant_name] = aggregated

        return results


# Global singleton
ab_manager = ABTestingManager()
