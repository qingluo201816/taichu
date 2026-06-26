"""插件发现测试。"""

import unittest

from taichu.infrastructure.plugin_discovery import (
    discover_agents,
    discover_tools,
)


class PluginDiscoveryTest(unittest.TestCase):
    """验证发现机制只返回插件候选。"""

    def test_discover_agents_finds_chat(self) -> None:
        plugins = discover_agents("taichu.application.agents")

        self.assertEqual(
            [plugin.manifest.name for plugin in plugins],
            ["chat"],
        )

    def test_discover_tools_ignores_contract_modules(self) -> None:
        plugins = discover_tools("taichu.application.tools")

        self.assertEqual(plugins, [])
