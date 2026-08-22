"""从真实 Runtime 后态构建可供 Typed Oracle 判定的案例观察。"""

from __future__ import annotations

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.assertion_context import (
    final_answer_provenance_refs,
)
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceKind,
    EvidenceOwner,
    EvidenceRecord,
    EvidenceRef,
    EvidenceSelector,
    ObservedArtifact,
    ObservedBudgetUsage,
    ObservedEffect,
    ObservedFinalAnswer,
    ObservedHumanDecision,
    ObservedInvocation,
    ObservedInvocationIdentity,
    ObservedNode,
    ObservedRecoveryDecision,
    ObservedResourceSnapshot,
    ObservedTerminalState,
    build_case_observation,
)
from taichu.application.general_agent.recovery import EffectRecord
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
)
from taichu.application.evaluations.general_agent_benchmark.run_lineage import (
    CapturedRunLineage,
)
from taichu.application.general_agent.models import GeneralAgentRun


class RuntimeUsageFacts(BenchmarkModel):
    """Runtime 与网关实际计量，不接受“是否超预算”之类结论字段。"""

    model_calls: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    runtime_ms: int = Field(ge=0)
    context_tokens: int = Field(ge=0)


class FixtureIsolationFacts(BenchmarkModel):
    """受保护夹具/作者活动事实执行前后的只读身份。"""

    before_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    after_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    changed_refs: tuple[str, ...] = ()
    external_backend_identity: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
    )
    network_attempt_count: int | None = Field(default=None, ge=0)


class ScriptConsumptionFacts(BenchmarkModel):
    """Strict Driver 的实际消费计量与协议偏差。"""

    declared_step_count: int = Field(ge=0)
    consumed_step_count: int = Field(ge=0)
    observed_interaction_count: int = Field(ge=0)
    deviations: tuple[str, ...] = ()


class RuntimeObservationFacts(BenchmarkModel):
    """Observer 已解析的窄事实；所有通过/失败均由 Oracle 与 Gate 派生。"""

    invocations: tuple[ObservedInvocation, ...]
    invocation_identities: tuple[ObservedInvocationIdentity, ...] = ()
    human_decisions: tuple[ObservedHumanDecision, ...] = ()
    effects: tuple[ObservedEffect, ...] = ()
    artifacts: tuple[ObservedArtifact, ...] = ()
    resource_snapshots: tuple[ObservedResourceSnapshot, ...] = ()
    recovery_decisions: tuple[ObservedRecoveryDecision, ...] = ()
    terminal: ObservedTerminalState
    usage: RuntimeUsageFacts
    fixture_isolation: FixtureIsolationFacts
    script_consumption: ScriptConsumptionFacts


def project_runtime_case_observation(
    *,
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
    run: GeneralAgentRun,
    facts: RuntimeObservationFacts,
    lineage: CapturedRunLineage | None = None,
) -> CaseObservation:
    """把真实运行后态投影为同 owner、内容寻址的最小观察。"""

    if owner.run_id != run.run_id:
        raise ValueError("案例观察 owner.run_id 与真实 Runtime run 不一致。")
    runs = lineage.runs if lineage is not None else (run,)
    entry_run = runs[0]
    if lineage is not None:
        if lineage.terminal_run_id != run.run_id:
            raise ValueError("案例观察的末尾 run 与真实运行谱系不一致。")
        if owner.entry_run_id != lineage.entry_run_id or (
            owner.lineage_run_ids != lineage.lineage_run_ids
        ):
            raise ValueError("案例观察 owner 与真实运行谱系不一致。")
    if entry_run.user_goal != case.user_request_raw:
        raise ValueError("真实 Runtime 未保留案例当前请求原文。")

    nodes = tuple(
        ObservedNode(
            run_id=source_run.run_id,
            node_id=item.node_id,
            plan_revision=item.plan_revision,
            capability_kind=item.kind.value,
            capability_name=item.capability_name,
            status=item.status.value,
            dependencies=tuple(item.dependencies),
            input_sha256=canonical_sha256(item.resolved_input),
            output_sha256=canonical_sha256(item.output),
            started_at=item.started_at,
            finished_at=item.finished_at,
        )
        for source_run in runs
        for item in source_run.node_runs
    )
    final_answer = (
        ObservedFinalAnswer.create(
            text=run.final_answer,
            source_refs=final_answer_provenance_refs(run),
        )
        if run.final_answer.strip()
        else None
    )
    budget = ObservedBudgetUsage(
        node_executions=sum(len(item.node_runs) for item in runs),
        replans=sum(item.replan_count for item in runs),
        capability_calls=len(facts.invocations),
        model_calls=facts.usage.model_calls,
        total_tokens=facts.usage.total_tokens,
        runtime_ms=facts.usage.runtime_ms,
        context_tokens=facts.usage.context_tokens,
    )
    plan = run.plan.model_dump(mode="json") if run.plan is not None else None
    records = _evidence_records(
        case=case,
        owner=owner,
        plan=plan,
        nodes=nodes,
        final_answer=final_answer,
        budget=budget,
        facts=facts,
    )
    return build_case_observation(
        case=case,
        owner=owner,
        user_request_raw=entry_run.user_goal,
        plan=plan,
        nodes=nodes,
        invocations=facts.invocations,
        final_answer=final_answer,
        artifacts=facts.artifacts,
        resource_snapshots=facts.resource_snapshots,
        recovery_decisions=facts.recovery_decisions,
        terminal=facts.terminal,
        budget=budget,
        script_protocol_deviations=facts.script_consumption.deviations,
        evidence_records=records,
    )


def project_observed_effects(
    records: tuple[EffectRecord, ...],
) -> tuple[ObservedEffect, ...]:
    """把 append-only Effect 事件收敛成每个 effect_id 的真实最新终态。"""

    grouped: dict[str, list[EffectRecord]] = {}
    for record in records:
        grouped.setdefault(record.effect_id, []).append(record)
    observed: list[ObservedEffect] = []
    for effect_id, events in grouped.items():
        first = events[0]
        immutable_identity = (
            first.run_id,
            first.node_id,
            first.tool_name,
            first.input_sha256,
            tuple(first.resource_scopes),
            first.authorization_reference,
        )
        if any(
            (
                event.run_id,
                event.node_id,
                event.tool_name,
                event.input_sha256,
                tuple(event.resource_scopes),
                event.authorization_reference,
            )
            != immutable_identity
            for event in events[1:]
        ):
            raise ValueError(f"Effect {effect_id} 的不可变身份发生漂移。")
        latest = events[-1]
        observed.append(
            ObservedEffect(
                effect_id=effect_id,
                run_id=latest.run_id,
                node_id=latest.node_id,
                tool_name=latest.tool_name,
                status=latest.status.value,
                input_sha256=latest.input_sha256,
                resource_scopes=tuple(latest.resource_scopes),
                authorization_reference=latest.authorization_reference,
                output_sha256=canonical_sha256(latest.output),
                evidence_sha256=canonical_sha256(latest.evidence),
            )
        )
    return tuple(observed)


def _evidence_records(
    *,
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
    plan: dict[str, object] | None,
    nodes: tuple[ObservedNode, ...],
    final_answer: ObservedFinalAnswer | None,
    budget: ObservedBudgetUsage,
    facts: RuntimeObservationFacts,
) -> tuple[EvidenceRecord, ...]:
    payloads: dict[tuple[EvidenceKind, EvidenceSelector], dict[str, object]] = {
        (
            EvidenceKind.RUN,
            EvidenceSelector.BUDGET,
        ): budget.model_dump(mode="json"),
        (
            EvidenceKind.RUN,
            EvidenceSelector.STOP_REASON,
        ): facts.terminal.model_dump(mode="json"),
        (
            EvidenceKind.ARTIFACT,
            EvidenceSelector.CONTRACT,
        ): {
            "plan_sha256": canonical_sha256(plan) if plan is not None else None,
            "node_output_sha256": tuple(item.output_sha256 for item in nodes),
            "final_answer_sha256": (
                final_answer.content_sha256 if final_answer is not None else None
            ),
            "artifact_contracts": tuple(
                {
                    "artifact_id": item.artifact_id,
                    "artifact_kind": item.artifact_kind,
                    "content_sha256": item.content_sha256,
                    "producer_node_id": item.producer_node_id,
                }
                for item in facts.artifacts
            ),
            "resource_snapshots": tuple(
                {
                    "snapshot_ref": item.snapshot_ref,
                    "phase": item.phase,
                    "content_sha256": item.content_sha256,
                }
                for item in facts.resource_snapshots
            ),
        },
        (
            EvidenceKind.ARTIFACT,
            EvidenceSelector.IDENTITY,
        ): {
            "final_answer_sha256": (
                final_answer.content_sha256 if final_answer is not None else None
            ),
            "final_answer_source_refs": (
                final_answer.source_refs if final_answer is not None else ()
            ),
            "artifacts": tuple(
                {
                    "artifact_id": item.artifact_id,
                    "artifact_kind": item.artifact_kind,
                    "content_sha256": item.content_sha256,
                    "source_refs": item.source_refs,
                }
                for item in facts.artifacts
            ),
        },
        (
            EvidenceKind.FIXTURE_SENTINEL,
            EvidenceSelector.ISOLATION,
        ): facts.fixture_isolation.model_dump(mode="json"),
        (
            EvidenceKind.SCRIPT_PROTOCOL,
            EvidenceSelector.CONSUMPTION,
        ): facts.script_consumption.model_dump(mode="json"),
    }
    records: list[EvidenceRecord] = []
    for requirement in case.required_evidence:
        key = (
            EvidenceKind(requirement.probe.kind),
            EvidenceSelector(requirement.probe.selector),
        )
        payload = payloads.get(key)
        if payload is None:
            continue
        content_sha256 = canonical_sha256(payload)
        record_identity = canonical_sha256(
            {
                "owner": owner,
                "evidence_id": requirement.evidence_id,
                "kind": key[0],
                "selector": key[1],
                "content_sha256": content_sha256,
            }
        )
        records.append(
            EvidenceRecord(
                ref=EvidenceRef(
                    evidence_id=requirement.evidence_id,
                    kind=key[0],
                    selector=key[1],
                    owner=owner,
                    record_id=f"observation_{record_identity}",
                    content_sha256=content_sha256,
                ),
                payload=payload,
            )
        )
    for effect in facts.effects:
        if effect.status not in {"succeeded", "reconciled"}:
            continue
        payload = effect.model_dump(mode="json")
        content_sha256 = canonical_sha256(payload)
        evidence_id = f"effect_observation_{effect.effect_id.removeprefix('effect_')}"
        record_identity = canonical_sha256(
            {
                "owner": owner,
                "evidence_id": evidence_id,
                "kind": EvidenceKind.EFFECT,
                "selector": EvidenceSelector.OUTCOME,
                "content_sha256": content_sha256,
            }
        )
        records.append(
            EvidenceRecord(
                ref=EvidenceRef(
                    evidence_id=evidence_id,
                    kind=EvidenceKind.EFFECT,
                    selector=EvidenceSelector.OUTCOME,
                    owner=owner,
                    record_id=f"observation_{record_identity}",
                    content_sha256=content_sha256,
                ),
                payload=payload,
            )
        )
    return tuple(records)


__all__ = [
    "FixtureIsolationFacts",
    "RuntimeObservationFacts",
    "RuntimeUsageFacts",
    "ScriptConsumptionFacts",
    "project_observed_effects",
    "project_runtime_case_observation",
]
