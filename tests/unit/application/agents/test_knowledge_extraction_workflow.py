"""Knowledge extraction workflow tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from taichu.application.services.import_service import ImportService
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.knowledge_extraction_service import (
    KnowledgeExtractionService,
)
from taichu.domain.models.agent_run import AgentRunStatus
from taichu.infrastructure.agent_runs import JsonAgentRunStore
from taichu.infrastructure.knowledge import JSONKnowledgeRepository
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend


class KnowledgeExtractionWorkflowTest(unittest.IsolatedAsyncioTestCase):
    """Verify LangGraph workflow behavior with mock LLM responses."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(self.storage).import_text(
            "第一章 山门\n秦阳握着青铜令牌走入太初教山门。",
            source_name="workflow_fixture.txt",
        )
        self.chapter_service = ChapterService(self.storage)
        self.repository = JSONKnowledgeRepository(self.storage)
        self.run_store = JsonAgentRunStore(self.assets_root)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_workflow_writes_completed_run_with_prompt_and_review_items(
        self,
    ) -> None:
        service = KnowledgeExtractionService(
            chapter_service=self.chapter_service,
            llm=_SequenceLLM(_success_responses()),
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )

        run = await service.create_run(chapter_id="chapter_001")
        loaded = await self.run_store.get_run(run.run_id)

        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIsNotNone(loaded)
        self.assertEqual(run.metrics.llm_call_count, 3)
        self.assertGreaterEqual(run.metrics.candidate_total, 4)
        self.assertTrue(
            all(call.input_prompt and call.raw_response for call in run.llm_calls)
        )
        self.assertIn("GeneralExtractionNode", {node.node_name for node in run.nodes})
        self.assertEqual(run.review_items[0].candidate_action.value, "create_card")

    async def test_non_json_llm_response_marks_run_failed(self) -> None:
        service = KnowledgeExtractionService(
            chapter_service=self.chapter_service,
            llm=_SequenceLLM(["不是 JSON"]),
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )

        run = await service.create_run(chapter_id="chapter_001")

        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertIn("不是有效 JSON", run.errors[0])
        self.assertEqual(run.llm_calls[0].error is not None, True)


class _SequenceLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses

    async def complete(self, prompt: str) -> str:
        if not self._responses:
            raise RuntimeError("没有可用的模拟 LLM 响应。")
        return self._responses.pop(0)


def _success_responses() -> list[str]:
    excerpt = "秦阳握着青铜令牌走入太初教山门。"
    return [
        json.dumps(
            {
                "characters": [{"name": "秦阳", "aliases": [], "source_excerpt": excerpt}],
                "locations": [
                    {
                        "name": "太初教山门",
                        "aliases": ["山门"],
                        "source_excerpt": excerpt,
                    }
                ],
                "factions": [{"name": "太初教", "aliases": [], "source_excerpt": excerpt}],
                "items": [{"name": "青铜令牌", "aliases": ["令牌"], "source_excerpt": excerpt}],
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
        json.dumps(
            {
                "locations": [
                    {
                        "name": "太初教山门",
                        "aliases": ["山门"],
                        "summary": "秦阳入山时出现的太初教入口。",
                        "importance": "normal",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "controlling_faction_id": None,
                        "first_seen_chapter_id": "chapter_001",
                    }
                ],
                "factions": [
                    {
                        "name": "太初教",
                        "aliases": [],
                        "summary": "本章出现的修行势力。",
                        "importance": "major",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "faction_type": "sect",
                        "leader_id": None,
                    }
                ],
                "items": [
                    {
                        "name": "青铜令牌",
                        "aliases": ["令牌"],
                        "summary": "秦阳入山时持有的令牌。",
                        "importance": "normal",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "item_type": "other",
                        "grade": None,
                        "current_holder_id": None,
                        "first_seen_chapter_id": "chapter_001",
                        "last_seen_chapter_id": "chapter_001",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    ]
