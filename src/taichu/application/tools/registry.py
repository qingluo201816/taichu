"""校验、注册和查询可复用 Tool。"""

from collections.abc import Iterable

from taichu.application.capabilities import CapabilityContext
from taichu.application.tools.contract import (
    ToolHandler,
    ToolManifest,
    ToolPlugin,
)


class ToolRegistry:
    """管理已通过协议校验的 Tool 插件。"""

    def __init__(self, context: CapabilityContext) -> None:
        self._context = context
        self._plugins: dict[str, ToolPlugin] = {}

    def register(self, plugin: ToolPlugin) -> None:
        """校验并注册单个 Tool。"""
        name = plugin.manifest.name
        if name in self._plugins:
            raise ToolRegistrationError(
                f"Tool '{name}' is already registered"
            )

        missing = (
            plugin.manifest.required_capabilities
            - self._context.capabilities.keys()
        )
        if missing:
            raise ToolRegistrationError(
                f"Tool '{name}' requires unavailable capabilities: "
                f"{', '.join(sorted(missing))}"
            )

        self._plugins[name] = plugin

    def register_all(self, plugins: Iterable[ToolPlugin]) -> None:
        """注册一组 Tool 候选。"""
        for plugin in plugins:
            self.register(plugin)

    def list_manifests(self) -> list[ToolManifest]:
        """按名称返回所有已注册 Tool 的元信息。"""
        return [
            self._plugins[name].manifest
            for name in sorted(self._plugins)
        ]

    def get(self, name: str) -> ToolHandler:
        """取得 Tool 调用函数。"""
        if name not in self._plugins:
            raise ToolNotFoundError(name)
        return self._plugins[name].run


class ToolRegistrationError(ValueError):
    """Tool 未通过注册校验。"""


class ToolNotFoundError(LookupError):
    """请求的 Tool 不存在。"""

    def __init__(self, name: str) -> None:
        super().__init__(f"Tool '{name}' not found")
