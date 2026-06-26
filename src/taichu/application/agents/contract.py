"""Agent 插件协议。"""

from collections.abc import Callable
from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field

from taichu.application.capabilities import CapabilityContext


class AgentManifest(BaseModel):
    """Agent 注册、调用和展示所需的稳定元信息。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    required_capabilities: frozenset[str] = frozenset()
    exposures: frozenset[str] = frozenset()
    supports_streaming: bool = False


AgentBuilder = Callable[[CapabilityContext], CompiledStateGraph]


@dataclass(frozen=True)
class AgentPlugin:
    """插件发现机制返回的 Agent 候选。"""

    manifest: AgentManifest
    build_graph: AgentBuilder
