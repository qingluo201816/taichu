"""CapabilityResult 接入动态 DAG 后的提交窄窗与恢复顺序测试。"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

from langgraph.checkpoint.memory import InMemorySaver
import pytest
from pydantic import BaseModel, ConfigDict

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
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentNodeKind,
    GeneralAgentNodeStatus,
    GeneralAgentPlanNode,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.recovery import (
    GeneralAgentRecoveryCoordinator,
)
from taichu.application.general_agent.service import (
    GeneralAgentRuntimeService,
)
from taichu.application.invocations.models import now_iso
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools.contract import ToolManifest, ToolPlugin
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentCapabilityResultRepository,
    JsonGeneralAgentEffectRepository,
    JsonLangGraphCheckpointSaver,
)


class _ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str


class _ReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    source_refs: list[str]


class _InjectedCrash(InjectedProcessTermination):
    """模拟 completed record/index 已提交、节点尚未投影时进程退出。"""


def test_committed_read_only_result_is_reused_without_invoking_again(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        policy = InvocationPolicyService()
        calls = 0

        async def counted_read(input_data, _invocation, _capabilities):
            nonlocal calls
            calls += 1
            return _ReadOutput(
                content=f"章节：{input_data.chapter_id}",
                source_refs=[f"manuscript:{input_data.chapter_id}"],
            )

        manifest = ToolManifest(
            name="read_fixture",
            description="读取固定章节。",
            input_schema=_ReadInput,
            output_schema=_ReadOutput,
        )
        tool_registry = ToolRegistry(
            CapabilityContext(
                capabilities={"invocation_policy_service": policy}
            )
        )
        tool_registry.register(ToolPlugin(manifest=manifest, run=counted_read))
        subagents = SubagentRegistry(CapabilityContext(capabilities={}))
        results = JsonGeneralAgentCapabilityResultRepository(
            tmp_path / "capability_results"
        )
        checkpointer = JsonLangGraphCheckpointSaver(tmp_path)
        class CommitCrashHook:
            crashed = False
            context: GeneralAgentFaultContext | None = None

            def on_fault_point(
                self,
                *,
                point: GeneralAgentFaultPoint,
                context: GeneralAgentFaultContext,
            ) -> None:
                if (
                    point
                    is GeneralAgentFaultPoint.CAPABILITY_RESULT_COMMITTED
                    and not self.crashed
                ):
                    self.crashed = True
                    self.context = context
                    raise _InjectedCrash()

        hook = CommitCrashHook()

        first = DynamicDagExecutor(
            tool_registry=tool_registry,
            subagent_registry=subagents,
            policy_service=policy,
            graph_checkpointer=checkpointer,
            effect_repository=JsonGeneralAgentEffectRepository(tmp_path),
            capability_result_repository=results,
            capability_handler_identities={
                ("tool", "read_fixture"): (
                    f"{counted_read.__module__}:{counted_read.__qualname__}"
                )
            },
            fault_hook=hook,
        )
        run = _run()

        with pytest.raises(_InjectedCrash):
            await first.execute(run, checkpoint=_checkpoint)

        owner = CapabilityResultOwner(
            conversation_id=run.conversation_id,
            run_id=run.run_id,
        )
        committed = await results.list_for_run(owner)
        assert calls == 1
        assert len(committed) == 1
        assert hook.context is not None
        assert hook.context.durable_identity == committed[0].result_id

        restored = DynamicDagExecutor(
            tool_registry=tool_registry,
            subagent_registry=subagents,
            policy_service=policy,
            graph_checkpointer=JsonLangGraphCheckpointSaver(tmp_path),
            effect_repository=JsonGeneralAgentEffectRepository(tmp_path),
            capability_result_repository=(
                JsonGeneralAgentCapabilityResultRepository(
                    tmp_path / "capability_results"
                )
            ),
            capability_handler_identities={
                ("tool", "read_fixture"): (
                    f"{counted_read.__module__}:{counted_read.__qualname__}"
                )
            },
        )
        completed = await restored.execute(run, checkpoint=_checkpoint)

        assert calls == 1
        current = [
            item
            for item in completed.node_runs
            if item.plan_revision == run.plan_revision
        ]
        assert current[0].status is GeneralAgentNodeStatus.SUCCESS
        assert current[0].output == committed[0].output
        assert committed[0].result_id in current[0].reconciliation_reason
        assert committed[0].content_sha256 in current[0].reconciliation_reason

    asyncio.run(scenario())


@pytest.mark.anyio
async def test_recovery_coordinator_reads_evidence_in_fixed_order() -> None:
    order: list[str] = []
    run = _run()

    class RunRepository:
        async def get(self, run_id: str) -> GeneralAgentRun | None:
            order.append("owner")
            assert run_id == run.run_id
            return run

    class EffectRepository:
        async def list_effects(self, run_id: str) -> list[object]:
            order.append("effect")
            assert run_id == run.run_id
            return []

    class Checkpointer:
        def inspect_thread(self, run_id: str) -> SimpleNamespace:
            order.append("checkpoint")
            assert run_id == run.run_id
            return SimpleNamespace(
                current_revision=3,
                available_revisions=[1, 2, 3],
                integrity_status="valid",
                recovered_from_revision=None,
                damage_warnings=[],
            )

    class ResultRepository:
        async def list_for_run(
            self,
            owner: CapabilityResultOwner,
        ) -> tuple[object, ...]:
            order.append("result")
            assert owner == CapabilityResultOwner(
                conversation_id=run.conversation_id,
                run_id=run.run_id,
            )
            return ()

    class ContextRepository:
        async def list_for_run(self, run_id: str) -> list[object]:
            order.append("context")
            assert run_id == run.run_id
            return []

    coordinator = GeneralAgentRecoveryCoordinator(
        run_repository=RunRepository(),  # type: ignore[arg-type]
        effect_repository=EffectRepository(),  # type: ignore[arg-type]
        graph_checkpointer=Checkpointer(),  # type: ignore[arg-type]
        capability_result_repository=ResultRepository(),  # type: ignore[arg-type]
        context_snapshot_repository=ContextRepository(),  # type: ignore[arg-type]
    )

    prepared = await coordinator.prepare(run)

    assert prepared.owner == CapabilityResultOwner(
        conversation_id=run.conversation_id,
        run_id=run.run_id,
    )
    assert prepared.checkpoint_revision == 3
    assert order == ["owner", "effect", "checkpoint", "result", "context"]


def test_runtime_composition_requires_one_shared_capability_result_repository(
    tmp_path: Path,
) -> None:
    executor_parameter = inspect.signature(
        DynamicDagExecutor
    ).parameters["capability_result_repository"]
    service_parameter = inspect.signature(
        GeneralAgentRuntimeService
    ).parameters["capability_result_repository"]
    assert executor_parameter.default is inspect.Parameter.empty
    assert service_parameter.default is inspect.Parameter.empty

    policy = InvocationPolicyService()
    tools = ToolRegistry(
        CapabilityContext(
            capabilities={"invocation_policy_service": policy}
        )
    )
    subagents = SubagentRegistry(CapabilityContext(capabilities={}))
    executor_results = JsonGeneralAgentCapabilityResultRepository(
        tmp_path / "executor_results"
    )
    service_results = JsonGeneralAgentCapabilityResultRepository(
        tmp_path / "service_results"
    )
    executor = DynamicDagExecutor(
        tool_registry=tools,
        subagent_registry=subagents,
        policy_service=policy,
        capability_result_repository=executor_results,
        capability_handler_identities={},
    )

    with pytest.raises(ValueError, match="同一 CapabilityResult"):
        GeneralAgentRuntimeService(
            repository=object(),  # type: ignore[arg-type]
            event_center=GeneralAgentEventCenter(),
            orchestrator=object(),  # type: ignore[arg-type]
            executor=executor,
            policy_service=policy,
            memory_service=object(),  # type: ignore[arg-type]
            context_assembler=object(),  # type: ignore[arg-type]
            capability_result_repository=service_results,
            graph_checkpointer=InMemorySaver(),
            effect_repository=object(),  # type: ignore[arg-type]
            context_snapshot_repository=object(),  # type: ignore[arg-type]
            llm_replay_repository=object(),  # type: ignore[arg-type]
        )


def _run() -> GeneralAgentRun:
    timestamp = now_iso()
    return GeneralAgentRun(
        run_id="general_run_20260730_120000_abcdef",
        task_id="conversation_capability_result",
        conversation_id="conversation_capability_result",
        request_index=1,
        user_goal="读取固定章节。",
        status=GeneralAgentRunStatus.EXECUTING,
        plan=GeneralAgentExecutionPlan(
            rationale="验证结果提交后的精确恢复。",
            nodes=[
                GeneralAgentPlanNode(
                    node_id="read_chapter",
                    kind=GeneralAgentNodeKind.TOOL,
                    capability_name="read_fixture",
                    objective="读取章节。",
                    input_data={"chapter_id": "chapter_001"},
                )
            ],
        ),
        plan_revision=1,
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp,
    )


async def _checkpoint(run: GeneralAgentRun, _event: str) -> GeneralAgentRun:
    return run
