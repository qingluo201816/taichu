"""案例 24—25：Subagent 完整提交边界与授权等待恢复。"""

from __future__ import annotations

from tests.fakes.capability_results import in_memory_capability_result_repository

import asyncio
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

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
    GeneralAgentNodeStatus,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
    canonical_input_hash,
)
from taichu.application.services.outline_service import OutlineService
from taichu.application.subagents.contract import (
    SubagentManifest,
    SubagentPlugin,
)
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools import (
    apply_manuscript_patch,
    get_novel_structure,
    preview_manuscript_patch,
)
from taichu.application.tools._shared import sha256_text
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.artifacts import JsonIntermediateArtifactRepository
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentEffectRepository,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.recovery_harness import (
    GeneralAgentRecoveryHarness,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from tests.unit.application.general_agent.test_runtime import (
    _ScriptedChatModel,
    _TraceRepository,
    _async_test,
    _register_tools,
    _runtime,
)
from tests.fakes.agent_memory import in_memory_agent_memory_repository

_PARTIAL_MARKER = "中断半成品-禁止父级可见"
_COMPLETE_MARKER = "完整子结果-唯一提交"


class _RecoverySubagentInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_version: str


class _RecoverySubagentOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_type: str = "recovery_subagent_result"
    content: str
    upstream_version: str
    source_refs: list[str] = Field(default_factory=list)


@_async_test
async def test_recovery_case_24_discards_partial_subagent_and_commits_complete_once(
    tmp_path: Path,
) -> None:
    traces = _TraceRepository()
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    attempts: list[str] = []
    partial_fragments: list[str] = []
    partial_started = asyncio.Event()

    async def interrupted_subagent(
        _manifest: SubagentManifest,
        input_data: BaseModel,
        invocation: InvocationContext,
        context: CapabilityContext,
    ) -> BaseModel:
        del _manifest, invocation, context
        parsed = _RecoverySubagentInput.model_validate(input_data)
        attempts.append(parsed.upstream_version)
        if len(attempts) == 1:
            partial_fragments.append(_PARTIAL_MARKER)
            partial_started.set()
            await asyncio.Event().wait()
            raise AssertionError("中断后的 Subagent 不得继续形成完整结果。")
        return _RecoverySubagentOutput(
            content=_COMPLETE_MARKER,
            upstream_version=parsed.upstream_version,
            source_refs=["fixture:complete-subagent-result"],
        )

    gateway = _ScriptedChatModel(
        plans=[
            {
                "rationale": "先取得稳定上游，再让专业子智能体形成完整结论。",
                "nodes": [
                    {
                        "node_id": "read_structure",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "取得当前结构版本。",
                        "input_data": {},
                    },
                    {
                        "node_id": "complete_analysis",
                        "kind": "subagent",
                        "capability_name": "recovery_probe",
                        "objective": "基于稳定结构版本形成完整分析。",
                        "dependencies": ["read_structure"],
                        "input_data": {},
                        "input_bindings": [
                            {
                                "source_node_id": "read_structure",
                                "source_path": "structure_version",
                                "target_path": "upstream_version",
                            }
                        ],
                    },
                ],
                "final_response_guidance": "只消费完整的专业子智能体结果。",
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": f"已消费：{_COMPLETE_MARKER}",
            "issues": [],
            "should_replan": False,
        },
    )

    def build_runtime(
        hook: GeneralAgentFaultHook | None,
    ) -> GeneralAgentRuntimeService:
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
        subagents = SubagentRegistry(
            CapabilityContext(
                capabilities={
                    "tool_registry": tools,
                    "artifact_repository": JsonIntermediateArtifactRepository(
                        tmp_path
                    ),
                }
            ),
            traces,
        )
        subagents.register(
            SubagentPlugin(
                manifest=SubagentManifest(
                    name="recovery_probe",
                    label="恢复探针",
                    description="验证专业子智能体完整结果的父级提交边界。",
                    input_schema=_RecoverySubagentInput,
                    output_schema=_RecoverySubagentOutput,
                    artifact_types=frozenset({"recovery_subagent_result"}),
                    model_role="recovery_probe",
                    required_capabilities=frozenset(
                        {"tool_registry", "artifact_repository"}
                    ),
                ),
                run=interrupted_subagent,
            )
        )
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
        user_goal="读取结构并形成一次完整分析。",
        plan_id="fault_during_subagent",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.SUBAGENT_STARTED,
                once=True,
            ),
        ),
    )

    assert partial_started.is_set()
    assert partial_fragments == [_PARTIAL_MARKER]
    assert result.triggered_ordinals == (1,)
    assert result.interrupted_run.status is GeneralAgentRunStatus.EXECUTING
    assert result.recovered_run.status is GeneralAgentRunStatus.COMPLETED
    assert result.plan_before_sha256 == result.plan_after_sha256
    assert attempts == [attempts[0], attempts[0]]
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 1

    completed_tool_traces = [
        trace
        for trace in traces.records
        if trace.capability_type == "tool"
        and trace.capability_name == "get_novel_structure"
        and trace.status.value == "completed"
    ]
    completed_subagent_traces = [
        trace
        for trace in traces.records
        if trace.capability_type == "subagent"
        and trace.capability_name == "recovery_probe"
        and trace.status.value == "completed"
    ]
    assert len(completed_tool_traces) == 1
    assert len(completed_subagent_traces) == 1

    owner = CapabilityResultOwner(
        conversation_id=result.recovered_run.conversation_id,
        run_id=result.recovered_run.run_id,
    )
    records = await in_memory_capability_result_repository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(owner)
    tool_records = [
        record
        for record in records
        if record.identity.capability_kind == "tool"
        and record.identity.capability_name == "get_novel_structure"
    ]
    subagent_records = [
        record
        for record in records
        if record.identity.capability_kind == "subagent"
        and record.identity.capability_name == "recovery_probe"
    ]
    assert len(records) == 2
    assert len(tool_records) == 1
    assert len(subagent_records) == 1
    subagent_record = subagent_records[0]
    assert subagent_record.output["content"] == _COMPLETE_MARKER
    assert len(subagent_record.artifact_refs) == 1

    current_nodes = {
        node.node_id: node
        for node in result.recovered_run.node_runs
        if node.plan_revision == result.recovered_run.plan_revision
    }
    assert current_nodes["read_structure"].status is GeneralAgentNodeStatus.SUCCESS
    assert current_nodes["complete_analysis"].status is GeneralAgentNodeStatus.SUCCESS
    assert current_nodes["complete_analysis"].output == subagent_record.output
    assert (
        current_nodes["complete_analysis"].resolved_input["upstream_version"]
        == current_nodes["read_structure"].output["structure_version"]
    )

    verification_request = next(
        request
        for request in gateway.requests
        if request.task_name == "general_writing_orchestrator.verify"
    )
    assert _COMPLETE_MARKER in str(verification_request)
    assert _PARTIAL_MARKER not in str(verification_request)
    assert result.recovered_run.final_answer == f"已消费：{_COMPLETE_MARKER}"

    artifacts = list(
        (tmp_path / "derived" / "capability_artifacts").glob("artifact_*.json")
    )
    assert len(artifacts) == 1
    assert _COMPLETE_MARKER in artifacts[0].read_text(encoding="utf-8")
    assert await JsonGeneralAgentEffectRepository(tmp_path).list_effects(
        result.recovered_run.run_id
    ) == []

    assert _PARTIAL_MARKER not in result.interrupted_run.model_dump_json()
    assert _PARTIAL_MARKER not in result.recovered_run.model_dump_json()
    _assert_marker_absent_from_carriers(tmp_path, _PARTIAL_MARKER)
    memories = await in_memory_agent_memory_repository(tmp_path).query(
        include_deleted=True
    )
    assert all(_PARTIAL_MARKER not in memory.content for memory in memories)
    result_records = await in_memory_capability_result_repository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(
        CapabilityResultOwner(
            conversation_id=result.recovered_run.conversation_id,
            run_id=result.recovered_run.run_id,
        )
    )
    assert all(
        _PARTIAL_MARKER not in str(record.output)
        for record in result_records
    )


@_async_test
async def test_recovery_case_25_preserves_pending_authorization_without_writes(
    tmp_path: Path,
) -> None:
    traces = _TraceRepository()
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    outline = await outline_service.create_chapter(
        outline.volumes[0].volume_id,
        "授权恢复章",
    )
    chapter_id = outline.current_chapter_id
    assert chapter_id is not None
    original = "旧内容。等待作者决定。"
    await chapter_service.save_chapter(chapter_id, original)
    original_bytes = (
        await chapter_service.read_chapter(chapter_id)
    ).markdown.encode("utf-8")
    base_hash = sha256_text(original)
    operations = [
        {
            "operation": "replace_span",
            "start_char": 0,
            "end_char": 3,
            "text": "新内容",
        }
    ]
    plan = {
        "rationale": "先冻结预览，再等待作者授权同一目标写入。",
        "nodes": [
            {
                "node_id": "preview_patch",
                "kind": "tool",
                "capability_name": "preview_manuscript_patch",
                "objective": "生成确定性正文修改预览。",
                "input_data": {
                    "chapter_id": chapter_id,
                    "base_content_sha256": base_hash,
                    "operations": operations,
                },
            },
            {
                "node_id": "apply_patch",
                "kind": "tool",
                "capability_name": "apply_manuscript_patch",
                "objective": "仅在作者授权后应用同一预览。",
                "dependencies": ["preview_patch"],
                "input_data": {
                    "chapter_id": chapter_id,
                    "base_content_sha256": base_hash,
                    "operations": operations,
                },
                "input_bindings": [
                    {
                        "source_node_id": "preview_patch",
                        "source_path": "patch_id",
                        "target_path": "patch_id",
                    },
                    {
                        "source_node_id": "preview_patch",
                        "source_path": "expected_content_sha256",
                        "target_path": "expected_content_sha256",
                    },
                    {
                        "source_node_id": "preview_patch",
                        "source_path": "normalized_operations",
                        "target_path": "operations",
                    },
                ],
            },
        ],
    }
    gateway = _ScriptedChatModel(
        plans=[plan],
        verification={
            "outcome": "satisfied",
            "final_answer": "作者授权后才允许写入。",
            "issues": [],
            "should_replan": False,
        },
    )

    def build_runtime(
        hook: GeneralAgentFaultHook | None,
    ) -> GeneralAgentRuntimeService:
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
        _register_tools(
            tools,
            [preview_manuscript_patch, apply_manuscript_patch],
        )
        subagents = SubagentRegistry(
            CapabilityContext(capabilities={}),
            traces,
        )
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
        user_goal="先预览，再等待我授权修改目标章节。",
        plan_id="fault_waiting_authorization",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.AUTHORIZATION_REQUEST_DURABLE,
                once=True,
            ),
        ),
    )

    assert result.triggered_ordinals == (1,)
    assert result.recover_interrupted_count == 0
    assert result.interrupted_run.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert result.recovered_run.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert result.recovered_run == result.interrupted_run
    assert result.plan_before_sha256 == result.plan_after_sha256
    assert (
        result.recovered_run.pending_human_request
        == result.interrupted_run.pending_human_request
    )
    request = result.recovered_run.pending_human_request
    assert request is not None
    assert request.kind == "write_authorization"
    assert request.node_id == "apply_patch"
    assert request.tool_name == "apply_manuscript_patch"
    assert request.resource_scopes == [f"chapter_id:{chapter_id}"]
    assert request.input_sha256 == canonical_input_hash(request.input_summary)

    interrupted_nodes = {
        node.node_id: node
        for node in result.interrupted_run.node_runs
        if node.plan_revision == result.interrupted_run.plan_revision
    }
    recovered_nodes = {
        node.node_id: node
        for node in result.recovered_run.node_runs
        if node.plan_revision == result.recovered_run.plan_revision
    }
    assert interrupted_nodes["preview_patch"].status is GeneralAgentNodeStatus.SUCCESS
    assert recovered_nodes["preview_patch"].output == interrupted_nodes[
        "preview_patch"
    ].output
    assert recovered_nodes["apply_patch"].status is GeneralAgentNodeStatus.WAITING_HUMAN
    assert request.input_summary == recovered_nodes["apply_patch"].resolved_input
    assert request.input_summary["patch_id"] == recovered_nodes[
        "preview_patch"
    ].output["patch_id"]
    assert request.input_summary["expected_content_sha256"] == recovered_nodes[
        "preview_patch"
    ].output["expected_content_sha256"]
    assert request.input_summary["chapter_id"] == chapter_id

    owner = CapabilityResultOwner(
        conversation_id=result.recovered_run.conversation_id,
        run_id=result.recovered_run.run_id,
    )
    records = await in_memory_capability_result_repository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(owner)
    assert len(records) == 1
    assert records[0].identity.capability_name == "preview_manuscript_patch"
    assert records[0].output == recovered_nodes["preview_patch"].output

    assert [item.task_name for item in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    assert [item.task_name for item in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 0
    assert (
        sum(
            trace.capability_type == "tool"
            and trace.capability_name == "preview_manuscript_patch"
            and trace.status.value == "completed"
            for trace in traces.records
        )
        == 1
    )
    assert not any(
        trace.capability_type == "tool"
        and trace.capability_name == "apply_manuscript_patch"
        for trace in traces.records
    )
    assert await JsonGeneralAgentEffectRepository(tmp_path).list_effects(
        result.recovered_run.run_id
    ) == []
    assert (
        await chapter_service.read_chapter(chapter_id)
    ).markdown.encode("utf-8") == original_bytes

    # WAITING_HUMAN 只有在官方 interrupt 已提交后才成为可见投影；
    # 进程随后终止时，作者的一次批准必须直接消费该 interrupt。
    resumed_runtime = build_runtime(None)
    try:
        config = {
            "configurable": {
                "thread_id": result.interrupted_run.conversation_id,
            }
        }
        before_resume = await resumed_runtime._graph.aget_state(config)  # noqa: SLF001
        assert len(before_resume.interrupts) == 1
        assert before_resume.interrupts[0].value["request_id"] == request.request_id

        completed = await resumed_runtime.resume(
            result.interrupted_run.run_id,
            approve=True,
        )

        assert completed.status is GeneralAgentRunStatus.COMPLETED
        assert completed.pending_human_request is None
        after_resume = await resumed_runtime._graph.aget_state(config)  # noqa: SLF001
        assert after_resume.interrupts == ()
        assert (
            await chapter_service.read_chapter(chapter_id)
        ).markdown.startswith("新内容")
    finally:
        await resumed_runtime.shutdown()


def _assert_marker_absent_from_carriers(root: Path, marker: str) -> None:
    carrier_roots = {
        "artifact": root / "derived" / "capability_artifacts",
    }
    encoded = marker.encode("utf-8")
    for label, carrier_root in carrier_roots.items():
        if not carrier_root.exists():
            continue
        for path in carrier_root.rglob("*"):
            if path.is_file():
                assert encoded not in path.read_bytes(), (
                    f"{label} 载体泄漏了 Subagent 半成品：{path}"
                )
