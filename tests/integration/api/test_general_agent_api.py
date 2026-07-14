"""通用写作助手 Runtime HTTP 全链路测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from taichu.application.contracts.llm import (
    LLMCost,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
from taichu.config import Settings
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class _DirectAnswerGateway:
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        payload: dict[str, object]
        if request.task_name == "general_writing_orchestrator.plan":
            payload = {
                "rationale": "这是不依赖小说事实的通用写作方法问题，可以直接回答。",
                "direct_response": "可以先明确场景目标，再安排冲突和信息释放。",
                "nodes": [],
            }
        else:
            payload = {
                "outcome": "satisfied",
                "final_answer": "可以先明确场景目标，再安排冲突升级与信息释放。",
                "issues": [],
                "should_replan": False,
            }
        return LLMResponse(
            text=json.dumps(payload, ensure_ascii=False),
            model_id=request.model_id,
            upstream_model=request.model_id,
            usage=LLMUsage(input_tokens=20, output_tokens=20, total_tokens=40),
            cost=LLMCost(amount=Decimal("0.001"), kind="estimated"),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        del request
        if False:
            yield LLMStreamEvent(event_type="completed")

    def list_models(self) -> list[LLMModelProfile]:
        return []


class GeneralAgentApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.gateway = _DirectAnswerGateway()
        self.app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm_gateway=self.gateway,
            knowledge_repository=InMemoryKnowledgeRepository(),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_run_list_detail_and_delete(self) -> None:
        response = await self.client.post(
            "/api/agent-workbench/general-assistant/runs",
            json={"user_goal": "怎样规划一个有冲突的场景？"},
        )

        self.assertEqual(response.status_code, 200)
        run = response.json()["run"]
        self.assertEqual(run["status"], "completed")
        self.assertIn("冲突升级", run["final_answer"])
        self.assertEqual(run["agent_name"], "general_writing_assistant")
        run_id = run["run_id"]

        detail = await self.client.get(
            f"/api/agent-workbench/general-assistant/runs/{run_id}"
        )
        listing = await self.client.get(
            "/api/agent-workbench/general-assistant/runs"
        )
        traces = await self.client.get(
            f"/api/agent-workbench/general-assistant/runs/{run_id}/traces"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(traces.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["runs"][0]["run_id"], run_id)
        self.assertEqual(traces.json()["total"], 2)
        self.assertEqual(
            [item["capability_name"] for item in traces.json()["traces"]],
            [
                "general_writing_orchestrator.plan",
                "general_writing_orchestrator.verify",
            ],
        )
        self.assertTrue(
            all(item["run_id"] == run_id for item in traces.json()["traces"])
        )

        deleted = await self.client.delete(
            f"/api/agent-workbench/general-assistant/runs/{run_id}"
        )
        missing = await self.client.get(
            f"/api/agent-workbench/general-assistant/runs/{run_id}"
        )
        missing_traces = await self.client.get(
            f"/api/agent-workbench/general-assistant/runs/{run_id}/traces"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing_traces.status_code, 404)
        self.assertEqual(
            [request.task_name for request in self.gateway.requests],
            [
                "general_writing_orchestrator.plan",
                "general_writing_orchestrator.verify",
            ],
        )
