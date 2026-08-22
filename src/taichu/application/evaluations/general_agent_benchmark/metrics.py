"""只从案例真值、实际调用与正式预算观察计算指标。"""

from __future__ import annotations

from statistics import mean, variance
from typing import Literal

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.capability_catalog import (
    ActualCapabilityInvocation,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    BudgetObservation,
    StableId,
    ValueAvailability,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseConclusion,
)


class CapabilityCoverageMetric(BenchmarkModel):
    expected_count: int = Field(ge=0)
    covered_count: int = Field(ge=0)
    ratio: float | None = Field(default=None, ge=0, le=1)
    covered: tuple[str, ...]
    missing: tuple[str, ...]


def capability_coverage(
    actual_invocations: tuple[ActualCapabilityInvocation, ...],
    *,
    expected_capabilities: frozenset[tuple[str, str]],
) -> CapabilityCoverageMetric:
    observed = {
        (item.kind.value, item.capability_name)
        for item in actual_invocations
        if item.outcome == "completed"
    }
    covered = expected_capabilities & observed
    missing = expected_capabilities - covered
    return CapabilityCoverageMetric(
        expected_count=len(expected_capabilities),
        covered_count=len(covered),
        ratio=(
            len(covered) / len(expected_capabilities)
            if expected_capabilities
            else None
        ),
        covered=tuple(sorted(f"{kind}:{name}" for kind, name in covered)),
        missing=tuple(sorted(f"{kind}:{name}" for kind, name in missing)),
    )


class CasePassRateMetric(BenchmarkModel):
    passed_count: int = Field(ge=0)
    evaluated_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    ratio: float | None = Field(default=None, ge=0, le=1)


def case_pass_rate(
    conclusions: tuple[CaseConclusion, ...],
) -> CasePassRateMetric:
    passed = sum(item is CaseConclusion.PASSED for item in conclusions)
    evaluated = sum(
        item in {CaseConclusion.PASSED, CaseConclusion.FAILED}
        for item in conclusions
    )
    return CasePassRateMetric(
        passed_count=passed,
        evaluated_count=evaluated,
        total_count=len(conclusions),
        ratio=passed / evaluated if evaluated else None,
    )


class BudgetMetricSummary(BenchmarkModel):
    exceeded: tuple[StableId, ...]
    unavailable: tuple[StableId, ...]
    within_limits: bool | None
    evidence_refs: tuple[str, ...]


def summarize_budgets(
    observations: dict[StableId, BudgetObservation],
) -> BudgetMetricSummary:
    exceeded = tuple(
        sorted(
            name
            for name, item in observations.items()
            if item.availability is ValueAvailability.AVAILABLE
            and item.within_limit is False
        )
    )
    unavailable = tuple(
        sorted(
            name
            for name, item in observations.items()
            if item.availability is not ValueAvailability.AVAILABLE
        )
    )
    return BudgetMetricSummary(
        exceeded=exceeded,
        unavailable=unavailable,
        within_limits=False if exceeded else None if unavailable else True,
        evidence_refs=tuple(
            dict.fromkeys(
                evidence_ref
                for item in observations.values()
                for evidence_ref in item.evidence_refs
            )
        ),
    )


class StabilityThresholdProfile(BenchmarkModel):
    profile_id: StableId
    max_range: float = Field(ge=0)
    max_variance: float = Field(ge=0)


class StabilitySummary(BenchmarkModel):
    sample_count: int = Field(ge=0)
    mean: float | None
    variance: float | None = Field(default=None, ge=0)
    minimum: float | None
    maximum: float | None
    range: float | None = Field(default=None, ge=0)
    repeatability: Literal[
        "stable",
        "unstable",
        "insufficient_samples",
        "invalid",
    ]
    threshold_profile_id: StableId | None


def summarize_stability(
    samples: tuple[float, ...],
    *,
    profile: StabilityThresholdProfile | None,
) -> StabilitySummary:
    if not samples:
        return StabilitySummary(
            sample_count=0,
            mean=None,
            variance=None,
            minimum=None,
            maximum=None,
            range=None,
            repeatability="insufficient_samples" if profile is not None else "invalid",
            threshold_profile_id=profile.profile_id if profile is not None else None,
        )
    sample_mean = mean(samples)
    minimum = min(samples)
    maximum = max(samples)
    sample_range = maximum - minimum
    sample_variance = variance(samples) if len(samples) >= 2 else None
    if profile is None:
        repeatability = "invalid"
    elif sample_variance is None:
        repeatability = "insufficient_samples"
    elif (
        sample_range <= profile.max_range
        and sample_variance <= profile.max_variance
    ):
        repeatability = "stable"
    else:
        repeatability = "unstable"
    return StabilitySummary(
        sample_count=len(samples),
        mean=sample_mean,
        variance=sample_variance,
        minimum=minimum,
        maximum=maximum,
        range=sample_range,
        repeatability=repeatability,
        threshold_profile_id=profile.profile_id if profile is not None else None,
    )
