"""需求 2.5、4.7、6.9、12.9：覆盖、通过、预算与稳定性指标。"""

from __future__ import annotations

from taichu.application.evaluations.general_agent_benchmark.capability_catalog import (
    ActualCapabilityInvocation,
)
from taichu.application.evaluations.general_agent_benchmark.metrics import (
    StabilityThresholdProfile,
    capability_coverage,
    case_pass_rate,
    summarize_budgets,
    summarize_stability,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BudgetObservation,
    ValueAvailability,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseConclusion,
)


def test_capability_coverage_only_counts_completed_actual_invocations() -> None:
    actual = (
        ActualCapabilityInvocation(
            case_id="case_a",
            call_id="call_a",
            kind="tool",
            capability_name="read_manuscript",
            outcome="completed",
        ),
        ActualCapabilityInvocation(
            case_id="case_b",
            call_id="call_b",
            kind="tool",
            capability_name="registered_but_failed",
            outcome="failed",
        ),
    )
    result = capability_coverage(
        actual,
        expected_capabilities=frozenset(
            {
                ("tool", "read_manuscript"),
                ("tool", "registered_but_failed"),
                ("subagent", "manifest_only"),
            }
        ),
    )

    assert result.covered_count == 1
    assert result.expected_count == 3
    assert result.ratio == 1 / 3
    assert result.missing == (
        "subagent:manifest_only",
        "tool:registered_but_failed",
    )


def test_case_pass_rate_keeps_invalid_cancelled_and_unfinished_out_of_passes() -> None:
    result = case_pass_rate(
        (
            CaseConclusion.PASSED,
            CaseConclusion.FAILED,
            CaseConclusion.INVALID,
            CaseConclusion.CANCELLED,
            CaseConclusion.UNFINISHED,
        )
    )
    assert result.passed_count == 1
    assert result.evaluated_count == 2
    assert result.total_count == 5
    assert result.ratio == 0.5


def test_budget_summary_separates_exceeded_from_unavailable() -> None:
    result = summarize_budgets(
        {
            "max_runtime_ms": BudgetObservation(
                limit=100,
                actual=120,
                availability=ValueAvailability.AVAILABLE,
                within_limit=False,
                evidence_refs=("evidence_runtime",),
            ),
            "max_total_tokens": BudgetObservation(
                limit=1000,
                actual=None,
                availability=ValueAvailability.MISSING,
                within_limit=None,
                evidence_refs=(),
            ),
        }
    )
    assert result.exceeded == ("max_runtime_ms",)
    assert result.unavailable == ("max_total_tokens",)
    assert result.within_limits is False


def test_stability_uses_sample_variance_and_requires_explicit_profile() -> None:
    profile = StabilityThresholdProfile(
        profile_id="strict_repeatability",
        max_range=2,
        max_variance=1,
    )
    stable = summarize_stability((10.0, 11.0, 12.0), profile=profile)
    assert stable.sample_count == 3
    assert stable.mean == 11
    assert stable.variance == 1
    assert stable.minimum == 10
    assert stable.maximum == 12
    assert stable.range == 2
    assert stable.repeatability == "stable"

    insufficient = summarize_stability((10.0,), profile=profile)
    assert insufficient.variance is None
    assert insufficient.repeatability == "insufficient_samples"

    invalid = summarize_stability((10.0, 10.0), profile=None)
    assert invalid.repeatability == "invalid"
