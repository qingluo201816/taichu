"""扫描并导入产品运行时插件候选。"""

from importlib import import_module
from pkgutil import iter_modules

from taichu.application.agents.contract import (
    AgentManifest,
    AgentPlugin,
)
from taichu.application.tools.contract import ToolManifest, ToolPlugin
from taichu.application.subagents.contract import (
    SubagentManifest,
    SubagentPlugin,
)


def discover_agents(package_name: str) -> list[AgentPlugin]:
    """发现指定包下的 Agent 子包。"""
    try:
        package = import_module(package_name)
    except Exception as error:
        raise PluginDiscoveryError(
            f"Unable to import Agent package '{package_name}'"
        ) from error

    plugins: list[AgentPlugin] = []
    ignored_packages = {"models"}
    for module_info in sorted(
        iter_modules(package.__path__, f"{package_name}."),
        key=lambda item: item.name,
    ):
        if not module_info.ispkg:
            continue
        short_name = module_info.name.rsplit(".", maxsplit=1)[-1]
        if short_name in ignored_packages:
            continue

        graph_module_name = f"{module_info.name}.graph"
        try:
            graph_module = import_module(graph_module_name)
            manifest = graph_module.manifest
            build_graph = graph_module.build_graph
        except Exception as error:
            raise PluginDiscoveryError(
                f"Unable to load Agent plugin '{module_info.name}'"
            ) from error

        if not isinstance(manifest, AgentManifest):
            raise PluginDiscoveryError(
                f"Agent '{module_info.name}' exports an invalid manifest"
            )
        if not callable(build_graph):
            raise PluginDiscoveryError(
                f"Agent '{module_info.name}' exports a non-callable build_graph"
            )

        plugins.append(
            AgentPlugin(
                manifest=manifest,
                build_graph=build_graph,
            )
        )

    return plugins


def discover_tools(package_name: str) -> list[ToolPlugin]:
    """发现指定包下的 Tool 模块或子包。"""
    try:
        package = import_module(package_name)
    except Exception as error:
        raise PluginDiscoveryError(
            f"Unable to import Tool package '{package_name}'"
        ) from error

    plugins: list[ToolPlugin] = []
    ignored_modules = {"contract", "models", "registry"}
    for module_info in sorted(
        iter_modules(package.__path__, f"{package_name}."),
        key=lambda item: item.name,
    ):
        short_name = module_info.name.rsplit(".", maxsplit=1)[-1]
        if short_name in ignored_modules or short_name.startswith("_"):
            continue

        module_name = (
            f"{module_info.name}.tool" if module_info.ispkg else module_info.name
        )
        try:
            tool_module = import_module(module_name)
            manifest = tool_module.manifest
            run = tool_module.run
            reconcile = getattr(tool_module, "reconcile", None)
        except Exception as error:
            raise PluginDiscoveryError(
                f"Unable to load Tool plugin '{module_info.name}'"
            ) from error

        if not isinstance(manifest, ToolManifest):
            raise PluginDiscoveryError(
                f"Tool '{module_info.name}' exports an invalid manifest"
            )
        if not callable(run):
            raise PluginDiscoveryError(
                f"Tool '{module_info.name}' exports a non-callable run"
            )
        if reconcile is not None and not callable(reconcile):
            raise PluginDiscoveryError(
                f"Tool '{module_info.name}' exports a non-callable reconcile"
            )

        plugins.append(ToolPlugin(manifest=manifest, run=run, reconcile=reconcile))

    return plugins


def discover_subagents(package_name: str) -> list[SubagentPlugin]:
    """发现独立异步 Handler 协议的专业子 Agent。"""
    try:
        package = import_module(package_name)
    except Exception as error:
        raise PluginDiscoveryError(
            f"Unable to import Subagent package '{package_name}'"
        ) from error

    plugins: list[SubagentPlugin] = []
    for module_info in sorted(
        iter_modules(package.__path__, f"{package_name}."),
        key=lambda item: item.name,
    ):
        short_name = module_info.name.rsplit(".", maxsplit=1)[-1]
        if not module_info.ispkg or short_name.startswith("_"):
            continue
        module_name = f"{module_info.name}.agent"
        try:
            agent_module = import_module(module_name)
            manifest = agent_module.manifest
            run = agent_module.run
        except Exception as error:
            raise PluginDiscoveryError(
                f"Unable to load Subagent plugin '{module_info.name}'"
            ) from error
        if not isinstance(manifest, SubagentManifest):
            raise PluginDiscoveryError(
                f"Subagent '{module_info.name}' exports an invalid manifest"
            )
        if not callable(run):
            raise PluginDiscoveryError(
                f"Subagent '{module_info.name}' exports a non-callable run"
            )
        plugins.append(SubagentPlugin(manifest=manifest, run=run))
    return plugins


class PluginDiscoveryError(RuntimeError):
    """插件扫描或动态导入失败。"""
