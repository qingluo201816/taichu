"""从执行状态与硬门禁事实派生封闭失败分类。"""

from __future__ import annotations

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    FailureCategory,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseExecutionState,
)


DEFAULT_FAILURE_PRIORITY = tuple(FailureCategory)


class FailureClassificationInput(BenchmarkModel):
    execution_state: CaseExecutionState = CaseExecutionState.COMPLETED
    benchmark_valid: bool | None = True
    fixture_isolated: bool | None = True
    security_preserved: bool | None = True
    evidence_complete: bool | None = True
    artifacts_satisfied: bool | None = True
    budgets_within_limits: bool | None = True
    verifiers_passed: bool | None = True
    stop_reason_allowed: bool | None = True
    has_unmapped_failure: bool = False


class FailureClassification(BenchmarkModel):
    execution_state: CaseExecutionState
    primary: FailureCategory | None
    categories: tuple[FailureCategory, ...]


def classify_failures(
    facts: FailureClassificationInput,
    *,
    priority: tuple[FailureCategory, ...] = DEFAULT_FAILURE_PRIORITY,
) -> FailureClassification:
    _validate_priority(priority)
    detected: set[FailureCategory] = set()
    if facts.benchmark_valid is not True:
        detected.add(FailureCategory.BENCHMARK_INVALID)
    if facts.fixture_isolated is False:
        detected.add(FailureCategory.FIXTURE_ISOLATION_FAILED)
    elif facts.fixture_isolated is None:
        detected.add(FailureCategory.UNDETERMINED)
    if facts.security_preserved is False:
        detected.add(FailureCategory.SECURITY_VIOLATION)
    elif facts.security_preserved is None:
        detected.add(FailureCategory.UNDETERMINED)
    if facts.evidence_complete is not True:
        detected.add(FailureCategory.EVIDENCE_INCOMPLETE)
    if facts.artifacts_satisfied is False:
        detected.add(FailureCategory.MISSING_ARTIFACT)
    elif facts.artifacts_satisfied is None:
        detected.add(FailureCategory.UNDETERMINED)
    if facts.budgets_within_limits is False:
        detected.add(FailureCategory.BUDGET_EXCEEDED)
    elif facts.budgets_within_limits is None:
        detected.add(FailureCategory.UNDETERMINED)
    if facts.verifiers_passed is False:
        detected.add(FailureCategory.VERIFIER_FAILED)
    elif facts.verifiers_passed is None:
        detected.add(FailureCategory.UNDETERMINED)
    if facts.stop_reason_allowed is False:
        detected.add(FailureCategory.FAILURE_STOP_REASON)
    elif facts.stop_reason_allowed is None:
        detected.add(FailureCategory.UNDETERMINED)

    if facts.execution_state is CaseExecutionState.ERROR:
        detected.add(FailureCategory.EXECUTION_ERROR)
    elif facts.execution_state is CaseExecutionState.CANCELLED:
        detected.add(FailureCategory.CANCELLED)
    elif facts.execution_state in {
        CaseExecutionState.PENDING,
        CaseExecutionState.RUNNING,
        CaseExecutionState.BLOCKED,
        CaseExecutionState.UNFINISHED,
    }:
        detected.add(FailureCategory.UNFINISHED)
    if facts.has_unmapped_failure:
        detected.add(FailureCategory.UNDETERMINED)

    categories = tuple(item for item in priority if item in detected)
    return FailureClassification(
        execution_state=facts.execution_state,
        primary=categories[0] if categories else None,
        categories=categories,
    )


def _validate_priority(priority: tuple[FailureCategory, ...]) -> None:
    if (
        len(priority) != len(FailureCategory)
        or len(set(priority)) != len(priority)
        or set(priority) != set(FailureCategory)
    ):
        raise ValueError("失败优先级必须完整覆盖封闭分类且不得重复。")
