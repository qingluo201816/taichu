"""独立于知识沉淀 Workflow Graph 的专业子 Agent 协议。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext


class SubagentResourceLimits(BaseModel):
    """单次专业能力内部允许使用的有限资源。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_seconds: float = Field(default=600, gt=0, le=900)
    max_tool_calls: int = Field(default=10, ge=0, le=50)
    max_output_chars: int = Field(default=50_000, ge=100, le=200_000)
    max_output_tokens: int = Field(default=8_000, ge=128, le=100_000)
    max_retries: int = Field(default=1, ge=0, le=3)


class SubagentManifest(BaseModel):
    """一个稳定专业能力的注册、权限、模型和校验契约。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    non_responsibilities: tuple[str, ...] = ()
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    artifact_types: frozenset[str]
    model_role: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    allowed_tools: frozenset[str] = frozenset()
    accepted_scopes: frozenset[str] = frozenset(
        {"selection", "chapter", "range", "novel"}
    )
    accepted_artifact_types: frozenset[str] = frozenset()
    required_capabilities: frozenset[str] = frozenset(
        {"llm", "model_role_router", "tool_registry", "artifact_repository"}
    )
    exposures: frozenset[str] = frozenset({"agent_runtime"})
    limits: SubagentResourceLimits = Field(default_factory=SubagentResourceLimits)
    supports_streaming: bool = False
    repair_attempts: int = Field(default=1, ge=0, le=2)


SubagentHandler = Callable[
    [SubagentManifest, BaseModel, InvocationContext, CapabilityContext],
    Awaitable[BaseModel],
]


@dataclass(frozen=True)
class SubagentPlugin:
    """插件发现返回的专业子 Agent 候选。"""

    manifest: SubagentManifest
    run: SubagentHandler
