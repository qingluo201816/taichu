"""通用写作助手的节点尝试、副作用和恢复决策模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
    CapabilityResultOwnerMismatchError,
    CapabilityResultOwnerNotFoundError,
)
from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunStatus,
    RecoveryAction,
    RecoveryDecision,
    recovery_evidence_sha256,
)
from taichu.application.invocations.models import now_iso

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from taichu.application.contracts.general_agent_capability_results import (
        GeneralAgentCapabilityResultRepository,
    )
    from taichu.application.contracts.general_agent_context_snapshot import (
        GeneralAgentContextSnapshotRepository,
    )
    from taichu.application.contracts.general_agent_effects import (
        GeneralAgentEffectRepository,
    )
    from taichu.application.contracts.general_agent_run import (
        GeneralAgentRunRepository,
    )


class RecoveryModel(BaseModel):
    """恢复证据使用的严格基础模型。"""

    model_config = ConfigDict(extra="forbid")


class EffectStatus(StrEnum):
    PREPARED = "prepared"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    RECONCILED = "reconciled"
    REQUIRES_HUMAN = "requires_human"


class EffectRecord(RecoveryModel):
    """写 Tool 副作用日志中的一条不可变状态事件。"""

    event_id: str = Field(pattern=r"^effect_event_[a-f0-9]{32}$")
    effect_id: str = Field(pattern=r"^effect_[a-f0-9]{32}$")
    attempt_id: str = Field(pattern=r"^attempt_[a-f0-9]{32}$")
    run_id: str = Field(min_length=1, max_length=128)
    plan_revision: int = Field(ge=1)
    node_id: str = Field(min_length=1, max_length=64)
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    status: EffectStatus
    input_sha256: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=500)
    resource_scopes: list[str] = Field(default_factory=list, max_length=200)
    authorization_reference: str | None = Field(default=None, max_length=200)
    output: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=2_000)
    created_at: str = Field(min_length=1)


class CheckpointPersistenceSummary(RecoveryModel):
    """面向监控页的官方 LangGraph 检查点摘要。"""

    status: Literal["available", "missing"] = "missing"
    checkpoint_count: int = Field(default=0, ge=0)
    latest_checkpoint_id: str | None = Field(default=None, max_length=256)
    latest_step: int | None = None


class CheckpointHistorySummary(RecoveryModel):
    """官方 Checkpointer 返回的单个检查点元数据。"""

    checkpoint_id: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=64)
    step: int
    created_at: str | None = None


class EffectSummary(RecoveryModel):
    """不暴露确定输入和正文输出的副作用监控摘要。"""

    effect_id: str = Field(pattern=r"^effect_[a-f0-9]{32}$")
    node_id: str = Field(min_length=1, max_length=64)
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    status: EffectStatus
    resource_scopes: list[str] = Field(default_factory=list, max_length=200)
    authorization_bound: bool = False
    duplicate_execution_protected: bool = True
    reason: str = Field(default="", max_length=2_000)
    updated_at: str = Field(min_length=1)


class GeneralAgentRecoverySnapshot(RecoveryModel):
    """官方检查点与各写节点最新副作用状态。"""

    run_id: str = Field(min_length=1, max_length=128)
    checkpoint: CheckpointPersistenceSummary
    checkpoints: list[CheckpointHistorySummary] = Field(default_factory=list)
    effects: list[EffectSummary] = Field(default_factory=list)


class GeneralAgentRecoveryPreparation(RecoveryModel):
    """恢复前按固定证据顺序完成的只读校验结果。"""

    owner: CapabilityResultOwner
    checkpoint_revision: int = Field(ge=1)
    checkpoint_id: str = Field(min_length=1, max_length=256)
    checkpoint_step: int
    effect_ids: tuple[str, ...] = ()
    capability_result_ids: tuple[str, ...] = ()
    capability_result_content_sha256: tuple[str, ...] = ()
    context_snapshot_ids: tuple[str, ...] = ()
    decision: RecoveryDecision


class GeneralAgentRecoveryCoordinator:
    """按 owner→Effect→Checkpoint→Result→Context 顺序准备恢复。"""

    def __init__(
        self,
        *,
        run_repository: GeneralAgentRunRepository,
        effect_repository: GeneralAgentEffectRepository | None,
        graph_checkpointer: BaseCheckpointSaver[Any],
        capability_result_repository: GeneralAgentCapabilityResultRepository,
        context_snapshot_repository: (
            GeneralAgentContextSnapshotRepository | None
        ),
    ) -> None:
        self._run_repository = run_repository
        self._effect_repository = effect_repository
        self._graph_checkpointer = graph_checkpointer
        self._capability_result_repository = capability_result_repository
        self._context_snapshot_repository = context_snapshot_repository

    async def validate_owner(
        self,
        run: GeneralAgentRun,
    ) -> CapabilityResultOwner:
        """只从已校验的父运行构造 owner，禁止 run-only 全局查找。"""

        stored = await self._run_repository.get(run.run_id)
        if stored is None:
            raise CapabilityResultOwnerNotFoundError()
        if (
            stored.run_id != run.run_id
            or stored.conversation_id != run.conversation_id
        ):
            raise CapabilityResultOwnerMismatchError()
        return CapabilityResultOwner(
            conversation_id=stored.conversation_id,
            run_id=stored.run_id,
        )

    async def prepare(
        self,
        run: GeneralAgentRun,
    ) -> GeneralAgentRecoveryPreparation:
        """校验所有恢复事实；任一损坏都在重新调用能力前失败。"""

        owner = await self.validate_owner(run)

        effects = (
            await self._effect_repository.list_effects(run.run_id)
            if self._effect_repository is not None
            else []
        )
        latest_effects: dict[str, EffectRecord] = {}
        for effect in effects:
            latest_effects[effect.effect_id] = effect
        unresolved = [
            effect
            for effect in latest_effects.values()
            if effect.status
            in {EffectStatus.UNKNOWN, EffectStatus.REQUIRES_HUMAN}
        ]
        if unresolved:
            unresolved = sorted(unresolved, key=lambda item: item.effect_id)
            evidence: dict[str, Any] = {
                "run_status_before_recovery": run.status.value,
                "projection_revision": run.checkpoint_revision,
                "effect_ids": [item.effect_id for item in unresolved],
                "effect_statuses": {
                    item.effect_id: item.status.value for item in unresolved
                },
                "automatic_restart_count": 0,
            }
            raise GeneralAgentRecoveryRequiresHumanError(
                "写入副作用仍处于未知或待人工核对状态，禁止由能力结果绕过。",
                decision=_recovery_decision(
                    run=run,
                    action=RecoveryAction.REQUIRES_HUMAN,
                    reason_code="effect_reconciliation_requires_human",
                    reason="已有写入副作用处于未知或待人工核对状态，禁止自动恢复。",
                    checkpoint_revision=None,
                    effect_id=(
                        unresolved[0].effect_id
                        if len(unresolved) == 1
                        else None
                    ),
                    evidence=evidence,
                ),
            )

        checkpoint = await self._graph_checkpointer.aget_tuple(
            _checkpoint_config(run.conversation_id)
        )
        if checkpoint is None:
            evidence = {
                "run_status_before_recovery": run.status.value,
                "projection_revision": run.checkpoint_revision,
                "checkpoint_status": "missing",
                "checkpoint_id": None,
                "checkpoint_source": None,
                "checkpoint_step": None,
                "automatic_restart_count": 0,
            }
            raise GeneralAgentRecoveryIntegrityError(
                "没有可恢复的 LangGraph 检查点。",
                decision=_recovery_decision(
                    run=run,
                    action=RecoveryAction.STOP,
                    reason_code="checkpoint_unrecoverable",
                    reason="官方 Checkpointer 中不存在该运行的检查点，恢复已安全停止。",
                    checkpoint_revision=None,
                    effect_id=None,
                    evidence=evidence,
                ),
            )
        checkpoint_evidence = _checkpoint_evidence(checkpoint)
        checkpoint_run_id = _checkpoint_run_id(checkpoint)
        if checkpoint_run_id != run.run_id:
            raise GeneralAgentRecoveryIntegrityError(
                "会话线程的最新检查点不属于当前待恢复运行。",
                decision=_recovery_decision(
                    run=run,
                    action=RecoveryAction.STOP,
                    reason_code="checkpoint_owner_mismatch",
                    reason="会话线程已经推进到其他请求，禁止恢复旧运行。",
                    checkpoint_revision=None,
                    effect_id=None,
                    evidence={
                        **checkpoint_evidence,
                        "expected_run_id": run.run_id,
                        "checkpoint_run_id": checkpoint_run_id,
                        "automatic_restart_count": 0,
                    },
                ),
            )
        checkpoint_id = str(checkpoint_evidence["checkpoint_id"])
        checkpoint_step = int(checkpoint_evidence["checkpoint_step"])
        # 恢复修订只来自官方 checkpoint metadata；业务投影序号仅留作审计。
        checkpoint_revision = max(1, checkpoint_step + 1)

        results = await self._capability_result_repository.list_for_run(owner)

        snapshots = (
            await self._context_snapshot_repository.list_for_run(run.run_id)
            if self._context_snapshot_repository is not None
            else []
        )
        pending_effects = sorted(
            (
                effect
                for effect in latest_effects.values()
                if effect.status is EffectStatus.STARTED
            ),
            key=lambda item: item.effect_id,
        )
        evidence = {
            "run_status_before_recovery": run.status.value,
            "projection_revision": run.checkpoint_revision,
            **checkpoint_evidence,
            "effect_ids": sorted(latest_effects),
            "effect_statuses": {
                effect_id: latest_effects[effect_id].status.value
                for effect_id in sorted(latest_effects)
            },
            "capability_result_ids": [item.result_id for item in results],
            "reused_capability_result_ids": [
                item.result_id for item in results
            ],
            "retried_capability_result_ids": [],
            "capability_result_content_sha256": [
                item.content_sha256 for item in results
            ],
            "context_snapshot_ids": [
                snapshot.snapshot_id for snapshot in snapshots
            ],
            "automatic_restart_count": 0,
            "checkpoint_resume_count": 1,
        }
        if pending_effects:
            decision = _recovery_decision(
                run=run,
                action=RecoveryAction.RECONCILE,
                reason_code="effect_reconciliation_started",
                reason="检测到已开始但未落成功证据的写入，恢复必须先对账真实资源。",
                checkpoint_revision=checkpoint_revision,
                effect_id=(
                    pending_effects[0].effect_id
                    if len(pending_effects) == 1
                    else None
                ),
                evidence=evidence,
            )
        elif run.status is GeneralAgentRunStatus.VERIFYING:
            decision = _recovery_decision(
                run=run,
                action=RecoveryAction.RESUME,
                reason_code="verification_resumed",
                reason="校验已启动但尚无最终结论，从同一运行的有效检查点继续校验。",
                checkpoint_revision=checkpoint_revision,
                effect_id=None,
                evidence=evidence,
            )
        else:
            decision = _recovery_decision(
                run=run,
                action=RecoveryAction.RESUME,
                reason_code="checkpoint_resumed",
                reason="检查点及其依赖证据有效，从同一运行继续执行。",
                checkpoint_revision=checkpoint_revision,
                effect_id=None,
                evidence=evidence,
            )
        return GeneralAgentRecoveryPreparation(
            owner=owner,
            checkpoint_revision=checkpoint_revision,
            checkpoint_id=checkpoint_id,
            checkpoint_step=checkpoint_step,
            effect_ids=tuple(sorted(latest_effects)),
            capability_result_ids=tuple(
                item.result_id for item in results
            ),
            capability_result_content_sha256=tuple(
                item.content_sha256 for item in results
            ),
            context_snapshot_ids=tuple(
                snapshot.snapshot_id for snapshot in snapshots
            ),
            decision=decision,
        )


class GeneralAgentRecoveryIntegrityError(RuntimeError):
    """恢复证据不完整或已损坏，必须安全停止。"""

    def __init__(
        self,
        message: str,
        *,
        decision: RecoveryDecision | None = None,
    ) -> None:
        super().__init__(message)
        self.decision = decision


class GeneralAgentRecoveryRequiresHumanError(RuntimeError):
    """写副作用结论不确定，必须先由作者核对。"""

    def __init__(
        self,
        message: str,
        *,
        decision: RecoveryDecision | None = None,
    ) -> None:
        super().__init__(message)
        self.decision = decision


def _checkpoint_config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def _checkpoint_evidence(checkpoint: object) -> dict[str, Any]:
    config = getattr(checkpoint, "config", {})
    configurable = config.get("configurable", {})
    payload = getattr(checkpoint, "checkpoint", {})
    metadata = getattr(checkpoint, "metadata", {})
    checkpoint_id = configurable.get("checkpoint_id") or payload.get("id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id:
        raise GeneralAgentRecoveryIntegrityError(
            "官方 Checkpointer 返回的检查点缺少 checkpoint_id。"
        )
    raw_step = metadata.get("step", -1)
    checkpoint_step = int(raw_step) if isinstance(raw_step, int) else -1
    return {
        "checkpoint_status": "available",
        "checkpoint_id": checkpoint_id,
        "checkpoint_source": str(metadata.get("source", "unknown")),
        "checkpoint_step": checkpoint_step,
    }


def _checkpoint_run_id(checkpoint: object) -> str | None:
    payload = getattr(checkpoint, "checkpoint", {})
    channel_values = payload.get("channel_values", {})
    run_payload = (
        channel_values.get("run")
        if isinstance(channel_values, dict)
        else None
    )
    if not isinstance(run_payload, dict):
        return None
    run_id = run_payload.get("run_id")
    return run_id if isinstance(run_id, str) else None


def _recovery_decision(
    *,
    run: GeneralAgentRun,
    action: RecoveryAction,
    reason_code: str,
    reason: str,
    checkpoint_revision: int | None,
    effect_id: str | None,
    evidence: dict[str, Any],
) -> RecoveryDecision:
    return RecoveryDecision(
        decision_id=f"recovery_decision_{uuid4().hex}",
        run_id=run.run_id,
        ordinal=len(run.recovery_decisions) + 1,
        action=action,
        reason_code=reason_code,
        reason=reason,
        checkpoint_revision=checkpoint_revision,
        effect_id=effect_id,
        evidence=evidence,
        evidence_sha256=recovery_evidence_sha256(evidence),
        created_at=now_iso(),
    )
