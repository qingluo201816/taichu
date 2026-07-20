"""Tool 插件协议。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext


class ToolSideEffect(StrEnum):
    """Tool 的副作用等级。"""

    READ_ONLY = "read_only"
    PREVIEW = "preview"
    WRITE = "write"
    HIGH_RISK_WRITE = "high_risk_write"


class ToolAuthorizationPolicy(StrEnum):
    """Tool 是否需要作者授权。"""

    NONE = "none"
    AUTHOR_GRANT = "author_grant"
    SECOND_CONFIRMATION = "second_confirmation"


class ToolIdempotencyPolicy(StrEnum):
    """Tool 的幂等要求。"""

    NONE = "none"
    REQUIRED = "required"


class ToolReconciliationStatus(StrEnum):
    """进程中断后对真实副作用的确定性核对结果。"""

    NOT_APPLIED = "not_applied"
    SUCCEEDED = "succeeded"
    UNKNOWN = "unknown"


class ToolReconciliationResult(BaseModel):
    """Tool 自己根据真实资源状态给出的对账证据。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ToolReconciliationStatus
    output: dict[str, object] = Field(default_factory=dict)
    evidence: dict[str, object] = Field(default_factory=dict)
    reason: str = ""


class ToolManifest(BaseModel):
    """Tool 注册与调用所需的稳定元信息。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    required_capabilities: frozenset[str] = frozenset()
    exposures: frozenset[str] = frozenset()
    side_effect: ToolSideEffect = ToolSideEffect.READ_ONLY
    allowed_callers: frozenset[str] = frozenset({"orchestrator"})
    requires_external_access: bool = False
    authorization_policy: ToolAuthorizationPolicy = ToolAuthorizationPolicy.NONE
    idempotency_policy: ToolIdempotencyPolicy = ToolIdempotencyPolicy.NONE
    default_timeout_seconds: float = Field(default=30, gt=0, le=600)
    max_result_chars: int = Field(default=50_000, ge=100, le=500_000)
    retryable: bool = False


ToolHandler = Callable[
    [BaseModel, InvocationContext, CapabilityContext],
    Awaitable[BaseModel],
]

ToolReconciler = Callable[
    [BaseModel, InvocationContext, CapabilityContext],
    Awaitable[ToolReconciliationResult],
]


@dataclass(frozen=True)
class ToolPlugin:
    """插件发现机制返回的 Tool 候选。"""

    manifest: ToolManifest
    run: ToolHandler
    reconcile: ToolReconciler | None = None
