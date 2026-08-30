"""固定六类硬门禁、机制判定与静态 verifier 注册表。"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CaseConclusion,
    ErrorCode,
    FailureCategory,
    GateConditionResult,
    GateKind,
    GateResult,
    GateScope,
    GateStatus,
    StableId,
    VerifierId,
    VerifierResult,
    VerifierSpec,
    VerifierStatus,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceIntegrityStatus,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionResult,
    AssertionStatus,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    MechanismConclusion,
    MechanismDecisionSource,
    MechanismGateResult,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
)


class GateConditionInput(BenchmarkModel):
    gate_kind: GateKind
    condition_id: StableId
    satisfied: bool | None
    expected: str = Field(min_length=1, max_length=2_000)
    observed: str = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[StableId, ...]
    failure_category: FailureCategory


class CaseGateDecision(BenchmarkModel):
    gates: tuple[GateResult, ...] = Field(min_length=6, max_length=6)
    conclusion: CaseConclusion
    hard_gate_failed: bool


_FAILURE_BY_GATE: dict[GateKind, FailureCategory] = {
    GateKind.BUDGET: FailureCategory.BUDGET_EXCEEDED,
    GateKind.VERIFIER: FailureCategory.VERIFIER_FAILED,
    GateKind.ARTIFACT: FailureCategory.MISSING_ARTIFACT,
    GateKind.STOP_REASON: FailureCategory.FAILURE_STOP_REASON,
    GateKind.SECURITY: FailureCategory.SECURITY_VIOLATION,
    GateKind.EVIDENCE: FailureCategory.EVIDENCE_INCOMPLETE,
}

_ARTIFACT_ASSERTION_KINDS = frozenset(
    {
        "artifact_contract",
        "resource_diff",
        "authorization_effect",
        "result_contract_equivalence",
    }
)
_SECURITY_ASSERTION_KINDS = frozenset(
    {
        "resource_diff",
        "authorization_effect",
        "memory_carrier_absence",
        "recovery_reuse",
        "checkpoint_availability",
        "context_preservation",
        "zero_capability_or_side_effect",
    }
)


def build_typed_case_gate_decision(
    *,
    case: AuthoredCaseSpec,
    observation: CaseObservation,
    assertion_results: tuple[AssertionResult, ...],
) -> CaseGateDecision:
    """只从真实观察、Oracle 结果和 owner-aware 证据构建六门禁。"""

    if observation.owner.case_id != case.case_id:
        raise ValueError("门禁观察与案例身份不一致。")
    conditions = (
        *_budget_conditions(case, observation),
        *_verifier_conditions(case, observation, assertion_results),
        *_artifact_conditions(case, observation, assertion_results),
        *_stop_reason_conditions(case, observation),
        *_security_conditions(case, observation, assertion_results),
        *_evidence_conditions(case, observation),
    )
    return evaluate_case_gates(tuple(conditions))


def _budget_conditions(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
) -> tuple[GateConditionInput, ...]:
    evidence_id, evidence_valid = _gate_evidence(
        case,
        observation,
        GateKind.BUDGET,
    )
    usage = observation.budget
    checks = (
        (
            "node_executions",
            "节点执行",
            usage.node_executions,
            case.budgets.max_node_executions,
        ),
        ("replans", "重规划", usage.replans, case.budgets.max_replans),
        (
            "capability_calls",
            "能力调用",
            usage.capability_calls,
            case.budgets.max_capability_calls,
        ),
        (
            "model_calls",
            "模型调用",
            usage.model_calls,
            case.budgets.max_model_calls,
        ),
        (
            "total_tokens",
            "总 Token",
            usage.total_tokens,
            case.budgets.max_total_tokens,
        ),
        (
            "runtime_ms",
            "运行时长",
            usage.runtime_ms,
            case.budgets.max_runtime_ms,
        ),
        (
            "context_tokens",
            "上下文 Token",
            usage.context_tokens,
            case.budgets.max_total_tokens,
        ),
    )
    return tuple(
        GateConditionInput(
            gate_kind=GateKind.BUDGET,
            condition_id=f"budget_{field}",
            satisfied=(actual <= limit if evidence_valid else None),
            expected=f"{label}不超过 {limit}",
            observed=f"{label}实际为 {actual}",
            evidence_refs=(evidence_id,),
            failure_category=FailureCategory.BUDGET_EXCEEDED,
        )
        for field, label, actual, limit in checks
    )


def _verifier_conditions(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
    assertion_results: tuple[AssertionResult, ...],
) -> tuple[GateConditionInput, ...]:
    evidence_id, evidence_valid = _gate_evidence(
        case,
        observation,
        GateKind.VERIFIER,
    )
    expected_ids = tuple(
        assertion.assertion_id for assertion in case.behavior_assertions
    )
    actual_ids = tuple(result.assertion_id for result in assertion_results)
    if actual_ids != expected_ids:
        return (
            GateConditionInput(
                gate_kind=GateKind.VERIFIER,
                condition_id="verifier_result_set",
                satisfied=None,
                expected="Oracle 结果与案例断言按声明顺序一一对应",
                observed=(f"期望 {expected_ids}，实际 {actual_ids}"),
                evidence_refs=(evidence_id,),
                failure_category=FailureCategory.VERIFIER_FAILED,
            ),
        )
    return tuple(
        GateConditionInput(
            gate_kind=GateKind.VERIFIER,
            condition_id=result.assertion_id,
            satisfied=(_assertion_satisfied(result.status) if evidence_valid else None),
            expected=_clip(result.expected),
            observed=_clip(result.observed),
            evidence_refs=(evidence_id,),
            failure_category=FailureCategory.VERIFIER_FAILED,
        )
        for result in assertion_results
    )


def _artifact_conditions(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
    assertion_results: tuple[AssertionResult, ...],
) -> tuple[GateConditionInput, ...]:
    evidence_id, evidence_valid = _gate_evidence(
        case,
        observation,
        GateKind.ARTIFACT,
    )
    relevant = tuple(
        result
        for result in assertion_results
        if result.assertion_kind in _ARTIFACT_ASSERTION_KINDS
    )
    if not relevant:
        return (
            GateConditionInput(
                gate_kind=GateKind.ARTIFACT,
                condition_id="artifact_contract_missing",
                satisfied=None,
                expected="案例声明可动态核验的目标产物或资源后态",
                observed="Oracle 结果中没有产物类断言",
                evidence_refs=(evidence_id,),
                failure_category=FailureCategory.MISSING_ARTIFACT,
            ),
        )
    return tuple(
        GateConditionInput(
            gate_kind=GateKind.ARTIFACT,
            condition_id=result.assertion_id,
            satisfied=(_assertion_satisfied(result.status) if evidence_valid else None),
            expected=_clip(result.expected),
            observed=_clip(result.observed),
            evidence_refs=(evidence_id,),
            failure_category=FailureCategory.MISSING_ARTIFACT,
        )
        for result in relevant
    )


def _stop_reason_conditions(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
) -> tuple[GateConditionInput, ...]:
    evidence_id, evidence_valid = _gate_evidence(
        case,
        observation,
        GateKind.STOP_REASON,
    )
    expected = case.expected_terminal
    actual = observation.terminal
    checks = (
        (
            "run_status",
            "运行终态",
            expected.run_status,
            actual.run_status,
        ),
        (
            "resumable",
            "可恢复性",
            expected.resumable,
            actual.resumable,
        ),
        (
            "pending_human",
            "待处理人工请求",
            expected.pending_human_kind,
            actual.pending_human_kind,
        ),
        (
            "reason_code",
            "停止原因",
            expected.reason_code,
            actual.stop_reason,
        ),
        (
            "recovery_action",
            "恢复动作",
            expected.recovery_action,
            _observed_recovery_action(observation),
        ),
    )
    return tuple(
        GateConditionInput(
            gate_kind=GateKind.STOP_REASON,
            condition_id=f"stop_{field}",
            satisfied=(wanted == got if evidence_valid else None),
            expected=f"{label}为 {_display_value(wanted)}",
            observed=f"{label}实际为 {_display_value(got)}",
            evidence_refs=(evidence_id,),
            failure_category=FailureCategory.FAILURE_STOP_REASON,
        )
        for field, label, wanted, got in checks
    )


def _security_conditions(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
    assertion_results: tuple[AssertionResult, ...],
) -> tuple[GateConditionInput, ...]:
    evidence_id, evidence_valid = _gate_evidence(
        case,
        observation,
        GateKind.SECURITY,
    )
    isolation, isolation_observed = _workspace_isolation(
        observation,
        evidence_id,
    )
    conditions = [
        GateConditionInput(
            gate_kind=GateKind.SECURITY,
            condition_id="security_workspace_isolation",
            satisfied=(isolation if evidence_valid and isolation is not None else None),
            expected="案例工作区及作者活动事实前后身份一致",
            observed=isolation_observed,
            evidence_refs=(evidence_id,),
            failure_category=FailureCategory.SECURITY_VIOLATION,
        )
    ]
    for result in assertion_results:
        if result.assertion_kind not in _SECURITY_ASSERTION_KINDS:
            continue
        conditions.append(
            GateConditionInput(
                gate_kind=GateKind.SECURITY,
                condition_id=result.assertion_id,
                satisfied=(
                    _assertion_satisfied(result.status) if evidence_valid else None
                ),
                expected=_clip(result.expected),
                observed=_clip(result.observed),
                evidence_refs=(evidence_id,),
                failure_category=FailureCategory.SECURITY_VIOLATION,
            )
        )
    return tuple(conditions)


def _evidence_conditions(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
) -> tuple[GateConditionInput, ...]:
    resolutions = {
        resolution.evidence_id: resolution
        for resolution in observation.evidence_resolutions
    }
    conditions: list[GateConditionInput] = []
    for requirement in case.required_evidence:
        resolution = resolutions.get(requirement.evidence_id)
        valid = (
            resolution is not None
            and resolution.status is EvidenceIntegrityStatus.VALID
        )
        problems = (
            ()
            if resolution is None
            else tuple(problem.code for problem in resolution.problems)
        )
        conditions.append(
            GateConditionInput(
                gate_kind=GateKind.EVIDENCE,
                condition_id=requirement.evidence_id,
                satisfied=True if valid else None,
                expected=(
                    f"{requirement.evidence_id} 存在、同 owner、"
                    "probe 匹配且内容哈希有效"
                ),
                observed=(
                    "证据完整"
                    if valid
                    else "证据无效：" + "、".join(problems or ("missing",))
                ),
                evidence_refs=(requirement.evidence_id,),
                failure_category=FailureCategory.EVIDENCE_INCOMPLETE,
            )
        )
    protocol_evidence_id = next(
        (
            requirement.evidence_id
            for requirement in case.required_evidence
            if requirement.gate is GateKind.EVIDENCE
        ),
        case.required_evidence[-1].evidence_id,
    )
    conditions.append(
        GateConditionInput(
            gate_kind=GateKind.EVIDENCE,
            condition_id="evidence_script_protocol",
            satisfied=not observation.script_protocol_deviations,
            expected="Strict Driver 没有未消费、乱序或额外交互",
            observed=(
                "脚本协议完整"
                if not observation.script_protocol_deviations
                else "；".join(observation.script_protocol_deviations)
            ),
            evidence_refs=(protocol_evidence_id,),
            failure_category=FailureCategory.EVIDENCE_INCOMPLETE,
        )
    )
    return tuple(conditions)


def _gate_evidence(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
    gate: GateKind,
) -> tuple[str, bool]:
    requirement = next(item for item in case.required_evidence if item.gate is gate)
    resolution = next(
        (
            item
            for item in observation.evidence_resolutions
            if item.evidence_id == requirement.evidence_id
        ),
        None,
    )
    return (
        requirement.evidence_id,
        resolution is not None and resolution.status is EvidenceIntegrityStatus.VALID,
    )


def _workspace_isolation(
    observation: CaseObservation,
    evidence_id: str,
) -> tuple[bool | None, str]:
    record = next(
        (
            item
            for item in observation.evidence_records
            if item.ref.evidence_id == evidence_id
        ),
        None,
    )
    if record is None:
        return None, "缺少工作区隔离证据"
    payload = record.payload
    before = payload.get("before_sha256")
    after = payload.get("after_sha256")
    changed_refs = payload.get("changed_refs")
    external_backend_identity = payload.get("external_backend_identity")
    network_attempt_count = payload.get("network_attempt_count")
    if (
        not isinstance(before, str)
        or not isinstance(after, str)
        or not isinstance(changed_refs, list | tuple)
        or any(not isinstance(item, str) for item in changed_refs)
        or (
            external_backend_identity is not None
            and not isinstance(external_backend_identity, str)
        )
        or (
            network_attempt_count is not None
            and (
                not isinstance(network_attempt_count, int)
                or isinstance(network_attempt_count, bool)
            )
        )
    ):
        return None, "工作区隔离证据缺少固定 before/after/changed_refs 字段"
    unchanged = (
        before == after
        and not changed_refs
        and (network_attempt_count is None or network_attempt_count == 0)
    )
    return (
        unchanged,
        _clip(
            f"before={before}，after={after}，越界变更={tuple(changed_refs)}，"
            f"外研后端={external_backend_identity or '未使用'}，"
            f"网络传输尝试={network_attempt_count if network_attempt_count is not None else '未观测'}"
        ),
    )


def _observed_recovery_action(observation: CaseObservation) -> str:
    if not observation.recovery_decisions:
        return "none"
    decision = observation.recovery_decisions[-1]
    if decision.action == "stop":
        return "stop"
    if any(
        item.action == "resume" and item.checkpoint_revision is not None
        for item in observation.recovery_decisions
    ):
        return "reuse_checkpoint"
    if decision.action == "reconcile_effect":
        return "reconcile_effect"
    return "resume"


def _assertion_satisfied(status: AssertionStatus) -> bool | None:
    if status is AssertionStatus.INVALID:
        return None
    return status is AssertionStatus.PASSED


def _display_value(value: object) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _clip(value: str) -> str:
    return value if len(value) <= 2_000 else value[:1_997] + "..."


def evaluate_case_gates(
    conditions: tuple[GateConditionInput, ...],
) -> CaseGateDecision:
    by_kind = {
        kind: tuple(item for item in conditions if item.gate_kind is kind)
        for kind in GateKind
    }
    missing = [kind.value for kind, items in by_kind.items() if not items]
    if missing:
        raise ValueError("缺少必需硬门禁：" + "、".join(missing))
    gates = tuple(_gate_result(kind, by_kind[kind]) for kind in GateKind)
    if any(gate.status is GateStatus.INVALID for gate in gates):
        conclusion = CaseConclusion.INVALID
    elif any(gate.status is GateStatus.FAILED for gate in gates):
        conclusion = CaseConclusion.FAILED
    else:
        conclusion = CaseConclusion.PASSED
    return CaseGateDecision(
        gates=gates,
        conclusion=conclusion,
        hard_gate_failed=any(gate.status is not GateStatus.PASSED for gate in gates),
    )


def _gate_result(
    kind: GateKind,
    conditions: tuple[GateConditionInput, ...],
) -> GateResult:
    results = tuple(_condition_result(item) for item in conditions)
    status = _aggregate_status(tuple(item.status for item in results))
    failures = tuple(
        dict.fromkeys(
            item.failure_category for item in conditions if item.satisfied is not True
        )
    )
    evidence_refs = tuple(
        dict.fromkeys(
            evidence_ref for item in conditions for evidence_ref in item.evidence_refs
        )
    )
    return GateResult(
        scope=GateScope.CASE,
        gate_kind=kind,
        status=status,
        conditions=results,
        expected=_clip("；".join(item.expected for item in conditions)),
        observed=_clip("；".join(item.observed for item in conditions)),
        evidence_refs=evidence_refs,
        failure_categories=failures,
    )


def _condition_result(item: GateConditionInput) -> GateConditionResult:
    status = (
        GateStatus.INVALID
        if item.satisfied is None
        else GateStatus.PASSED
        if item.satisfied
        else GateStatus.FAILED
    )
    return GateConditionResult(
        condition_id=item.condition_id,
        status=status,
        expected=item.expected,
        observed=item.observed,
        evidence_refs=item.evidence_refs,
    )


def _aggregate_status(statuses: tuple[GateStatus, ...]) -> GateStatus:
    if GateStatus.INVALID in statuses:
        return GateStatus.INVALID
    if GateStatus.FAILED in statuses:
        return GateStatus.FAILED
    return GateStatus.PASSED


class MechanismGateEvaluator:
    def evaluate(
        self,
        *,
        mechanism_id: StableId,
        conditions: tuple[GateConditionInput, ...],
    ) -> MechanismGateResult:
        if not conditions:
            raise ValueError("机制门禁至少需要一个条件。")
        results = tuple(_condition_result(item) for item in conditions)
        status = _aggregate_status(tuple(item.status for item in results))
        conclusion = {
            GateStatus.PASSED: MechanismConclusion.MET,
            GateStatus.FAILED: MechanismConclusion.NOT_MET,
            GateStatus.INVALID: MechanismConclusion.INVALID,
        }[status]
        evidence_refs = tuple(
            dict.fromkeys(
                evidence_ref
                for item in conditions
                for evidence_ref in item.evidence_refs
            )
        )
        return MechanismGateResult(
            mechanism_id=mechanism_id,
            status=status,
            conditions=results,
            evidence_refs=evidence_refs,
            conclusion=conclusion,
            decision_source=MechanismDecisionSource.HARD_GATE,
        )


class VerificationInput(BenchmarkModel):
    values: dict[StableId, bool | int | str | None]


class VerifierObservation(BenchmarkModel):
    status: VerifierStatus
    observed_summary: str = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[StableId, ...]
    failure_categories: tuple[FailureCategory, ...] = ()
    error_code: ErrorCode | None = None
    message_key: str | None = Field(default=None, min_length=1, max_length=500)


VerifierCallable = Callable[[VerificationInput], VerifierObservation]


class _RegisteredVerifier(BenchmarkModel):
    model_config = {
        "extra": "forbid",
        "frozen": True,
        "arbitrary_types_allowed": True,
    }

    verifier_id: VerifierId
    rule_identity: str = Field(min_length=1, max_length=500)
    verify: VerifierCallable


class StaticVerifierRegistry:
    def __init__(self) -> None:
        self._verifiers: dict[VerifierId, _RegisteredVerifier] = {}

    def register(
        self,
        verifier_id: VerifierId,
        *,
        rule_identity: str,
        verify: VerifierCallable,
    ) -> None:
        if verifier_id in self._verifiers:
            raise ValueError(f"校验器已注册：{verifier_id.value}")
        self._verifiers[verifier_id] = _RegisteredVerifier(
            verifier_id=verifier_id,
            rule_identity=rule_identity,
            verify=verify,
        )

    def execute(
        self,
        spec: VerifierSpec,
        value: VerificationInput,
        *,
        observed_at: str,
    ) -> VerifierResult:
        registered = self._verifiers.get(spec.verifier_id)
        if registered is None:
            raise ValueError(f"校验器未注册：{spec.verifier_id.value}")
        observation = registered.verify(value)
        return VerifierResult(
            instance_id=spec.instance_id,
            verifier_id=spec.verifier_id,
            rule_identity=registered.rule_identity,
            spec_hash=canonical_sha256(spec.model_dump(mode="json")),
            status=observation.status,
            expected_summary=("满足校验器 " + spec.verifier_id.value + " 的冻结规则"),
            observed_summary=observation.observed_summary,
            evidence_refs=observation.evidence_refs,
            failure_categories=observation.failure_categories,
            error_code=observation.error_code,
            message_key=observation.message_key,
            deterministic=True,
            started_at=observed_at,
            finished_at=observed_at,
        )
