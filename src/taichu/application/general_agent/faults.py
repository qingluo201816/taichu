"""通用写作助手 Runtime 的故障注入边界契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class GeneralAgentFaultPoint(StrEnum):
    """Runtime 在真实持久化或调用边界公开的固定故障点。"""

    PLAN_CREATED = "plan_created"
    CAPABILITY_RESULT_COMMITTED = "capability_result_committed"
    SUBAGENT_STARTED = "subagent_started"
    AUTHORIZATION_REQUEST_DURABLE = "authorization_request_durable"
    RESOURCE_WRITE_APPLIED = "resource_write_applied"
    VERIFICATION_STARTED = "verification_started"
    CHECKPOINT_REVISION_VALIDATION = "checkpoint_revision_validation"


@dataclass(frozen=True, slots=True)
class GeneralAgentFaultContext:
    """故障点的运行身份与当前持久边界，不包含任何评测案例身份。"""

    conversation_id: str
    run_id: str
    plan_revision: int
    checkpoint_revision: int
    node_id: str | None = None
    attempt_id: str | None = None
    capability_kind: str | None = None
    capability_name: str | None = None
    durable_identity: str | None = None


@runtime_checkable
class GeneralAgentFaultHook(Protocol):
    """由组合根选择性注入；未注入时 Runtime 不执行额外行为。"""

    def on_fault_point(
        self,
        *,
        point: GeneralAgentFaultPoint,
        context: GeneralAgentFaultContext,
    ) -> None: ...


class InjectedProcessTermination(RuntimeError):
    """只用于故障注入，要求 Runtime 保留活动状态并模拟进程终止。"""


__all__ = [
    "GeneralAgentFaultContext",
    "GeneralAgentFaultHook",
    "GeneralAgentFaultPoint",
    "InjectedProcessTermination",
]
