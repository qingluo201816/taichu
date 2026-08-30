"""需求 9.1—9.10：上下文压力计划与案例 30—37。"""

from __future__ import annotations

import asyncio
from hashlib import sha256
import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from taichu.application.agent_memory.models import (
    AgentMemoryKind,
    AgentMemoryValidity,
    MemoryWriteCandidate,
)
from taichu.application.evaluations.general_agent_benchmark.pressure import (
    PressureBehaviorArtifact,
    PressureBehaviorEvaluator,
    PressureBehaviorOracle,
    PressureContextPreservationProjector,
    PressureFixtureBlob,
    PressureKind,
    PressureMemoryIsolationProjector,
    PressureMemorySeed,
    PressurePlan,
    PressureResultContractProjector,
    PressureRetrievalFragmentSeed,
    PressureSeed,
    PressureSeedGenerator,
    PressureUnsafeRefusalArtifact,
    PressureUnsafeRefusalProjector,
)
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    ClaimCatalog,
    ClaimNormalizerRef,
    ClaimPolarity,
    ExpectedClaimSpec,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceIntegrityStatus,
    EvidenceOwner,
    ObservedBudgetUsage,
    ObservedFinalAnswer,
    ObservedInvocation,
    ObservedTerminalState,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    AssertionStatus,
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    ContextPreservationAssertionSpec,
    MemoryCarrierAbsenceAssertionSpec,
    ResultContractEquivalenceAssertionSpec,
    ZeroCapabilityOrSideEffectAssertionSpec,
)
from taichu.application.general_agent.context import (
    ContextAssembler,
    ContextAssemblyError,
    ContextCompactor,
    GeneralAgentContextPolicy,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentContextSnapshot,
    GeneralAgentInputBinding,
    GeneralAgentMessage,
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentPlanNode,
    GeneralAgentRun,
    GeneralAgentScope,
)
from taichu.application.services.agent_memory_service import AgentMemoryService
from tests.fakes.agent_memory import in_memory_agent_memory_repository


def _fixture_blob() -> PressureFixtureBlob:
    return PressureFixtureBlob.seal(
        blob_ref="pressure/context-anchor.txt",
        content="灯塔火焰必须始终保持青白色。",
    )


def _plan(
    kind: PressureKind,
    *,
    repetition_count: int = 24,
    unit_size: int = 240,
) -> PressurePlan:
    plan_ids = {
        PressureKind.HISTORY: "pressure_long_history",
        PressureKind.WORKING_MEMORY: "pressure_long_working_memory",
        PressureKind.NODE_OUTPUT: "pressure_large_node_output",
        PressureKind.MULTI_SOURCE: "pressure_multi_source",
        PressureKind.EQUIVALENCE_PAIR: "pressure_equivalence",
        PressureKind.INVALID_MEMORY: "pressure_invalid_memory",
        PressureKind.CURRENT_REQUEST: "pressure_long_current_request",
        PressureKind.UNSAFE_TOTAL: "pressure_unsafe_compression",
    }
    protected_refs = (
        "current_request",
        "fact_lighthouse_flame",
        "stable_rules",
    )
    invalid_refs = (
        ("sentinel_rejected", "sentinel_stale", "sentinel_superseded")
        if kind is PressureKind.INVALID_MEMORY
        else ()
    )
    return PressurePlan.seal(
        plan_id=plan_ids.get(kind, f"pressure_{kind.value}"),
        kind=kind,
        fixture_blob_ref="pressure/context-anchor.txt",
        repetition_count=repetition_count,
        unit_size=unit_size,
        protected_fact_refs=protected_refs,
        invalid_sentinel_refs=invalid_refs,
        paired_case_ref=(
            "context_baseline_pair" if kind is PressureKind.EQUIVALENCE_PAIR else None
        ),
    )


def _generate(
    kind: PressureKind,
    *,
    repetition_count: int = 24,
    unit_size: int = 240,
) -> PressureSeed:
    return PressureSeedGenerator().generate(
        _plan(
            kind,
            repetition_count=repetition_count,
            unit_size=unit_size,
        ),
        _fixture_blob(),
    )


def _memory_service(root: Path) -> AgentMemoryService:
    return AgentMemoryService(
        repository=in_memory_agent_memory_repository(root),
    )


def _base_run(
    seed: PressureSeed,
    *,
    messages: list[GeneralAgentMessage] | None = None,
    plan: GeneralAgentExecutionPlan | None = None,
    node_runs: list[GeneralAgentNodeRun] | None = None,
    verification_issues: list[str] | None = None,
) -> GeneralAgentRun:
    timestamp = "2026-07-30T12:00:00Z"
    return GeneralAgentRun(
        run_id="general_run_20260730_120000_abc123",
        task_id="conversation_context_pressure",
        conversation_id="conversation_context_pressure",
        request_index=50,
        user_goal=seed.current_request,
        author_constraints=list(seed.author_constraints),
        scope=GeneralAgentScope(scope_type="novel"),
        messages=messages or [],
        plan=plan,
        plan_revision=1 if plan is not None else 0,
        node_runs=node_runs or [],
        verification_issues=verification_issues or [],
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp,
    )


def _messages(seed: PressureSeed) -> list[GeneralAgentMessage]:
    return [
        GeneralAgentMessage(
            role=item.role,
            content=item.content,
            created_at=f"2026-07-30T10:{index:02d}:00Z",
        )
        for index, item in enumerate(seed.history_messages)
    ]


async def _write_seed_memories(
    service: AgentMemoryService,
    seed: PressureSeed,
) -> dict[str, str]:
    memory_ids: dict[str, str] = {}
    items: tuple[PressureMemorySeed | PressureRetrievalFragmentSeed, ...] = (
        *seed.working_memories,
        *seed.retrieval_fragments,
    )
    for item in items:
        validity = (
            AgentMemoryValidity(item.validity)
            if isinstance(item, PressureMemorySeed)
            else AgentMemoryValidity.ACTIVE
        )
        entry = await service.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind(item.kind),
                content=item.content,
                source_refs=list(item.source_refs),
                artifact_refs=list(item.artifact_refs),
                run_ids=["run_pressure_seed"],
                conversation_id="conversation_context_pressure",
                created_request_index=1,
                retention_priority=item.retention_priority,
                validity=validity,
                invalidation_reason=(
                    "该压力记忆已由固定夹具标记为失效。"
                    if validity is not AgentMemoryValidity.ACTIVE
                    else ""
                ),
            )
        )
        memory_ids[item.seed_id] = entry.memory_id
    return memory_ids


def _dependency_plan(
    seed: PressureSeed,
) -> tuple[GeneralAgentExecutionPlan, list[GeneralAgentNodeRun]]:
    direct = next(item for item in seed.node_artifacts if item.direct_dependency)
    incidental = [item for item in seed.node_artifacts if not item.direct_dependency]
    source = GeneralAgentPlanNode(
        node_id=direct.node_id,
        kind=GeneralAgentNodeKind.TOOL,
        capability_name="get_novel_structure",
        objective="读取下游消费所需的结构合同。",
    )
    incidental_nodes = [
        GeneralAgentPlanNode(
            node_id=item.node_id,
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="read_manuscript",
            objective=f"读取可在预算压力下退出的旁支资料 {index}。",
        )
        for index, item in enumerate(incidental)
    ]
    consumer = GeneralAgentPlanNode(
        node_id="consume_contract",
        kind=GeneralAgentNodeKind.SUBAGENT,
        capability_name="story_architecture",
        objective="消费直接依赖的结构合同。",
        dependencies=[direct.node_id],
        input_bindings=[
            GeneralAgentInputBinding(
                source_node_id=direct.node_id,
                source_path=direct.required_output_paths[0],
                target_path="structure_items",
            )
        ],
    )
    plan = GeneralAgentExecutionPlan(
        rationale="先读取结构，再消费合同字段。",
        nodes=[*incidental_nodes, source, consumer],
        final_response_guidance="只依据保留下来的直接依赖回答。",
    )
    runs = [
        GeneralAgentNodeRun(
            node_id=item.node_id,
            plan_revision=1,
            kind=GeneralAgentNodeKind.TOOL,
            capability_name=(
                "get_novel_structure" if item.direct_dependency else "read_manuscript"
            ),
            objective=(
                "读取下游消费所需的结构合同。"
                if item.direct_dependency
                else "读取旁支资料。"
            ),
            status=GeneralAgentNodeStatus.SUCCESS,
            output=item.output,
            source_refs=list(item.source_refs),
            artifact_refs=list(item.artifact_refs),
        )
        for item in [*incidental, direct]
    ]
    return plan, runs


def _replace_fixture_text(value: object, fixture_text: str) -> object:
    if isinstance(value, str):
        return value.replace(fixture_text, "中性压力占位内容。")
    if isinstance(value, list):
        return [_replace_fixture_text(item, fixture_text) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_fixture_text(item, fixture_text)
            for key, item in value.items()
        }
    return value


async def _assemble_behavior_case(
    root: Path,
    kind: PressureKind,
    *,
    lose_protected_fact: bool,
) -> tuple[PressurePlan, PressureSeed, GeneralAgentContextSnapshot]:
    sizes = {
        PressureKind.HISTORY: (36, 220),
        PressureKind.WORKING_MEMORY: (18, 700),
        PressureKind.NODE_OUTPUT: (96, 180),
        PressureKind.MULTI_SOURCE: (20, 520),
    }
    repetition_count, unit_size = sizes[kind]
    plan = _plan(
        kind,
        repetition_count=repetition_count,
        unit_size=unit_size,
    )
    seed = PressureSeedGenerator().generate(plan, _fixture_blob())
    fixture_text = _fixture_blob().content
    service = _memory_service(root)
    memory_items: tuple[
        PressureMemorySeed | PressureRetrievalFragmentSeed,
        ...,
    ] = (*seed.working_memories, *seed.retrieval_fragments)
    for item in memory_items:
        if (
            lose_protected_fact
            and kind in {PressureKind.WORKING_MEMORY, PressureKind.MULTI_SOURCE}
            and item.protected_fact_refs
        ):
            continue
        content = item.content
        if lose_protected_fact and kind in {
            PressureKind.WORKING_MEMORY,
            PressureKind.MULTI_SOURCE,
        }:
            content = str(_replace_fixture_text(content, fixture_text))
        await service.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind(item.kind),
                content=content,
                source_refs=list(item.source_refs),
                artifact_refs=list(item.artifact_refs),
                run_ids=["run_pressure_behavior"],
                conversation_id="conversation_context_pressure",
                created_request_index=1,
                retention_priority=item.retention_priority,
            )
        )

    messages = _messages(seed)
    author_constraints = list(seed.author_constraints)
    if lose_protected_fact and kind in {
        PressureKind.HISTORY,
        PressureKind.MULTI_SOURCE,
    }:
        messages = [
            item.model_copy(
                update={
                    "content": str(_replace_fixture_text(item.content, fixture_text))
                }
            )
            for item in messages
        ]
        author_constraints = []

    execution_plan: GeneralAgentExecutionPlan | None = None
    node_runs: list[GeneralAgentNodeRun] = []
    if seed.node_artifacts:
        execution_plan, node_runs = _dependency_plan(seed)
    if lose_protected_fact and kind in {
        PressureKind.WORKING_MEMORY,
        PressureKind.NODE_OUTPUT,
        PressureKind.MULTI_SOURCE,
    }:
        updated_runs: list[GeneralAgentNodeRun] = []
        for node_run in node_runs:
            output = _replace_fixture_text(node_run.output, fixture_text)
            if (
                kind is PressureKind.NODE_OUTPUT
                and node_run.node_id == "pressure_source"
                and isinstance(output, dict)
            ):
                output = {key: value for key, value in output.items() if key != "items"}
            updated_runs.append(node_run.model_copy(update={"output": output}))
        node_runs = updated_runs

    timestamp = "2026-07-30T12:00:00Z"
    run = GeneralAgentRun(
        run_id="general_run_20260730_120000_abc123",
        task_id="conversation_context_pressure",
        conversation_id="conversation_context_pressure",
        request_index=50,
        user_goal=seed.current_request,
        author_constraints=author_constraints,
        scope=GeneralAgentScope(scope_type="novel"),
        messages=messages,
        plan=execution_plan,
        plan_revision=1 if execution_plan is not None else 0,
        node_runs=node_runs,
        verification_issues=list(seed.todos),
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp,
    )
    total_budget = {
        PressureKind.HISTORY: 8_000,
        PressureKind.WORKING_MEMORY: 12_000,
        PressureKind.NODE_OUTPUT: 12_000,
        PressureKind.MULTI_SOURCE: 30_000,
    }[kind]
    snapshot = (
        await ContextAssembler(
            memory_service=service,
            policy=GeneralAgentContextPolicy(
                total_char_budget=total_budget,
                working_memory_char_budget=7_000,
                history_memory_limit=5,
                history_memory_char_budget=2_400,
                node_summary_char_budget=3_000,
                plan_summary_char_budget=1_800,
                message_compaction_threshold=3,
                node_output_compaction_threshold=500,
            ),
        ).assemble(run, phase="verify")
    ).snapshot
    return plan, seed, snapshot


def _pressure_claim_catalog() -> ClaimCatalog:
    normalizer = ClaimNormalizerRef(
        normalizer_id="claim_text",
        version="1",
    )
    claim = ExpectedClaimSpec(
        claim_id="pressure_behavior_claim",
        subject="pressure_context",
        predicate="preserves",
        object="protected_fact",
        polarity=ClaimPolarity.POSITIVE,
        canonical_forms=("灯塔火焰必须始终保持青白色。",),
        aliases=(),
        source_fixture_refs=("pressure_fixture",),
        allowed_normalizers=(normalizer,),
    )
    payload = {
        "schema": "taichu.general_agent_benchmark.claim_catalog@1",
        "catalog_version": 1,
        "fixture_id": "pressure_fixture",
        "claims": (claim,),
    }
    return ClaimCatalog.model_validate(
        {**payload, "content_hash": canonical_sha256(payload)}
    )


def _pressure_observation(
    plan: PressurePlan,
    seed: PressureSeed,
    behavior: PressureBehaviorArtifact,
) -> CaseObservation:
    owner = _pressure_owner(plan)
    payload = {
        "owner": owner,
        "user_request_raw": seed.current_request,
        "user_request_sha256": canonical_sha256(seed.current_request),
        "plan": None,
        "plan_sha256": None,
        "nodes": (),
        "invocations": (),
        "final_answer": ObservedFinalAnswer.create(
            text=behavior.final_answer,
            source_refs=behavior.source_refs,
        ),
        "artifacts": (),
        "resource_snapshots": (),
        "capability_result_refs": (),
        "effect_refs": (),
        "checkpoint_refs": (),
        "context_snapshot_refs": (),
        "recovery_decisions": (),
        "terminal": ObservedTerminalState(
            run_status=behavior.status,
            stop_reason=(
                "goal_satisfied"
                if behavior.status == "completed"
                else "context_preservation_failed"
            ),
            resumable=behavior.status == "failed",
            pending_human_kind=None,
        ),
        "budget": ObservedBudgetUsage(
            node_executions=0,
            capability_calls=0,
            model_calls=0,
            total_tokens=0,
            runtime_ms=10,
            context_tokens=0,
        ),
        "script_protocol_deviations": (),
        "evidence_records": (),
        "evidence_resolutions": (),
        "evidence_integrity": EvidenceIntegrityStatus.VALID,
        "evidence_problems": (),
    }
    return CaseObservation.model_validate(
        {**payload, "observation_sha256": canonical_sha256(payload)}
    )


def _pressure_owner(plan: PressurePlan) -> EvidenceOwner:
    return EvidenceOwner(
        suite_id="pressure_suite",
        suite_content_hash="a" * 64,
        case_id=plan.plan_id,
        case_execution_id=f"benchmark_case_{'b' * 32}",
        run_id="general_run_20260730_120000_abc123",
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_id=f"fixture_{'c' * 64}",
    )


class _FailingCompactor(ContextCompactor):
    def compact(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("固定压缩器故障")


def _with_invocation(observation: CaseObservation) -> CaseObservation:
    payload = observation.model_dump(
        mode="python",
        exclude={"observation_sha256"},
    )
    payload["invocations"] = (
        ObservedInvocation(
            call_id="call_before_safe_refusal",
            sequence=0,
            run_id=observation.owner.run_id,
            node_id="pressure_source",
            capability_kind="tool",
            capability_name="get_novel_structure",
            status="succeeded",
            input_sha256=canonical_sha256({"scope": "novel"}),
            output_sha256=canonical_sha256({"items": []}),
        ),
    )
    payload["budget"] = {
        **observation.budget.model_dump(mode="python"),
        "capability_calls": 1,
    }
    return CaseObservation.model_validate(
        {
            **payload,
            "observation_sha256": canonical_sha256(payload),
        }
    )


def test_pressure_plan_and_generated_seed_are_content_addressed_and_fixed() -> None:
    plan = _plan(PressureKind.MULTI_SOURCE)
    blob = _fixture_blob()
    generator = PressureSeedGenerator()

    first = generator.generate(plan, blob)
    second = generator.generate(plan, blob)
    changed = generator.generate(
        plan,
        PressureFixtureBlob.seal(
            blob_ref=blob.blob_ref,
            content=blob.content + "不得改成赤红色。",
        ),
    )

    assert first == second
    assert first.content_hash == second.content_hash
    assert first.content_hash != changed.content_hash
    assert first.generation_seed == second.generation_seed
    assert first.fixture_blob_sha256 == blob.content_sha256
    assert first.long_term_memories == ()
    assert "case_id" not in inspect.signature(generator.generate).parameters

    payload = first.model_dump(mode="json", by_alias=True)
    payload["current_request"] = "篡改后的请求"
    with pytest.raises(ValidationError, match="content_hash"):
        PressureSeed.model_validate(payload)


def test_pressure_plan_rejects_unknown_kind_bad_identity_and_invalid_pairing() -> None:
    payload = _plan(PressureKind.HISTORY).model_dump(mode="json", by_alias=True)

    with pytest.raises(ValidationError):
        PressurePlan.model_validate({**payload, "kind": "case_30_only"})
    with pytest.raises(ValidationError, match="规范化内容"):
        PressurePlan.model_validate(
            {
                **payload,
                "protected_fact_refs": [
                    "current_request",
                    "current_request",
                ],
            }
        )
    with pytest.raises(ValidationError, match="paired_case_ref"):
        PressurePlan.seal(
            plan_id="pressure_bad_pair",
            kind=PressureKind.HISTORY,
            fixture_blob_ref="pressure/context-anchor.txt",
            repetition_count=2,
            unit_size=100,
            protected_fact_refs=("current_request",),
            invalid_sentinel_refs=(),
            paired_case_ref="context_baseline_pair",
        )


def test_case_30_long_history_keeps_early_constraint_recent_raw_and_request(
    tmp_path: Path,
) -> None:
    seed = _generate(
        PressureKind.HISTORY,
        repetition_count=36,
        unit_size=220,
    )
    run = _base_run(seed, messages=_messages(seed))
    policy = GeneralAgentContextPolicy(
        total_char_budget=8_000,
        history_memory_limit=5,
        history_memory_char_budget=2_400,
        message_compaction_threshold=4,
    )
    snapshot = asyncio.run(
        ContextAssembler(
            memory_service=_memory_service(tmp_path),
            policy=policy,
        ).assemble(run, phase="plan")
    ).snapshot

    history = snapshot.envelope.history_memory
    trace = snapshot.assembly_trace
    assert seed.author_constraints[0] in history.summary
    assert history.messages[-1].content == seed.history_messages[-1].content
    assert snapshot.envelope.current_request.content == seed.current_request
    assert snapshot.envelope.current_request.user_constraints == list(
        seed.author_constraints
    )
    assert trace is not None
    history_trace = next(
        item for item in trace.layers if item.layer == "history_memory"
    )
    assert history_trace.pre_count == len(seed.history_messages)
    assert history_trace.post_count < history_trace.pre_count
    assert history_trace.omitted_item_refs
    assert (
        trace.current_request_sha256
        == sha256(seed.current_request.encode("utf-8")).hexdigest()
    )
    assert "current_request" in trace.protected_refs
    assert any(item.startswith("stable_memory:") for item in trace.protected_refs)


def test_case_31_working_pressure_drops_low_priority_before_protected_dependencies(
    tmp_path: Path,
) -> None:
    async def scenario() -> tuple[
        PressureSeed,
        dict[str, str],
        GeneralAgentContextSnapshot,
    ]:
        seed = _generate(
            PressureKind.WORKING_MEMORY,
            repetition_count=18,
            unit_size=700,
        )
        service = _memory_service(tmp_path)
        memory_ids = await _write_seed_memories(service, seed)
        plan, node_runs = _dependency_plan(seed)
        run = _base_run(
            seed,
            messages=_messages(seed),
            plan=plan,
            node_runs=node_runs,
            verification_issues=list(seed.todos),
        )
        result = await ContextAssembler(
            memory_service=service,
            policy=GeneralAgentContextPolicy(
                total_char_budget=12_000,
                working_memory_char_budget=7_000,
                history_memory_char_budget=1_200,
                node_summary_char_budget=2_600,
                plan_summary_char_budget=1_800,
                message_compaction_threshold=2,
                node_output_compaction_threshold=500,
            ),
        ).assemble(run, phase="verify")
        return seed, memory_ids, result.snapshot

    seed, memory_ids, snapshot = asyncio.run(scenario())
    working = snapshot.envelope.working_memory
    trace = snapshot.assembly_trace
    assert trace is not None
    protected_seed_ids = {
        item.seed_id for item in seed.working_memories if item.protected_fact_refs
    }
    low_priority_seed_ids = {
        item.seed_id
        for item in seed.working_memories
        if item.kind == AgentMemoryKind.WORK_NOTE.value
    }
    selected_ids = {item.memory_id for item in working.memories}
    assert {memory_ids[item] for item in protected_seed_ids} <= selected_ids
    assert any(memory_ids[item] not in selected_ids for item in low_priority_seed_ids)
    assert {f"memory:{memory_ids[item]}" for item in protected_seed_ids} <= set(
        trace.protected_refs
    )
    assert any(
        f"memory:{memory_ids[item]}" in trace.omitted_item_refs
        for item in low_priority_seed_ids
    )

    direct = next(item for item in seed.node_artifacts if item.direct_dependency)
    assert direct.node_id in {str(item["node_id"]) for item in working.node_summaries}
    projection = next(
        item for item in trace.projections if item.node_id == direct.node_id
    )
    assert projection.required_output_paths == direct.required_output_paths
    assert f"node:{direct.node_id}" in trace.protected_refs
    assert f"node:{direct.node_id}" not in trace.omitted_item_refs


def test_case_32_large_result_keeps_contract_count_sources_and_nonabsence_notice(
    tmp_path: Path,
) -> None:
    seed = _generate(
        PressureKind.NODE_OUTPUT,
        repetition_count=96,
        unit_size=180,
    )
    plan, node_runs = _dependency_plan(seed)
    run = _base_run(seed, plan=plan, node_runs=node_runs)
    snapshot = asyncio.run(
        ContextAssembler(
            memory_service=_memory_service(tmp_path),
            policy=GeneralAgentContextPolicy(
                total_char_budget=12_000,
                node_summary_char_budget=3_000,
                plan_summary_char_budget=1_800,
                node_output_compaction_threshold=500,
            ),
        ).assemble(run, phase="verify")
    ).snapshot

    direct = next(item for item in seed.node_artifacts if item.direct_dependency)
    summary = next(
        item
        for item in snapshot.envelope.working_memory.node_summaries
        if item["node_id"] == direct.node_id
    )
    output = summary["output_summary"]
    assert output["_projection_status"] == "compressed"
    assert output["fields"]["total"] == 96
    assert output["fields"]["items"]["item_count"] == 96
    assert output["fields"]["items"]["omitted_item_count"] > 0
    assert output["_required_fields"]["items"]["item_count"] == 96
    assert "不得据此断言未展示的条目不存在" in output["_projection_notice"]
    assert tuple(summary["source_refs"]) == direct.source_refs

    trace = snapshot.assembly_trace
    assert trace is not None
    projection = next(
        item for item in trace.projections if item.node_id == direct.node_id
    )
    assert projection.required_output_paths == ("items",)
    assert projection.original_item_count > projection.projected_item_count
    assert projection.omitted_item_count > 0
    assert projection.source_refs == direct.source_refs
    assert projection.artifact_refs == direct.artifact_refs


def test_case_33_multi_source_overflow_respects_five_layers_and_priority(
    tmp_path: Path,
) -> None:
    async def scenario() -> tuple[
        PressureSeed,
        dict[str, str],
        GeneralAgentContextSnapshot,
    ]:
        seed = _generate(
            PressureKind.MULTI_SOURCE,
            repetition_count=20,
            unit_size=520,
        )
        service = _memory_service(tmp_path)
        memory_ids = await _write_seed_memories(service, seed)
        plan, node_runs = _dependency_plan(seed)
        run = _base_run(
            seed,
            messages=_messages(seed),
            plan=plan,
            node_runs=node_runs,
            verification_issues=list(seed.todos),
        )
        result = await ContextAssembler(
            memory_service=service,
            policy=GeneralAgentContextPolicy(
                total_char_budget=14_000,
                working_memory_char_budget=7_000,
                history_memory_limit=5,
                history_memory_char_budget=2_200,
                node_summary_char_budget=2_800,
                plan_summary_char_budget=1_800,
                message_compaction_threshold=3,
                node_output_compaction_threshold=600,
            ),
        ).assemble(run, phase="verify")
        return seed, memory_ids, result.snapshot

    seed, memory_ids, snapshot = asyncio.run(scenario())
    trace = snapshot.assembly_trace
    assert trace is not None
    by_layer = {item.layer: item for item in trace.layers}
    assert by_layer["stable_memory"].pre_count == by_layer["stable_memory"].post_count
    assert by_layer["current_request"].pre_count == 1
    assert by_layer["current_request"].post_count == 1
    assert by_layer["history_memory"].post_count < by_layer["history_memory"].pre_count
    assert by_layer["working_memory"].post_char_count < (
        by_layer["working_memory"].pre_char_count
    )
    assert all(
        layer.pre_token_estimate >= layer.post_token_estimate for layer in trace.layers
    )
    assert snapshot.envelope.long_term_memory == []
    assert snapshot.envelope.current_request.content == seed.current_request
    assert snapshot.envelope.stable_memory

    selected_ids = {
        item.memory_id for item in snapshot.envelope.working_memory.memories
    }
    protected_ids = {
        memory_ids[item.seed_id]
        for item in seed.working_memories
        if item.protected_fact_refs
    }
    low_priority_ids = {
        memory_ids[item.seed_id]
        for item in seed.working_memories
        if item.kind == AgentMemoryKind.WORK_NOTE.value
    }
    assert protected_ids <= selected_ids
    assert any(item not in selected_ids for item in low_priority_ids)

    direct = next(item for item in seed.node_artifacts if item.direct_dependency)
    assert direct.node_id in {
        str(item["node_id"]) for item in snapshot.envelope.working_memory.node_summaries
    }
    assert f"node:{direct.node_id}" not in trace.omitted_item_refs
    assert trace.omitted_item_refs
    assert trace.omitted_source_refs
    assert (
        json.dumps(
            snapshot.envelope.model_dump(mode="json"),
            ensure_ascii=False,
        ).count(seed.current_request)
        == 1
    )


@pytest.mark.parametrize(
    "kind",
    (
        PressureKind.HISTORY,
        PressureKind.WORKING_MEMORY,
        PressureKind.NODE_OUTPUT,
        PressureKind.MULTI_SOURCE,
    ),
)
def test_cases_30_to_33_behavior_and_typed_context_oracle_fail_on_fact_loss(
    tmp_path: Path,
    kind: PressureKind,
) -> None:
    plan, seed, preserved_snapshot = asyncio.run(
        _assemble_behavior_case(
            tmp_path / kind.value / "preserved",
            kind,
            lose_protected_fact=False,
        )
    )
    _, _, lost_snapshot = asyncio.run(
        _assemble_behavior_case(
            tmp_path / kind.value / "lost",
            kind,
            lose_protected_fact=True,
        )
    )
    evaluator = PressureBehaviorEvaluator()
    behavior_oracle = PressureBehaviorOracle()
    preserved_behavior = evaluator.evaluate(
        plan=plan,
        seed=seed,
        snapshot=preserved_snapshot,
    )
    lost_behavior = evaluator.evaluate(
        plan=plan,
        seed=seed,
        snapshot=lost_snapshot,
    )
    preserved_result = behavior_oracle.evaluate(preserved_behavior)
    lost_result = behavior_oracle.evaluate(lost_behavior)
    influential_fact = next(
        item for item in seed.protected_facts if item.affects_final_answer
    )

    assert preserved_behavior.status == "completed"
    assert (
        preserved_behavior.context_snapshot_sha256 == preserved_snapshot.content_sha256
    )
    assert preserved_result.status == "passed"
    assert influential_fact.expected_text in preserved_behavior.final_answer
    assert preserved_behavior.source_refs
    assert lost_behavior.status == "failed"
    assert lost_behavior.context_snapshot_sha256 == lost_snapshot.content_sha256
    assert lost_result.status == "failed"
    assert lost_result.failed_check_ids
    assert lost_result.missing_fact_refs == (influential_fact.fact_ref,)
    assert influential_fact.expected_text not in lost_behavior.final_answer
    assert lost_behavior.final_answer != preserved_behavior.final_answer

    projector = PressureContextPreservationProjector()
    preserved_context = projector.project(
        plan=plan,
        seed=seed,
        snapshot=preserved_snapshot,
    )
    lost_context = projector.project(
        plan=plan,
        seed=seed,
        snapshot=lost_snapshot,
    )
    assert preserved_context.pressure_plan_ref == plan.plan_id
    assert tuple(item.carrier for item in preserved_context.carriers) == (
        "stable_memory",
        "working_memory",
        "long_term_memory",
        "history_memory",
        "current_request",
    )
    preserved_carriers = {item.carrier: item for item in preserved_context.carriers}
    lost_carriers = {item.carrier: item for item in lost_context.carriers}
    assert all(
        preserved_carriers[carrier].preserved
        for carrier in influential_fact.required_carriers
    )
    assert all(
        not lost_carriers[carrier].preserved
        for carrier in influential_fact.required_carriers
    )

    assertion = ContextPreservationAssertionSpec(
        kind="context_preservation",
        assertion_id=f"assert_{kind.value}",
        description="压力下的受保护上下文必须真实保留。",
        pressure_plan_ref=plan.plan_id,
        protected_carriers=(
            "stable_memory",
            "working_memory",
            "history_memory",
            "current_request",
        ),
    )
    typed_oracle = TypedOracle(catalog=_pressure_claim_catalog())
    preserved_oracle_result = typed_oracle.evaluate(
        assertion,
        _pressure_observation(
            plan,
            seed,
            preserved_behavior,
        ),
        context=AssertionEvaluationContext(context_preservation=(preserved_context,)),
    )
    lost_oracle_result = typed_oracle.evaluate(
        assertion,
        _pressure_observation(
            plan,
            seed,
            lost_behavior,
        ),
        context=AssertionEvaluationContext(context_preservation=(lost_context,)),
    )

    assert preserved_oracle_result.status is AssertionStatus.PASSED
    assert lost_oracle_result.status is AssertionStatus.FAILED


async def _assemble_equivalence_pair(
    root: Path,
    *,
    drift_required_contract: bool,
) -> tuple[
    PressurePlan,
    PressureSeed,
    GeneralAgentExecutionPlan,
    GeneralAgentContextSnapshot,
    PressureBehaviorArtifact,
    GeneralAgentContextSnapshot,
    PressureBehaviorArtifact,
]:
    plan = _plan(
        PressureKind.EQUIVALENCE_PAIR,
        repetition_count=18,
        unit_size=520,
    )
    seed = PressureSeedGenerator().generate(plan, _fixture_blob())
    execution_plan, pressure_node_runs = _dependency_plan(seed)
    direct = next(item for item in seed.node_artifacts if item.direct_dependency)
    baseline_service = _memory_service(root / "baseline")
    for item in seed.working_memories:
        if not item.protected_fact_refs:
            continue
        await baseline_service.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind(item.kind),
                content=item.content,
                source_refs=list(item.source_refs),
                artifact_refs=list(item.artifact_refs),
                run_ids=["run_pressure_baseline"],
                conversation_id="conversation_context_pressure",
                created_request_index=1,
                retention_priority=item.retention_priority,
            )
        )
    baseline_messages = [
        _messages(seed)[0],
        _messages(seed)[-1],
    ]
    baseline_node_runs = [
        item for item in pressure_node_runs if item.node_id == direct.node_id
    ]
    baseline_run = _base_run(
        seed,
        messages=baseline_messages,
        plan=execution_plan,
        node_runs=baseline_node_runs,
        verification_issues=list(seed.todos),
    )
    baseline_snapshot = (
        await ContextAssembler(
            memory_service=baseline_service,
            policy=GeneralAgentContextPolicy(
                total_char_budget=90_000,
                working_memory_char_budget=20_000,
                history_memory_limit=10,
                history_memory_char_budget=20_000,
                node_summary_char_budget=40_000,
                plan_summary_char_budget=20_000,
                message_compaction_threshold=100,
                node_output_compaction_threshold=100_000,
            ),
        ).assemble(baseline_run, phase="verify")
    ).snapshot

    pressure_service = _memory_service(root / "pressure")
    await _write_seed_memories(pressure_service, seed)
    candidate_node_runs = pressure_node_runs
    if drift_required_contract:
        candidate_node_runs = [
            (
                item.model_copy(
                    update={
                        "output": {
                            key: value
                            for key, value in item.output.items()
                            if key != "items"
                        }
                    }
                )
                if item.node_id == direct.node_id
                else item
            )
            for item in pressure_node_runs
        ]
    pressure_run = _base_run(
        seed,
        messages=_messages(seed),
        plan=execution_plan,
        node_runs=candidate_node_runs,
        verification_issues=list(seed.todos),
    )
    pressure_snapshot = (
        await ContextAssembler(
            memory_service=pressure_service,
            policy=GeneralAgentContextPolicy(
                total_char_budget=40_000,
                working_memory_char_budget=5_000,
                history_memory_limit=5,
                history_memory_char_budget=2_400,
                node_summary_char_budget=4_000,
                plan_summary_char_budget=2_000,
                message_compaction_threshold=3,
                node_output_compaction_threshold=500,
            ),
        ).assemble(pressure_run, phase="verify")
    ).snapshot
    evaluator = PressureBehaviorEvaluator()
    return (
        plan,
        seed,
        execution_plan,
        baseline_snapshot,
        evaluator.evaluate(
            plan=plan,
            seed=seed,
            snapshot=baseline_snapshot,
        ),
        pressure_snapshot,
        evaluator.evaluate(
            plan=plan,
            seed=seed,
            snapshot=pressure_snapshot,
        ),
    )


def test_case_34_compares_real_result_contract_not_output_wording(
    tmp_path: Path,
) -> None:
    (
        plan,
        seed,
        execution_plan,
        baseline_snapshot,
        baseline_behavior,
        pressure_snapshot,
        pressure_behavior,
    ) = asyncio.run(
        _assemble_equivalence_pair(
            tmp_path / "preserved",
            drift_required_contract=False,
        )
    )
    projector = PressureResultContractProjector()
    unchanged_resource = {"manuscript": "sealed", "knowledge": "sealed"}
    baseline_contract = projector.project_result(
        seed=seed,
        snapshot=baseline_snapshot,
        behavior=baseline_behavior,
        execution_plan=execution_plan,
        resource_before=unchanged_resource,
        resource_after=unchanged_resource,
    )
    reworded_payload = pressure_behavior.model_dump(
        mode="python",
        by_alias=True,
        exclude={"content_hash"},
    )
    reworded_payload["final_answer"] = (
        "压力版采用不同措辞，但关键结论、能力链、工件合同和资源后态不变。"
    )
    reworded_behavior = PressureBehaviorArtifact.seal(**reworded_payload)
    pressure_contract = projector.project_result(
        seed=seed,
        snapshot=pressure_snapshot,
        behavior=reworded_behavior,
        execution_plan=execution_plan,
        resource_before=unchanged_resource,
        resource_after=unchanged_resource,
    )
    comparison = projector.compare(
        plan=plan,
        baseline=baseline_contract,
        candidate=pressure_contract,
    )

    assert baseline_snapshot.envelope.compressed is False
    assert pressure_snapshot.envelope.compressed is True
    assert baseline_behavior.status == reworded_behavior.status == "completed"
    assert baseline_behavior.final_answer != reworded_behavior.final_answer
    assert baseline_contract == pressure_contract
    assert baseline_contract.claim_ids
    assert baseline_contract.capability_names == (
        "get_novel_structure",
        "story_architecture",
    )
    assert baseline_contract.topology_edges == (
        "get_novel_structure>story_architecture",
    )
    assert baseline_contract.artifact_contracts == (
        "final_answer",
        "structure_items",
    )

    assertion = ResultContractEquivalenceAssertionSpec(
        kind="result_contract_equivalence",
        assertion_id="assert_pressure_equivalence",
        description="正常版与压力版的语义结果合同必须等价。",
        pressure_plan_ref=plan.plan_id,
        comparison="semantic_contract",
    )
    result = TypedOracle(catalog=_pressure_claim_catalog()).evaluate(
        assertion,
        _pressure_observation(plan, seed, reworded_behavior),
        context=AssertionEvaluationContext(result_contract_equivalences=(comparison,)),
    )
    assert result.status is AssertionStatus.PASSED


def test_case_34_contract_drift_fails_even_when_pressure_run_has_an_answer(
    tmp_path: Path,
) -> None:
    (
        plan,
        seed,
        execution_plan,
        baseline_snapshot,
        baseline_behavior,
        drifted_snapshot,
        drifted_behavior,
    ) = asyncio.run(
        _assemble_equivalence_pair(
            tmp_path / "drifted",
            drift_required_contract=True,
        )
    )
    projector = PressureResultContractProjector()
    resource = {"manuscript": "sealed"}
    comparison = projector.compare(
        plan=plan,
        baseline=projector.project_result(
            seed=seed,
            snapshot=baseline_snapshot,
            behavior=baseline_behavior,
            execution_plan=execution_plan,
            resource_before=resource,
            resource_after=resource,
        ),
        candidate=projector.project_result(
            seed=seed,
            snapshot=drifted_snapshot,
            behavior=drifted_behavior,
            execution_plan=execution_plan,
            resource_before=resource,
            resource_after=resource,
        ),
    )
    assertion = ResultContractEquivalenceAssertionSpec(
        kind="result_contract_equivalence",
        assertion_id="assert_pressure_equivalence_drift",
        description="必要输出合同漂移必须失败。",
        pressure_plan_ref=plan.plan_id,
        comparison="semantic_contract",
    )
    result = TypedOracle(catalog=_pressure_claim_catalog()).evaluate(
        assertion,
        _pressure_observation(plan, seed, drifted_behavior),
        context=AssertionEvaluationContext(result_contract_equivalences=(comparison,)),
    )

    assert drifted_behavior.final_answer
    assert drifted_behavior.status == "failed"
    assert comparison.baseline != comparison.candidate
    assert result.status is AssertionStatus.FAILED


async def _assemble_invalid_memory_case(
    root: Path,
) -> tuple[
    PressurePlan,
    PressureSeed,
    GeneralAgentContextSnapshot,
    GeneralAgentContextSnapshot,
    PressureBehaviorArtifact,
]:
    plan = _plan(
        PressureKind.INVALID_MEMORY,
        repetition_count=12,
        unit_size=420,
    )
    seed = PressureSeedGenerator().generate(plan, _fixture_blob())
    service = _memory_service(root)
    await _write_seed_memories(service, seed)
    execution_plan, node_runs = _dependency_plan(seed)
    run = _base_run(
        seed,
        messages=_messages(seed),
        plan=execution_plan,
        node_runs=node_runs,
        verification_issues=list(seed.todos),
    )
    policy = GeneralAgentContextPolicy(
        total_char_budget=40_000,
        working_memory_char_budget=5_000,
        history_memory_limit=4,
        history_memory_char_budget=2_200,
        node_summary_char_budget=3_600,
        plan_summary_char_budget=2_000,
        message_compaction_threshold=2,
        node_output_compaction_threshold=500,
    )
    snapshot = (
        await ContextAssembler(
            memory_service=service,
            policy=policy,
        ).assemble(run, phase="verify")
    ).snapshot
    fallback_snapshot = (
        await ContextAssembler(
            memory_service=service,
            policy=policy,
            compactor=_FailingCompactor(),
        ).assemble(run, phase="verify")
    ).snapshot
    behavior = PressureBehaviorEvaluator().evaluate(
        plan=plan,
        seed=seed,
        snapshot=snapshot,
    )
    return plan, seed, snapshot, fallback_snapshot, behavior


def _memory_absence_assertion(
    plan: PressurePlan,
) -> MemoryCarrierAbsenceAssertionSpec:
    return MemoryCarrierAbsenceAssertionSpec(
        kind="memory_carrier_absence",
        assertion_id="assert_invalid_memory_absence",
        description="三类失效运行记忆不得经任何模型可见载体复活。",
        memory_seed_ref=plan.plan_id,
        forbidden_states=("stale", "rejected", "superseded"),
    )


def test_case_35_invalid_memory_is_absent_from_all_normal_and_fallback_carriers(
    tmp_path: Path,
) -> None:
    plan, seed, snapshot, fallback_snapshot, behavior = asyncio.run(
        _assemble_invalid_memory_case(tmp_path / "isolated")
    )
    observations = PressureMemoryIsolationProjector().project(
        plan=plan,
        seed=seed,
        snapshot=snapshot,
        fallback_snapshot=fallback_snapshot,
        behavior=behavior,
    )
    serialized = json.dumps(
        {
            "normal": snapshot.envelope.model_dump(mode="json"),
            "fallback": fallback_snapshot.envelope.model_dump(mode="json"),
            "final": behavior.final_answer,
        },
        ensure_ascii=False,
    )
    result = TypedOracle(catalog=_pressure_claim_catalog()).evaluate(
        _memory_absence_assertion(plan),
        _pressure_observation(plan, seed, behavior),
        context=AssertionEvaluationContext(memory_carriers=observations),
    )

    assert behavior.status == "completed"
    assert snapshot.envelope.digest is not None
    assert snapshot.envelope.fallback_used is False
    assert fallback_snapshot.envelope.digest is not None
    assert fallback_snapshot.envelope.fallback_used is True
    assert {item.state for item in observations} == {
        "stale",
        "rejected",
        "superseded",
    }
    assert {item.carrier for item in observations} == {
        "basis",
        "repair",
        "digest",
        "fallback",
        "history",
        "working_memory",
        "node",
        "subagent",
        "final",
    }
    assert all(item.occurrence_count == 0 for item in observations)
    for invalid in (
        item
        for item in seed.working_memories
        if item.validity != AgentMemoryValidity.ACTIVE.value
    ):
        assert invalid.content not in serialized
        assert all(
            sentinel not in serialized for sentinel in invalid.invalid_sentinel_refs
        )
    assert result.status is AssertionStatus.PASSED


@pytest.mark.parametrize(
    "carrier",
    (
        "basis",
        "repair",
        "digest",
        "fallback",
        "history",
        "working_memory",
        "node",
        "subagent",
        "final",
    ),
)
def test_case_35_each_resurrection_carrier_independently_fails(
    tmp_path: Path,
    carrier: str,
) -> None:
    plan, seed, snapshot, fallback_snapshot, behavior = asyncio.run(
        _assemble_invalid_memory_case(tmp_path / carrier)
    )
    sentinel = next(
        item.invalid_sentinel_refs[0]
        for item in seed.working_memories
        if item.invalid_sentinel_refs
    )
    observations = PressureMemoryIsolationProjector().project(
        plan=plan,
        seed=seed,
        snapshot=snapshot,
        fallback_snapshot=fallback_snapshot,
        behavior=behavior,
        carrier_overrides={carrier: f"错误复活：{sentinel}"},
    )
    result = TypedOracle(catalog=_pressure_claim_catalog()).evaluate(
        _memory_absence_assertion(plan),
        _pressure_observation(plan, seed, behavior),
        context=AssertionEvaluationContext(memory_carriers=observations),
    )

    assert sum(item.occurrence_count for item in observations) > 0
    assert result.status is AssertionStatus.FAILED


async def _assemble_long_current_request(
    root: Path,
    *,
    current_request: str | None = None,
) -> tuple[
    PressurePlan,
    PressureSeed,
    GeneralAgentContextSnapshot,
    PressureBehaviorArtifact,
]:
    plan = _plan(
        PressureKind.CURRENT_REQUEST,
        repetition_count=12,
        unit_size=1_000,
    )
    seed = PressureSeedGenerator().generate(plan, _fixture_blob())
    execution_plan, node_runs = _dependency_plan(seed)
    run = _base_run(
        seed,
        plan=execution_plan,
        node_runs=node_runs,
    )
    if current_request is not None:
        run = run.model_copy(update={"user_goal": current_request})
    snapshot = (
        await ContextAssembler(
            memory_service=_memory_service(root),
            policy=GeneralAgentContextPolicy(
                total_char_budget=30_000,
                working_memory_char_budget=4_000,
                history_memory_char_budget=1_000,
                node_summary_char_budget=4_000,
                plan_summary_char_budget=2_000,
                node_output_compaction_threshold=500,
            ),
        ).assemble(run, phase="verify")
    ).snapshot
    behavior = PressureBehaviorEvaluator().evaluate(
        plan=plan,
        seed=seed,
        snapshot=snapshot,
    )
    return plan, seed, snapshot, behavior


def test_case_36_preserves_intake_snapshot_and_model_visible_request_bytes(
    tmp_path: Path,
) -> None:
    plan, seed, snapshot, behavior = asyncio.run(
        _assemble_long_current_request(tmp_path / "preserved")
    )
    serialized = json.dumps(
        snapshot.envelope.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    model_visible = json.loads(serialized)["current_request"]["content"]
    byte_hashes = {
        sha256(value.encode("utf-8")).hexdigest()
        for value in (
            seed.current_request,
            snapshot.envelope.current_request.content,
            model_visible,
        )
    }
    chain_check = next(
        item
        for item in behavior.checks
        if item.check_id == "necessary_execution_chain_completed"
    )
    context_observation = PressureContextPreservationProjector().project(
        plan=plan,
        seed=seed,
        snapshot=snapshot,
    )
    assertion = ContextPreservationAssertionSpec(
        kind="context_preservation",
        assertion_id="assert_long_current_request",
        description="当前请求必须逐字保持且任务合同完成。",
        pressure_plan_ref=plan.plan_id,
        protected_carriers=(
            "stable_memory",
            "working_memory",
            "history_memory",
            "current_request",
        ),
    )
    result = TypedOracle(catalog=_pressure_claim_catalog()).evaluate(
        assertion,
        _pressure_observation(plan, seed, behavior),
        context=AssertionEvaluationContext(context_preservation=(context_observation,)),
    )

    assert seed.current_request.startswith("  ")
    assert "\n" in seed.current_request
    assert len(seed.current_request) == 12_000
    assert len(byte_hashes) == 1
    assert chain_check.satisfied is True
    assert behavior.status == "completed"
    assert result.status is AssertionStatus.PASSED


def test_case_36_one_whitespace_byte_change_fails_behavior_and_typed_oracle(
    tmp_path: Path,
) -> None:
    plan, seed, _, _ = asyncio.run(
        _assemble_long_current_request(tmp_path / "original")
    )
    changed_request = seed.current_request[1:]
    _, _, changed_snapshot, changed_behavior = asyncio.run(
        _assemble_long_current_request(
            tmp_path / "changed",
            current_request=changed_request,
        )
    )
    context_observation = PressureContextPreservationProjector().project(
        plan=plan,
        seed=seed,
        snapshot=changed_snapshot,
    )
    assertion = ContextPreservationAssertionSpec(
        kind="context_preservation",
        assertion_id="assert_long_current_request_changed",
        description="任一空白字节变化都必须失败。",
        pressure_plan_ref=plan.plan_id,
        protected_carriers=("current_request",),
    )
    result = TypedOracle(catalog=_pressure_claim_catalog()).evaluate(
        assertion,
        _pressure_observation(plan, seed, changed_behavior),
        context=AssertionEvaluationContext(context_preservation=(context_observation,)),
    )

    assert (
        sha256(changed_request.encode("utf-8")).hexdigest()
        != sha256(seed.current_request.encode("utf-8")).hexdigest()
    )
    assert changed_behavior.status == "failed"
    assert result.status is AssertionStatus.FAILED


def test_case_37_refuses_before_planning_and_projects_zero_effect_observation(
    tmp_path: Path,
) -> None:
    plan = _plan(
        PressureKind.UNSAFE_TOTAL,
        repetition_count=120,
        unit_size=1_000,
    )
    seed = PressureSeedGenerator().generate(plan, _fixture_blob())
    run = _base_run(seed)
    assembler = ContextAssembler(
        memory_service=_memory_service(tmp_path),
        policy=GeneralAgentContextPolicy(total_char_budget=80_000),
    )
    with pytest.raises(ContextAssemblyError) as caught:
        asyncio.run(assembler.assemble(run, phase="plan"))

    refusal = PressureUnsafeRefusalArtifact.from_error(
        plan=plan,
        seed=seed,
        error=caught.value,
    )
    projector = PressureUnsafeRefusalProjector()
    observation = projector.project_observation(
        plan=plan,
        seed=seed,
        artifact=refusal,
        owner=_pressure_owner(plan),
        resource_state={"manuscript": "sealed", "knowledge": "sealed"},
    )
    context_observation = projector.project_context(
        plan=plan,
        seed=seed,
        artifact=refusal,
    )
    oracle = TypedOracle(catalog=_pressure_claim_catalog())
    zero_result = oracle.evaluate(
        ZeroCapabilityOrSideEffectAssertionSpec(
            kind="zero_capability_or_side_effect",
            assertion_id="assert_unsafe_zero",
            description="不安全上下文必须在任何能力调用或副作用前停止。",
            require_zero_capability_calls=True,
            require_zero_side_effects=True,
        ),
        observation,
    )
    context_result = oracle.evaluate(
        ContextPreservationAssertionSpec(
            kind="context_preservation",
            assertion_id="assert_unsafe_context",
            description="拒绝不得通过截断稳定记忆或当前请求来伪装完成。",
            pressure_plan_ref=plan.plan_id,
            protected_carriers=(
                "stable_memory",
                "working_memory",
                "history_memory",
                "current_request",
            ),
        ),
        observation,
        context=AssertionEvaluationContext(context_preservation=(context_observation,)),
    )

    assert caught.value.reason_code == "unsafe_context"
    assert (
        caught.value.current_request_sha256
        == sha256(seed.current_request.encode("utf-8")).hexdigest()
    )
    assert refusal.run_status == "safe_failure"
    assert refusal.resumable is False
    assert refusal.recovery_action == "stop"
    assert "无法安全容纳" in refusal.message
    assert observation.invocations == ()
    assert observation.effect_refs == ()
    assert len(observation.recovery_decisions) == 1
    assert observation.recovery_decisions[0].action == "stop"
    assert observation.recovery_decisions[0].reason_code == "unsafe_context"
    assert observation.recovery_decisions[0].evidence_sha256 == refusal.content_hash
    assert observation.terminal.stop_reason == "unsafe_context"
    assert zero_result.status is AssertionStatus.PASSED
    assert context_result.status is AssertionStatus.PASSED


def test_case_37_call_before_refusal_and_fake_completion_are_rejected(
    tmp_path: Path,
) -> None:
    plan = _plan(
        PressureKind.UNSAFE_TOTAL,
        repetition_count=120,
        unit_size=1_000,
    )
    seed = PressureSeedGenerator().generate(plan, _fixture_blob())
    with pytest.raises(ContextAssemblyError) as caught:
        asyncio.run(
            ContextAssembler(
                memory_service=_memory_service(tmp_path),
                policy=GeneralAgentContextPolicy(total_char_budget=80_000),
            ).assemble(
                _base_run(seed),
                phase="plan",
            )
        )
    refusal = PressureUnsafeRefusalArtifact.from_error(
        plan=plan,
        seed=seed,
        error=caught.value,
    )
    projector = PressureUnsafeRefusalProjector()
    observation = projector.project_observation(
        plan=plan,
        seed=seed,
        artifact=refusal,
        owner=_pressure_owner(plan),
        resource_state={"manuscript": "sealed"},
    )
    called_observation = _with_invocation(observation)
    result = TypedOracle(catalog=_pressure_claim_catalog()).evaluate(
        ZeroCapabilityOrSideEffectAssertionSpec(
            kind="zero_capability_or_side_effect",
            assertion_id="assert_unsafe_call_negative",
            description="拒绝前发生任一能力调用都必须失败。",
            require_zero_capability_calls=True,
            require_zero_side_effects=True,
        ),
        called_observation,
    )
    fake_payload = refusal.model_dump(mode="python", by_alias=True)
    fake_payload["run_status"] = "completed"
    fake_payload["content_hash"] = canonical_sha256(
        {key: value for key, value in fake_payload.items() if key != "content_hash"}
    )

    assert result.status is AssertionStatus.FAILED
    with pytest.raises(ValidationError):
        PressureUnsafeRefusalArtifact.model_validate(fake_payload)
