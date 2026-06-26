"""Agent 注册中心测试。"""

import unittest

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from taichu.application.agents.contract import (
    AgentManifest,
    AgentPlugin,
)
from taichu.application.agents.registry import (
    AgentNotFoundError,
    AgentRegistrationError,
    AgentRegistry,
    DuplicateAgentError,
)
from taichu.application.capabilities import CapabilityContext


class EmptyInput(BaseModel):
    """测试输入。"""


class EmptyOutput(BaseModel):
    """测试输出。"""


def build_unused_graph(context: CapabilityContext) -> CompiledStateGraph:
    """返回测试占位 Graph。"""
    raise AssertionError("Graph should not be built during registration")


def create_plugin(
    name: str = "test_agent",
    required_capabilities: frozenset[str] = frozenset(),
) -> AgentPlugin:
    """创建测试 Agent 插件。"""
    return AgentPlugin(
        manifest=AgentManifest(
            name=name,
            label="测试",
            description="测试 Agent",
            input_schema=EmptyInput,
            output_schema=EmptyOutput,
            required_capabilities=required_capabilities,
            exposures=frozenset({"api"}),
        ),
        build_graph=build_unused_graph,
    )


class AgentRegistryTest(unittest.TestCase):
    """验证 Agent 注册边界。"""

    def test_register_valid_plugin_lists_manifest(self) -> None:
        registry = AgentRegistry(CapabilityContext(capabilities={}))

        registry.register(create_plugin())

        self.assertEqual(
            [manifest.name for manifest in registry.list_manifests()],
            ["test_agent"],
        )

    def test_register_duplicate_name_raises(self) -> None:
        registry = AgentRegistry(CapabilityContext(capabilities={}))
        registry.register(create_plugin())

        with self.assertRaises(DuplicateAgentError):
            registry.register(create_plugin())

    def test_register_missing_capability_raises(self) -> None:
        registry = AgentRegistry(CapabilityContext(capabilities={}))

        with self.assertRaises(AgentRegistrationError):
            registry.register(
                create_plugin(
                    required_capabilities=frozenset({"knowledge_search"})
                )
            )

    def test_get_unknown_agent_raises(self) -> None:
        registry = AgentRegistry(CapabilityContext(capabilities={}))

        with self.assertRaises(AgentNotFoundError):
            registry.get_graph("missing")
