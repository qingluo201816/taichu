"""通用写作助手的节点尝试、副作用和恢复决策模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class RecoveryAction(StrEnum):
    REUSE = "reuse"
    RETRY = "retry"
    RECONCILE = "reconcile"
    RESUME = "resume"
    REQUIRES_HUMAN = "requires_human"
    STOP = "stop"


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


class RecoveryDecision(RecoveryModel):
    """Runtime 根据检查点与副作用证据作出的显式恢复决定。"""

    action: RecoveryAction
    reason: str = Field(min_length=1, max_length=2_000)
    checkpoint_revision: int | None = Field(default=None, ge=1)
    effect_id: str | None = Field(default=None, max_length=80)
    evidence: dict[str, Any] = Field(default_factory=dict)


class CheckpointIntegritySummary(RecoveryModel):
    """面向监控页的脱敏 LangGraph 检查点摘要。"""

    current_revision: int = Field(default=0, ge=0)
    available_revisions: list[int] = Field(default_factory=list)
    integrity_status: str = Field(default="missing", max_length=64)
    recovered_from_revision: int | None = Field(default=None, ge=1)
    damage_warnings: list[str] = Field(default_factory=list, max_length=100)
    legacy_migrated: bool = False


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
    effects: list[EffectSummary] = Field(default_factory=list)
