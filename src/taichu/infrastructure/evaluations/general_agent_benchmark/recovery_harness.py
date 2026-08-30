"""以持久 FaultPlan 驱动真实通用 Runtime 重建与恢复。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.faults import (
    FaultPlan,
    FaultPoint,
    FaultPressureAdapter,
    FaultStep,
)
from taichu.application.general_agent.faults import GeneralAgentFaultHook
from taichu.application.general_agent.faults import InjectedProcessTermination
from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.service import GeneralAgentRuntimeService

RecoveryRuntimeBuilder = Callable[
    [GeneralAgentFaultHook],
    GeneralAgentRuntimeService,
]

_RECOVERY_TERMINAL_STATUSES = {
    GeneralAgentRunStatus.COMPLETED,
    GeneralAgentRunStatus.CANCELLED,
    GeneralAgentRunStatus.FAILED,
    GeneralAgentRunStatus.TIMEOUT,
    GeneralAgentRunStatus.WAITING_HUMAN,
}
_DURABLE_NON_AUTO_RESUME_STATUSES = {
    GeneralAgentRunStatus.WAITING_HUMAN,
}


@dataclass(frozen=True, slots=True)
class RecoveryHarnessResult:
    fault_plan: FaultPlan
    interrupted_run: GeneralAgentRun
    interrupted_runs: tuple[GeneralAgentRun, ...]
    recovered_run: GeneralAgentRun
    recover_interrupted_count: int
    triggered_ordinals: tuple[int, ...]
    plan_before_sha256: str
    plan_after_sha256: str


class GeneralAgentRecoveryHarness:
    """不按案例编号分支，只按计划重建同一 Runtime run。"""

    def __init__(
        self,
        *,
        runtime_builder: RecoveryRuntimeBuilder,
        fault_adapter: FaultPressureAdapter,
        poll_timeout_seconds: float = 10,
    ) -> None:
        if poll_timeout_seconds <= 0:
            raise ValueError("恢复轮询超时必须为正数。")
        self._runtime_builder = runtime_builder
        self._fault_adapter = fault_adapter
        self._poll_timeout_seconds = poll_timeout_seconds

    async def execute(
        self,
        *,
        user_goal: str,
        plan_id: str,
        steps: tuple[FaultStep, ...],
        runtime_arguments: dict[str, Any] | None = None,
    ) -> RecoveryHarnessResult:
        first_hook = self._fault_adapter.bind_runtime(
            plan_id=plan_id,
            steps=steps,
        )
        first_runtime = self._runtime_builder(first_hook)
        try:
            try:
                first_result = await first_runtime.run(
                    user_goal=user_goal,
                    **(runtime_arguments or {}),
                )
                while self._should_approve_pending_write(
                    run=first_result,
                    hook=first_hook,
                ):
                    request = first_result.pending_human_request
                    assert request is not None
                    first_result = await first_runtime.resume(
                        first_result.run_id,
                        approve=True,
                        second_confirmation=request.second_confirmation_required,
                    )
            except InjectedProcessTermination:
                pass
            else:
                raise RecoveryHarnessDeviationError(
                    "Runtime 未在 FaultPlan 声明的故障点中断："
                    f"状态={first_result.status.value}；"
                    f"错误={first_result.errors}。"
                )
            plan = first_hook.resolved_plan
            if plan is None:
                raise RecoveryHarnessDeviationError(
                    "故障发生前未持久绑定 Runtime FaultPlan。"
                )
            interrupted = await first_runtime.get(plan.run_identity.run_id)
        finally:
            await first_runtime.shutdown()

        recovered_count = 0
        current_interrupted = interrupted
        interrupted_runs = [interrupted]
        recovered = interrupted
        while True:
            triggered_before = self._fault_adapter.store.load(
                plan
            ).triggered_ordinals
            restarted_hook = self._fault_adapter.bind(plan)
            restarted_runtime = self._runtime_builder(restarted_hook)
            interrupted_again = False
            try:
                try:
                    current_recovered_count = (
                        await restarted_runtime.recover_interrupted()
                    )
                except InjectedProcessTermination:
                    await asyncio.sleep(0)
                    recovered = await restarted_runtime.get(
                        plan.run_identity.run_id
                    )
                    self._assert_next_fault_triggered(
                        plan=plan,
                        previous=triggered_before,
                    )
                    self._assert_interruption_consistent(
                        initial=interrupted,
                        current=recovered,
                        plan=plan,
                    )
                    current_interrupted = recovered
                    interrupted_runs.append(recovered)
                    interrupted_again = True
                    continue

                preflight_stopped: GeneralAgentRun | None = None
                if current_recovered_count == 0:
                    candidate = await restarted_runtime.get(
                        plan.run_identity.run_id
                    )
                    if (
                        candidate.status is GeneralAgentRunStatus.WAITING_HUMAN
                        or (
                            candidate.status is GeneralAgentRunStatus.FAILED
                            and not candidate.resumable
                        )
                    ):
                        preflight_stopped = candidate
                expected_recovered_count = (
                    0
                    if (
                        current_interrupted.status
                        in _DURABLE_NON_AUTO_RESUME_STATUSES
                        or preflight_stopped is not None
                    )
                    else 1
                )
                if current_recovered_count != expected_recovered_count:
                    raise RecoveryHarnessDeviationError(
                        "Runtime 自动恢复数量与中断时持久状态不一致："
                        f"状态={current_interrupted.status.value}，"
                        f"预期={expected_recovered_count}，"
                        f"实际={current_recovered_count}。"
                    )
                recovered_count += current_recovered_count
                if expected_recovered_count == 0:
                    recovered = preflight_stopped or await restarted_runtime.get(
                        plan.run_identity.run_id
                    )
                    if (
                        current_interrupted.status
                        in _DURABLE_NON_AUTO_RESUME_STATUSES
                        and recovered != current_interrupted
                    ):
                        raise RecoveryHarnessDeviationError(
                            "无需自动执行的持久状态在 Runtime 重建后发生了漂移。"
                        )
                else:
                    recovered, interrupted_again = (
                        await self._wait_for_terminal_or_fault(
                            restarted_runtime,
                            plan,
                            triggered_before=triggered_before,
                        )
                    )
                    if interrupted_again:
                        self._assert_interruption_consistent(
                            initial=interrupted,
                            current=recovered,
                            plan=plan,
                        )
                        current_interrupted = recovered
                        interrupted_runs.append(recovered)
            finally:
                await restarted_runtime.shutdown()
            if interrupted_again:
                continue
            break

        state = self._fault_adapter.store.load(plan)
        if state.triggered_ordinals != tuple(step.ordinal for step in plan.steps):
            raise RecoveryHarnessDeviationError(
                "Runtime 已结束但仍有 FaultPlan ordinal 未触发。"
            )
        return RecoveryHarnessResult(
            fault_plan=plan,
            interrupted_run=interrupted,
            interrupted_runs=tuple(interrupted_runs),
            recovered_run=recovered,
            recover_interrupted_count=recovered_count,
            triggered_ordinals=state.triggered_ordinals,
            plan_before_sha256=_plan_sha256(interrupted),
            plan_after_sha256=_plan_sha256(recovered),
        )

    async def _wait_for_terminal_or_fault(
        self,
        runtime: GeneralAgentRuntimeService,
        plan: FaultPlan,
        *,
        triggered_before: tuple[int, ...],
    ) -> tuple[GeneralAgentRun, bool]:
        deadline = monotonic() + self._poll_timeout_seconds
        current = await runtime.get(plan.run_identity.run_id)
        while monotonic() < deadline:
            if current.status in _RECOVERY_TERMINAL_STATUSES:
                if self._should_approve_pending_write(
                    run=current,
                    plan=plan,
                ):
                    request = current.pending_human_request
                    assert request is not None
                    try:
                        current = await runtime.resume(
                            current.run_id,
                            approve=True,
                            second_confirmation=(
                                request.second_confirmation_required
                            ),
                        )
                    except InjectedProcessTermination:
                        await asyncio.sleep(0)
                        current = await runtime.get(plan.run_identity.run_id)
                        self._assert_next_fault_triggered(
                            plan=plan,
                            previous=triggered_before,
                        )
                        return current, True
                    continue
                return current, False
            state = self._fault_adapter.store.load(plan)
            if state.triggered_ordinals != triggered_before:
                self._assert_next_fault_triggered(
                    plan=plan,
                    previous=triggered_before,
                )
                await asyncio.sleep(0)
                return current, True
            await asyncio.sleep(0.01)
            current = await runtime.get(plan.run_identity.run_id)
        raise RecoveryHarnessDeviationError(
            "Runtime 恢复未在门限内进入可判定终态或下一故障点。"
        )

    def _should_approve_pending_write(
        self,
        *,
        run: GeneralAgentRun,
        hook: object | None = None,
        plan: FaultPlan | None = None,
    ) -> bool:
        """仅在后续故障点要求真实写入时推进当前授权，不读取案例编号。"""

        if (
            run.status is not GeneralAgentRunStatus.WAITING_HUMAN
            or run.pending_human_request is None
            or run.pending_human_request.kind != "write_authorization"
        ):
            return False
        resolved = plan
        if resolved is None:
            candidate = getattr(hook, "resolved_plan", None)
            if isinstance(candidate, FaultPlan):
                resolved = candidate
        if resolved is None:
            return False
        triggered = self._fault_adapter.store.load(resolved).triggered_ordinals
        remaining = resolved.steps[len(triggered) :]
        return any(
            step.point is FaultPoint.RESOURCE_WRITE_APPLIED
            for step in remaining
        )

    def _assert_next_fault_triggered(
        self,
        *,
        plan: FaultPlan,
        previous: tuple[int, ...],
    ) -> None:
        current = self._fault_adapter.store.load(plan).triggered_ordinals
        expected = (
            *previous,
            len(previous) + 1,
        )
        if current != expected:
            raise RecoveryHarnessDeviationError(
                "每次 Runtime 重建只能按持久 FaultPlan 触发下一个 ordinal："
                f"恢复前={previous}，恢复后={current}。"
            )

    @staticmethod
    def _assert_interruption_consistent(
        *,
        initial: GeneralAgentRun,
        current: GeneralAgentRun,
        plan: FaultPlan,
    ) -> None:
        if (
            current.run_id != plan.run_identity.run_id
            or current.conversation_id != plan.run_identity.conversation_id
        ):
            raise RecoveryHarnessDeviationError(
                "多次中断没有保持 FaultPlan 声明的同一逻辑运行 owner。"
            )
        if current.plan_revision != initial.plan_revision:
            raise RecoveryHarnessDeviationError(
                "多次中断期间计划修订发生漂移。"
            )
        if _plan_sha256(current) != _plan_sha256(initial):
            raise RecoveryHarnessDeviationError(
                "多次中断期间计划内容发生漂移。"
            )


class RecoveryHarnessDeviationError(RuntimeError):
    """真实 Runtime 的恢复轨迹偏离了密封故障计划。"""


def _plan_sha256(run: GeneralAgentRun) -> str:
    if run.plan is None:
        raise RecoveryHarnessDeviationError("恢复运行缺少已持久化计划。")
    return canonical_sha256(run.plan)


__all__ = [
    "GeneralAgentRecoveryHarness",
    "RecoveryHarnessDeviationError",
    "RecoveryHarnessResult",
    "RecoveryRuntimeBuilder",
]
