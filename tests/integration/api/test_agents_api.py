"""Agent API 集成测试。"""

import unittest

from httpx import ASGITransport, AsyncClient

from taichu.main import create_app


class AgentApiTest(unittest.IsolatedAsyncioTestCase):
    """验证通用 Agent manifest API 保留，但旧 Chat 入口已移除。"""

    async def asyncSetUp(self) -> None:
        app = create_app()
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_list_agents_includes_knowledge_extraction_without_chat_manifest(
        self,
    ) -> None:
        response = await self.client.get("/api/agents")

        self.assertEqual(response.status_code, 200)
        agents = response.json()["agents"]
        self.assertEqual([agent["name"] for agent in agents], ["knowledge_extraction"])
        self.assertEqual(agents[0]["label"], "正文知识沉淀 Agent")

    async def test_legacy_chat_endpoint_is_removed(self) -> None:
        response = await self.client.post(
            "/api/chat",
            json={"agent": "chat", "message": "你好"},
        )

        self.assertEqual(response.status_code, 404)

    async def test_agent_chat_endpoint_is_removed(self) -> None:
        response = await self.client.post(
            "/api/agents/chat",
            json={"message": "你好"},
        )

        self.assertEqual(response.status_code, 404)

    async def test_selection_ai_is_not_registered_as_agent(self) -> None:
        response = await self.client.get("/api/agents")

        agent_names = {agent["name"] for agent in response.json()["agents"]}
        self.assertIn("knowledge_extraction", agent_names)
        self.assertNotIn("selection_ai", agent_names)
        self.assertNotIn("selection_assistant", agent_names)
