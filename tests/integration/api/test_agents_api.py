"""Agent API 集成测试。"""

import unittest

from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage

from taichu.main import create_app


class AgentApiTest(unittest.IsolatedAsyncioTestCase):
    """验证 Agent manifest API，旧 /api/chat 不再作为产品入口保留。"""

    async def asyncSetUp(self) -> None:
        app = create_app(
            llm=FakeMessagesListChatModel(responses=[AIMessage(content="测试回复")])
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_list_agents_returns_manifest_fields(self) -> None:
        response = await self.client.get("/api/agents")

        self.assertEqual(response.status_code, 200)
        agent = response.json()["agents"][0]
        self.assertEqual(agent["name"], "chat")
        self.assertEqual(agent["required_capabilities"], ["llm", "retrieval"])
        self.assertEqual(agent["exposures"], ["api", "mcp", "ui"])
        self.assertFalse(agent["supports_streaming"])

    async def test_legacy_chat_endpoint_is_removed(self) -> None:
        response = await self.client.post(
            "/api/chat",
            json={"agent": "chat", "message": "你好"},
        )

        self.assertEqual(response.status_code, 404)

    async def test_selection_ai_is_not_registered_as_agent(self) -> None:
        response = await self.client.get("/api/agents")

        agent_names = {agent["name"] for agent in response.json()["agents"]}
        self.assertNotIn("selection_ai", agent_names)
        self.assertNotIn("selection_assistant", agent_names)
