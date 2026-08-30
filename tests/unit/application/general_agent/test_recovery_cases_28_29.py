"""案例 28—29：有序多次中断与官方 Checkpointer 恢复。"""

from __future__ import annotations

from tests.fakes.capability_results import in_memory_capability_result_repository

from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
import pytest

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
)
from taichu.application.evaluations.general_agent_benchmark.faults import (
    FaultPoint,
    FaultPressureAdapter,
    FaultRunIdentity,
    FaultStep,
    JsonFaultTriggerStore,
)
from taichu.application.general_agent.faults import (
    GeneralAgentFaultHook,
    InjectedProcessTermination,
)
from taichu.application.general_agent.models import (
    GeneralAgentRunStatus,
    RecoveryAction,
)
from taichu.application.general_agent.recovery import (
    EffectRecord,
    EffectStatus,
)
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.invocations.models import InvocationContext, now_iso
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.outline_service import OutlineService
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools import (
    apply_manuscript_patch,
    get_novel_structure,
)
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolPlugin,
    ToolReconciliationResult,
)
from taichu.application.tools._shared import sha256_text
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.evaluations.general_agent_benchmark.recovery_harness import (
    GeneralAgentRecoveryHarness,
)
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentEffectRepository,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from tests.unit.application.general_agent.test_recovery_cases_26_27 import (
    _prepare_patch_fixture,
)
from tests.unit.application.general_agent.test_runtime import (
    _ScriptedChatModel,
    _TraceRepository,
    _async_test,
    _checkpointer,
    _register_tools,
    _runtime,
)

_WriteHandler = Callable[
    [BaseModel, InvocationContext, CapabilityContext],
    Awaitable[BaseModel],
]
_Reconciler = Callable[
    [BaseModel, InvocationContext, CapabilityContext],
    Awaitable[ToolReconciliationResult],
]


@_async_test
async def test_recovery_case_28_handles_two_ordered_interruptions_without_repeats(
    tmp_path: Path,
) -> None:
    fixture = await _prepare_patch_fixture(tmp_path)
    traces = _TraceRepository()
    write_calls: list[str] = []
    reconciliation_calls: list[str] = []
    gateway = _ScriptedChatModel(
        plans=[
            {
                "rationale": "同一计划先完成两次只读，再执行一次确定性写入。",
                "nodes": [
                    {
                        "node_id": "read_structure_first",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取一次结构。",
                        "input_data": {},
                    },
                    {
                        "node_id": "read_structure_second",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "按同一计划再次读取结构。",
                        "input_data": {},
                        "dependencies": ["read_structure_first"],
                    },
                    {
                        "node_id": "apply_patch",
                        "kind": "tool",
                        "capability_name": "apply_manuscript_patch",
                        "objective": "只写入一次确定性正文补丁。",
                        "input_data": fixture.plan_input,
                        "dependencies": ["read_structure_second"],
                    },
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "两次恢复后，同一计划已完成且正文只写入一次。",
            "issues": [],
            "should_replan": False,
        },
    )

    async def counted_write(
        input_data: BaseModel,
        invocation: InvocationContext,
        context: CapabilityContext,
    ) -> BaseModel:
        write_calls.append(input_data.model_dump_json())
        return await apply_manuscript_patch.run(input_data, invocation, context)

    async def counted_reconcile(
        input_data: BaseModel,
        invocation: InvocationContext,
        context: CapabilityContext,
    ) -> ToolReconciliationResult:
        reconciliation_calls.append(input_data.model_dump_json())
        return await apply_manuscript_patch.reconcile(
            input_data,
            invocation,
            context,
        )

    builder = _write_and_read_runtime_builder(
        root=tmp_path,
        gateway=gateway,
        traces=traces,
        write_handler=counted_write,
        reconciler=counted_reconcile,
    )
    result = await GeneralAgentRecoveryHarness(
        runtime_builder=builder,
        fault_adapter=FaultPressureAdapter(
            JsonFaultTriggerStore(tmp_path / "fault_pressure")
        ),
    ).execute(
        user_goal="按已确定方案读取结构并修改正文。",
        plan_id="fault_ordered_multiple_interruptions",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.PLAN_CREATED,
                once=True,
            ),
            FaultStep(
                ordinal=2,
                point=FaultPoint.RESOURCE_WRITE_APPLIED,
                once=True,
            ),
        ),
    )
    assert result.triggered_ordinals == (1, 2)
    assert result.recover_interrupted_count == 2
    assert len(result.interrupted_runs) == 2
    assert {item.run_id for item in result.interrupted_runs} == {
        result.interrupted_run.run_id
    }
    assert {item.conversation_id for item in result.interrupted_runs} == {
        result.interrupted_run.conversation_id
    }
    assert {item.plan_revision for item in result.interrupted_runs} == {
        result.interrupted_run.plan_revision
    }
    assert result.recovered_run.run_id == result.interrupted_run.run_id
    assert result.recovered_run.conversation_id == (
        result.interrupted_run.conversation_id
    )
    assert result.recovered_run.status is GeneralAgentRunStatus.COMPLETED
    assert result.plan_before_sha256 == result.plan_after_sha256
    assert set(result.interrupted_run.memory_refs).issubset(
        result.recovered_run.memory_refs
    )
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    assert len(write_calls) == 1
    assert len(reconciliation_calls) == 1
    assert (
        await fixture.chapter_service.read_chapter(fixture.chapter_id)
    ).markdown == fixture.expected_content

    owner = CapabilityResultOwner(
        conversation_id=result.recovered_run.conversation_id,
        run_id=result.recovered_run.run_id,
    )
    records = await in_memory_capability_result_repository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(owner)
    assert len(records) == 2
    assert len({record.result_id for record in records}) == 2
    assert {record.identity.node_id for record in records} == {
        "read_structure_first",
        "read_structure_second",
    }
    assert (
        sum(
            trace.capability_type == "tool"
            and trace.capability_name == "get_novel_structure"
            and trace.status.value == "completed"
            for trace in traces.records
        )
        == 2
    )

    effects = await JsonGeneralAgentEffectRepository(tmp_path).list_effects(
        result.recovered_run.run_id
    )
    assert [effect.status for effect in effects] == [
        EffectStatus.PREPARED,
        EffectStatus.STARTED,
        EffectStatus.RECONCILED,
    ]
    assert len({effect.effect_id for effect in effects}) == 1
    assert len({effect.attempt_id for effect in effects}) == 1
    current_nodes = [
        node
        for node in result.recovered_run.node_runs
        if node.plan_revision == result.recovered_run.plan_revision
    ]
    assert len(current_nodes) == 3
    assert len({node.node_id for node in current_nodes}) == 3
    assert len(result.recovered_run.recovery_decisions) == 2
    first_decision, second_decision = result.recovered_run.recovery_decisions
    assert first_decision.ordinal == 1
    assert first_decision.action is RecoveryAction.RESUME
    assert first_decision.reason_code == "checkpoint_resumed"
    assert first_decision.evidence["automatic_restart_count"] == 0
    assert first_decision.evidence["checkpoint_resume_count"] == 1
    assert second_decision.ordinal == 2
    assert second_decision.action is RecoveryAction.RECONCILE
    assert second_decision.reason_code == "effect_reconciled"
    assert second_decision.evidence["automatic_restart_count"] == 0
    assert second_decision.evidence["checkpoint_resume_count"] == 1
    assert set(first_decision.evidence["context_snapshot_ids"]).issubset(
        second_decision.evidence["context_snapshot_ids"]
    )
    assert second_decision.evidence["capability_result_ids"] == [
        record.result_id for record in records
    ]
    assert second_decision.evidence["reused_capability_result_ids"] == [
        record.result_id for record in records
    ]
    assert second_decision.evidence["retried_capability_result_ids"] == []


@_async_test
async def test_recovery_case_29_stops_when_official_checkpoint_is_missing(
    tmp_path: Path,
) -> None:
    traces = _TraceRepository()
    gateway = _read_gateway()
    adapter = FaultPressureAdapter(JsonFaultTriggerStore(tmp_path / "fault_pressure"))
    hook = adapter.bind_runtime(
        plan_id="fault_prepare_unrecoverable_checkpoint",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.PLAN_CREATED,
                once=True,
            ),
        ),
    )
    first_runtime = _read_runtime(tmp_path, gateway, traces, hook)
    try:
        with pytest.raises(InjectedProcessTermination):
            await first_runtime.run(user_goal="读取结构后给出结论。")
        plan = hook.resolved_plan
        assert plan is not None
        interrupted = await first_runtime.get(plan.run_identity.run_id)
    finally:
        await first_runtime.shutdown()

    await _checkpointer(tmp_path).adelete_thread(interrupted.conversation_id)

    checkpoint_adapter = FaultPressureAdapter(
        JsonFaultTriggerStore(tmp_path / "checkpoint_fault_pressure")
    )
    checkpoint_plan = checkpoint_adapter.store.load_or_create_plan(
        plan_id="fault_checkpoint_availability_validation",
        run_identity=FaultRunIdentity(
            conversation_id=interrupted.conversation_id,
            run_id=interrupted.run_id,
        ),
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.CHECKPOINT_REVISION_VALIDATION,
                once=True,
            ),
        ),
    )
    validation_runtime = _read_runtime(
        tmp_path,
        gateway,
        traces,
        checkpoint_adapter.bind(checkpoint_plan),
    )
    try:
        with pytest.raises(InjectedProcessTermination):
            await validation_runtime.recover_interrupted()
        still_interrupted = await validation_runtime.get(interrupted.run_id)
    finally:
        await validation_runtime.shutdown()

    assert still_interrupted.status is interrupted.status
    assert still_interrupted.recovery_decisions == []
    assert checkpoint_adapter.store.load(checkpoint_plan).triggered_ordinals == (1,)

    restarted = _read_runtime(
        tmp_path,
        gateway,
        traces,
        checkpoint_adapter.bind(checkpoint_plan),
    )
    try:
        assert await restarted.recover_interrupted() == 0
        stopped = await restarted.get(interrupted.run_id)
    finally:
        await restarted.shutdown()

    assert stopped.status is GeneralAgentRunStatus.FAILED
    assert stopped.resumable is False
    assert stopped.finished_at is not None
    assert stopped.final_answer == ""
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 0
    assert len(stopped.recovery_decisions) == 1
    decision = stopped.recovery_decisions[0]
    assert decision.action is RecoveryAction.STOP
    assert decision.reason_code == "checkpoint_unrecoverable"
    assert decision.checkpoint_revision is None
    assert decision.evidence["checkpoint_status"] == "missing"
    assert decision.evidence["checkpoint_id"] is None
    assert decision.evidence["checkpoint_step"] is None
    assert decision.evidence["automatic_restart_count"] == 0


@_async_test
async def test_recovery_case_29_unknown_effect_precedes_valid_checkpoint(
    tmp_path: Path,
) -> None:
    traces = _TraceRepository()
    gateway = _read_gateway()
    adapter = FaultPressureAdapter(JsonFaultTriggerStore(tmp_path / "fault_pressure"))
    hook = adapter.bind_runtime(
        plan_id="fault_prepare_unknown_effect",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.PLAN_CREATED,
                once=True,
            ),
        ),
    )
    first_runtime = _read_runtime(tmp_path, gateway, traces, hook)
    try:
        with pytest.raises(InjectedProcessTermination):
            await first_runtime.run(user_goal="读取结构后给出结论。")
        plan = hook.resolved_plan
        assert plan is not None
        interrupted = await first_runtime.get(plan.run_identity.run_id)
    finally:
        await first_runtime.shutdown()

    effect_id = f"effect_{uuid4().hex}"
    await JsonGeneralAgentEffectRepository(tmp_path).append(
        EffectRecord(
            event_id=f"effect_event_{uuid4().hex}",
            effect_id=effect_id,
            attempt_id=f"attempt_{uuid4().hex}",
            run_id=interrupted.run_id,
            plan_revision=interrupted.plan_revision,
            node_id="write_unknown",
            tool_name="apply_manuscript_patch",
            status=EffectStatus.UNKNOWN,
            input_sha256=sha256_text("不确定写入"),
            idempotency_key="unknown-effect-before-checkpoint",
            resource_scopes=["chapter_id:unknown"],
            reason="进程退出后无法确定真实写入是否发生。",
            created_at=now_iso(),
        )
    )

    restarted = _read_runtime(tmp_path, gateway, traces, None)
    try:
        assert await restarted.recover_interrupted() == 0
        stopped = await restarted.get(interrupted.run_id)
        cancelled = await restarted.resume(
            interrupted.run_id,
            effect_resolution="cancel",
        )
    finally:
        await restarted.shutdown()

    assert stopped.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert stopped.resumable is True
    assert stopped.pending_human_request is not None
    assert stopped.pending_human_request.kind == "effect_reconciliation"
    assert stopped.pending_human_request.effect_id == effect_id
    assert stopped.pending_human_request.node_id == "write_unknown"
    assert stopped.pending_human_request.tool_name == "apply_manuscript_patch"
    assert cancelled.run_id == interrupted.run_id
    assert cancelled.status is GeneralAgentRunStatus.CANCELLED
    assert cancelled.resumable is False
    assert cancelled.pending_human_request is None
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    assert len(stopped.recovery_decisions) == 1
    decision = stopped.recovery_decisions[0]
    assert decision.action is RecoveryAction.REQUIRES_HUMAN
    assert decision.reason_code == "effect_reconciliation_requires_human"
    assert decision.effect_id == effect_id
    assert decision.evidence["automatic_restart_count"] == 0


def _write_and_read_runtime_builder(
    *,
    root: Path,
    gateway: _ScriptedChatModel,
    traces: _TraceRepository,
    write_handler: _WriteHandler,
    reconciler: _Reconciler,
) -> Callable[[GeneralAgentFaultHook], GeneralAgentRuntimeService]:
    def build_runtime(hook: GeneralAgentFaultHook) -> GeneralAgentRuntimeService:
        policy = InvocationPolicyService()
        tools = _tool_registry(root, traces, policy)
        _register_tools(tools, [get_novel_structure])
        tools.register(
            ToolPlugin(
                manifest=apply_manuscript_patch.manifest.model_copy(
                    update={
                        "authorization_policy": ToolAuthorizationPolicy.NONE,
                    }
                ),
                run=write_handler,
                reconcile=reconciler,
            )
        )
        subagents = SubagentRegistry(CapabilityContext(capabilities={}), traces)
        return _runtime(
            root,
            gateway,
            tools,
            subagents,
            policy,
            traces,
            fault_hook=hook,
        )

    return build_runtime


def _read_runtime(
    root: Path,
    gateway: _ScriptedChatModel,
    traces: _TraceRepository,
    hook: GeneralAgentFaultHook | None,
) -> GeneralAgentRuntimeService:
    policy = InvocationPolicyService()
    tools = _tool_registry(root, traces, policy)
    _register_tools(tools, [get_novel_structure])
    subagents = SubagentRegistry(CapabilityContext(capabilities={}), traces)
    return _runtime(
        root,
        gateway,
        tools,
        subagents,
        policy,
        traces,
        fault_hook=hook,
    )


def _tool_registry(
    root: Path,
    traces: _TraceRepository,
    policy: InvocationPolicyService,
) -> ToolRegistry:
    storage = ProjectAssetStorageBackend(root)
    return ToolRegistry(
        CapabilityContext(
            capabilities={
                "chapter_service": ChapterService(storage),
                "outline_service": OutlineService(storage),
                "invocation_policy_service": policy,
            }
        ),
        traces,
    )


def _read_gateway() -> _ScriptedChatModel:
    return _ScriptedChatModel(
        plans=[
            {
                "rationale": "读取一次结构后给出结论。",
                "nodes": [
                    {
                        "node_id": "read_structure",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取当前结构。",
                        "input_data": {},
                    }
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "结构读取完成。",
            "issues": [],
            "should_replan": False,
        },
    )
