"""需求 15.14-15.40：缺陷关闭证明与模型比较唯一准入。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ComparisonAdmissionInput,
    ModelComparisonAdmission,
    evaluate_model_comparison_admission,
)
from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    IssueStatus,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)


class ClosureLeaseConflict(RuntimeError):
    """缺陷闭环租约由其他协调器持有或 revision 已变化。"""


class ClosureEvidence(BenchmarkModel):
    intent_id: str = Field(pattern=r"^issue_intent_[a-f0-9]{64}$")
    issue_id: str = Field(min_length=1, max_length=300)
    issue_revision: int = Field(ge=0)
    targeted_case_passed: bool
    full_suite_passed: bool
    rerun_suite_hash: Sha256
    current_suite_hash: Sha256
    core_gates_passed: bool
    symmetry_gate_passed: bool
    issue_status: IssueStatus
    first_live_artifact_ref: str | None = Field(
        default=None,
        pattern=r"^first_live_[a-f0-9]{64}$",
    )
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class IssueClosureDecision(BenchmarkModel):
    closure_id: str | None = Field(
        default=None,
        pattern=r"^issue_closure_[a-f0-9]{64}$",
    )
    intent_id: str = Field(pattern=r"^issue_intent_[a-f0-9]{64}$")
    issue_id: str = Field(min_length=1, max_length=300)
    issue_revision: int = Field(ge=0)
    ready: bool
    blocked_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    decision_hash: Sha256


class ClosureLease(BenchmarkModel):
    intent_id: str = Field(pattern=r"^issue_intent_[a-f0-9]{64}$")
    owner_id: StableId
    revision: int = Field(ge=1)


class IssueClosureCoordinator:
    """关闭提交点只接受已读回、已复跑且四方对称的证据。"""

    def __init__(self) -> None:
        self._leases: dict[str, ClosureLease] = {}
        self._closures: dict[str, IssueClosureDecision] = {}

    @staticmethod
    def evaluate(evidence: ClosureEvidence) -> IssueClosureDecision:
        reasons: list[str] = []
        if not evidence.targeted_case_passed:
            reasons.append("定向案例复跑未通过。")
        if not evidence.full_suite_passed:
            reasons.append("当前套件全量复跑未通过。")
        if evidence.rerun_suite_hash != evidence.current_suite_hash:
            reasons.append("复跑套件哈希不是当前套件。")
        if not evidence.core_gates_passed:
            reasons.append("核心硬门禁未通过。")
        if not evidence.symmetry_gate_passed:
            reasons.append("问题关联对称性门禁未通过。")
        if evidence.issue_status is not IssueStatus.PROCESSED:
            reasons.append("Inbox 问题尚未读回为已处理。")
        if evidence.first_live_artifact_ref is None:
            reasons.append("首轮工件尚未冻结。")
        payload = {
            "intent_id": evidence.intent_id,
            "issue_id": evidence.issue_id,
            "issue_revision": evidence.issue_revision,
            "ready": not reasons,
            "blocked_reasons": tuple(reasons),
            "evidence_refs": evidence.evidence_refs,
            "rerun_suite_hash": evidence.rerun_suite_hash,
            "current_suite_hash": evidence.current_suite_hash,
            "first_live_artifact_ref": evidence.first_live_artifact_ref,
        }
        decision_hash = canonical_sha256(payload)
        return IssueClosureDecision(
            closure_id=(
                f"issue_closure_{decision_hash}" if not reasons else None
            ),
            intent_id=evidence.intent_id,
            issue_id=evidence.issue_id,
            issue_revision=evidence.issue_revision,
            ready=not reasons,
            blocked_reasons=tuple(reasons),
            evidence_refs=evidence.evidence_refs,
            decision_hash=decision_hash,
        )

    def acquire_lease(
        self,
        *,
        intent_id: str,
        owner_id: str,
        expected_revision: int,
    ) -> ClosureLease:
        current = self._leases.get(intent_id)
        current_revision = current.revision if current is not None else 0
        if current_revision != expected_revision:
            raise ClosureLeaseConflict(
                f"闭环租约 revision 冲突：当前 {current_revision}。"
            )
        if current is not None and current.owner_id != owner_id:
            raise ClosureLeaseConflict("闭环租约已由其他协调器持有。")
        lease = ClosureLease(
            intent_id=intent_id,
            owner_id=owner_id,
            revision=current_revision + 1,
        )
        self._leases[intent_id] = lease
        return lease

    def commit(
        self,
        evidence: ClosureEvidence,
        *,
        owner_id: str,
        expected_lease_revision: int,
    ) -> IssueClosureDecision:
        existing = self._closures.get(evidence.intent_id)
        decision = self.evaluate(evidence)
        if existing is not None:
            if existing != decision:
                raise ValueError("闭环意图已经提交不同证据。")
            return existing
        if not decision.ready:
            raise ValueError(
                "缺陷尚未满足关闭条件：" + "；".join(decision.blocked_reasons)
            )
        lease = self._leases.get(evidence.intent_id)
        if (
            lease is None
            or lease.owner_id != owner_id
            or lease.revision != expected_lease_revision
        ):
            raise ClosureLeaseConflict("闭环提交未持有匹配租约。")
        self._closures[evidence.intent_id] = decision
        return decision


class ModelComparisonRequest(BenchmarkModel):
    comparison_id: StableId
    idempotency_key: str = Field(min_length=1, max_length=300)
    first_live_artifact_ref: str | None = Field(
        default=None,
        pattern=r"^first_live_[a-f0-9]{64}$",
    )
    admission_input: ComparisonAdmissionInput
    closure_decisions: tuple[IssueClosureDecision, ...]


class ProviderExperimentState(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ERROR = "error"


class ModelEvidenceScope(StrEnum):
    FULL_SUITE = "full_suite"
    CAPABILITY_PROBE = "capability_probe"


class ModelQualification(StrEnum):
    QUALIFIED = "qualified"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


class ModelComparisonCandidateResult(BenchmarkModel):
    candidate_id: StableId
    display_name: str = Field(min_length=1, max_length=200)
    run_id: StableId
    execution_state: ProviderExperimentState
    evidence_scope: ModelEvidenceScope = ModelEvidenceScope.FULL_SUITE
    qualification: ModelQualification = ModelQualification.FAILED
    eligible_for_ranking: bool
    requested_provider_id: str = Field(min_length=1, max_length=100)
    requested_model_id: str = Field(min_length=1, max_length=200)
    actual_provider_id: str | None = Field(default=None, max_length=100)
    actual_model_id: str | None = Field(default=None, max_length=200)
    fallback_used: bool
    request_timeout_seconds: float = Field(default=0, ge=0)
    provider_max_retries: int = Field(default=0, ge=0)
    case_count: int = Field(ge=0)
    passed_case_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    model_call_attempts: int = Field(ge=0)
    completed_model_calls: int = Field(default=0, ge=0)
    failed_model_calls: int = Field(default=0, ge=0)
    avg_model_call_attempts: float = Field(ge=0)
    capability_steps: int = Field(ge=0)
    avg_capability_steps: float = Field(ge=0)
    tool_steps: int = Field(ge=0)
    subagent_steps: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(ge=0)
    suite_elapsed_ms: int = Field(default=0, ge=0)
    total_duration_ms: int = Field(default=0, ge=0)
    avg_model_call_duration_ms: float = Field(default=0, ge=0)
    p50_model_call_duration_ms: int = Field(default=0, ge=0)
    p95_model_call_duration_ms: int = Field(default=0, ge=0)
    cost_amount: float | None = Field(default=None, ge=0)
    cost_currency: str = Field(default="CNY", min_length=1, max_length=20)
    cost_kind_counts: dict[str, int] = Field(default_factory=dict)
    unavailable_cost_calls: int = Field(default=0, ge=0)
    provider_error_count: int = Field(ge=0)
    failed_case_ids: tuple[StableId, ...] = ()
    failure_category_counts: dict[str, int] = Field(default_factory=dict)
    gate_pass_counts: dict[str, int] = Field(default_factory=dict)
    artifact_ref: str = Field(min_length=1, max_length=400)
    artifact_hash: Sha256
    blocked_reason: str | None = Field(default=None, max_length=2000)


class ModelComparisonRecord(BenchmarkModel):
    comparison_id: StableId
    admitted: bool
    first_live_artifact_ref: str | None
    admission: ModelComparisonAdmission
    closure_ids: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    ranking_candidate_ids: tuple[StableId, ...]
    ranking_basis: tuple[str, ...] = ()
    candidate_results: tuple[ModelComparisonCandidateResult, ...] = ()
    catalog_model_count: int = Field(default=0, ge=0)
    covered_model_count: int = Field(default=0, ge=0)
    full_suite_model_count: int = Field(default=0, ge=0)
    blocked_model_count: int = Field(default=0, ge=0)
    record_hash: Sha256


class ModelComparisonService:
    """只消费冻结首轮引用、关闭决定与正式 admission，不重判运行证据。"""

    def __init__(self) -> None:
        self._records: dict[str, ModelComparisonRecord] = {}
        self._claims: dict[str, tuple[Sha256, str]] = {}

    def restore_frozen(self, record: ModelComparisonRecord) -> None:
        """恢复只读的冻结准入结论，禁止覆盖不同记录。"""

        existing = self._records.get(record.comparison_id)
        if existing is not None and existing != record:
            raise ValueError("冻结模型比较恢复冲突。")
        self._records[record.comparison_id] = record

    def create(self, request: ModelComparisonRequest) -> ModelComparisonRecord:
        request_hash = canonical_sha256(
            request.model_dump(mode="json", exclude={"idempotency_key"})
        )
        claim = self._claims.get(request.idempotency_key)
        if claim is not None:
            claimed_hash, comparison_id = claim
            if claimed_hash != request_hash:
                raise ValueError("模型比较幂等键已经绑定不同请求。")
            return self._records[comparison_id]
        if request.comparison_id in self._records:
            raise ValueError("模型比较标识已经由其他幂等键绑定。")

        admission = evaluate_model_comparison_admission(
            request.admission_input
        )
        reasons: list[str] = []
        if request.first_live_artifact_ref is None:
            reasons.append("首轮工件尚未冻结。")
        closure_ids: list[str] = []
        for decision in request.closure_decisions:
            reasons.extend(decision.blocked_reasons)
            if decision.ready and decision.closure_id is not None:
                closure_ids.append(decision.closure_id)
        reasons.extend(admission.blocked_reasons)
        blocked_reasons = tuple(dict.fromkeys(reasons))
        admitted = not blocked_reasons
        payload = {
            "comparison_id": request.comparison_id,
            "admitted": admitted,
            "first_live_artifact_ref": request.first_live_artifact_ref,
            "admission": admission,
            "closure_ids": tuple(closure_ids),
            "blocked_reasons": blocked_reasons,
            "ranking_candidate_ids": (
                admission.ranking_candidate_ids if admitted else ()
            ),
        }
        record = ModelComparisonRecord(
            **payload,
            record_hash=canonical_sha256(payload),
        )
        self._records[request.comparison_id] = record
        self._claims[request.idempotency_key] = (
            request_hash,
            request.comparison_id,
        )
        return record

    def list(self) -> tuple[ModelComparisonRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def get(self, comparison_id: str) -> ModelComparisonRecord:
        try:
            return self._records[comparison_id]
        except KeyError as error:
            raise KeyError(f"模型比较不存在：{comparison_id}") from error
