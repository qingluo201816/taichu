"""全量 deterministic synthetic 套件执行与严格门禁聚合。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.assertion_context import (
    build_runtime_assertion_context,
)
from taichu.application.evaluations.general_agent_benchmark.gates import (
    CaseGateDecision,
    GateConditionInput,
    build_typed_case_gate_decision,
    evaluate_case_gates,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CapabilityCatalogSnapshot,
    CapabilityKind,
    CaseConclusion,
    FailureCategory,
    GateKind,
    GateResult,
    StableId,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceOwner,
    ObservedHumanDecision,
    ObservedInvocation,
    ObservedInvocationIdentity,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    AssertionResult,
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.runtime_observer import (
    RuntimeObservationFacts,
    project_runtime_case_observation,
)
from taichu.application.evaluations.general_agent_benchmark.run_lineage import (
    CapturedRunLineage,
)
from taichu.application.evaluations.general_agent_benchmark.selection import (
    SelectionError,
    SuiteSelectionValidator,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ObservedInteraction,
    StrictScriptedDriver,
    SyntheticNormalizationArtifact,
    SyntheticProtocolError,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    AuthoredSuiteSpec,
    RequiredInvocationSpec,
)
from taichu.application.general_agent.models import GeneralAgentRun


class RuntimeInteractionRecord(BenchmarkModel):
    """由真实 Runtime wrapper 产生的一次交互，能力交互必须带真实身份。"""

    interaction: ObservedInteraction
    call_id: str | None = Field(default=None, min_length=1)
    handler_identity: str | None = Field(default=None, min_length=1)
    parent_call_id: str | None = Field(default=None, min_length=1)
    run_id: str | None = Field(default=None, min_length=1)
    node_id: str | None = Field(default=None, min_length=1)
    request_payload: dict[str, object] | None = None
    response_payload: dict[str, object] | None = None
    source_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    started_at: str | None = Field(default=None, min_length=1)
    finished_at: str | None = Field(default=None, min_length=1)
    human_request_id: str | None = Field(default=None, min_length=1, max_length=128)
    human_request_kind: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    human_tool_name: str | None = Field(default=None, min_length=1, max_length=128)
    human_input_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    human_resource_scopes: tuple[str, ...] = ()
    human_second_confirmation_required: bool = False
    human_approved: bool | None = None
    human_second_confirmation: bool = False
    human_request_created_at: str | None = Field(default=None, min_length=1)


class SyntheticCaseObservation(BenchmarkModel):
    """案例 Runtime 停止后交给评测 runner 的只读观察。"""

    interactions: tuple[RuntimeInteractionRecord, ...]
    case_execution_id: str | None = Field(
        default=None,
        pattern=r"^benchmark_case_[a-f0-9]{32}$",
    )
    fixture_snapshot_id: str | None = Field(
        default=None,
        pattern=r"^fixture_[a-f0-9]{64}$",
    )
    run: GeneralAgentRun | None = None
    run_lineage: CapturedRunLineage | None = None
    runtime_facts: RuntimeObservationFacts | None = None
    assertion_context: AssertionEvaluationContext | None = None
    normalized_result: object


class SyntheticRuntimePort(Protocol):
    async def execute(
        self,
        case: AuthoredCaseSpec,
    ) -> SyntheticCaseObservation: ...


class SyntheticCapabilityInvocation(BenchmarkModel):
    kind: CapabilityKind
    capability_name: StableId
    call_id: str = Field(min_length=1)
    handler_identity: str = Field(min_length=1)
    outcome: str = Field(min_length=1)


class SyntheticCaseBaselineResult(BenchmarkModel):
    case_id: StableId
    conclusion: CaseConclusion
    invocations: tuple[SyntheticCapabilityInvocation, ...]
    gates: tuple[GateResult, ...]
    assertions: tuple[AssertionResult, ...] = ()
    case_observation: CaseObservation | None = None
    observation_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    evidence_ids: tuple[StableId, ...] = ()
    normalization_artifact: SyntheticNormalizationArtifact | None
    protocol_error_code: str | None = None
    problems: tuple[str, ...] = ()


class SyntheticSuiteBaselineResult(BenchmarkModel):
    suite_id: StableId
    suite_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_config_identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    cases: tuple[SyntheticCaseBaselineResult, ...]
    case_count: int = Field(ge=0)
    passed_case_count: int = Field(ge=0)
    failed_case_count: int = Field(ge=0)
    complete: bool
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    stable_result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SyntheticSuiteRunner:
    """逐案运行且永不因单案失败跳过后续案例。"""

    def __init__(
        self,
        *,
        runtime: SyntheticRuntimePort,
        runtime_config_identity: str,
        capability_catalog: CapabilityCatalogSnapshot,
        oracle: TypedOracle | None = None,
        track: TrackKind = TrackKind.SYNTHETIC,
    ) -> None:
        if len(runtime_config_identity) != 64 or any(
            character not in "0123456789abcdef" for character in runtime_config_identity
        ):
            raise ValueError("runtime_config_identity 必须是 SHA-256。")
        self._runtime = runtime
        self._runtime_config_identity = runtime_config_identity
        self._oracle = oracle
        self._track = track
        self._capability_handlers = {
            (item.kind, item.capability_id): item.handler_identity
            for item in capability_catalog.tools + capability_catalog.subagents
        }

    async def run(
        self,
        suite: AuthoredSuiteSpec,
        *,
        requested_case_ids: Iterable[str] | None = None,
    ) -> SyntheticSuiteBaselineResult | SelectionError:
        selection = SuiteSelectionValidator.validate(
            suite,
            self._track,
            requested_case_ids,
        )
        if isinstance(selection, SelectionError):
            return selection
        cases: list[SyntheticCaseBaselineResult] = []
        for case in selection.cases:
            cases.append(await self._run_case(suite, case))
        frozen_cases = tuple(cases)
        passed = sum(item.conclusion is CaseConclusion.PASSED for item in frozen_cases)
        payload = {
            "suite_id": suite.suite_id,
            "suite_content_hash": suite.content_hash,
            "runtime_config_identity": self._runtime_config_identity,
            "cases": [item.model_dump(mode="json") for item in frozen_cases],
        }
        stable_payload = {
            "suite_id": suite.suite_id,
            "suite_content_hash": suite.content_hash,
            "runtime_config_identity": self._runtime_config_identity,
            "cases": [_stable_case_result_payload(item) for item in frozen_cases],
        }
        return SyntheticSuiteBaselineResult(
            **payload,
            case_count=selection.case_count,
            passed_case_count=passed,
            failed_case_count=selection.case_count - passed,
            complete=(
                selection.complete_admission
                and len(frozen_cases) == selection.case_count
                and passed == selection.case_count
            ),
            result_hash=canonical_sha256(payload),
            stable_result_hash=canonical_sha256(stable_payload),
        )

    async def _run_case(
        self,
        suite: AuthoredSuiteSpec,
        case: AuthoredCaseSpec,
    ) -> SyntheticCaseBaselineResult:
        try:
            observation = await self._runtime.execute(case)
        except Exception as error:
            return _runtime_error_result(case, error)

        driver = StrictScriptedDriver(case.scripted_steps)
        invocations: list[SyntheticCapabilityInvocation] = []
        try:
            for record in observation.interactions:
                driver.observe(record.interaction)
                capability = self._capability_invocation(record)
                if capability is not None:
                    invocations.append(capability)
            normalization = driver.finalize(
                script_identity=canonical_sha256(
                    [step.model_dump(mode="json") for step in case.scripted_steps]
                ),
                runtime_config_identity=self._runtime_config_identity,
                normalized_result=observation.normalized_result,
            )
        except SyntheticProtocolError as error:
            return _protocol_error_result(
                case,
                tuple(invocations),
                error,
            )
        except ValueError as error:
            return _invalid_observation_result(
                case,
                tuple(invocations),
                str(error),
            )

        invocation_problems = _invocation_problems(
            case.required_invocations,
            tuple(invocations),
            scripted_capabilities=frozenset(
                (
                    CapabilityKind(step.kind.value),
                    step.name,
                )
                for step in case.scripted_steps
                if step.kind in {InteractionKind.TOOL, InteractionKind.SUBAGENT}
            ),
        )
        typed = self.evaluate_runtime_observation(
            suite=suite,
            case=case,
            runtime_observation=observation,
            invocation_problems=invocation_problems,
        )
        if isinstance(typed, SyntheticCaseBaselineResult):
            return typed
        decision, assertions, case_observation = typed
        return SyntheticCaseBaselineResult(
            case_id=case.case_id,
            conclusion=decision.conclusion,
            invocations=tuple(invocations),
            gates=decision.gates,
            assertions=assertions,
            case_observation=case_observation,
            observation_sha256=case_observation.observation_sha256,
            evidence_ids=tuple(
                record.ref.evidence_id
                for record in case_observation.evidence_records
            ),
            normalization_artifact=normalization,
            problems=invocation_problems,
        )

    def evaluate_runtime_observation(
        self,
        *,
        suite: AuthoredSuiteSpec,
        case: AuthoredCaseSpec,
        runtime_observation: SyntheticCaseObservation,
        invocation_problems: tuple[str, ...],
    ) -> (
        tuple[
            CaseGateDecision,
            tuple[AssertionResult, ...],
            CaseObservation,
        ]
        | SyntheticCaseBaselineResult
    ):
        if self._oracle is None:
            return _typed_observation_missing_result(
                case,
                "typed_oracle_missing",
            )
        if (
            runtime_observation.run is None
            or runtime_observation.runtime_facts is None
            or runtime_observation.case_execution_id is None
            or runtime_observation.fixture_snapshot_id is None
        ):
            return _typed_observation_missing_result(
                case,
                "runtime_typed_observation_missing",
            )
        if runtime_observation.fixture_snapshot_id != suite.fixture.snapshot_id:
            return _typed_observation_missing_result(
                case,
                "runtime_fixture_identity_mismatch",
            )
        projected_invocations = project_observed_invocations(
            runtime_observation.interactions
        )
        if projected_invocations != runtime_observation.runtime_facts.invocations:
            return _typed_observation_missing_result(
                case,
                "runtime_invocation_projection_mismatch",
            )
        projected_identities = project_invocation_identities(
            runtime_observation.interactions
        )
        if (
            projected_identities
            != runtime_observation.runtime_facts.invocation_identities
        ):
            return _typed_observation_missing_result(
                case,
                "runtime_invocation_identity_projection_mismatch",
            )
        projected_human_decisions = project_observed_human_decisions(
            runtime_observation.interactions
        )
        if (
            projected_human_decisions
            != runtime_observation.runtime_facts.human_decisions
        ):
            return _typed_observation_missing_result(
                case,
                "runtime_human_decision_projection_mismatch",
            )
        script_facts = runtime_observation.runtime_facts.script_consumption
        facts = runtime_observation.runtime_facts.model_copy(
            update={
                "script_consumption": script_facts.model_copy(
                    update={
                        "deviations": (
                            *script_facts.deviations,
                            *invocation_problems,
                        )
                    }
                )
            }
        )
        owner = EvidenceOwner(
            suite_id=suite.suite_id,
            suite_content_hash=suite.content_hash,
            case_id=case.case_id,
            case_execution_id=runtime_observation.case_execution_id,
            run_id=runtime_observation.run.run_id,
            entry_run_id=(
                runtime_observation.run_lineage.entry_run_id
                if runtime_observation.run_lineage is not None
                else None
            ),
            lineage_run_ids=(
                runtime_observation.run_lineage.lineage_run_ids
                if runtime_observation.run_lineage is not None
                else ()
            ),
            track=self._track,
            fixture_snapshot_id=runtime_observation.fixture_snapshot_id,
        )
        case_observation = project_runtime_case_observation(
            case=case,
            owner=owner,
            run=runtime_observation.run,
            facts=facts,
            lineage=runtime_observation.run_lineage,
        )
        assertion_context = build_runtime_assertion_context(
            case=case,
            run=runtime_observation.run,
            runs=(
                runtime_observation.run_lineage.runs
                if runtime_observation.run_lineage is not None
                else None
            ),
            invocations=facts.invocations,
            invocation_identities=facts.invocation_identities,
            human_decisions=facts.human_decisions,
            effects=facts.effects,
            resource_snapshots=facts.resource_snapshots,
            base=runtime_observation.assertion_context,
        )
        assertions = self._oracle.evaluate_case(
            case,
            case_observation,
            context=assertion_context,
        )
        decision = build_typed_case_gate_decision(
            case=case,
            observation=case_observation,
            assertion_results=assertions,
        )
        return (
            decision,
            assertions,
            case_observation,
        )

    def _capability_invocation(
        self,
        record: RuntimeInteractionRecord,
    ) -> SyntheticCapabilityInvocation | None:
        capability = _capability_invocation(record)
        if capability is None:
            return None
        expected_handler = self._capability_handlers.get(
            (capability.kind, capability.capability_name)
        )
        if expected_handler is None:
            raise ValueError(
                "Runtime 观察包含生产能力目录之外的调用："
                f"{capability.kind.value}:{capability.capability_name}"
            )
        if capability.handler_identity != expected_handler:
            raise ValueError(
                "能力 handler_identity 与冻结生产目录不一致："
                f"{capability.kind.value}:{capability.capability_name}"
            )
        return capability


def project_observed_invocations(
    records: tuple[RuntimeInteractionRecord, ...],
) -> tuple[ObservedInvocation, ...]:
    """把真实能力 wrapper 记录投影为 Typed Oracle 的调用事实。"""

    projected: list[ObservedInvocation] = []
    for sequence, record in enumerate(records):
        if record.interaction.kind not in {
            InteractionKind.TOOL,
            InteractionKind.SUBAGENT,
        }:
            continue
        if (
            record.call_id is None
            or record.handler_identity is None
            or record.request_payload is None
        ):
            raise ValueError(
                "能力交互缺少调用身份、Handler 身份或真实输入，不能构建行为证据。"
            )
        if (
            record.interaction.outcome == "completed"
            and record.response_payload is None
        ):
            raise ValueError("成功能力交互缺少真实输出，不能构建数据流证据。")
        projected.append(
            ObservedInvocation(
                call_id=record.call_id,
                sequence=sequence,
                parent_call_id=record.parent_call_id,
                run_id=record.run_id,
                node_id=record.node_id,
                capability_kind=record.interaction.kind.value,
                capability_name=record.interaction.name,
                status=record.interaction.outcome,
                input_sha256=canonical_sha256(record.request_payload),
                output_sha256=(
                    canonical_sha256(record.response_payload)
                    if record.response_payload is not None
                    else None
                ),
                source_refs=record.source_refs,
                artifact_refs=record.artifact_refs,
                started_at=record.started_at,
                finished_at=record.finished_at,
            )
        )
    return tuple(projected)


def project_observed_human_decisions(
    records: tuple[RuntimeInteractionRecord, ...],
) -> tuple[ObservedHumanDecision, ...]:
    """只接受带真实 Runtime 人工请求身份的已提交决定。"""

    projected: list[ObservedHumanDecision] = []
    for record in records:
        if record.interaction.kind is not InteractionKind.HUMAN:
            continue
        if (
            record.run_id is None
            or record.human_request_id is None
            or record.human_request_kind is None
            or record.human_approved is None
            or record.human_request_created_at is None
        ):
            raise ValueError("人工交互缺少真实请求身份或实际决定，不能构建授权证据。")
        if record.interaction.name != record.human_request_kind:
            raise ValueError("人工交互名称与 Runtime 请求类型不一致。")
        projected.append(
            ObservedHumanDecision(
                source_run_id=record.run_id,
                request_id=record.human_request_id,
                request_kind=record.human_request_kind,
                node_id=record.node_id,
                tool_name=record.human_tool_name,
                input_sha256=record.human_input_sha256,
                resource_scopes=record.human_resource_scopes,
                second_confirmation_required=(
                    record.human_second_confirmation_required
                ),
                approved=record.human_approved,
                second_confirmation=record.human_second_confirmation,
                request_created_at=record.human_request_created_at,
            )
        )
    return tuple(projected)


_INVOCATION_IDENTITY_PATHS: dict[
    tuple[str, str, str],
    str,
] = {
    (
        "preview_manuscript_patch",
        "output",
        "preview_sha256",
    ): "expected_content_sha256",
    (
        "apply_manuscript_patch",
        "input",
        "preview_sha256",
    ): "expected_content_sha256",
    (
        "create_novel_structure_items",
        "output",
        "resource_id",
    ): "changes.*.item_id",
    (
        "update_novel_structure",
        "input",
        "resource_id",
    ): "operations.*.target_id",
    (
        "create_novel_structure_items",
        "output",
        "revision",
    ): "structure_version",
    (
        "update_novel_structure",
        "input",
        "revision",
    ): "expected_structure_version",
    (
        "create_confirmed_knowledge",
        "output",
        "resource_id",
    ): "card.id",
    (
        "update_confirmed_knowledge",
        "input",
        "resource_id",
    ): "card_id",
    (
        "create_confirmed_knowledge",
        "output",
        "revision",
    ): "card.updated_at",
    (
        "update_confirmed_knowledge",
        "input",
        "revision",
    ): "expected_updated_at",
}


def project_invocation_identities(
    records: tuple[RuntimeInteractionRecord, ...],
) -> tuple[ObservedInvocationIdentity, ...]:
    """按生产能力稳定 payload 字段提取最小身份，不复制整包内容。"""

    projected: list[ObservedInvocationIdentity] = []
    for record in records:
        if record.call_id is None:
            continue
        for (capability, direction, identity_field), path in (
            _INVOCATION_IDENTITY_PATHS.items()
        ):
            if record.interaction.name != capability:
                continue
            payload = (
                record.request_payload
                if direction == "input"
                else record.response_payload
            )
            if payload is None:
                continue
            values = tuple(dict.fromkeys(_read_identity_values(payload, path)))
            if len(values) != 1:
                continue
            projected.append(
                ObservedInvocationIdentity(
                    call_id=record.call_id,
                    capability_name=capability,
                    direction=direction,
                    identity_field=identity_field,
                    selector_path=path,
                    identity=values[0],
                    payload_sha256=canonical_sha256(payload),
                )
            )
    return tuple(projected)


def _read_identity_values(payload: object, path: str) -> tuple[str, ...]:
    current: tuple[object, ...] = (payload,)
    for part in path.split("."):
        next_values: list[object] = []
        for value in current:
            if part == "*" and isinstance(value, list):
                next_values.extend(value)
            elif isinstance(value, dict) and part in value:
                next_values.append(value[part])
        current = tuple(next_values)
    return tuple(
        value
        for value in current
        if isinstance(value, str) and value
    )


def _capability_invocation(
    record: RuntimeInteractionRecord,
) -> SyntheticCapabilityInvocation | None:
    kind = record.interaction.kind
    if kind not in {InteractionKind.TOOL, InteractionKind.SUBAGENT}:
        return None
    if record.call_id is None or record.handler_identity is None:
        raise ValueError("能力交互缺少真实 call_id 或 handler_identity，不能计入覆盖。")
    return SyntheticCapabilityInvocation(
        kind=CapabilityKind(kind.value),
        capability_name=record.interaction.name,
        call_id=record.call_id,
        handler_identity=record.handler_identity,
        outcome=record.interaction.outcome,
    )


def _stable_case_result_payload(
    result: SyntheticCaseBaselineResult,
) -> dict[str, object]:
    """排除调用身份与并行完成次序，只保留可跨隔离运行比较的权威语义。"""
    return {
        "case_id": result.case_id,
        "conclusion": result.conclusion.value,
        "invocations": sorted(
            (
                invocation.kind.value,
                invocation.capability_name,
                invocation.handler_identity,
                invocation.outcome,
            )
            for invocation in result.invocations
        ),
        "gates": [
            {
                "kind": gate.gate_kind.value,
                "status": gate.status.value,
                "condition_ids": [
                    condition.condition_id for condition in gate.conditions
                ],
                "failure_categories": [
                    category.value for category in gate.failure_categories
                ],
            }
            for gate in result.gates
        ],
        "normalization_hash": (
            result.normalization_artifact.normalization_hash
            if result.normalization_artifact is not None
            else None
        ),
        "protocol_error_code": result.protocol_error_code,
        "problems": result.problems,
    }


def _invocation_problems(
    expected: tuple[RequiredInvocationSpec, ...],
    observed: tuple[SyntheticCapabilityInvocation, ...],
    *,
    scripted_capabilities: frozenset[tuple[CapabilityKind, str]] = frozenset(),
) -> tuple[str, ...]:
    problems: list[str] = []
    expected_keys = {(item.type, item.name) for item in expected}
    observed_keys = {(item.kind, item.capability_name) for item in observed}
    for item in expected:
        matching = tuple(
            invocation
            for invocation in observed
            if invocation.kind is item.type and invocation.capability_name == item.name
        )
        if not item.min_calls <= len(matching) <= item.max_calls:
            problems.append(
                f"{item.type.value}:{item.name} 调用次数 {len(matching)}"
                f" 不在 {item.min_calls}..{item.max_calls}"
            )
        if any(invocation.outcome != item.expected_outcome for invocation in matching):
            problems.append(
                f"{item.type.value}:{item.name} outcome 不符合 {item.expected_outcome}"
            )
    auxiliary = tuple(
        invocation
        for invocation in observed
        if (invocation.kind, invocation.capability_name)
        in scripted_capabilities - expected_keys
    )
    if any(invocation.outcome != "completed" for invocation in auxiliary):
        problems.append("脚本辅助能力存在非 completed outcome")
    unexpected = sorted(
        f"{kind.value}:{name}"
        for kind, name in (observed_keys - expected_keys - scripted_capabilities)
    )
    if unexpected:
        problems.append("出现未声明能力调用：" + "、".join(unexpected))
    return tuple(problems)


def _runtime_error_result(
    case: AuthoredCaseSpec,
    error: Exception,
) -> SyntheticCaseBaselineResult:
    problem = f"runtime_error:{type(error).__name__}"
    return SyntheticCaseBaselineResult(
        case_id=case.case_id,
        conclusion=CaseConclusion.INVALID,
        invocations=(),
        gates=_invalid_six_gates(
            condition_prefix="runtime_error",
            observed=problem,
            failure_category=FailureCategory.EXECUTION_ERROR,
        ),
        normalization_artifact=None,
        problems=(problem,),
    )


def _typed_observation_missing_result(
    case: AuthoredCaseSpec,
    problem: str,
) -> SyntheticCaseBaselineResult:
    return SyntheticCaseBaselineResult(
        case_id=case.case_id,
        conclusion=CaseConclusion.INVALID,
        invocations=(),
        gates=_invalid_six_gates(
            condition_prefix="typed_observation",
            observed=problem,
            failure_category=FailureCategory.BENCHMARK_INVALID,
        ),
        normalization_artifact=None,
        problems=(problem,),
    )


def _invalid_six_gates(
    *,
    condition_prefix: str,
    observed: str,
    failure_category: FailureCategory,
) -> tuple[GateResult, ...]:
    """异常案例仍显式输出完整六门禁，禁止用空集合掩盖未执行。"""

    decision = evaluate_case_gates(
        tuple(
            GateConditionInput(
                gate_kind=kind,
                condition_id=f"{condition_prefix}_{kind.value}",
                satisfied=None,
                expected="案例必须形成可校验的真实 Runtime 观察",
                observed=observed,
                evidence_refs=(),
                failure_category=failure_category,
            )
            for kind in GateKind
        )
    )
    return decision.gates


def _protocol_error_result(
    case: AuthoredCaseSpec,
    invocations: tuple[SyntheticCapabilityInvocation, ...],
    error: SyntheticProtocolError,
) -> SyntheticCaseBaselineResult:
    return SyntheticCaseBaselineResult(
        case_id=case.case_id,
        conclusion=CaseConclusion.INVALID,
        invocations=invocations,
        gates=_invalid_six_gates(
            condition_prefix="synthetic_protocol",
            observed=error.evidence.error_code,
            failure_category=FailureCategory.BENCHMARK_INVALID,
        ),
        normalization_artifact=None,
        protocol_error_code=error.evidence.error_code,
        problems=(error.evidence.error_code,),
    )


def _invalid_observation_result(
    case: AuthoredCaseSpec,
    invocations: tuple[SyntheticCapabilityInvocation, ...],
    problem: str,
) -> SyntheticCaseBaselineResult:
    return SyntheticCaseBaselineResult(
        case_id=case.case_id,
        conclusion=CaseConclusion.INVALID,
        invocations=invocations,
        gates=_invalid_six_gates(
            condition_prefix="runtime_interaction_identity",
            observed=problem,
            failure_category=FailureCategory.EVIDENCE_INCOMPLETE,
        ),
        normalization_artifact=None,
        problems=(problem,),
    )
