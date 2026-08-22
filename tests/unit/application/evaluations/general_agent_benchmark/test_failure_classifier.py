"""需求 6.1—6.17：失败分类穷尽、互斥主类与固定优先级。"""

from __future__ import annotations

import pytest

from taichu.application.evaluations.general_agent_benchmark.failure_classifier import (
    DEFAULT_FAILURE_PRIORITY,
    FailureClassificationInput,
    classify_failures,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    FailureCategory,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseExecutionState,
)


@pytest.mark.parametrize(
    ("category", "updates"),
    (
        (FailureCategory.BENCHMARK_INVALID, {"benchmark_valid": False}),
        (FailureCategory.FIXTURE_ISOLATION_FAILED, {"fixture_isolated": False}),
        (FailureCategory.SECURITY_VIOLATION, {"security_preserved": False}),
        (FailureCategory.EVIDENCE_INCOMPLETE, {"evidence_complete": False}),
        (FailureCategory.MISSING_ARTIFACT, {"artifacts_satisfied": False}),
        (FailureCategory.BUDGET_EXCEEDED, {"budgets_within_limits": False}),
        (FailureCategory.VERIFIER_FAILED, {"verifiers_passed": False}),
        (FailureCategory.FAILURE_STOP_REASON, {"stop_reason_allowed": False}),
        (
            FailureCategory.EXECUTION_ERROR,
            {"execution_state": CaseExecutionState.ERROR},
        ),
        (
            FailureCategory.CANCELLED,
            {"execution_state": CaseExecutionState.CANCELLED},
        ),
        (
            FailureCategory.UNFINISHED,
            {"execution_state": CaseExecutionState.UNFINISHED},
        ),
        (FailureCategory.UNDETERMINED, {"has_unmapped_failure": True}),
    ),
)
def test_each_failure_fact_maps_to_exactly_one_primary_category(
    category: FailureCategory,
    updates: dict[str, object],
) -> None:
    facts = FailureClassificationInput().model_copy(update=updates)
    result = classify_failures(facts)

    assert result.execution_state is facts.execution_state
    assert result.primary is category
    assert result.categories == (category,)


def test_multiple_failures_keep_all_categories_and_choose_declared_priority() -> None:
    result = classify_failures(
        FailureClassificationInput(
            security_preserved=False,
            evidence_complete=False,
            budgets_within_limits=False,
            verifiers_passed=False,
        )
    )

    assert result.primary is FailureCategory.SECURITY_VIOLATION
    assert result.categories == (
        FailureCategory.SECURITY_VIOLATION,
        FailureCategory.EVIDENCE_INCOMPLETE,
        FailureCategory.BUDGET_EXCEEDED,
        FailureCategory.VERIFIER_FAILED,
    )


def test_success_has_no_failure_and_priority_must_be_exhaustive() -> None:
    result = classify_failures(FailureClassificationInput())
    assert result.primary is None
    assert result.categories == ()
    assert set(DEFAULT_FAILURE_PRIORITY) == set(FailureCategory)

    with pytest.raises(ValueError, match="完整覆盖"):
        classify_failures(
            FailureClassificationInput(verifiers_passed=False),
            priority=(FailureCategory.VERIFIER_FAILED,),
        )
