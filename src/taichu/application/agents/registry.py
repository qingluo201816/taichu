"""校验、注册和查询产品运行时 Agent。"""

from collections.abc import Iterable

from langgraph.graph.state import CompiledStateGraph

from taichu.application.agents.contract import (
    AgentManifest,
    AgentPlugin,
)
from taichu.application.capabilities import CapabilityContext


class AgentRegistry:
    """管理已通过协议校验的 Agent 插件。"""

    def __init__(self, context: CapabilityContext) -> None:
        self._context = context
        self._plugins: dict[str, AgentPlugin] = {}
        self._graphs: dict[str, CompiledStateGraph] = {}

    def register(self, plugin: AgentPlugin) -> None:
        """校验并注册单个 Agent。"""
        name = plugin.manifest.name
        if name in self._plugins:
            raise DuplicateAgentError(name)

        missing = (
            plugin.manifest.required_capabilities
            - self._context.capabilities.keys()
        )
        if missing:
            raise AgentRegistrationError(
                f"智能体“{name}”缺少所需能力：{', '.join(sorted(missing))}"
            )

        self._plugins[name] = plugin

    def register_all(self, plugins: Iterable[AgentPlugin]) -> None:
        """注册一组 Agent 候选。"""
        for plugin in plugins:
            self.register(plugin)

    def list_manifests(self) -> list[AgentManifest]:
        """按名称返回所有已注册 Agent 的元信息。"""
        return [
            self._plugins[name].manifest
            for name in sorted(self._plugins)
        ]

    def get_graph(self, name: str) -> CompiledStateGraph:
        """取得 Agent Graph，并在第一次访问时构建。"""
        if name not in self._plugins:
            raise AgentNotFoundError(name, sorted(self._plugins))

        if name not in self._graphs:
            self._graphs[name] = self._plugins[name].build_graph(
                self._context
            )
        return self._graphs[name]


class AgentRegistrationError(ValueError):
    """Agent 未通过注册校验。"""


class DuplicateAgentError(AgentRegistrationError):
    """Agent 名称重复。"""

    def __init__(self, name: str) -> None:
        super().__init__(f"智能体“{name}”已经注册")


class AgentNotFoundError(LookupError):
    """请求的 Agent 不存在。"""

    def __init__(self, name: str, available: list[str]) -> None:
        choices = ", ".join(available) or "无"
        super().__init__(
            f"智能体“{name}”不存在。当前可用智能体：{choices}"
        )
