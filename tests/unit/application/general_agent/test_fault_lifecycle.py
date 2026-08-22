"""需求 8.1—8.11：通用 Runtime 生命周期故障点必须位于真实边界。"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.faults import (
    GeneralAgentFaultContext,
    GeneralAgentFaultHook,
    GeneralAgentFaultPoint,
    InjectedProcessTermination,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentHumanRequest,
    GeneralAgentNodeKind,
    GeneralAgentPlanNode,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.invocations.models import now_iso
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)


class _RecordingHook:
    def __init__(self, order: list[str] | None = None) -> None:
        self.calls: list[
            tuple[GeneralAgentFaultPoint, GeneralAgentFaultContext]
        ] = []
        self._order = order

    def on_fault_point(
        self,
        *,
        point: GeneralAgentFaultPoint,
        context: GeneralAgentFaultContext,
    ) -> None:
        self.calls.append((point, context))
        if self._order is not None:
            self._order.append(f"hook:{point.value}")


class _RunRepository:
    def __init__(self) -> None:
        self.saved: list[GeneralAgentRun] = []

    async def save(self, run: GeneralAgentRun) -> None:
        self.saved.append(run)

    async def get(self, run_id: str) -> GeneralAgentRun | None:
        return next(
            (
                run
                for run in reversed(self.saved)
                if run.run_id == run_id
            ),
            None,
        )


class _EventCenter:
    def __init__(self) -> None:
        self.events: list[tuple[str, GeneralAgentRun]] = []

    async def publish(
        self,
        *,
        event_type: str,
        run: GeneralAgentRun,
    ) -> None:
        self.events.append((event_type, run))


def _service_shell(hook: _RecordingHook | None) -> GeneralAgentRuntimeService:
    service = object.__new__(GeneralAgentRuntimeService)
    service._repository = _RunRepository()  # type: ignore[attr-defined]
    service._event_center = _EventCenter()  # type: ignore[attr-defined]
    service._effect_repository = None  # type: ignore[attr-defined]
    service._fault_hook = hook  # type: ignore[attr-defined]
    return service


def _run() -> GeneralAgentRun:
    timestamp = now_iso()
    return GeneralAgentRun(
        run_id="general_run_20260730_140000_fault1",
        task_id="conversation_fault_lifecycle",
        conversation_id="conversation_fault_lifecycle",
        request_index=1,
        user_goal="验证通用故障生命周期点。",
        status=GeneralAgentRunStatus.EXECUTING,
        plan=GeneralAgentExecutionPlan(
            rationale="固定真实边界。",
            nodes=[],
            direct_response="用于构造生命周期测试运行。",
        ),
        plan_revision=1,
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp,
    )


def test_fault_hook_protocol_has_no_case_identifier() -> None:
    parameters = inspect.signature(
        GeneralAgentFaultHook.on_fault_point
    ).parameters
    assert "case_id" not in parameters
    assert tuple(point.value for point in GeneralAgentFaultPoint) == (
        "plan_created",
        "capability_result_committed",
        "subagent_started",
        "authorization_request_durable",
        "resource_write_applied",
        "verification_started",
        "checkpoint_revision_validation",
    )


def test_durable_runtime_checkpoints_emit_only_their_fixed_fault_points() -> None:
    async def scenario() -> None:
        hook = _RecordingHook()
        service = _service_shell(hook)
        run = _run()

        planned = await service._checkpoint(run, "plan_created")  # noqa: SLF001
        waiting = planned.model_copy(
            update={
                "pending_human_request": GeneralAgentHumanRequest(
                    request_id=f"human_{'a' * 32}",
                    kind="write_authorization",
                    prompt="请确认写入。",
                    created_at=now_iso(),
                )
            }
        )
        authorized = await service._checkpoint(  # noqa: SLF001
            waiting,
            "waiting_human_after_capability_checkpoint",
        )
        verifying = await service._checkpoint(  # noqa: SLF001
            authorized,
            "verification_started",
        )
        await service._checkpoint(verifying, "unrelated_checkpoint")  # noqa: SLF001

        assert [point for point, _ in hook.calls] == [
            GeneralAgentFaultPoint.PLAN_CREATED,
            GeneralAgentFaultPoint.AUTHORIZATION_REQUEST_DURABLE,
            GeneralAgentFaultPoint.VERIFICATION_STARTED,
        ]
        assert hook.calls[0][1].checkpoint_revision == (
            planned.checkpoint_revision
        )
        assert hook.calls[1][1].durable_identity == f"human_{'a' * 32}"
        assert hook.calls[2][1].checkpoint_revision == (
            verifying.checkpoint_revision
        )

    asyncio.run(scenario())


def test_no_fault_hook_keeps_checkpoint_behavior_unchanged() -> None:
    async def scenario() -> None:
        service = _service_shell(None)
        run = _run()

        updated = await service._checkpoint(run, "plan_created")  # noqa: SLF001

        assert updated.checkpoint_revision == run.checkpoint_revision + 1
        assert service._repository.saved == [updated]  # type: ignore[attr-defined]
        assert service._event_center.events == [  # type: ignore[attr-defined]
            ("plan_created", updated)
        ]

    asyncio.run(scenario())


def test_checkpoint_validation_hook_runs_before_recovery_inspection() -> None:
    async def scenario() -> None:
        order: list[str] = []
        hook = _RecordingHook(order)
        service = _service_shell(hook)

        class Coordinator:
            async def prepare(self, run: GeneralAgentRun) -> object:
                order.append("recovery:prepare")
                return SimpleNamespace(decision=object())

        service._recovery_coordinator = Coordinator()  # type: ignore[attr-defined]

        async def persist_decision(
            run: GeneralAgentRun,
            decision: object,
        ) -> GeneralAgentRun:
            del decision
            return run

        service._persist_recovery_decision = persist_decision  # type: ignore[method-assign]

        await service._prepare_recovery(_run())  # noqa: SLF001

        assert order == [
            "hook:checkpoint_revision_validation",
            "recovery:prepare",
        ]

    asyncio.run(scenario())


def test_subagent_started_hook_runs_after_dispatch_and_before_completed_commit() -> None:
    async def scenario() -> None:
        order: list[str] = []
        started = asyncio.Event()

        class Input(BaseModel):
            model_config = ConfigDict(extra="forbid")

            subject: str

        class Output(BaseModel):
            model_config = ConfigDict(extra="forbid")

            conclusion: str

        class Subagents:
            def get_manifest(self, name: str) -> object:
                assert name == "fixture_subagent"
                return SimpleNamespace(
                    input_schema=Input,
                    output_schema=Output,
                )

            async def invoke(self, *_args: Any, **_kwargs: Any) -> object:
                order.append("subagent:started")
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("中断后不得提交完整 envelope。")

        class Results:
            committed = False

            async def get_completed(self, *_args: Any) -> None:
                return None

            async def commit_completed(self, *_args: Any) -> object:
                self.committed = True
                raise AssertionError("故障点必须早于完整结果提交。")

        class CrashHook(_RecordingHook):
            def on_fault_point(
                self,
                *,
                point: GeneralAgentFaultPoint,
                context: GeneralAgentFaultContext,
            ) -> None:
                assert started.is_set()
                super().on_fault_point(point=point, context=context)
                raise InjectedProcessTermination()

        hook = CrashHook(order)
        results = Results()
        executor = DynamicDagExecutor(
            tool_registry=SimpleNamespace(),
            subagent_registry=Subagents(),  # type: ignore[arg-type]
            policy_service=InvocationPolicyService(),
            capability_result_repository=results,  # type: ignore[arg-type]
            capability_handler_identities={
                ("subagent", "fixture_subagent"): (
                    "tests.fixture_subagent:invoke"
                )
            },
            fault_hook=hook,
        )
        timestamp = now_iso()
        run = GeneralAgentRun(
            run_id="general_run_20260730_140000_fault2",
            task_id="conversation_fault_subagent",
            conversation_id="conversation_fault_subagent",
            request_index=1,
            user_goal="验证子 Agent 中断边界。",
            status=GeneralAgentRunStatus.EXECUTING,
            plan=GeneralAgentExecutionPlan(
                rationale="调用一个专业子 Agent。",
                nodes=[
                    GeneralAgentPlanNode(
                        node_id="inspect_subject",
                        kind=GeneralAgentNodeKind.SUBAGENT,
                        capability_name="fixture_subagent",
                        objective="检查目标。",
                        input_data={"subject": "目标"},
                    )
                ],
            ),
            plan_revision=1,
            created_at=timestamp,
            updated_at=timestamp,
            started_at=timestamp,
        )

        async def checkpoint(
            current: GeneralAgentRun,
            _event_type: str,
        ) -> GeneralAgentRun:
            return current

        with pytest.raises(InjectedProcessTermination):
            await executor.execute(run, checkpoint=checkpoint)

        assert order == [
            "subagent:started",
            "hook:subagent_started",
        ]
        assert not results.committed
        assert hook.calls[0][1].durable_identity is not None
        assert hook.calls[0][1].durable_identity.startswith("attempt_")

    asyncio.run(scenario())


def test_recording_hook_conforms_to_runtime_protocol() -> None:
    hook: GeneralAgentFaultHook = _RecordingHook()
    assert hook is not None
