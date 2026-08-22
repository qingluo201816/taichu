"""单案例 Runtime 执行、真实调用 outcome 与预算观察关联。"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import Field

from taichu.application.contracts.runtime_evidence import (
    EvidenceAvailability,
    RuntimeEvidenceReader,
)
from taichu.application.evaluations.general_agent_benchmark.correlation import (
    CorrelationSubjectKind,
    CorrelationSubjectRef,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    BudgetObservation,
    ResourceBudget,
    StableId,
    ValueAvailability,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseExecutionState,
)


class CaseRuntimePort(Protocol):
    async def run(self, **kwargs: object) -> Any: ...


class CorrelationScopePort(Protocol):
    async def finalize_all(self) -> object: ...


class EvaluationCaseRequest(BenchmarkModel):
    suite_id: StableId
    case_id: StableId
    case_execution_id: str = Field(pattern=r"^benchmark_case_[a-f0-9]{32}$")
    user_request: str = Field(min_length=1, max_length=100_000)
    allowed_stop_reasons: frozenset[str] = Field(min_length=1)
    budgets: ResourceBudget


class ObservedCapabilityInvocation(BenchmarkModel):
    call_id: str
    parent_call_id: str | None
    capability_type: Literal["llm", "tool", "subagent"]
    name: str
    outcome: str


class EvaluationCaseExecution(BenchmarkModel):
    suite_id: StableId
    case_id: StableId
    case_execution_id: str
    run_id: str | None
    execution_state: CaseExecutionState
    stop_reason: str
    stop_reason_allowed: bool
    invocations: tuple[ObservedCapabilityInvocation, ...]
    budgets: dict[str, BudgetObservation]
    correlation_subjects: tuple[CorrelationSubjectRef, ...]
    evidence_availability: EvidenceAvailability
    correlation_problems: tuple[str, ...] = ()
    error_type: str | None = None


class EvaluationCaseExecutor:
    """运行真实 Runtime，并只按 invocation/outcome 计入能力调用。"""

    def __init__(
        self,
        *,
        runtime: CaseRuntimePort,
        evidence: RuntimeEvidenceReader,
        correlation_scope: CorrelationScopePort | None = None,
    ) -> None:
        self._runtime = runtime
        self._evidence = evidence
        self._correlation_scope = correlation_scope

    async def execute(
        self,
        request: EvaluationCaseRequest,
    ) -> EvaluationCaseExecution:
        result = await self._execute_runtime(request)
        if self._correlation_scope is None:
            return result
        try:
            await self._correlation_scope.finalize_all()
        except Exception:
            return result.model_copy(
                update={
                    "evidence_availability": EvidenceAvailability.CORRUPT,
                    "correlation_problems": (
                        "correlation_repository_unavailable",
                    ),
                }
            )
        return result

    async def _execute_runtime(
        self,
        request: EvaluationCaseRequest,
    ) -> EvaluationCaseExecution:
        case_subject = CorrelationSubjectRef(
            kind=CorrelationSubjectKind.CASE_EXECUTION,
            stable_id=request.case_execution_id,
        )
        try:
            run = await self._runtime.run(user_goal=request.user_request)
        except Exception as error:
            return EvaluationCaseExecution(
                suite_id=request.suite_id,
                case_id=request.case_id,
                case_execution_id=request.case_execution_id,
                run_id=None,
                execution_state=CaseExecutionState.ERROR,
                stop_reason="exception",
                stop_reason_allowed="exception" in request.allowed_stop_reasons,
                invocations=(),
                budgets=_unavailable_budgets(request.budgets),
                correlation_subjects=(case_subject,),
                evidence_availability=EvidenceAvailability.MISSING,
                error_type=type(error).__name__,
            )

        run_id = str(run.run_id)
        invocation_item = await self._evidence.read_invocations(run_id)
        records = invocation_item.value or ()
        invocations = tuple(
            ObservedCapabilityInvocation(
                call_id=record.call_id,
                parent_call_id=record.parent_call_id,
                capability_type=record.capability_type,
                name=record.capability_name,
                outcome=record.status,
            )
            for record in records
        )
        model_call_ids = tuple(
            record.call_id
            for record in records
            if record.capability_type == "llm"
        )
        usage_item = await self._evidence.read_llm_usage(model_call_ids)
        status = str(run.status)
        return EvaluationCaseExecution(
            suite_id=request.suite_id,
            case_id=request.case_id,
            case_execution_id=request.case_execution_id,
            run_id=run_id,
            execution_state=_execution_state(status),
            stop_reason=status,
            stop_reason_allowed=status in request.allowed_stop_reasons,
            invocations=invocations,
            budgets=_budget_observations(
                request.budgets,
                run=run,
                invocation_availability=invocation_item.availability,
                invocation_records=records,
                usage_availability=usage_item.availability,
                usage_records=usage_item.value or (),
            ),
            correlation_subjects=(case_subject,)
            + tuple(
                CorrelationSubjectRef(
                    kind=CorrelationSubjectKind.CAPABILITY_INVOCATION,
                    stable_id=record.call_id,
                )
                for record in records
                if record.capability_type in {"tool", "subagent"}
            ),
            evidence_availability=_combined_availability(
                invocation_item.availability,
                usage_item.availability,
            ),
            error_type=None,
        )


def _budget_observations(
    limits: ResourceBudget,
    *,
    run: Any,
    invocation_availability: EvidenceAvailability,
    invocation_records: tuple[Any, ...],
    usage_availability: EvidenceAvailability,
    usage_records: tuple[Any, ...],
) -> dict[str, BudgetObservation]:
    node_runs = tuple(getattr(run, "node_runs", ()))
    observations = {
        "max_node_executions": _available_budget(
            limits.max_node_executions,
            len(node_runs),
        ),
        "max_replans": _available_budget(
            limits.max_replans,
            int(getattr(run, "replan_count", 0)),
        ),
        "max_runtime_ms": _available_budget(
            limits.max_runtime_ms,
            sum(int(getattr(node, "duration_ms", 0)) for node in node_runs),
        ),
    }
    if invocation_availability is EvidenceAvailability.AVAILABLE:
        observations["max_capability_calls"] = _available_budget(
            limits.max_capability_calls,
            sum(
                record.capability_type in {"tool", "subagent"}
                for record in invocation_records
            ),
        )
        observations["max_model_calls"] = _available_budget(
            limits.max_model_calls,
            sum(record.capability_type == "llm" for record in invocation_records),
        )
    else:
        observations["max_capability_calls"] = _missing_budget(
            limits.max_capability_calls
        )
        observations["max_model_calls"] = _missing_budget(limits.max_model_calls)
    if usage_availability is EvidenceAvailability.AVAILABLE and all(
        record.total_tokens is not None for record in usage_records
    ):
        observations["max_total_tokens"] = _available_budget(
            limits.max_total_tokens,
            sum(int(record.total_tokens) for record in usage_records),
        )
    else:
        observations["max_total_tokens"] = _missing_budget(
            limits.max_total_tokens
        )
    return observations


def _available_budget(limit: int, actual: int) -> BudgetObservation:
    return BudgetObservation(
        limit=limit,
        actual=actual,
        availability=ValueAvailability.AVAILABLE,
        within_limit=actual <= limit,
        evidence_refs=(),
    )


def _missing_budget(limit: int) -> BudgetObservation:
    return BudgetObservation(
        limit=limit,
        actual=None,
        availability=ValueAvailability.MISSING,
        within_limit=None,
        evidence_refs=(),
    )


def _unavailable_budgets(limits: ResourceBudget) -> dict[str, BudgetObservation]:
    return {
        field: _missing_budget(int(value))
        for field, value in limits.model_dump(mode="python").items()
    }


def _execution_state(status: str) -> CaseExecutionState:
    if status == "completed":
        return CaseExecutionState.COMPLETED
    if status == "cancelled":
        return CaseExecutionState.CANCELLED
    if status == "waiting_human":
        return CaseExecutionState.BLOCKED
    if status in {"failed", "timeout"}:
        return CaseExecutionState.ERROR
    return CaseExecutionState.UNFINISHED


def _combined_availability(
    left: EvidenceAvailability,
    right: EvidenceAvailability,
) -> EvidenceAvailability:
    priority = (
        EvidenceAvailability.CONFLICTING,
        EvidenceAvailability.CORRUPT,
        EvidenceAvailability.MISSING,
        EvidenceAvailability.NOT_APPLICABLE,
        EvidenceAvailability.AVAILABLE,
    )
    return next(item for item in priority if item in {left, right})
