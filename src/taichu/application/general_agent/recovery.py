"""通用写作助手的节点尝试、副作用和恢复决策模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

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


class NodeAttemptStatus(StrEnum):
    PREPARED = "prepared"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EffectStatus(StrEnum):
    PREPARED = "prepared"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    RECONCILED = "reconciled"
    REQUIRES_HUMAN = "requires_human"


class NodeAttempt(RecoveryModel):
    """一次计划修订中某个能力节点的稳定执行身份。"""

    attempt_id: str = Field(pattern=r"^attempt_[a-f0-9]{32}$")
    run_id: str = Field(min_length=1, max_length=128)
    plan_revision: int = Field(ge=1)
    node_id: str = Field(min_length=1, max_length=64)
    status: NodeAttemptStatus
    started_at: str | None = None
    finished_at: str | None = None
    error_type: str | None = Field(default=None, max_length=200)
    error_message: str | None = Field(default=None, max_length=2_000)


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


class CheckpointIntegritySummary(RecoveryModel):
    """面向监控页的脱敏 LangGraph 检查点摘要。"""

    current_revision: int = Field(default=0, ge=0)
    available_revisions: list[int] = Field(default_factory=list)
    invalid_revisions: list[int] = Field(default_factory=list)
    integrity_status: str = Field(default="missing", max_length=64)
    recovered_from_revision: int | None = Field(default=None, ge=1)
    damage_warnings: list[str] = Field(default_factory=list, max_length=100)
    legacy_migrated: bool = False


class CheckpointRevisionSummary(RecoveryModel):
    """单次检查点持久化的可读审计元数据。"""

    revision: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=128)
    created_at: str = Field(min_length=1)


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
    """检查点完整性与各写节点最新副作用状态。"""

    run_id: str = Field(min_length=1, max_length=128)
    checkpoint: CheckpointIntegritySummary
    revisions: list[CheckpointRevisionSummary] = Field(default_factory=list)
    effects: list[EffectSummary] = Field(default_factory=list)


class GeneralAgentRecoveryPreparation(RecoveryModel):
    """恢复前按固定证据顺序完成的只读校验结果。"""

    owner: CapabilityResultOwner
    checkpoint_revision: int = Field(ge=1)
    checkpoint_integrity_status: str = Field(min_length=1, max_length=64)
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
            evidence = {
                "run_status_before_recovery": run.status.value,
                "run_checkpoint_revision": run.checkpoint_revision,
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

        inspect_thread = getattr(self._graph_checkpointer, "inspect_thread", None)
        if not callable(inspect_thread):
            integrity_evidence: dict[str, Any] = {
                "run_status_before_recovery": run.status.value,
                "run_checkpoint_revision": run.checkpoint_revision,
                "checkpoint_integrity_status": "unsupported",
                "checkpoint_valid_revisions": [],
                "checkpoint_invalid_revisions": [],
                "checkpoint_selected_revision": None,
                "checkpoint_recovered_from_revision": None,
                "checkpoint_damage_warnings": [
                    "当前检查点仓储不支持恢复完整性检查。"
                ],
                "automatic_restart_count": 0,
            }
            raise GeneralAgentRecoveryIntegrityError(
                "当前检查点仓储不支持恢复完整性检查。",
                decision=_recovery_decision(
                    run=run,
                    action=RecoveryAction.STOP,
                    reason_code="checkpoint_unrecoverable",
                    reason="检查点仓储无法提供完整性证据，恢复已安全停止。",
                    checkpoint_revision=None,
                    effect_id=None,
                    evidence=integrity_evidence,
                ),
            )
        checkpoint = inspect_thread(run.run_id)
        checkpoint_evidence = _checkpoint_integrity_evidence(checkpoint)
        integrity_status = str(
            checkpoint_evidence["checkpoint_integrity_status"]
        )
        selected_revision = checkpoint_evidence[
            "checkpoint_selected_revision"
        ]
        checkpoint_revision = (
            int(selected_revision)
            if isinstance(selected_revision, int)
            else 0
        )
        if (
            checkpoint_revision < 1
            or integrity_status not in {"valid", "recovered"}
        ):
            evidence = {
                "run_status_before_recovery": run.status.value,
                "run_checkpoint_revision": run.checkpoint_revision,
                **checkpoint_evidence,
                "automatic_restart_count": 0,
            }
            raise GeneralAgentRecoveryIntegrityError(
                "没有可安全恢复的 LangGraph 检查点修订。",
                decision=_recovery_decision(
                    run=run,
                    action=RecoveryAction.STOP,
                    reason_code="checkpoint_unrecoverable",
                    reason="不存在可验证的有效检查点修订，恢复已安全停止。",
                    checkpoint_revision=None,
                    effect_id=None,
                    evidence=evidence,
                ),
            )

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
            "run_checkpoint_revision": run.checkpoint_revision,
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
            checkpoint_integrity_status=integrity_status,
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


def _checkpoint_integrity_evidence(checkpoint: object) -> dict[str, Any]:
    current_revision = int(getattr(checkpoint, "current_revision", 0))
    integrity_status = str(
        getattr(checkpoint, "integrity_status", "missing")
    )
    valid_revisions = [
        int(item)
        for item in getattr(checkpoint, "available_revisions", [])
    ]
    invalid_revisions = [
        int(item)
        for item in getattr(checkpoint, "invalid_revisions", [])
    ]
    recovered_from = getattr(checkpoint, "recovered_from_revision", None)
    damage_warnings = [
        str(item) for item in getattr(checkpoint, "damage_warnings", [])
    ]
    selected_revision = (
        current_revision
        if current_revision >= 1
        and integrity_status in {"valid", "recovered"}
        else None
    )
    return {
        "checkpoint_integrity_status": integrity_status,
        "checkpoint_valid_revisions": valid_revisions,
        "checkpoint_invalid_revisions": invalid_revisions,
        "checkpoint_selected_revision": selected_revision,
        "checkpoint_recovered_from_revision": (
            int(recovered_from) if recovered_from is not None else None
        ),
        "checkpoint_damage_warnings": damage_warnings,
    }


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
