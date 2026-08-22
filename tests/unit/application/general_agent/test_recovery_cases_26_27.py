"""案例 26—27：真实写后对账与校验启动后恢复。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
)
from taichu.application.evaluations.general_agent_benchmark.faults import (
    FaultPoint,
    FaultPressureAdapter,
    FaultStep,
    JsonFaultTriggerStore,
)
from taichu.application.general_agent.faults import GeneralAgentFaultHook
from taichu.application.general_agent.models import (
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.recovery import (
    EffectStatus,
    RecoveryAction,
)
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.invocations.models import InvocationContext
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
from taichu.application.tools._manuscript import (
    normalize_and_apply_patch,
    patch_id,
)
from taichu.application.tools._shared import sha256_text
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolPlugin,
    ToolReconciliationResult,
)
from taichu.application.tools.models import ManuscriptPatchOperation
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.evaluations.general_agent_benchmark.recovery_harness import (
    GeneralAgentRecoveryHarness,
)
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentCapabilityResultRepository,
    JsonGeneralAgentEffectRepository,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from tests.unit.application.general_agent.test_runtime import (
    _ScriptedGateway,
    _TraceRepository,
    _async_test,
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
async def test_recovery_case_26_reconciles_real_write_without_reapplying(
    tmp_path: Path,
) -> None:
    fixture = await _prepare_patch_fixture(tmp_path)
    traces = _TraceRepository()
    write_calls: list[str] = []
    reconciliation_calls: list[str] = []
    gateway = _write_gateway(fixture.plan_input)

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

    build_runtime = _write_runtime_builder(
        root=tmp_path,
        gateway=gateway,
        traces=traces,
        chapter_service=fixture.chapter_service,
        write_handler=counted_write,
        reconciler=counted_reconcile,
    )
    result = await GeneralAgentRecoveryHarness(
        runtime_builder=build_runtime,
        fault_adapter=FaultPressureAdapter(
            JsonFaultTriggerStore(tmp_path / "fault_pressure")
        ),
    ).execute(
        user_goal="把目标章节中的旧句替换成已经确定的新句。",
        plan_id="fault_after_real_write",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.RESOURCE_WRITE_APPLIED,
                once=True,
            ),
        ),
    )

    assert result.triggered_ordinals == (1,)
    assert result.recover_interrupted_count == 1
    assert result.interrupted_run.status is GeneralAgentRunStatus.EXECUTING
    assert result.recovered_run.status is GeneralAgentRunStatus.COMPLETED
    assert result.recovered_run.run_id == result.interrupted_run.run_id
    assert result.plan_before_sha256 == result.plan_after_sha256
    assert len(write_calls) == 1
    assert len(reconciliation_calls) == 1
    assert (
        await fixture.chapter_service.read_chapter(fixture.chapter_id)
    ).markdown == fixture.expected_content

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
    assert len({effect.input_sha256 for effect in effects}) == 1
    assert len({effect.idempotency_key for effect in effects}) == 1
    assert len({tuple(effect.resource_scopes) for effect in effects}) == 1
    terminal_effect = effects[-1]
    assert terminal_effect.output["content_sha256"] == fixture.expected_hash
    assert terminal_effect.evidence["actual_content_sha256"] == (
        fixture.expected_hash
    )
    assert terminal_effect.evidence["expected_content_sha256"] == (
        fixture.expected_hash
    )

    current_node = _current_node(result.recovered_run, "apply_patch")
    assert current_node.status is GeneralAgentNodeStatus.SUCCESS
    assert current_node.effect_id == terminal_effect.effect_id
    assert current_node.effect_status == EffectStatus.RECONCILED.value
    assert current_node.output["content_sha256"] == fixture.expected_hash
    assert current_node.duplicate_execution_protected is True
    owner = CapabilityResultOwner(
        conversation_id=result.recovered_run.conversation_id,
        run_id=result.recovered_run.run_id,
    )
    assert await JsonGeneralAgentCapabilityResultRepository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(owner) == ()
    assert (
        sum(
            trace.capability_type == "tool"
            and trace.capability_name == "apply_manuscript_patch"
            and trace.status.value == "completed"
            for trace in traces.records
        )
        == 1
    )

    assert len(result.recovered_run.recovery_decisions) == 1
    decision = result.recovered_run.recovery_decisions[0]
    assert decision.action is RecoveryAction.RECONCILE
    assert decision.reason_code == "effect_reconciled"
    assert decision.effect_id == terminal_effect.effect_id
    assert decision.checkpoint_revision is not None
    assert decision.checkpoint_revision >= 1
    assert decision.evidence["run_checkpoint_revision"] == (
        result.interrupted_run.checkpoint_revision
    )
    assert decision.evidence["reconciliation_status"] == "succeeded"
    assert decision.evidence["resource_content_sha256"] == fixture.expected_hash


@_async_test
async def test_recovery_case_26_stops_for_human_when_resource_is_ambiguous(
    tmp_path: Path,
) -> None:
    fixture = await _prepare_patch_fixture(tmp_path)
    traces = _TraceRepository()
    write_calls: list[str] = []
    reconciliation_calls: list[str] = []
    gateway = _write_gateway(fixture.plan_input)
    build_count = 0
    ambiguous_content = "外部并发修改后的第三种正文。"

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

    base_builder = _write_runtime_builder(
        root=tmp_path,
        gateway=gateway,
        traces=traces,
        chapter_service=fixture.chapter_service,
        write_handler=counted_write,
        reconciler=counted_reconcile,
    )

    def build_runtime(hook: GeneralAgentFaultHook) -> GeneralAgentRuntimeService:
        nonlocal build_count
        build_count += 1
        if build_count == 2:
            fixture.chapter_path.write_text(ambiguous_content, encoding="utf-8")
        return base_builder(hook)

    result = await GeneralAgentRecoveryHarness(
        runtime_builder=build_runtime,
        fault_adapter=FaultPressureAdapter(
            JsonFaultTriggerStore(tmp_path / "fault_pressure")
        ),
    ).execute(
        user_goal="把目标章节中的旧句替换成已经确定的新句。",
        plan_id="fault_after_real_write_with_ambiguous_resource",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.RESOURCE_WRITE_APPLIED,
                once=True,
            ),
        ),
    )

    assert result.triggered_ordinals == (1,)
    assert result.recover_interrupted_count == 1
    assert result.recovered_run.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert result.recovered_run.resumable is True
    assert result.recovered_run.final_answer == ""
    assert len(write_calls) == 1
    assert len(reconciliation_calls) == 1
    assert (
        await fixture.chapter_service.read_chapter(fixture.chapter_id)
    ).markdown == ambiguous_content

    effects = await JsonGeneralAgentEffectRepository(tmp_path).list_effects(
        result.recovered_run.run_id
    )
    assert [effect.status for effect in effects] == [
        EffectStatus.PREPARED,
        EffectStatus.STARTED,
        EffectStatus.REQUIRES_HUMAN,
    ]
    assert len({effect.effect_id for effect in effects}) == 1
    assert effects[-1].evidence["actual_content_sha256"] == sha256_text(
        ambiguous_content
    )
    assert effects[-1].evidence["base_content_sha256"] == fixture.base_hash
    assert effects[-1].evidence["expected_content_sha256"] == (
        fixture.expected_hash
    )

    current_node = _current_node(result.recovered_run, "apply_patch")
    assert current_node.status is GeneralAgentNodeStatus.WAITING_HUMAN
    assert current_node.effect_status == EffectStatus.REQUIRES_HUMAN.value
    assert current_node.duplicate_execution_protected is True
    request = result.recovered_run.pending_human_request
    assert request is not None
    assert request.kind == "effect_reconciliation"
    assert request.node_id == "apply_patch"
    assert request.tool_name == "apply_manuscript_patch"
    assert request.resource_scopes == [f"chapter_id:{fixture.chapter_id}"]
    owner = CapabilityResultOwner(
        conversation_id=result.recovered_run.conversation_id,
        run_id=result.recovered_run.run_id,
    )
    assert await JsonGeneralAgentCapabilityResultRepository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(owner) == ()
    assert (
        sum(
            trace.capability_type == "tool"
            and trace.capability_name == "apply_manuscript_patch"
            and trace.status.value == "completed"
            for trace in traces.records
        )
        == 1
    )

    assert len(result.recovered_run.recovery_decisions) == 1
    decision = result.recovered_run.recovery_decisions[0]
    assert decision.action is RecoveryAction.REQUIRES_HUMAN
    assert decision.reason_code == "effect_reconciliation_requires_human"
    assert decision.effect_id == effects[-1].effect_id
    assert decision.evidence["reconciliation_status"] == "unknown"
    assert decision.evidence["resource_content_sha256"] == sha256_text(
        ambiguous_content
    )
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 0


@_async_test
async def test_recovery_case_27_resumes_same_run_verification_without_reread(
    tmp_path: Path,
) -> None:
    traces = _TraceRepository()
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    gateway = _ScriptedGateway(
        plans=[
            {
                "rationale": "只读取一次结构，然后校验结论。",
                "nodes": [
                    {
                        "node_id": "read_structure",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取当前小说结构。",
                        "input_data": {},
                    }
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "同一运行已恢复并完成最终校验。",
            "issues": [],
            "should_replan": False,
        },
    )

    def build_runtime(hook: GeneralAgentFaultHook) -> GeneralAgentRuntimeService:
        policy = InvocationPolicyService()
        tools = ToolRegistry(
            CapabilityContext(
                capabilities={
                    "chapter_service": chapter_service,
                    "outline_service": outline_service,
                    "invocation_policy_service": policy,
                }
            ),
            traces,
        )
        _register_tools(tools, [get_novel_structure])
        subagents = SubagentRegistry(CapabilityContext(capabilities={}), traces)
        return _runtime(
            tmp_path,
            gateway,
            tools,
            subagents,
            policy,
            traces,
            fault_hook=hook,
        )

    result = await GeneralAgentRecoveryHarness(
        runtime_builder=build_runtime,
        fault_adapter=FaultPressureAdapter(
            JsonFaultTriggerStore(tmp_path / "fault_pressure")
        ),
    ).execute(
        user_goal="读取结构并完成一次最终校验。",
        plan_id="fault_during_verification",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.VERIFICATION_STARTED,
                once=True,
            ),
        ),
    )

    assert result.triggered_ordinals == (1,)
    assert result.interrupted_run.status is GeneralAgentRunStatus.VERIFYING
    assert result.recovered_run.status is GeneralAgentRunStatus.COMPLETED
    assert result.recovered_run.run_id == result.interrupted_run.run_id
    assert result.plan_before_sha256 == result.plan_after_sha256
    assert result.recovered_run.final_answer == (
        "同一运行已恢复并完成最终校验。"
    )
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 1
    assert (
        sum(
            trace.capability_type == "tool"
            and trace.capability_name == "get_novel_structure"
            and trace.status.value == "completed"
            for trace in traces.records
        )
        == 1
    )
    owner = CapabilityResultOwner(
        conversation_id=result.recovered_run.conversation_id,
        run_id=result.recovered_run.run_id,
    )
    records = await JsonGeneralAgentCapabilityResultRepository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(owner)
    assert len(records) == 1
    assert records[0].identity.capability_name == "get_novel_structure"
    assert _current_node(
        result.recovered_run,
        "read_structure",
    ).output == records[0].output
    assert result.interrupted_run.verification_attempt_count == 1
    assert result.recovered_run.verification_attempt_count == 2

    assert len(result.recovered_run.recovery_decisions) == 1
    decision = result.recovered_run.recovery_decisions[0]
    assert decision.action is RecoveryAction.RESUME
    assert decision.reason_code == "verification_resumed"
    assert decision.checkpoint_revision is not None
    assert decision.checkpoint_revision >= 1
    assert decision.evidence["run_checkpoint_revision"] == (
        result.interrupted_run.checkpoint_revision
    )
    assert decision.effect_id is None
    assert decision.evidence["run_status_before_recovery"] == "verifying"
    assert decision.evidence["capability_result_ids"] == [records[0].result_id]
    assert await JsonGeneralAgentEffectRepository(tmp_path).list_effects(
        result.recovered_run.run_id
    ) == []


class _PatchFixture:
    def __init__(
        self,
        *,
        chapter_service: ChapterService,
        chapter_id: str,
        chapter_path: Path,
        plan_input: dict[str, object],
        base_hash: str,
        expected_hash: str,
        expected_content: str,
    ) -> None:
        self.chapter_service = chapter_service
        self.chapter_id = chapter_id
        self.chapter_path = chapter_path
        self.plan_input = plan_input
        self.base_hash = base_hash
        self.expected_hash = expected_hash
        self.expected_content = expected_content


async def _prepare_patch_fixture(root: Path) -> _PatchFixture:
    storage = ProjectAssetStorageBackend(root)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    outline = await outline_service.create_chapter(
        outline.volumes[0].volume_id,
        "写后恢复章",
    )
    chapter_id = outline.current_chapter_id
    assert chapter_id is not None
    original = "旧句。其余正文保持不变。"
    await chapter_service.save_chapter(chapter_id, original)
    operation = ManuscriptPatchOperation(
        operation="replace_span",
        start_char=0,
        end_char=3,
        text="新句",
    )
    normalized_operations, expected_content = normalize_and_apply_patch(
        original,
        [operation],
    )
    base_hash = sha256_text(original)
    expected_hash = sha256_text(expected_content)
    chapter = await chapter_service.read_chapter(chapter_id)
    return _PatchFixture(
        chapter_service=chapter_service,
        chapter_id=chapter_id,
        chapter_path=(
            root
            / "source"
            / chapter.chapter.markdown_path
        ),
        plan_input={
            "patch_id": patch_id(
                chapter_id,
                base_hash,
                normalized_operations,
            ),
            "chapter_id": chapter_id,
            "base_content_sha256": base_hash,
            "expected_content_sha256": expected_hash,
            "operations": [
                item.model_dump(mode="json") for item in normalized_operations
            ],
            "author_grant_id": "test_recovery_grant",
            "idempotency_key": "case26-write-once",
        },
        base_hash=base_hash,
        expected_hash=expected_hash,
        expected_content=expected_content,
    )


def _write_gateway(plan_input: dict[str, object]) -> _ScriptedGateway:
    return _ScriptedGateway(
        plans=[
            {
                "rationale": "执行已冻结输入的单次真实正文写入。",
                "nodes": [
                    {
                        "node_id": "apply_patch",
                        "kind": "tool",
                        "capability_name": "apply_manuscript_patch",
                        "objective": "应用确定性的正文补丁。",
                        "input_data": plan_input,
                    }
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "正文写入已由真实资源后态确认。",
            "issues": [],
            "should_replan": False,
        },
    )


def _write_runtime_builder(
    *,
    root: Path,
    gateway: _ScriptedGateway,
    traces: _TraceRepository,
    chapter_service: ChapterService,
    write_handler: _WriteHandler,
    reconciler: _Reconciler,
) -> Callable[[GeneralAgentFaultHook], GeneralAgentRuntimeService]:
    def build_runtime(hook: GeneralAgentFaultHook) -> GeneralAgentRuntimeService:
        policy = InvocationPolicyService()
        tools = ToolRegistry(
            CapabilityContext(
                capabilities={
                    "chapter_service": chapter_service,
                    "invocation_policy_service": policy,
                }
            ),
            traces,
        )
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


def _current_node(
    run: GeneralAgentRun,
    node_id: str,
) -> GeneralAgentNodeRun:
    return next(
        node
        for node in run.node_runs
        if node.plan_revision == run.plan_revision and node.node_id == node_id
    )
