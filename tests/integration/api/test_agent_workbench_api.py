"""Agent workbench API integration tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from taichu.application.services.import_service import ImportService
from taichu.config import Settings
from taichu.domain.models.agent_run import (
    AgentReviewCandidateAction,
    AgentReviewCandidateStatus,
    AgentReviewItem,
    AgentRun,
    AgentRunScope,
    AgentRunStatus,
    AgentSchemaValidation,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from taichu.main import create_app


class AgentWorkbenchApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify knowledge extraction workbench endpoints."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(storage).import_text(
            "第一章 山门\n秦阳握着青铜令牌走入太初教山门。",
            source_name="agent_workbench_api_fixture.txt",
        )
        self.app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=_SequenceChatModel(responses=_success_responses()),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_create_run_detail_candidates_and_confirm_create_card(self) -> None:
        create_response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/runs",
            json={"chapter_id": "chapter_001"},
        )
        run_id = create_response.json()["run"]["run_id"]
        detail_response = await self.client.get(
            f"/api/agent-workbench/knowledge-extraction/runs/{run_id}"
        )
        candidates_response = await self.client.get(
            f"/api/agent-workbench/knowledge-extraction/runs/{run_id}/candidates"
        )
        candidate_id = candidates_response.json()["candidates"][0]["review_item_id"]
        confirm_response = await self.client.post(
            f"/api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/confirm"
        )
        knowledge_response = await self.client.get(
            "/api/knowledge/cards?type=character&status=active"
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["run"]["status"], "completed")
        self.assertEqual(detail_response.status_code, 200)
        self.assertGreaterEqual(len(detail_response.json()["run"]["nodes"]), 1)
        self.assertEqual(candidates_response.status_code, 200)
        self.assertGreaterEqual(len(candidates_response.json()["candidates"]), 1)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(
            confirm_response.json()["run"]["review_items"][0]["candidate_status"],
            "confirmed",
        )
        self.assertEqual(knowledge_response.status_code, 200)
        self.assertEqual(knowledge_response.json()["cards"][0]["name"], "秦阳")

    async def test_conflict_and_ignore_candidates_reject_direct_confirm(self) -> None:
        await self.app.state.knowledge_run_store.write_run(_manual_review_run())

        conflict_response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_conflict/confirm"
        )
        ignore_response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_ignore/confirm"
        )
        reject_response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_conflict/reject"
        )
        defer_response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_ignore/defer"
        )

        self.assertEqual(conflict_response.status_code, 422)
        self.assertIn("编辑后确认", conflict_response.json()["error"]["message"])
        self.assertEqual(ignore_response.status_code, 422)
        self.assertIn("不能直接确认", ignore_response.json()["error"]["message"])
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(
            reject_response.json()["run"]["review_items"][0]["candidate_status"],
            "rejected",
        )
        self.assertEqual(defer_response.status_code, 200)
        self.assertEqual(
            defer_response.json()["run"]["review_items"][1]["candidate_status"],
            "deferred",
        )


class _SequenceChatModel(BaseChatModel):
    responses: list[str]

    @property
    def _llm_type(self) -> str:
        return "taichu-test-sequence"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if not self.responses:
            raise RuntimeError("没有可用的模拟 LLM 响应。")
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=self.responses.pop(0)))
            ]
        )


def _success_responses() -> list[str]:
    excerpt = "秦阳握着青铜令牌走入太初教山门。"
    return [
        json.dumps(
            {
                "characters": [{"name": "秦阳", "aliases": [], "source_excerpt": excerpt}],
                "locations": [],
                "factions": [],
                "items": [],
                "ignored": [],
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "knowledge_type": "character",
                "cards": [
                    {
                        "name": "秦阳",
                        "aliases": [],
                        "summary": "本章走入太初教山门的人物。",
                        "importance": "core",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "role_type": "protagonist",
                        "identity": "太初教弟子",
                        "relationship_summary": None,
                        "death_chapter_id": None,
                        "current_realm_text": None,
                        "first_seen_chapter_id": "chapter_001",
                        "last_seen_chapter_id": "chapter_001",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    ]


def _manual_review_run() -> AgentRun:
    now = "2026-07-04T15:30:22Z"
    return AgentRun(
        run_id="extract_run_20260704_153022_b1c2d3",
        status=AgentRunStatus.COMPLETED,
        scope=AgentRunScope(chapter_id="chapter_001", chapter_title="第一章 山门"),
        started_at=now,
        finished_at=now,
        review_items=[
            AgentReviewItem(
                review_item_id="review_item_conflict",
                run_id="extract_run_20260704_153022_b1c2d3",
                candidate_action=AgentReviewCandidateAction.CONFLICT,
                knowledge_type=StructuredKnowledgeType.CHARACTER,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="秦阳",
                suggested_card={"type": "character", "name": "秦阳"},
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="存在冲突，建议编辑后确认",
                created_at=now,
                updated_at=now,
            ),
            AgentReviewItem(
                review_item_id="review_item_ignore",
                run_id="extract_run_20260704_153022_b1c2d3",
                candidate_action=AgentReviewCandidateAction.IGNORE,
                knowledge_type=StructuredKnowledgeType.ITEM,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="碎片信息",
                suggested_card={"type": "item", "name": "碎片信息"},
                schema_validation=AgentSchemaValidation(
                    passed=False,
                    errors=["信息太碎，建议忽略。"],
                ),
                suggested_action_label="建议忽略",
                created_at=now,
                updated_at=now,
            ),
        ],
    )
