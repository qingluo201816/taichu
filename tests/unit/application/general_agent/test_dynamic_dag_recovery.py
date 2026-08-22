"""动态能力 LangGraph 子图与真实写副作用恢复测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
)
from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.faults import (
    GeneralAgentFaultContext,
    GeneralAgentFaultPoint,
    InjectedProcessTermination,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentPlanNode,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.recovery import EffectStatus
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
    preview_manuscript_patch,
    read_manuscript,
)
from taichu.application.tools._shared import sha256_text
from taichu.application.tools.contract import ToolPlugin
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentCapabilityResultRepository,
    JsonGeneralAgentEffectRepository,
    JsonLangGraphCheckpointSaver,
)
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend


class _InjectedProcessCrash(InjectedProcessTermination):
    """模拟进程在 Python 异常处理之外被强制终止。"""


def test_capability_graph_resumes_failed_node_without_rerunning_success_node(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        chapter_service, outline_service, chapter_id = await _chapter_services(tmp_path)
        policy = InvocationPolicyService()
        calls = {"read": 0, "search": 0}
        crash_search = True

        async def counted_read(input_data, invocation, capabilities):
            calls["read"] += 1
            return await read_manuscript.run(input_data, invocation, capabilities)

        async def unstable_search(input_data, invocation, capabilities):
            nonlocal crash_search
            calls["search"] += 1
            if crash_search:
                raise _InjectedProcessCrash()
            return await get_novel_structure.run(input_data, invocation, capabilities)

        registry = ToolRegistry(
            CapabilityContext(
                capabilities={
                    "chapter_service": chapter_service,
                    "outline_service": outline_service,
                    "invocation_policy_service": policy,
                }
            )
        )
        registry.register(
            ToolPlugin(manifest=read_manuscript.manifest, run=counted_read)
        )
        registry.register(
            ToolPlugin(manifest=get_novel_structure.manifest, run=unstable_search)
        )
        run = _run(
            nodes=[
                GeneralAgentPlanNode(
                    node_id="read_chapter",
                    kind=GeneralAgentNodeKind.TOOL,
                    capability_name="read_manuscript",
                    objective="读取章节。",
                    input_data={"chapter_ids": [chapter_id]},
                ),
                GeneralAgentPlanNode(
                    node_id="search_chapter",
                    kind=GeneralAgentNodeKind.TOOL,
                    capability_name="get_novel_structure",
                    objective="再次读取卷章结构。",
                    input_data={},
                    dependencies=["read_chapter"],
                ),
            ]
        )
        saver = JsonLangGraphCheckpointSaver(tmp_path)
        first = _executor(registry, policy, saver, tmp_path)

        with pytest.raises(_InjectedProcessCrash):
            await first.execute(run, checkpoint=_checkpoint)

        assert calls == {"read": 1, "search": 1}
        crash_search = False
        restored = _executor(
            registry,
            policy,
            JsonLangGraphCheckpointSaver(tmp_path),
            tmp_path,
        )
        completed = await restored.execute(run, checkpoint=_checkpoint)

        assert calls == {"read": 1, "search": 2}
        assert all(
            node.status is GeneralAgentNodeStatus.SUCCESS
            for node in completed.node_runs
            if node.plan_revision == 1
        )

    asyncio.run(scenario())


def test_real_manuscript_write_is_reconciled_after_crash_without_duplicate(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        chapter_service, _, chapter_id = await _chapter_services(tmp_path)
        policy = InvocationPolicyService()
        registry = _write_registry(chapter_service, policy)
        invocation = InvocationContext(
            task_id="conversation-write-recovery",
            run_id="general_run_20260720_050505_abcdef",
            caller_type="orchestrator",
            caller_name="general_writing_orchestrator",
        )
        preview = await registry.invoke(
            "preview_manuscript_patch",
            {
                "chapter_id": chapter_id,
                "base_content_sha256": sha256_text(
                    (await chapter_service.read_chapter(chapter_id)).markdown
                ),
                "operations": [
                    {
                        "operation": "replace_span",
                        "start_char": 0,
                        "end_char": 3,
                        "text": "新内容",
                    }
                ],
            },
            invocation,
        )
        preview_output = preview.output.model_dump(mode="json")
        input_data = {
            "patch_id": preview_output["patch_id"],
            "chapter_id": chapter_id,
            "base_content_sha256": preview_output["base_content_sha256"],
            "expected_content_sha256": preview_output["expected_content_sha256"],
            "operations": preview_output["normalized_operations"],
            "idempotency_key": "recovery-real-write-0001",
        }
        node = GeneralAgentPlanNode(
            node_id="apply_patch",
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="apply_manuscript_patch",
            objective="应用作者确认的正文补丁。",
            input_data=input_data,
        )
        run = _run(nodes=[node]).model_copy(
            update={
                "node_runs": [
                    GeneralAgentNodeRun(
                        node_id=node.node_id,
                        plan_revision=1,
                        kind=node.kind,
                        capability_name=node.capability_name,
                        objective=node.objective,
                        status=GeneralAgentNodeStatus.PENDING,
                        authorization_grant_id="author_frozen_from_confirmation",
                        authorization_approved=True,
                        authorization_resource_scopes=[f"chapter_id:{chapter_id}"],
                    )
                ]
            }
        )
        class ResourceWriteCrashHook:
            crashed = False
            context: GeneralAgentFaultContext | None = None

            def on_fault_point(
                self,
                *,
                point: GeneralAgentFaultPoint,
                context: GeneralAgentFaultContext,
            ) -> None:
                if (
                    point is GeneralAgentFaultPoint.RESOURCE_WRITE_APPLIED
                    and not self.crashed
                ):
                    self.crashed = True
                    self.context = context
                    raise _InjectedProcessCrash()

        hook = ResourceWriteCrashHook()

        saver = JsonLangGraphCheckpointSaver(tmp_path)
        effects = JsonGeneralAgentEffectRepository(tmp_path)
        results = JsonGeneralAgentCapabilityResultRepository(
            tmp_path / "capability_results"
        )
        first = DynamicDagExecutor(
            tool_registry=registry,
            subagent_registry=_subagents(policy),
            policy_service=policy,
            graph_checkpointer=saver,
            effect_repository=effects,
            capability_result_repository=results,
            capability_handler_identities=_handler_identities(registry),
            fault_hook=hook,
        )

        with pytest.raises(_InjectedProcessCrash):
            await first.execute(run, checkpoint=_checkpoint)

        after_crash = await chapter_service.read_chapter(chapter_id)
        assert after_crash.markdown == "新内容。秦阳走入山门。"
        assert (await effects.list_effects(run.run_id))[
            -1
        ].status is EffectStatus.STARTED
        assert hook.context is not None
        assert hook.context.durable_identity == (
            await effects.list_effects(run.run_id)
        )[-1].effect_id

        restarted_policy = InvocationPolicyService()
        restarted_registry = _write_registry(chapter_service, restarted_policy)
        restarted_effects = JsonGeneralAgentEffectRepository(tmp_path)
        restored = DynamicDagExecutor(
            tool_registry=restarted_registry,
            subagent_registry=_subagents(restarted_policy),
            policy_service=restarted_policy,
            graph_checkpointer=JsonLangGraphCheckpointSaver(tmp_path),
            effect_repository=restarted_effects,
            capability_result_repository=(
                JsonGeneralAgentCapabilityResultRepository(
                    tmp_path / "capability_results"
                )
            ),
            capability_handler_identities=(
                _handler_identities(restarted_registry)
            ),
        )
        completed = await restored.execute(run, checkpoint=_checkpoint)

        current = [item for item in completed.node_runs if item.plan_revision == 1]
        assert current[0].status is GeneralAgentNodeStatus.SUCCESS
        assert current[0].effect_status == EffectStatus.RECONCILED
        assert current[0].duplicate_execution_protected
        assert (await chapter_service.read_chapter(chapter_id)).markdown == (
            "新内容。秦阳走入山门。"
        )
        assert [
            event.status for event in await restarted_effects.list_effects(run.run_id)
        ] == [
            EffectStatus.PREPARED,
            EffectStatus.STARTED,
            EffectStatus.RECONCILED,
        ]
        assert await results.list_for_run(
            CapabilityResultOwner(
                conversation_id=run.conversation_id,
                run_id=run.run_id,
            )
        ) == ()

    asyncio.run(scenario())


async def _chapter_services(
    root: Path,
) -> tuple[ChapterService, OutlineService, str]:
    storage = ProjectAssetStorageBackend(root)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    outline = await outline_service.create_chapter(
        outline.volumes[0].volume_id,
        "开端",
    )
    chapter_id = outline.current_chapter_id
    assert chapter_id is not None
    await chapter_service.save_chapter(chapter_id, "旧内容。秦阳走入山门。")
    return chapter_service, outline_service, chapter_id


def _write_registry(
    chapter_service: ChapterService,
    policy: InvocationPolicyService,
) -> ToolRegistry:
    registry = ToolRegistry(
        CapabilityContext(
            capabilities={
                "chapter_service": chapter_service,
                "invocation_policy_service": policy,
            }
        )
    )
    registry.register(
        ToolPlugin(
            manifest=preview_manuscript_patch.manifest,
            run=preview_manuscript_patch.run,
        )
    )
    registry.register(
        ToolPlugin(
            manifest=apply_manuscript_patch.manifest,
            run=apply_manuscript_patch.run,
            reconcile=apply_manuscript_patch.reconcile,
        )
    )
    return registry


def _executor(
    registry: ToolRegistry,
    policy: InvocationPolicyService,
    saver: JsonLangGraphCheckpointSaver,
    root: Path,
) -> DynamicDagExecutor:
    return DynamicDagExecutor(
        tool_registry=registry,
        subagent_registry=_subagents(policy),
        policy_service=policy,
        graph_checkpointer=saver,
        effect_repository=JsonGeneralAgentEffectRepository(root),
        capability_result_repository=(
            JsonGeneralAgentCapabilityResultRepository(
                root / "capability_results"
            )
        ),
        capability_handler_identities=_handler_identities(registry),
    )


def _handler_identities(
    registry: ToolRegistry,
) -> dict[tuple[str, str], str]:
    return {
        ("tool", manifest.name): f"test:tool:{manifest.name}"
        for manifest in registry.list_manifests()
    }


def _subagents(policy: InvocationPolicyService) -> SubagentRegistry:
    return SubagentRegistry(
        CapabilityContext(capabilities={"invocation_policy_service": policy})
    )


def _run(*, nodes: list[GeneralAgentPlanNode]) -> GeneralAgentRun:
    created_at = now_iso()
    return GeneralAgentRun(
        run_id="general_run_20260720_050505_abcdef",
        task_id="conversation-recovery-test",
        conversation_id="conversation-recovery-test",
        request_index=1,
        user_goal="执行恢复测试。",
        status=GeneralAgentRunStatus.EXECUTING,
        plan=GeneralAgentExecutionPlan(rationale="验证恢复边界。", nodes=nodes),
        plan_revision=1,
        created_at=created_at,
        updated_at=created_at,
        started_at=created_at,
    )


async def _checkpoint(run: GeneralAgentRun, _event: str) -> GeneralAgentRun:
    return run
