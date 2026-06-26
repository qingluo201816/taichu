"""Tool 插件协议。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from taichu.application.capabilities import CapabilityContext


class ToolManifest(BaseModel):
    """Tool 注册与调用所需的稳定元信息。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    required_capabilities: frozenset[str] = frozenset()
    exposures: frozenset[str] = frozenset()


ToolHandler = Callable[
    [BaseModel, CapabilityContext],
    Awaitable[BaseModel],
]


@dataclass(frozen=True)
class ToolPlugin:
    """插件发现机制返回的 Tool 候选。"""

    manifest: ToolManifest
    run: ToolHandler
