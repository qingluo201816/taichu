"""套件运行、机制判定、证据与提供商状态合同。"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CaseConclusion,
    FailureCategory,
    FixtureSnapshotId,
    GateConditionResult,
    GateResult,
    GateStatus,
    Sha256,
    StableId,
    TrackKind,
)

T = TypeVar("T")


class EvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    CORRUPT = "corrupt"
    NOT_APPLICABLE = "not_applicable"
    CONFLICTING = "conflicting"


class EvidenceItem(BenchmarkModel, Generic[T]):
    availability: EvidenceAvailability
    value: T | None
    problems: tuple[str, ...]
    locators: tuple[str, ...]

    @model_validator(mode="after")
    def _availability_matches_value(self) -> EvidenceItem[T]:
        if self.availability is EvidenceAvailability.AVAILABLE:
            if self.value is None:
                raise ValueError("available 证据必须包含 value。")
            if self.problems:
                raise ValueError("available 证据不得携带未解决问题。")
        elif self.value is not None:
            raise ValueError("不可用证据不得携带伪造 value。")
        return self


class EvidenceBundleIdentity(BenchmarkModel):
    bundle_id: str = Field(pattern=r"^evidence_[a-f0-9]{64}$")
    bundle_hash: Sha256
    suite_id: StableId
    case_id: StableId
    run_id: str = Field(min_length=1, max_length=200)
    case_execution_id: str = Field(pattern=r"^benchmark_case_[a-f0-9]{32}$")
    track: TrackKind
    fixture_snapshot_id: FixtureSnapshotId


class FrozenCapabilityInvocationEvidence(BenchmarkModel):
    kind: Literal["tool", "subagent"]
    capability_name: StableId
    call_id: str = Field(min_length=1)
    handler_identity: str = Field(min_length=1)
    outcome: str = Field(min_length=1)


class FrozenNormalizationActionEvidence(BenchmarkModel):
    kind: Literal["human", "model", "tool", "subagent"]
    name: StableId
    outcome: str = Field(min_length=1)
    step_id: StableId
    step_index: int = Field(ge=0)
    evidence: dict[str, object]


class FrozenCaseEvidenceDetails(BenchmarkModel):
    gates: tuple[GateResult, ...] = Field(min_length=1)
    capability_invocations: tuple[FrozenCapabilityInvocationEvidence, ...]
    normalization_actions: tuple[FrozenNormalizationActionEvidence, ...]
    normalization_hash: Sha256
    runtime_evidence_refs: tuple[str, ...] = Field(min_length=1)
    user_request_sha256: Sha256 | None = None
    track: TrackKind | None = None
    assertions: tuple[dict[str, object], ...] = ()
    observation_sha256: Sha256 | None = None
    final_answer_sha256: Sha256 | None = None
    final_answer_text: str | None = Field(default=None, max_length=200_000)
    artifact_refs: tuple[str, ...] = ()
    runtime_failure: dict[str, object] | None = None
    resource_after_refs: tuple[str, ...] = ()
    terminal: dict[str, object] | None = None
    capability_result_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()
    checkpoint_refs: tuple[str, ...] = ()
    context_snapshot_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _empty_normalization_is_only_for_preplan_safe_failure(
        self,
    ) -> FrozenCaseEvidenceDetails:
        terminal_status = (
            self.terminal.get("run_status")
            if isinstance(self.terminal, dict)
            else None
        )
        if not self.normalization_actions and terminal_status != "safe_failure":
            raise ValueError(
                "只有规划前安全失败可以没有脚本归一化动作。"
            )
        return self


class EvidenceBundle(BenchmarkModel):
    identity: EvidenceBundleIdentity
    availability: dict[StableId, EvidenceAvailability]
    problems: tuple[str, ...]
    details: FrozenCaseEvidenceDetails | None = None

    @model_validator(mode="after")
    def _available_bundle_has_no_problems(self) -> EvidenceBundle:
        if (
            self.availability
            and all(
                item
                in {
                    EvidenceAvailability.AVAILABLE,
                    EvidenceAvailability.NOT_APPLICABLE,
                }
                for item in self.availability.values()
            )
            and self.problems
        ):
            raise ValueError("完整证据包不得携带未解决问题。")
        return self


class SuiteRunLifecycle(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    UNFINISHED = "unfinished"
    CANCELLED = "cancelled"


class SuiteConclusion(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INVALID = "invalid"
    NOT_EVALUATED = "not_evaluated"


class ProviderExecutionState(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    ERROR = "error"
    COMPLETED = "completed"


class CaseExecutionState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNFINISHED = "unfinished"


class CaseResultRow(BenchmarkModel):
    suite_id: StableId
    case_id: StableId
    case_execution_id: str = Field(pattern=r"^benchmark_case_[a-f0-9]{32}$")
    attempt_number: int = Field(ge=1)
    execution_state: CaseExecutionState
    conclusion: CaseConclusion | None
    failure_category: FailureCategory | None
    failure_categories: tuple[FailureCategory, ...]
    evidence_bundle_id: str = Field(pattern=r"^evidence_[a-f0-9]{64}$")
    evidence_availability: EvidenceAvailability

    @model_validator(mode="after")
    def _state_maps_to_conclusion(self) -> CaseResultRow:
        if self.execution_state is CaseExecutionState.COMPLETED:
            if self.conclusion not in {
                CaseConclusion.PASSED,
                CaseConclusion.FAILED,
                CaseConclusion.INVALID,
            }:
                raise ValueError("completed 案例必须有可判断的业务结论。")
        elif self.execution_state is CaseExecutionState.CANCELLED:
            if self.conclusion is not CaseConclusion.CANCELLED:
                raise ValueError("cancelled 案例必须保留 cancelled 结论。")
        elif self.execution_state is CaseExecutionState.UNFINISHED:
            if self.conclusion is not CaseConclusion.UNFINISHED:
                raise ValueError("unfinished 案例必须保留 unfinished 结论。")
        elif self.conclusion is not None:
            raise ValueError("pending/running/blocked/error 不得伪造业务结论。")

        categories = set(self.failure_categories)
        if len(categories) != len(self.failure_categories):
            raise ValueError("failure_categories 不得重复。")
        if self.failure_category is not None and self.failure_category not in categories:
            raise ValueError("主要失败类别必须属于完整失败类别集合。")
        if self.conclusion is CaseConclusion.PASSED and categories:
            raise ValueError("通过案例不得携带失败类别。")
        return self


class MechanismConclusion(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


class MechanismDecisionSource(StrEnum):
    HARD_GATE = "hard_gate"
    QUALIFIED_ABLATION = "qualified_ablation"


class MechanismGateResult(BenchmarkModel):
    scope: Literal["mechanism"] = "mechanism"
    mechanism_id: StableId
    status: GateStatus
    conditions: tuple[GateConditionResult, ...] = Field(min_length=1)
    evidence_refs: tuple[StableId, ...]
    conclusion: MechanismConclusion
    decision_source: MechanismDecisionSource

    @model_validator(mode="after")
    def _status_matches_conclusion(self) -> MechanismGateResult:
        expected = {
            GateStatus.PASSED: MechanismConclusion.MET,
            GateStatus.FAILED: MechanismConclusion.NOT_MET,
            GateStatus.INVALID: MechanismConclusion.INVALID,
        }
        if self.conclusion is not expected[self.status]:
            raise ValueError("机制门禁状态与机制结论不一致。")
        return self


class SuiteRun(BenchmarkModel):
    run_id: str = Field(
        pattern=r"^benchmark_run_\d{8}T\d{6}Z_[a-f0-9]{12}$"
    )
    revision: int = Field(ge=0)
    lifecycle: SuiteRunLifecycle
    conclusion: SuiteConclusion | None
    suite_content_hash: Sha256
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    track: TrackKind
    provider_state: ProviderExecutionState
    case_row_refs: tuple[str, ...]
    pending_case_ids: tuple[StableId, ...]
    terminal_artifact_ref: str | None

    @model_validator(mode="after")
    def _validate_lifecycle_conclusion(self) -> SuiteRun:
        if self.lifecycle is SuiteRunLifecycle.COMPLETED:
            if self.conclusion is None:
                raise ValueError("completed suite run 必须有 conclusion。")
            if not self.terminal_artifact_ref:
                raise ValueError("completed suite run 必须有终态工件引用。")
        else:
            if self.conclusion is not None:
                raise ValueError("非 completed suite run 的 conclusion 必须为 null。")
            if self.terminal_artifact_ref is not None:
                raise ValueError("非 completed suite run 不得伪造终态工件。")
        return self


class SuiteArtifact(BenchmarkModel):
    artifact_id: str = Field(min_length=1, max_length=300)
    run_id: str = Field(min_length=1, max_length=200)
    conclusion: SuiteConclusion
    case_rows: tuple[CaseResultRow, ...]
    evidence_bundles: tuple[EvidenceBundle, ...]
    provider_state: ProviderExecutionState
    artifact_hash: Sha256

    @model_validator(mode="after")
    def _passed_artifact_has_only_available_evidence(self) -> SuiteArtifact:
        row_keys = tuple((row.suite_id, row.case_id) for row in self.case_rows)
        if len(row_keys) != len(set(row_keys)):
            raise ValueError("套件工件不得包含重复案例行。")
        bundles_by_id = {
            bundle.identity.bundle_id: bundle for bundle in self.evidence_bundles
        }
        if len(bundles_by_id) != len(self.evidence_bundles):
            raise ValueError("套件工件不得包含重复证据包。")
        for row in self.case_rows:
            bundle = bundles_by_id.get(row.evidence_bundle_id)
            if bundle is None:
                raise ValueError(f"案例行缺少对应证据包：{row.case_id}。")
            identity = bundle.identity
            if (
                identity.suite_id != row.suite_id
                or identity.case_id != row.case_id
                or identity.case_execution_id != row.case_execution_id
            ):
                raise ValueError(f"案例行与证据包 owner 不一致：{row.case_id}。")
        if self.conclusion is SuiteConclusion.PASSED:
            if not self.case_rows or any(
                row.execution_state is not CaseExecutionState.COMPLETED
                or row.conclusion is not CaseConclusion.PASSED
                or row.evidence_availability is not EvidenceAvailability.AVAILABLE
                for row in self.case_rows
            ):
                raise ValueError("passed 套件必须由实际已完成且证据可用的通过案例行组成。")
            invalid = [
                bundle.identity.bundle_id
                for bundle in self.evidence_bundles
                if any(
                    availability
                    not in {
                        EvidenceAvailability.AVAILABLE,
                        EvidenceAvailability.NOT_APPLICABLE,
                    }
                    for availability in bundle.availability.values()
                )
            ]
            if invalid:
                raise ValueError(
                    "passed 套件不得包含不可用证据包：" + ", ".join(invalid)
                )
        return self


class SuiteRunCounts(BenchmarkModel):
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    running: int = Field(ge=0)
    blocked: int = Field(ge=0)
    error: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    invalid: int = Field(ge=0)
    unfinished: int = Field(ge=0)
    cancelled: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_sum_to_total(self) -> SuiteRunCounts:
        if self.total != sum(
            (
                self.pending,
                self.running,
                self.blocked,
                self.error,
                self.passed,
                self.failed,
                self.invalid,
                self.unfinished,
                self.cancelled,
            )
        ):
            raise ValueError("套件运行计数必须由案例行完整且互斥地派生。")
        return self


def aggregate_case_rows(rows: tuple[CaseResultRow, ...]) -> SuiteRunCounts:
    return SuiteRunCounts(
        total=len(rows),
        pending=sum(
            item.execution_state is CaseExecutionState.PENDING for item in rows
        ),
        running=sum(
            item.execution_state is CaseExecutionState.RUNNING for item in rows
        ),
        blocked=sum(
            item.execution_state is CaseExecutionState.BLOCKED for item in rows
        ),
        error=sum(item.execution_state is CaseExecutionState.ERROR for item in rows),
        passed=sum(item.conclusion is CaseConclusion.PASSED for item in rows),
        failed=sum(item.conclusion is CaseConclusion.FAILED for item in rows),
        invalid=sum(item.conclusion is CaseConclusion.INVALID for item in rows),
        unfinished=sum(
            item.conclusion is CaseConclusion.UNFINISHED for item in rows
        ),
        cancelled=sum(
            item.conclusion is CaseConclusion.CANCELLED for item in rows
        ),
    )
