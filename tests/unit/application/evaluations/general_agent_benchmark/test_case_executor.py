"""需求 4.3、4.7、5.12、7.9、10.17：案例执行与真实调用结果关联。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from taichu.application.contracts.runtime_evidence import (
    EvidenceAvailability,
    EvidenceItem,
    InvocationSourceRecord,
    UsageSourceRecord,
)
from taichu.application.evaluations.general_agent_benchmark.execution import (
    EvaluationCaseExecutor,
    EvaluationCaseRequest,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    ResourceBudget,
)


def _budget() -> ResourceBudget:
    return ResourceBudget(
        max_node_executions=4,
        max_replans=1,
        max_capability_calls=3,
        max_model_calls=2,
        max_total_tokens=1_000,
        max_runtime_ms=5_000,
    )


class _Runtime:
    async def run(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            run_id="general_run_20260727_010203_abcdef",
            status="completed",
            node_runs=(SimpleNamespace(node_id="read", duration_ms=10),),
            replan_count=0,
            errors=(),
        )


class _Evidence:
    async def read_invocations(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]:
        assert run_id == "general_run_20260727_010203_abcdef"
        return EvidenceItem(
            value=(
                InvocationSourceRecord(
                    call_id="call_model",
                    parent_call_id=None,
                    run_id=run_id,
                    capability_type="llm",
                    capability_name="planner",
                    status="completed",
                    started_at="2026-07-27T01:02:03Z",
                ),
                InvocationSourceRecord(
                    call_id="call_tool",
                    parent_call_id="call_model",
                    run_id=run_id,
                    capability_type="tool",
                    capability_name="read_manuscript",
                    status="completed",
                    started_at="2026-07-27T01:02:04Z",
                ),
                InvocationSourceRecord(
                    call_id="call_subagent",
                    parent_call_id="call_model",
                    run_id=run_id,
                    capability_type="subagent",
                    capability_name="canon_evidence",
                    status="completed",
                    started_at="2026-07-27T01:02:05Z",
                ),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_llm_usage(
        self,
        call_ids: tuple[str, ...],
    ) -> EvidenceItem[tuple[UsageSourceRecord, ...]]:
        assert call_ids == ("call_model",)
        return EvidenceItem(
            value=(
                UsageSourceRecord(
                    call_id="call_model",
                    run_id="general_run_20260727_010203_abcdef",
                    provider="synthetic",
                    model_id="synthetic",
                    status="completed",
                    total_tokens=0,
                ),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )


def test_executor_pairs_actual_invocations_outcomes_budgets_and_subjects() -> None:
    result = asyncio.run(
        EvaluationCaseExecutor(runtime=_Runtime(), evidence=_Evidence()).execute(
            EvaluationCaseRequest(
                suite_id="general_writing_agent_core",
                case_id="single_manuscript_search",
                case_execution_id=f"benchmark_case_{'a' * 32}",
                user_request="检索第一章中的灵火线索。",
                allowed_stop_reasons=frozenset({"completed"}),
                budgets=_budget(),
            )
        )
    )

    assert result.run_id == "general_run_20260727_010203_abcdef"
    assert result.stop_reason == "completed"
    assert [(item.capability_type, item.name, item.outcome) for item in result.invocations] == [
        ("llm", "planner", "completed"),
        ("tool", "read_manuscript", "completed"),
        ("subagent", "canon_evidence", "completed"),
    ]
    assert result.budgets["max_capability_calls"].actual == 2
    assert result.budgets["max_model_calls"].actual == 1
    assert result.budgets["max_total_tokens"].actual == 0
    assert {subject.kind for subject in result.correlation_subjects} == {
        "case_execution",
        "capability_invocation",
    }


class _FailedRuntime:
    async def run(self, **_: object) -> SimpleNamespace:
        raise TimeoutError("底层 Runtime 超时")


class _BrokenCorrelationScope:
    async def finalize_all(self) -> object:
        raise OSError("correlation repository unavailable")


def test_executor_preserves_runtime_exception_as_outcome_without_fake_invocation() -> None:
    result = asyncio.run(
        EvaluationCaseExecutor(
            runtime=_FailedRuntime(),
            evidence=_Evidence(),
        ).execute(
            EvaluationCaseRequest(
                suite_id="general_writing_agent_core",
                case_id="recovery_verification_interruption",
                case_execution_id=f"benchmark_case_{'b' * 32}",
                user_request="从检查点恢复。",
                allowed_stop_reasons=frozenset({"timeout"}),
                budgets=_budget(),
            )
        )
    )

    assert result.stop_reason == "exception"
    assert result.error_type == "TimeoutError"
    assert result.invocations == ()
    assert result.correlation_subjects == (
        result.correlation_subjects[0],
    )


def test_correlation_repository_failure_does_not_change_runtime_outcome() -> None:
    completed = asyncio.run(
        EvaluationCaseExecutor(
            runtime=_Runtime(),
            evidence=_Evidence(),
            correlation_scope=_BrokenCorrelationScope(),
        ).execute(
            EvaluationCaseRequest(
                suite_id="general_writing_agent_core",
                case_id="single_manuscript_search",
                case_execution_id=f"benchmark_case_{'c' * 32}",
                user_request="检索正文。",
                allowed_stop_reasons=frozenset({"completed"}),
                budgets=_budget(),
            )
        )
    )
    raised = asyncio.run(
        EvaluationCaseExecutor(
            runtime=_FailedRuntime(),
            evidence=_Evidence(),
            correlation_scope=_BrokenCorrelationScope(),
        ).execute(
            EvaluationCaseRequest(
                suite_id="general_writing_agent_core",
                case_id="recovery_verification_interruption",
                case_execution_id=f"benchmark_case_{'d' * 32}",
                user_request="恢复。",
                allowed_stop_reasons=frozenset({"exception"}),
                budgets=_budget(),
            )
        )
    )

    assert completed.run_id == "general_run_20260727_010203_abcdef"
    assert completed.stop_reason == "completed"
    assert completed.evidence_availability is EvidenceAvailability.CORRUPT
    assert completed.correlation_problems == ("correlation_repository_unavailable",)
    assert raised.error_type == "TimeoutError"
    assert raised.stop_reason == "exception"
    assert raised.correlation_problems == ("correlation_repository_unavailable",)


class _StatusRuntime:
    def __init__(self, status: str) -> None:
        self._status = status

    async def run(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            run_id="general_run_20260727_010203_bcdefa",
            status=self._status,
            node_runs=(),
            replan_count=0,
            errors=(),
        )


class _EmptyEvidence:
    async def read_invocations(
        self,
        _: str,
    ) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]:
        return EvidenceItem(
            value=(),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_llm_usage(
        self,
        _: tuple[str, ...],
    ) -> EvidenceItem[tuple[UsageSourceRecord, ...]]:
        return EvidenceItem(
            value=(),
            availability=EvidenceAvailability.AVAILABLE,
        )


@pytest.mark.parametrize(
    ("runtime_status", "expected_state"),
    [
        ("completed", "completed"),
        ("waiting_human", "blocked"),
        ("cancelled", "cancelled"),
        ("failed", "error"),
        ("timeout", "error"),
        ("executing", "unfinished"),
    ],
)
def test_executor_keeps_runtime_stop_state_matrix(
    runtime_status: str,
    expected_state: str,
) -> None:
    result = asyncio.run(
        EvaluationCaseExecutor(
            runtime=_StatusRuntime(runtime_status),
            evidence=_EmptyEvidence(),
        ).execute(
            EvaluationCaseRequest(
                suite_id="general_writing_agent_core",
                case_id="recovery_verification_interruption",
                case_execution_id=f"benchmark_case_{'e' * 32}",
                user_request="执行代表性状态路径。",
                allowed_stop_reasons=frozenset(
                    {
                        "completed",
                        "waiting_human",
                        "cancelled",
                        "failed",
                        "timeout",
                        "executing",
                    }
                ),
                budgets=_budget(),
            )
        )
    )

    assert result.execution_state == expected_state
    assert result.stop_reason == runtime_status
    assert result.stop_reason_allowed is True
    assert result.invocations == ()
