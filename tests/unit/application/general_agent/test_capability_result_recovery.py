"""CapabilityResult 接入动态 DAG 后的提交窄窗与恢复顺序测试。"""

from __future__ import annotations

from tests.fakes.capability_results import in_memory_capability_result_repository
from tests.fakes import InMemoryGeneralAgentEffectRepository

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
import pytest
from pydantic import BaseModel, ConfigDict

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
)
from taichu.application.contracts.general_agent_tool_budget import (
    GeneralAgentToolBudgetOwner,
    GeneralAgentToolBudgetUnavailableError,
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
    GeneralAgentRunLimits,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.recovery import (
    GeneralAgentRecoveryCoordinator,
)
from taichu.application.general_agent.service import (
    GeneralAgentRuntimeService,
)
from taichu.application.invocations.models import (
    InvocationBudget,
    InvocationContext,
    now_iso,
)
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.subagents.contract import SubagentManifest, SubagentPlugin
from taichu.application.subagents.models import AgentSourceRequest
from taichu.application.subagents.runner import _collect_sources
from taichu.application.tools.contract import ToolManifest, ToolPlugin
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentEffectRepository,
)
from taichu.infrastructure.artifacts import JsonIntermediateArtifactRepository
from tests.fakes import InMemoryGeneralAgentToolBudgetRepository


class _ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str


class _ReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    source_refs: list[str]


class _EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _BudgetSubagentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_request: AgentSourceRequest


class _BudgetSubagentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["budget_probe"] = "budget_probe"
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
            CapabilityContext(capabilities={"invocation_policy_service": policy})
        )
        tool_registry.register(ToolPlugin(manifest=manifest, run=counted_read))
        subagents = SubagentRegistry(CapabilityContext(capabilities={}))
        results = in_memory_capability_result_repository(
            tmp_path / "capability_results"
        )
        checkpointer = InMemorySaver()

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
                    point is GeneralAgentFaultPoint.CAPABILITY_RESULT_COMMITTED
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
            await first.execute(
                run,
                checkpoint=_checkpoint,
                checkpointer=checkpointer,
            )

        assert run.conversation_id in checkpointer.storage
        assert run.run_id not in checkpointer.storage

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
            effect_repository=JsonGeneralAgentEffectRepository(tmp_path),
            capability_result_repository=(
                in_memory_capability_result_repository(tmp_path / "capability_results")
            ),
            capability_handler_identities={
                ("tool", "read_fixture"): (
                    f"{counted_read.__module__}:{counted_read.__qualname__}"
                )
            },
        )
        completed = await restored.execute(
            run,
            checkpoint=_checkpoint,
            checkpointer=checkpointer,
        )

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


def test_executor_parallel_tools_share_one_durable_run_budget(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        policy = InvocationPolicyService()
        budget_repository = InMemoryGeneralAgentToolBudgetRepository()
        calls: list[str] = []

        async def counted_read(input_data, _invocation, _capabilities):
            calls.append(input_data.chapter_id)
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
            CapabilityContext(capabilities={"invocation_policy_service": policy}),
            tool_budget_repository=budget_repository,
            require_tool_budget=True,
        )
        tool_registry.register(ToolPlugin(manifest=manifest, run=counted_read))
        run = _run().model_copy(
            update={
                "limits": GeneralAgentRunLimits(
                    max_total_tool_calls=1,
                    max_concurrency=2,
                ),
                "plan": GeneralAgentExecutionPlan(
                    rationale="验证并行节点共享任务级预算。",
                    nodes=[
                        GeneralAgentPlanNode(
                            node_id="read_first",
                            kind=GeneralAgentNodeKind.TOOL,
                            capability_name="read_fixture",
                            objective="读取第一章。",
                            input_data={"chapter_id": "chapter_001"},
                        ),
                        GeneralAgentPlanNode(
                            node_id="read_second",
                            kind=GeneralAgentNodeKind.TOOL,
                            capability_name="read_fixture",
                            objective="读取第二章。",
                            input_data={"chapter_id": "chapter_002"},
                        ),
                    ],
                ),
            }
        )
        executor = DynamicDagExecutor(
            tool_registry=tool_registry,
            subagent_registry=SubagentRegistry(CapabilityContext(capabilities={})),
            policy_service=policy,
            effect_repository=JsonGeneralAgentEffectRepository(tmp_path),
            capability_result_repository=(
                in_memory_capability_result_repository(tmp_path / "budget_results")
            ),
            capability_handler_identities={
                ("tool", "read_fixture"): (
                    f"{counted_read.__module__}:{counted_read.__qualname__}"
                )
            },
        )

        completed = await executor.execute(
            run,
            checkpoint=_checkpoint,
            checkpointer=InMemorySaver(),
        )

        current = [
            item
            for item in completed.node_runs
            if item.plan_revision == run.plan_revision
        ]
        assert len(calls) == 1
        assert (
            sum(item.status is GeneralAgentNodeStatus.SUCCESS for item in current) == 1
        )
        failed = next(
            item for item in current if item.status is GeneralAgentNodeStatus.FAILED
        )
        assert failed.error_type == "GeneralAgentToolBudgetExceededError"
        assert "Tool 调用总预算已用尽" in (failed.error_message or "")
        snapshot = await budget_repository.read(
            GeneralAgentToolBudgetOwner(
                conversation_id=run.conversation_id,
                run_id=run.run_id,
            )
        )
        assert snapshot is not None
        assert snapshot.used == 1
        assert snapshot.remaining == 0

    asyncio.run(scenario())


def test_executor_projects_budget_repository_failure_without_calling_handler(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        class UnavailableBudgetRepository(InMemoryGeneralAgentToolBudgetRepository):
            async def initialize(self, owner, limit):
                del owner, limit
                raise GeneralAgentToolBudgetUnavailableError

        policy = InvocationPolicyService()
        calls = 0

        async def counted_read(input_data, _invocation, _capabilities):
            nonlocal calls
            calls += 1
            return _ReadOutput(
                content=input_data.chapter_id,
                source_refs=[f"manuscript:{input_data.chapter_id}"],
            )

        tool_registry = ToolRegistry(
            CapabilityContext(capabilities={"invocation_policy_service": policy}),
            tool_budget_repository=UnavailableBudgetRepository(),
            require_tool_budget=True,
        )
        tool_registry.register(
            ToolPlugin(
                manifest=ToolManifest(
                    name="read_fixture",
                    description="读取固定章节。",
                    input_schema=_ReadInput,
                    output_schema=_ReadOutput,
                ),
                run=counted_read,
            )
        )
        run = _run()
        executor = DynamicDagExecutor(
            tool_registry=tool_registry,
            subagent_registry=SubagentRegistry(CapabilityContext(capabilities={})),
            policy_service=policy,
            effect_repository=JsonGeneralAgentEffectRepository(tmp_path),
            capability_result_repository=(
                in_memory_capability_result_repository(
                    tmp_path / "unavailable_budget_results"
                )
            ),
            capability_handler_identities={
                ("tool", "read_fixture"): (
                    f"{counted_read.__module__}:{counted_read.__qualname__}"
                )
            },
        )

        completed = await executor.execute(
            run,
            checkpoint=_checkpoint,
            checkpointer=InMemorySaver(),
        )

        current = next(
            item
            for item in completed.node_runs
            if item.plan_revision == run.plan_revision
        )
        assert calls == 0
        assert current.status is GeneralAgentNodeStatus.FAILED
        assert current.error_type == "GeneralAgentToolBudgetUnavailableError"
        assert "预算仓储当前不可用" in (current.error_message or "")

    asyncio.run(scenario())


def test_executor_direct_tool_and_subagent_prefetch_share_one_budget(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        policy = InvocationPolicyService()
        budget_repository = InMemoryGeneralAgentToolBudgetRepository()
        calls = 0

        async def get_structure(_input_data, _invocation, _capabilities):
            nonlocal calls
            calls += 1
            return _ReadOutput(
                content="第一卷",
                source_refs=["manuscript:structure"],
            )

        tool_manifest = ToolManifest(
            name="get_novel_structure",
            description="读取卷章结构。",
            input_schema=_EmptyInput,
            output_schema=_ReadOutput,
            allowed_callers=frozenset({"orchestrator", "budget_probe"}),
        )
        tool_registry = ToolRegistry(
            CapabilityContext(capabilities={"invocation_policy_service": policy}),
            tool_budget_repository=budget_repository,
            require_tool_budget=True,
        )
        tool_registry.register(ToolPlugin(manifest=tool_manifest, run=get_structure))
        subagent_manifest = SubagentManifest(
            name="budget_probe",
            label="预算探针",
            description="验证子 Agent 确定性来源预取共享任务预算。",
            input_schema=_BudgetSubagentInput,
            output_schema=_BudgetSubagentOutput,
            artifact_types=frozenset({"budget_probe"}),
            model_role="budget_probe",
            allowed_tools=frozenset({"get_novel_structure"}),
            required_capabilities=frozenset({"tool_registry", "artifact_repository"}),
        )
        artifact_repository = JsonIntermediateArtifactRepository(tmp_path)
        subagent_context = CapabilityContext(
            capabilities={
                "tool_registry": tool_registry,
                "artifact_repository": artifact_repository,
            }
        )

        async def run_budget_probe(
            manifest,
            input_data,
            invocation,
            context,
        ):
            _source_context, source_refs = await _collect_sources(
                manifest,
                input_data,
                invocation,
                context,
            )
            return _BudgetSubagentOutput(source_refs=source_refs)

        subagent_registry = SubagentRegistry(subagent_context)
        subagent_registry.register(
            SubagentPlugin(
                manifest=subagent_manifest,
                run=run_budget_probe,
            )
        )
        run = _run().model_copy(
            update={
                "limits": GeneralAgentRunLimits(max_total_tool_calls=1),
                "plan": GeneralAgentExecutionPlan(
                    rationale="验证顶层 Tool 与子 Agent 来源预取共享预算。",
                    nodes=[
                        GeneralAgentPlanNode(
                            node_id="direct_structure",
                            kind=GeneralAgentNodeKind.TOOL,
                            capability_name="get_novel_structure",
                            objective="先读取一次结构。",
                            input_data={},
                        ),
                        GeneralAgentPlanNode(
                            node_id="probe_sources",
                            kind=GeneralAgentNodeKind.SUBAGENT,
                            capability_name="budget_probe",
                            objective="由子 Agent 再次预取结构。",
                            input_data={
                                "source_request": {
                                    "auto_collect": False,
                                    "include_structure": True,
                                }
                            },
                            dependencies=["direct_structure"],
                        ),
                    ],
                ),
            }
        )
        executor = DynamicDagExecutor(
            tool_registry=tool_registry,
            subagent_registry=subagent_registry,
            policy_service=policy,
            effect_repository=JsonGeneralAgentEffectRepository(tmp_path),
            capability_result_repository=(
                in_memory_capability_result_repository(
                    tmp_path / "subagent_budget_results"
                )
            ),
            capability_handler_identities={
                ("tool", "get_novel_structure"): (
                    f"{get_structure.__module__}:{get_structure.__qualname__}"
                ),
                ("subagent", "budget_probe"): (
                    f"{run_budget_probe.__module__}:{run_budget_probe.__qualname__}"
                ),
            },
        )

        completed = await executor.execute(
            run,
            checkpoint=_checkpoint,
            checkpointer=InMemorySaver(),
        )

        current = {
            item.node_id: item
            for item in completed.node_runs
            if item.plan_revision == run.plan_revision
        }
        assert current["direct_structure"].status is GeneralAgentNodeStatus.SUCCESS, (
            current["direct_structure"].error_type,
            current["direct_structure"].error_message,
        )
        assert calls == 1
        assert current["probe_sources"].status is GeneralAgentNodeStatus.FAILED
        assert (
            current["probe_sources"].error_type == "GeneralAgentToolBudgetExceededError"
        )
        assert "Tool 调用总预算已用尽" in (current["probe_sources"].error_message or "")

    asyncio.run(scenario())


def test_subagent_source_prefetch_replay_reuses_stable_tool_call_identity() -> None:
    async def scenario() -> None:
        policy = InvocationPolicyService()
        budget_repository = InMemoryGeneralAgentToolBudgetRepository()
        calls = 0

        async def get_structure(_input_data, _invocation, _capabilities):
            nonlocal calls
            calls += 1
            return _ReadOutput(
                content="第一卷",
                source_refs=["manuscript:structure"],
            )

        tool_registry = ToolRegistry(
            CapabilityContext(capabilities={"invocation_policy_service": policy}),
            tool_budget_repository=budget_repository,
            require_tool_budget=True,
        )
        tool_registry.register(
            ToolPlugin(
                manifest=ToolManifest(
                    name="get_novel_structure",
                    description="读取卷章结构。",
                    input_schema=_EmptyInput,
                    output_schema=_ReadOutput,
                    allowed_callers=frozenset({"budget_probe"}),
                ),
                run=get_structure,
            )
        )
        manifest = SubagentManifest(
            name="budget_probe",
            label="预算探针",
            description="验证来源预取恢复身份。",
            input_schema=_BudgetSubagentInput,
            output_schema=_BudgetSubagentOutput,
            artifact_types=frozenset({"budget_probe"}),
            model_role="budget_probe",
            allowed_tools=frozenset({"get_novel_structure"}),
        )
        input_data = _BudgetSubagentInput(
            source_request=AgentSourceRequest(
                auto_collect=False,
                include_structure=True,
            )
        )
        invocation = InvocationContext(
            task_id="conversation-prefetch-replay",
            conversation_id="conversation-prefetch-replay",
            run_id="general_run_20260830_000000_replay",
            call_id="attempt_prefetch_replay",
            caller_type="orchestrator",
            caller_name="general_writing_orchestrator",
            budget=InvocationBudget(max_tool_calls=1),
        )
        context = CapabilityContext(capabilities={"tool_registry": tool_registry})

        await _collect_sources(manifest, input_data, invocation, context)
        await _collect_sources(manifest, input_data, invocation, context)

        snapshot = await budget_repository.read(
            GeneralAgentToolBudgetOwner(
                conversation_id=invocation.conversation_id or "",
                run_id=invocation.run_id,
            )
        )
        assert calls == 2
        assert snapshot is not None
        assert snapshot.used == 1
        assert snapshot.claims[0].parent_call_id == invocation.call_id
        assert snapshot.claims[0].caller_name == manifest.name

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
        async def aget_tuple(self, config: dict[str, object]) -> SimpleNamespace:
            order.append("checkpoint")
            thread_id = config["configurable"]["thread_id"]  # type: ignore[index]
            assert thread_id == run.conversation_id
            return SimpleNamespace(
                config={
                    "configurable": {
                        "thread_id": run.conversation_id,
                        "checkpoint_id": "checkpoint-test",
                    }
                },
                checkpoint={
                    "id": "checkpoint-test",
                    "channel_values": {"run": run.model_dump(mode="json")},
                },
                metadata={"source": "loop", "step": 3},
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
    assert prepared.checkpoint_revision == prepared.checkpoint_step + 1
    assert prepared.checkpoint_id == "checkpoint-test"
    assert prepared.checkpoint_step == 3
    assert order == ["owner", "effect", "checkpoint", "result", "context"]


def test_runtime_composition_requires_one_shared_capability_result_repository(
    tmp_path: Path,
) -> None:
    executor_parameter = inspect.signature(DynamicDagExecutor).parameters[
        "capability_result_repository"
    ]
    service_parameter = inspect.signature(GeneralAgentRuntimeService).parameters[
        "capability_result_repository"
    ]
    assert executor_parameter.default is inspect.Parameter.empty
    assert service_parameter.default is inspect.Parameter.empty

    policy = InvocationPolicyService()
    tools = ToolRegistry(
        CapabilityContext(capabilities={"invocation_policy_service": policy})
    )
    subagents = SubagentRegistry(CapabilityContext(capabilities={}))
    executor_results = in_memory_capability_result_repository(
        tmp_path / "executor_results"
    )
    service_results = in_memory_capability_result_repository(
        tmp_path / "service_results"
    )
    executor = DynamicDagExecutor(
        tool_registry=tools,
        subagent_registry=subagents,
        policy_service=policy,
        capability_result_repository=executor_results,
        capability_handler_identities={},
        effect_repository=InMemoryGeneralAgentEffectRepository(),
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
