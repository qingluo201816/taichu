"""恢复基准的通用故障计划、持久触发状态与密封后态合同。"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_json_bytes,
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)
from taichu.application.general_agent.faults import (
    GeneralAgentFaultContext,
    GeneralAgentFaultHook,
    GeneralAgentFaultPoint,
    InjectedProcessTermination,
)

FaultPoint = GeneralAgentFaultPoint


class FaultRunIdentity(BenchmarkModel):
    """故障状态唯一归属的业务运行身份。"""

    conversation_id: StableId
    run_id: StableId


class FaultStep(BenchmarkModel):
    ordinal: int = Field(gt=0)
    point: FaultPoint
    once: Literal[True]


class FaultPlan(BenchmarkModel):
    """内容寻址且只允许顺序单次触发的故障计划。"""

    schema_: Literal["taichu.general_agent_benchmark.fault_plan@1"] = Field(
        alias="schema"
    )
    plan_id: StableId
    run_identity: FaultRunIdentity
    steps: tuple[FaultStep, ...] = Field(min_length=1)
    content_hash: Sha256

    @model_validator(mode="after")
    def _identity_and_order_are_sealed(self) -> Self:
        ordinals = tuple(step.ordinal for step in self.steps)
        expected = tuple(range(1, len(self.steps) + 1))
        if ordinals != expected:
            raise ValueError("FaultPlan ordinal 必须从 1 连续递增且不得重复。")
        points = tuple(step.point for step in self.steps)
        if len(points) != len(set(points)):
            raise ValueError("FaultPlan 中每个故障点最多声明一次。")
        payload = self.model_dump(
            mode="python",
            by_alias=True,
            exclude={"content_hash"},
        )
        if self.content_hash != canonical_sha256(payload):
            raise ValueError("FaultPlan content_hash 与规范化内容不一致。")
        return self

    @classmethod
    def seal(
        cls,
        *,
        plan_id: str,
        run_identity: FaultRunIdentity,
        steps: tuple[FaultStep, ...],
    ) -> FaultPlan:
        payload = {
            "schema": "taichu.general_agent_benchmark.fault_plan@1",
            "plan_id": plan_id,
            "run_identity": run_identity,
            "steps": steps,
        }
        return cls.model_validate(
            {**payload, "content_hash": canonical_sha256(payload)}
        )

    def step_at(self, ordinal: int) -> FaultStep | None:
        return next(
            (step for step in self.steps if step.ordinal == ordinal),
            None,
        )


class FaultTriggerState(BenchmarkModel):
    """按 run identity 落盘的已触发序号事实。"""

    schema_: Literal["taichu.general_agent_benchmark.fault_trigger_state@1"] = Field(
        alias="schema"
    )
    plan_id: StableId
    plan_hash: Sha256
    run_identity: FaultRunIdentity
    triggered_ordinals: tuple[int, ...]
    generation: int = Field(ge=0)
    state_hash: Sha256

    @model_validator(mode="after")
    def _state_is_sealed(self) -> Self:
        if any(ordinal <= 0 for ordinal in self.triggered_ordinals):
            raise ValueError("已触发 ordinal 必须为正整数。")
        if self.triggered_ordinals != tuple(sorted(set(self.triggered_ordinals))):
            raise ValueError("已触发 ordinal 必须有序且不得重复。")
        expected_prefix = tuple(range(1, len(self.triggered_ordinals) + 1))
        if self.triggered_ordinals != expected_prefix:
            raise ValueError("已触发 ordinal 必须是从 1 开始的连续前缀。")
        if self.generation != len(self.triggered_ordinals):
            raise ValueError("故障触发状态 generation 与已触发数量不一致。")
        payload = self.model_dump(
            mode="python",
            by_alias=True,
            exclude={"state_hash"},
        )
        if self.state_hash != canonical_sha256(payload):
            raise ValueError("故障触发状态哈希与规范化内容不一致。")
        return self

    @classmethod
    def empty_for(cls, plan: FaultPlan) -> FaultTriggerState:
        return cls._seal(
            plan_id=plan.plan_id,
            plan_hash=plan.content_hash,
            run_identity=plan.run_identity,
            triggered_ordinals=(),
            generation=0,
        )

    def with_triggered(self, ordinal: int) -> FaultTriggerState:
        return self._seal(
            plan_id=self.plan_id,
            plan_hash=self.plan_hash,
            run_identity=self.run_identity,
            triggered_ordinals=(*self.triggered_ordinals, ordinal),
            generation=self.generation + 1,
        )

    @classmethod
    def _seal(
        cls,
        *,
        plan_id: str,
        plan_hash: str,
        run_identity: FaultRunIdentity,
        triggered_ordinals: tuple[int, ...],
        generation: int,
    ) -> FaultTriggerState:
        payload = {
            "schema": ("taichu.general_agent_benchmark.fault_trigger_state@1"),
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "run_identity": run_identity,
            "triggered_ordinals": triggered_ordinals,
            "generation": generation,
        }
        return cls.model_validate({**payload, "state_hash": canonical_sha256(payload)})


class FaultPlanErrorCode(StrEnum):
    STATE_CORRUPT = "FAULT_PLAN_STATE_CORRUPT"
    STATE_IDENTITY_MISMATCH = "FAULT_PLAN_STATE_IDENTITY_MISMATCH"
    STRICT_DEVIATION = "FAULT_PLAN_STRICT_DEVIATION"


class FaultPlanContractError(ValueError):
    def __init__(self, code: FaultPlanErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class FaultPlanStateCorruptError(FaultPlanContractError):
    def __init__(self, message: str = "故障触发状态损坏。") -> None:
        super().__init__(FaultPlanErrorCode.STATE_CORRUPT, message)


class FaultPlanStateIdentityMismatchError(FaultPlanContractError):
    def __init__(
        self,
        message: str = "故障触发状态与运行或计划身份不匹配。",
    ) -> None:
        super().__init__(FaultPlanErrorCode.STATE_IDENTITY_MISMATCH, message)


class FaultPlanStrictDeviationError(FaultPlanContractError):
    def __init__(self, message: str) -> None:
        super().__init__(FaultPlanErrorCode.STRICT_DEVIATION, message)


class FaultTriggerDecision(BenchmarkModel):
    point: FaultPoint
    ordinal: int = Field(gt=0)
    should_interrupt: bool
    already_triggered: bool
    state: FaultTriggerState


class JsonFaultTriggerStore:
    """无内存缓存的 case-scoped 文件状态仓储。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def state_path(self, run_identity: FaultRunIdentity) -> Path:
        identity_hash = canonical_sha256(run_identity)
        return self._root / "runs" / f"{identity_hash}.json"

    def plan_path(self, run_identity: FaultRunIdentity) -> Path:
        identity_hash = canonical_sha256(run_identity)
        return self._root / "plans" / f"{identity_hash}.json"

    def load_or_create_plan(
        self,
        *,
        plan_id: str,
        run_identity: FaultRunIdentity,
        steps: tuple[FaultStep, ...],
    ) -> FaultPlan:
        candidate = FaultPlan.seal(
            plan_id=plan_id,
            run_identity=run_identity,
            steps=steps,
        )
        path = self.plan_path(run_identity)
        if not path.exists():
            self._publish_create_once(
                path,
                canonical_json_bytes(candidate),
            )
        try:
            persisted = FaultPlan.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValueError) as error:
            raise FaultPlanStateCorruptError(
                f"持久 FaultPlan 损坏：{path.name}。"
            ) from error
        if persisted != candidate:
            raise FaultPlanStateIdentityMismatchError(
                "同一运行身份已绑定不同的 FaultPlan。"
            )
        return persisted

    def load(self, plan: FaultPlan) -> FaultTriggerState:
        path = self.state_path(plan.run_identity)
        if not path.exists():
            return FaultTriggerState.empty_for(plan)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            state = FaultTriggerState.model_validate(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise FaultPlanStateCorruptError(
                f"故障触发状态损坏：{path.name}。"
            ) from error
        self._assert_state_owner(state, plan)
        declared_ordinals = {step.ordinal for step in plan.steps}
        if not set(state.triggered_ordinals).issubset(declared_ordinals):
            raise FaultPlanStateCorruptError("故障触发状态包含计划未声明的 ordinal。")
        return state

    def claim(
        self,
        *,
        plan: FaultPlan,
        run_identity: FaultRunIdentity,
        point: FaultPoint,
        ordinal: int,
    ) -> FaultTriggerDecision:
        if run_identity != plan.run_identity:
            raise FaultPlanStateIdentityMismatchError(
                "通用 fault hook 的运行身份与 FaultPlan 不匹配。"
            )
        step = plan.step_at(ordinal)
        if step is None:
            raise FaultPlanStrictDeviationError(
                f"fault hook ordinal={ordinal} 与 FaultPlan 不匹配。"
            )
        if step.point is not point:
            raise FaultPlanStrictDeviationError(
                "fault hook 故障点与 FaultPlan 不匹配。"
            )

        state = self.load(plan)
        if ordinal in state.triggered_ordinals:
            return FaultTriggerDecision(
                point=point,
                ordinal=ordinal,
                should_interrupt=False,
                already_triggered=True,
                state=state,
            )
        next_ordinal = next(
            (
                candidate.ordinal
                for candidate in plan.steps
                if candidate.ordinal not in state.triggered_ordinals
            ),
            None,
        )
        if ordinal != next_ordinal:
            raise FaultPlanStrictDeviationError(
                "fault hook 未按 FaultPlan 声明顺序触发。"
            )

        updated = state.with_triggered(ordinal)
        self._write(updated)
        return FaultTriggerDecision(
            point=point,
            ordinal=ordinal,
            should_interrupt=True,
            already_triggered=False,
            state=updated,
        )

    @staticmethod
    def _assert_state_owner(
        state: FaultTriggerState,
        plan: FaultPlan,
    ) -> None:
        if (
            state.run_identity != plan.run_identity
            or state.plan_id != plan.plan_id
            or state.plan_hash != plan.content_hash
        ):
            raise FaultPlanStateIdentityMismatchError()

    def _write(self, state: FaultTriggerState) -> None:
        path = self.state_path(state.run_identity)
        self._replace_atomically(path, canonical_json_bytes(state))

    @staticmethod
    def _replace_atomically(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError as error:
            raise FaultPlanStateCorruptError("故障触发状态无法原子持久化。") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _publish_create_once(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                pass
        except OSError as error:
            raise FaultPlanStateCorruptError(
                "FaultPlan 无法原子持久化。"
            ) from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


class FaultPressureAdapter:
    """Harness 到生产通用 fault hook 的唯一适配边界。"""

    def __init__(self, store: JsonFaultTriggerStore) -> None:
        self.store = store

    def on_fault_point(
        self,
        *,
        plan: FaultPlan,
        run_identity: FaultRunIdentity,
        point: FaultPoint,
        ordinal: int,
    ) -> FaultTriggerDecision:
        return self.store.claim(
            plan=plan,
            run_identity=run_identity,
            point=point,
            ordinal=ordinal,
        )

    def bind(self, plan: FaultPlan) -> GeneralAgentFaultHook:
        """把密封计划绑定成 Runtime 可注入的通用 Hook。"""

        return _PlannedFaultHook(store=self.store, plan=plan)

    def bind_runtime(
        self,
        *,
        plan_id: str,
        steps: tuple[FaultStep, ...],
    ) -> RuntimeBoundFaultHook:
        """在首次真实生命周期回调时按 run identity 持久绑定计划。"""

        return RuntimeBoundFaultHook(
            store=self.store,
            plan_id=plan_id,
            steps=steps,
        )


class RuntimeBoundFaultHook:
    """把预声明步骤绑定到 Runtime 实际生成的唯一运行身份。"""

    def __init__(
        self,
        *,
        store: JsonFaultTriggerStore,
        plan_id: str,
        steps: tuple[FaultStep, ...],
    ) -> None:
        self._store = store
        self._plan_id = plan_id
        self._steps = steps
        self._resolved_plan: FaultPlan | None = None
        self._delegate: _PlannedFaultHook | None = None

    @property
    def resolved_plan(self) -> FaultPlan | None:
        return self._resolved_plan

    def on_fault_point(
        self,
        *,
        point: GeneralAgentFaultPoint,
        context: GeneralAgentFaultContext,
    ) -> None:
        run_identity = FaultRunIdentity(
            conversation_id=context.conversation_id,
            run_id=context.run_id,
        )
        if self._resolved_plan is None:
            if point is not self._steps[0].point:
                return
            self._resolved_plan = self._store.load_or_create_plan(
                plan_id=self._plan_id,
                run_identity=run_identity,
                steps=self._steps,
            )
            self._delegate = _PlannedFaultHook(
                store=self._store,
                plan=self._resolved_plan,
            )
        assert self._delegate is not None
        self._delegate.on_fault_point(point=point, context=context)


class _PlannedFaultHook:
    """只按 FaultPlan 选择故障点，不读取或推断案例编号。"""

    def __init__(
        self,
        *,
        store: JsonFaultTriggerStore,
        plan: FaultPlan,
    ) -> None:
        self._store = store
        self._plan = plan
        self._steps_by_point = {step.point: step for step in plan.steps}

    def on_fault_point(
        self,
        *,
        point: GeneralAgentFaultPoint,
        context: GeneralAgentFaultContext,
    ) -> None:
        run_identity = FaultRunIdentity(
            conversation_id=context.conversation_id,
            run_id=context.run_id,
        )
        if run_identity != self._plan.run_identity:
            raise FaultPlanStateIdentityMismatchError(
                "通用 fault hook 的运行身份与 FaultPlan 不匹配。"
            )
        step = self._steps_by_point.get(point)
        if step is None:
            return
        decision = self._store.claim(
            plan=self._plan,
            run_identity=run_identity,
            point=point,
            ordinal=step.ordinal,
        )
        if decision.should_interrupt:
            raise InjectedProcessTermination(
                f"FaultPlan 已在 {point.value} 持久触发 ordinal={step.ordinal}。"
            )


class RecoveryResource(StrEnum):
    MANUSCRIPT = "manuscript"
    STRUCTURE = "structure"
    KNOWLEDGE = "knowledge"
    CONVERSATION = "conversation"
    WORKING_MEMORY = "working_memory"
    RUN = "run"
    RESULT = "result"
    EFFECT = "effect"
    CHECKPOINT = "checkpoint"
    CONTEXT = "context"


class RecoveryResourceCopy(BenchmarkModel):
    resource: RecoveryResource
    copy_id: StableId
    source_ref: str = Field(min_length=1, max_length=512)
    before_sha256: Sha256
    expected_after_sha256: Sha256
    author_active_fact: bool
    workspace_sentinel: Literal[True]


class RecoveryExpectedCount(BenchmarkModel):
    name: StableId
    count: int = Field(ge=0)


class RecoveryCheckpointExpectation(BenchmarkModel):
    revision_chain: tuple[StableId, ...] = Field(min_length=1)
    selected_revision: StableId | None
    integrity_outcome: Literal[
        "latest_valid",
        "fallback_valid",
        "unrecoverable",
    ]
    zero_restart: bool

    @model_validator(mode="after")
    def _selection_matches_integrity(self) -> Self:
        if (self.integrity_outcome == "unrecoverable") != (
            self.selected_revision is None
        ):
            raise ValueError("只有 checkpoint 不可恢复时 selected_revision 才能为空。")
        return self


class RecoveryExpectedState(BenchmarkModel):
    """单个恢复场景的完整资源复制与可验证后态。"""

    schema_: Literal["taichu.general_agent_benchmark.recovery_expected_state@1"] = (
        Field(alias="schema")
    )
    expectation_id: StableId
    run_identity: FaultRunIdentity
    fault_plan_hash: Sha256
    expected_triggered_ordinals: tuple[int, ...] = Field(min_length=1)
    pre_injection_state: StableId
    recovery_entry: StableId
    reused_items: tuple[StableId, ...]
    retried_items: tuple[StableId, ...]
    final_run_status: Literal["completed", "waiting_human", "failed"]
    resumable: bool
    pending_human_kind: StableId | None
    recovery_action: Literal[
        "resume",
        "reuse_checkpoint",
        "reconcile_effect",
        "stop",
    ]
    reason_code: StableId
    side_effect_reconciliation: Literal[
        "not_applicable",
        "no_effect",
        "reconciled_success",
        "requires_human",
        "blocked",
    ]
    expected_counts: tuple[RecoveryExpectedCount, ...]
    checkpoint: RecoveryCheckpointExpectation
    resource_copies: tuple[RecoveryResourceCopy, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def _expected_state_is_complete_and_sealed(self) -> Self:
        expected_ordinals = tuple(range(1, len(self.expected_triggered_ordinals) + 1))
        if self.expected_triggered_ordinals != expected_ordinals:
            raise ValueError("预期触发 ordinal 必须从 1 连续递增且不得重复。")
        if (self.final_run_status == "waiting_human") != (
            self.pending_human_kind is not None
        ):
            raise ValueError("只有 waiting_human 后态可以携带 pending_human_kind。")
        if self.final_run_status == "waiting_human" and not self.resumable:
            raise ValueError("waiting_human 后态必须可继续。")
        names = tuple(item.name for item in self.expected_counts)
        if names != tuple(sorted(set(names))):
            raise ValueError("expected_counts 必须按 name 排序且不得重复。")
        resources = tuple(item.resource for item in self.resource_copies)
        if resources != tuple(RecoveryResource):
            raise ValueError("resource_copies 必须按固定顺序完整密封十类资源。")
        author_resources = {
            item.resource for item in self.resource_copies if item.author_active_fact
        }
        if author_resources != {
            RecoveryResource.MANUSCRIPT,
            RecoveryResource.STRUCTURE,
            RecoveryResource.KNOWLEDGE,
        }:
            raise ValueError("作者活动事实哨兵必须覆盖正文、结构和知识。")
        payload = self.model_dump(
            mode="python",
            by_alias=True,
            exclude={"content_hash"},
        )
        if self.content_hash != canonical_sha256(payload):
            raise ValueError("恢复预期后态 content_hash 与规范化内容不一致。")
        return self

    def verify_observed_after(
        self,
        observed: Mapping[RecoveryResource | str, str],
    ) -> None:
        normalized: dict[RecoveryResource, str] = {}
        unknown: list[str] = []
        for resource, digest in observed.items():
            try:
                normalized[RecoveryResource(resource)] = digest
            except ValueError:
                unknown.append(str(resource))
        mismatches = [
            item.resource.value
            for item in self.resource_copies
            if normalized.get(item.resource) != item.expected_after_sha256
        ]
        if unknown:
            mismatches.extend(f"unknown:{item}" for item in unknown)
        if mismatches:
            raise RecoverySentinelMismatchError(tuple(mismatches))


class RecoverySentinelMismatchError(ValueError):
    def __init__(self, resources: tuple[str, ...]) -> None:
        self.resources = resources
        super().__init__("恢复后资源哨兵不匹配：" + "、".join(resources) + "。")


__all__ = [
    "FaultPlan",
    "FaultPlanContractError",
    "FaultPlanErrorCode",
    "FaultPlanStateCorruptError",
    "FaultPlanStateIdentityMismatchError",
    "FaultPlanStrictDeviationError",
    "FaultPoint",
    "FaultPressureAdapter",
    "FaultRunIdentity",
    "FaultStep",
    "FaultTriggerDecision",
    "FaultTriggerState",
    "JsonFaultTriggerStore",
    "RecoveryCheckpointExpectation",
    "RecoveryExpectedCount",
    "RecoveryExpectedState",
    "RecoveryResource",
    "RecoveryResourceCopy",
    "RecoverySentinelMismatchError",
    "RuntimeBoundFaultHook",
]
