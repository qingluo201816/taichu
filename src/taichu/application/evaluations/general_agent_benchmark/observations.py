"""Benchmark 案例的 owner-aware 真实观察与证据完整性投影。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    GateKind,
    Sha256,
    StableId,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
)


class EvidenceKind(StrEnum):
    RUN = "run"
    INVOCATION = "invocation"
    ARTIFACT = "artifact"
    RESOURCE_SNAPSHOT = "resource_snapshot"
    CAPABILITY_RESULT = "capability_result"
    EFFECT = "effect"
    CHECKPOINT = "checkpoint"
    CONTEXT_SNAPSHOT = "context_snapshot"
    FIXTURE_SENTINEL = "fixture_sentinel"
    SCRIPT_PROTOCOL = "script_protocol"


class EvidenceSelector(StrEnum):
    BUDGET = "budget"
    STATUS = "status"
    STOP_REASON = "stop_reason"
    RECOVERY = "recovery"
    COUNT = "count"
    TOPOLOGY = "topology"
    OUTCOME = "outcome"
    DATAFLOW = "dataflow"
    IDENTITY = "identity"
    CONTRACT = "contract"
    PROVENANCE = "provenance"
    BEFORE = "before"
    AFTER = "after"
    DIFF = "diff"
    PAYLOAD = "payload"
    REUSE = "reuse"
    REQUEST = "request"
    RECONCILIATION = "reconciliation"
    REVISION = "revision"
    INTEGRITY = "integrity"
    RESUME = "resume"
    LAYERS = "layers"
    PROJECTION = "projection"
    COMPRESSION = "compression"
    ISOLATION = "isolation"
    UNCHANGED = "unchanged"
    CONSUMPTION = "consumption"
    ORDER = "order"
    COMPLETION = "completion"


_ALLOWED_SELECTORS: dict[EvidenceKind, frozenset[EvidenceSelector]] = {
    EvidenceKind.RUN: frozenset(
        {
            EvidenceSelector.BUDGET,
            EvidenceSelector.STATUS,
            EvidenceSelector.STOP_REASON,
            EvidenceSelector.RECOVERY,
        }
    ),
    EvidenceKind.INVOCATION: frozenset(
        {
            EvidenceSelector.COUNT,
            EvidenceSelector.TOPOLOGY,
            EvidenceSelector.OUTCOME,
            EvidenceSelector.DATAFLOW,
        }
    ),
    EvidenceKind.ARTIFACT: frozenset(
        {
            EvidenceSelector.IDENTITY,
            EvidenceSelector.CONTRACT,
            EvidenceSelector.PROVENANCE,
        }
    ),
    EvidenceKind.RESOURCE_SNAPSHOT: frozenset(
        {
            EvidenceSelector.BEFORE,
            EvidenceSelector.AFTER,
            EvidenceSelector.DIFF,
        }
    ),
    EvidenceKind.CAPABILITY_RESULT: frozenset(
        {
            EvidenceSelector.IDENTITY,
            EvidenceSelector.PAYLOAD,
            EvidenceSelector.REUSE,
        }
    ),
    EvidenceKind.EFFECT: frozenset(
        {
            EvidenceSelector.REQUEST,
            EvidenceSelector.OUTCOME,
            EvidenceSelector.RECONCILIATION,
        }
    ),
    EvidenceKind.CHECKPOINT: frozenset(
        {
            EvidenceSelector.REVISION,
            EvidenceSelector.INTEGRITY,
            EvidenceSelector.RESUME,
        }
    ),
    EvidenceKind.CONTEXT_SNAPSHOT: frozenset(
        {
            EvidenceSelector.LAYERS,
            EvidenceSelector.PROJECTION,
            EvidenceSelector.COMPRESSION,
        }
    ),
    EvidenceKind.FIXTURE_SENTINEL: frozenset(
        {
            EvidenceSelector.IDENTITY,
            EvidenceSelector.ISOLATION,
            EvidenceSelector.UNCHANGED,
        }
    ),
    EvidenceKind.SCRIPT_PROTOCOL: frozenset(
        {
            EvidenceSelector.CONSUMPTION,
            EvidenceSelector.ORDER,
            EvidenceSelector.COMPLETION,
        }
    ),
}


class EvidenceIntegrityStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class EvidenceOwner(BenchmarkModel):
    """证据必须共同绑定的 suite/case/execution/run/track/fixture 身份。"""

    suite_id: StableId
    suite_content_hash: Sha256
    case_id: StableId
    case_execution_id: str = Field(pattern=r"^benchmark_case_[a-f0-9]{32}$")
    run_id: str = Field(min_length=1, max_length=128)
    entry_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    lineage_run_ids: tuple[str, ...] = ()
    track: TrackKind
    fixture_snapshot_id: str = Field(pattern=r"^fixture_[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _lineage_is_consistent(self) -> EvidenceOwner:
        if not self.lineage_run_ids:
            if self.entry_run_id is not None:
                raise ValueError("owner 缺少 lineage_run_ids。")
            return self
        if len(self.lineage_run_ids) != len(set(self.lineage_run_ids)):
            raise ValueError("owner lineage_run_ids 不得重复。")
        if self.entry_run_id != self.lineage_run_ids[0]:
            raise ValueError("owner entry_run_id 必须是谱系入口。")
        if self.run_id != self.lineage_run_ids[-1]:
            raise ValueError("owner run_id 必须是谱系叶节点。")
        return self


class EvidenceRef(BenchmarkModel):
    """只能使用固定 kind/selector 的内容寻址证据引用。"""

    evidence_id: StableId
    kind: EvidenceKind
    selector: EvidenceSelector
    owner: EvidenceOwner
    record_id: str = Field(min_length=1, max_length=256)
    content_sha256: Sha256

    @model_validator(mode="after")
    def _selector_belongs_to_kind(self) -> EvidenceRef:
        if self.selector not in _ALLOWED_SELECTORS[self.kind]:
            raise ValueError(
                f"证据类型 {self.kind.value} 不允许 selector={self.selector.value}。"
            )
        return self


class EvidenceRecord(BenchmarkModel):
    """解析后的只读证据投影；hash 由观察构建器独立复核。"""

    ref: EvidenceRef
    payload: dict[str, Any]


class EvidenceProblem(BenchmarkModel):
    code: Literal[
        "evidence_missing",
        "evidence_id_conflict",
        "evidence_owner_mismatch",
        "evidence_content_hash_mismatch",
        "evidence_probe_mismatch",
    ]
    message: str = Field(min_length=1, max_length=2_000)
    evidence_id: StableId
    record_id: str | None = None


class EvidenceResolution(BenchmarkModel):
    evidence_id: StableId
    gate: GateKind
    expected_kind: EvidenceKind
    expected_selector: EvidenceSelector
    status: EvidenceIntegrityStatus
    ref: EvidenceRef | None = None
    problems: tuple[EvidenceProblem, ...] = ()

    @model_validator(mode="after")
    def _status_matches_problems(self) -> EvidenceResolution:
        expected = (
            EvidenceIntegrityStatus.INVALID
            if self.problems
            else EvidenceIntegrityStatus.VALID
        )
        if self.status is not expected:
            raise ValueError("证据解析状态必须由完整性问题唯一派生。")
        if self.status is EvidenceIntegrityStatus.VALID and self.ref is None:
            raise ValueError("有效证据解析必须保留实际 EvidenceRef。")
        return self


class ObservedNode(BenchmarkModel):
    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    plan_revision: int = Field(ge=0)
    capability_kind: Literal["tool", "subagent"]
    capability_name: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64)
    dependencies: tuple[str, ...] = ()
    input_sha256: Sha256 | None = None
    output_sha256: Sha256 | None = None
    started_at: str | None = None
    finished_at: str | None = None


class ObservedInvocation(BenchmarkModel):
    call_id: str = Field(min_length=1, max_length=256)
    sequence: int | None = Field(default=None, ge=0)
    parent_call_id: str | None = Field(default=None, max_length=256)
    run_id: str | None = Field(default=None, max_length=128)
    node_id: str | None = Field(default=None, max_length=128)
    capability_kind: Literal["tool", "subagent"]
    capability_name: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64)
    input_sha256: Sha256
    output_sha256: Sha256 | None = None
    source_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    started_at: str | None = None
    finished_at: str | None = None


class ObservedInvocationIdentity(BenchmarkModel):
    """从真实能力 payload 按稳定接口字段提取的最小数据交接身份。"""

    call_id: str = Field(min_length=1, max_length=256)
    capability_name: str = Field(min_length=1, max_length=128)
    direction: Literal["input", "output"]
    identity_field: Literal[
        "content_sha256",
        "output_sha256",
        "input_sha256",
        "source_ref",
        "artifact_ref",
        "result_id",
        "preview_sha256",
        "resource_id",
        "revision",
        "claim_id",
    ]
    selector_path: str = Field(min_length=1, max_length=256)
    identity: str = Field(min_length=1, max_length=512)
    payload_sha256: Sha256


class ObservedHumanDecision(BenchmarkModel):
    """Runtime 已创建的人工请求与控制器实际提交决定。"""

    source_run_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    request_kind: str = Field(min_length=1, max_length=128)
    node_id: str | None = Field(default=None, max_length=128)
    tool_name: str | None = Field(default=None, max_length=128)
    input_sha256: Sha256 | None = None
    resource_scopes: tuple[str, ...] = ()
    second_confirmation_required: bool = False
    approved: bool
    second_confirmation: bool = False
    request_created_at: str = Field(min_length=1)


class ObservedEffect(BenchmarkModel):
    """按 effect_id 收敛后的真实副作用终态。"""

    effect_id: str = Field(pattern=r"^effect_[a-f0-9]{32}$")
    run_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64)
    input_sha256: Sha256
    resource_scopes: tuple[str, ...] = ()
    authorization_reference: str | None = Field(default=None, max_length=200)
    output_sha256: Sha256
    evidence_sha256: Sha256


class ObservedFinalAnswer(BenchmarkModel):
    text: str = Field(min_length=1, max_length=200_000)
    content_sha256: Sha256
    source_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _content_hash_is_valid(self) -> ObservedFinalAnswer:
        if self.content_sha256 != canonical_sha256(self.text):
            raise ValueError("最终回答内容哈希不匹配。")
        return self

    @classmethod
    def create(
        cls,
        *,
        text: str,
        source_refs: tuple[str, ...],
    ) -> ObservedFinalAnswer:
        return cls(
            text=text,
            content_sha256=canonical_sha256(text),
            source_refs=source_refs,
        )


class ObservedArtifact(BenchmarkModel):
    artifact_id: str = Field(min_length=1, max_length=256)
    artifact_kind: str = Field(min_length=1, max_length=128)
    producer_node_id: str | None = Field(default=None, max_length=128)
    content_sha256: Sha256
    source_refs: tuple[str, ...] = ()
    payload: dict[str, Any] = Field(default_factory=dict)


class ObservedResourceSnapshot(BenchmarkModel):
    snapshot_ref: str = Field(min_length=1, max_length=256)
    phase: Literal["before", "after"]
    content_sha256: Sha256
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _snapshot_hash_is_valid(self) -> ObservedResourceSnapshot:
        if self.content_sha256 != canonical_sha256(self.payload):
            raise ValueError("资源快照内容哈希不匹配。")
        return self


class ObservedRecoveryDecision(BenchmarkModel):
    decision_id: str = Field(min_length=1, max_length=256)
    action: Literal[
        "resume",
        "reuse_result",
        "retry",
        "reconcile_effect",
        "stop",
    ]
    reason_code: str = Field(min_length=1, max_length=128)
    result_id: str | None = Field(default=None, max_length=128)
    checkpoint_revision: int | None = Field(default=None, ge=1)
    evidence_sha256: Sha256


class ObservedTerminalState(BenchmarkModel):
    run_status: str = Field(min_length=1, max_length=64)
    stop_reason: str = Field(min_length=1, max_length=128)
    resumable: bool
    pending_human_kind: str | None = Field(default=None, max_length=128)


class ObservedBudgetUsage(BenchmarkModel):
    node_executions: int = Field(ge=0)
    replans: int = Field(default=0, ge=0)
    capability_calls: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    runtime_ms: int = Field(ge=0)
    context_tokens: int = Field(ge=0)


class CaseObservation(BenchmarkModel):
    """供 Typed Oracle 消费的最小、可审计案例观察。"""

    owner: EvidenceOwner
    user_request_raw: str = Field(min_length=1, max_length=100_000)
    user_request_sha256: Sha256
    plan: dict[str, Any] | None
    plan_sha256: Sha256 | None
    nodes: tuple[ObservedNode, ...]
    invocations: tuple[ObservedInvocation, ...]
    final_answer: ObservedFinalAnswer | None
    artifacts: tuple[ObservedArtifact, ...]
    resource_snapshots: tuple[ObservedResourceSnapshot, ...]
    capability_result_refs: tuple[EvidenceRef, ...]
    effect_refs: tuple[EvidenceRef, ...]
    checkpoint_refs: tuple[EvidenceRef, ...]
    context_snapshot_refs: tuple[EvidenceRef, ...]
    recovery_decisions: tuple[ObservedRecoveryDecision, ...]
    terminal: ObservedTerminalState
    budget: ObservedBudgetUsage
    script_protocol_deviations: tuple[str, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    evidence_resolutions: tuple[EvidenceResolution, ...]
    evidence_integrity: EvidenceIntegrityStatus
    evidence_problems: tuple[EvidenceProblem, ...]
    observation_sha256: Sha256

    @model_validator(mode="after")
    def _identity_and_hashes_are_valid(self) -> CaseObservation:
        if self.user_request_sha256 != canonical_sha256(self.user_request_raw):
            raise ValueError("当前请求内容哈希不匹配。")
        expected_plan_hash = (
            canonical_sha256(self.plan) if self.plan is not None else None
        )
        if self.plan_sha256 != expected_plan_hash:
            raise ValueError("计划内容哈希不匹配。")
        expected_integrity = (
            EvidenceIntegrityStatus.INVALID
            if self.evidence_problems
            else EvidenceIntegrityStatus.VALID
        )
        if self.evidence_integrity is not expected_integrity:
            raise ValueError("案例证据完整性状态与问题集合不一致。")
        if self.observation_sha256 != canonical_sha256(
            self.model_dump(mode="json", exclude={"observation_sha256"})
        ):
            raise ValueError("案例观察内容哈希不匹配。")
        return self


def build_case_observation(
    *,
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
    user_request_raw: str,
    plan: dict[str, Any] | None,
    nodes: tuple[ObservedNode, ...],
    invocations: tuple[ObservedInvocation, ...],
    final_answer: ObservedFinalAnswer | None,
    artifacts: tuple[ObservedArtifact, ...],
    resource_snapshots: tuple[ObservedResourceSnapshot, ...],
    recovery_decisions: tuple[ObservedRecoveryDecision, ...],
    terminal: ObservedTerminalState,
    budget: ObservedBudgetUsage,
    script_protocol_deviations: tuple[str, ...],
    evidence_records: tuple[EvidenceRecord, ...],
) -> CaseObservation:
    """构建观察并把所有证据缺损收敛为 typed INVALID。"""

    if owner.case_id != case.case_id:
        raise ValueError("案例观察 owner.case_id 与正式案例不一致。")
    if user_request_raw != case.user_request_raw:
        raise ValueError("案例观察必须保留当前请求原文。")

    records_by_id: dict[str, list[EvidenceRecord]] = {}
    global_problems: list[EvidenceProblem] = []
    for record in evidence_records:
        records_by_id.setdefault(record.ref.evidence_id, []).append(record)
        global_problems.extend(_record_integrity_problems(record, owner=owner))

    for evidence_id, records in records_by_id.items():
        if len(records) <= 1:
            continue
        global_problems.append(
            EvidenceProblem(
                code="evidence_id_conflict",
                message=f"证据 {evidence_id} 存在多个相互竞争的记录。",
                evidence_id=evidence_id,
            )
        )

    resolutions: list[EvidenceResolution] = []
    for requirement in case.required_evidence:
        expected_kind = EvidenceKind(requirement.probe.kind)
        expected_selector = EvidenceSelector(requirement.probe.selector)
        matching = records_by_id.get(requirement.evidence_id, [])
        resolution_problems: list[EvidenceProblem] = []
        ref: EvidenceRef | None = matching[0].ref if matching else None
        if not matching:
            problem = EvidenceProblem(
                code="evidence_missing",
                message=f"缺少必需证据：{requirement.evidence_id}。",
                evidence_id=requirement.evidence_id,
            )
            global_problems.append(problem)
            resolution_problems.append(problem)
        else:
            if len(matching) > 1:
                resolution_problems.extend(
                    problem
                    for problem in global_problems
                    if problem.evidence_id == requirement.evidence_id
                    and problem.code == "evidence_id_conflict"
                )
            actual_ref = matching[0].ref
            if (
                actual_ref.kind != expected_kind
                or actual_ref.selector != expected_selector
            ):
                problem = EvidenceProblem(
                    code="evidence_probe_mismatch",
                    message=(
                        f"证据 {requirement.evidence_id} 的实际 probe "
                        f"{actual_ref.kind}/{actual_ref.selector} 与合同不一致。"
                    ),
                    evidence_id=requirement.evidence_id,
                    record_id=actual_ref.record_id,
                )
                global_problems.append(problem)
                resolution_problems.append(problem)
            resolution_problems.extend(
                problem
                for problem in global_problems
                if problem.evidence_id == requirement.evidence_id
                and problem.code
                in {
                    "evidence_owner_mismatch",
                    "evidence_content_hash_mismatch",
                }
            )
        resolution_problems = list(_unique_problems(resolution_problems))
        resolutions.append(
            EvidenceResolution(
                evidence_id=requirement.evidence_id,
                gate=requirement.gate,
                expected_kind=expected_kind,
                expected_selector=expected_selector,
                status=(
                    EvidenceIntegrityStatus.INVALID
                    if resolution_problems
                    else EvidenceIntegrityStatus.VALID
                ),
                ref=ref,
                problems=tuple(resolution_problems),
            )
        )

    problems = _unique_problems(global_problems)
    content: dict[str, Any] = {
        "owner": owner,
        "user_request_raw": user_request_raw,
        "user_request_sha256": canonical_sha256(user_request_raw),
        "plan": plan,
        "plan_sha256": canonical_sha256(plan) if plan is not None else None,
        "nodes": nodes,
        "invocations": invocations,
        "final_answer": final_answer,
        "artifacts": artifacts,
        "resource_snapshots": resource_snapshots,
        "capability_result_refs": _refs_for_kind(
            evidence_records,
            EvidenceKind.CAPABILITY_RESULT,
        ),
        "effect_refs": _refs_for_kind(evidence_records, EvidenceKind.EFFECT),
        "checkpoint_refs": _refs_for_kind(
            evidence_records,
            EvidenceKind.CHECKPOINT,
        ),
        "context_snapshot_refs": _refs_for_kind(
            evidence_records,
            EvidenceKind.CONTEXT_SNAPSHOT,
        ),
        "recovery_decisions": recovery_decisions,
        "terminal": terminal,
        "budget": budget,
        "script_protocol_deviations": script_protocol_deviations,
        "evidence_records": evidence_records,
        "evidence_resolutions": tuple(resolutions),
        "evidence_integrity": (
            EvidenceIntegrityStatus.INVALID
            if problems
            else EvidenceIntegrityStatus.VALID
        ),
        "evidence_problems": problems,
    }
    return CaseObservation(
        **content,
        observation_sha256=canonical_sha256(content),
    )


def _record_integrity_problems(
    record: EvidenceRecord,
    *,
    owner: EvidenceOwner,
) -> tuple[EvidenceProblem, ...]:
    problems: list[EvidenceProblem] = []
    if record.ref.owner != owner:
        problems.append(
            EvidenceProblem(
                code="evidence_owner_mismatch",
                message=(
                    f"证据 {record.ref.evidence_id} 不属于当前 "
                    "suite/case/execution/run/track/fixture。"
                ),
                evidence_id=record.ref.evidence_id,
                record_id=record.ref.record_id,
            )
        )
    if record.ref.content_sha256 != canonical_sha256(record.payload):
        problems.append(
            EvidenceProblem(
                code="evidence_content_hash_mismatch",
                message=f"证据 {record.ref.evidence_id} 的内容哈希不一致。",
                evidence_id=record.ref.evidence_id,
                record_id=record.ref.record_id,
            )
        )
    return tuple(problems)


def _refs_for_kind(
    records: tuple[EvidenceRecord, ...],
    kind: EvidenceKind,
) -> tuple[EvidenceRef, ...]:
    return tuple(record.ref for record in records if record.ref.kind == kind)


def _unique_problems(
    problems: list[EvidenceProblem],
) -> tuple[EvidenceProblem, ...]:
    unique: dict[tuple[str, str, str | None], EvidenceProblem] = {}
    for problem in problems:
        key = (problem.code, problem.evidence_id, problem.record_id)
        unique.setdefault(key, problem)
    return tuple(unique.values())
