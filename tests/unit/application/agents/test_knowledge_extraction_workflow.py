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
            default_model_name="test-model",
        )

        run = await service.create_run(chapter_id="chapter_001")
        loaded = await self.run_store.get_run(run.run_id)

        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIsNotNone(loaded)
        self.assertEqual(run.metrics.llm_call_count, 3)
        self.assertEqual(run.model_name, "test-model")
        self.assertTrue(all(call.model_name == "test-model" for call in run.llm_calls))
        self.assertGreaterEqual(run.metrics.candidate_total, 4)
        self.assertGreaterEqual(len(run.raw_mentions), 4)
        self.assertEqual(run.raw_mentions[0].name, "秦阳")
        self.assertGreaterEqual(len(run.entity_groups), 4)
        self.assertEqual(run.entity_groups[0].quality_decision, "accepted")
        node_names = [node.node_name for node in run.nodes]
        self.assertIn("MentionNormalizeNode", node_names)
        self.assertIn("EntityAggregationNode", node_names)
        self.assertIn("CandidateQualityGateNode", node_names)
        self.assertIn("WriteIntermediateJsonNode", node_names)
        self.assertNotIn("MergeChapterCandidatesNode", node_names)
        self.assertTrue(
            all(call.input_prompt and call.raw_response for call in run.llm_calls)
        )
        self.assertEqual(
            [call.prompt_version for call in run.llm_calls],
            ["general_extraction_v2", "character_expert_v2", "entity_expert_v2"],
        )
        self.assertEqual(run.prompt_version, "knowledge_extraction_prompt_v2")
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

    async def test_quality_gate_filters_generic_mentions_before_experts(self) -> None:
        service = KnowledgeExtractionService(
            chapter_service=self.chapter_service,
            llm=_SequenceLLM([_generic_mentions_response()]),
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )

        run = await service.create_run(chapter_id="chapter_001")

        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertEqual(run.metrics.llm_call_count, 1)
        self.assertEqual(run.metrics.candidate_total, 0)
        self.assertEqual(len(run.entity_groups), 3)
        self.assertTrue(
            all(group.quality_decision == "rejected" for group in run.entity_groups)
        )
        self.assertEqual(run.raw_candidates, [])


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
                "mentions": [
                    {
                        "name": "秦阳",
                        "knowledge_type": "character",
                        "description": "秦阳走入太初教山门。",
                        "evidence_excerpts": [excerpt],
                        "reason": "稳定专名角色。",
                    },
                    {
                        "name": "太初教山门",
                        "knowledge_type": "location",
                        "description": "太初教入口地点。",
                        "evidence_excerpts": [excerpt],
                        "reason": "稳定地点名。",
                    },
                    {
                        "name": "太初教",
                        "knowledge_type": "faction",
                        "description": "本章出现的修行势力。",
                        "evidence_excerpts": [excerpt],
                        "reason": "稳定组织名称。",
                    },
                    {
                        "name": "青铜令牌",
                        "knowledge_type": "item",
                        "description": "秦阳持有的令牌。",
                        "evidence_excerpts": [excerpt],
                        "reason": "具备可追踪归属的物品。",
                    },
                ],
                "ignored": [],
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "knowledge_type": "character",
                "cards": [
                    {
                        "entity_group_id": "entity_group_001",
                        "name": "秦阳",
                        "aliases": [],
                        "summary": "本章走入太初教山门的人物。",
                        "importance": "core",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "evidence_excerpts": [excerpt],
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
                        "entity_group_id": "entity_group_002",
                        "name": "太初教山门",
                        "aliases": ["山门"],
                        "summary": "秦阳入山时出现的太初教入口。",
                        "importance": "normal",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "evidence_excerpts": [excerpt],
                        "controlling_faction_id": None,
                        "first_seen_chapter_id": "chapter_001",
                    }
                ],
                "factions": [
                    {
                        "entity_group_id": "entity_group_003",
                        "name": "太初教",
                        "aliases": [],
                        "summary": "本章出现的修行势力。",
                        "importance": "major",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "evidence_excerpts": [excerpt],
                        "faction_type": "sect",
                        "leader_id": None,
                    }
                ],
                "items": [
                    {
                        "entity_group_id": "entity_group_004",
                        "name": "青铜令牌",
                        "aliases": ["令牌"],
                        "summary": "秦阳入山时持有的令牌。",
                        "importance": "normal",
                        "source_origin": "agent_extract",
                        "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                        "evidence_excerpt": excerpt,
                        "evidence_excerpts": [excerpt],
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


def _generic_mentions_response() -> str:
    return json.dumps(
        {
            "mentions": [
                {
                    "name": "小山羊胡子",
                    "knowledge_type": "character",
                    "description": "只有外貌特征的临时称呼。",
                    "evidence_excerpts": ["小山羊胡子在旁边看了一眼。"],
                    "reason": "临时称呼",
                },
                {
                    "name": "少年们",
                    "knowledge_type": "character",
                    "description": "普通人群泛称。",
                    "evidence_excerpts": ["少年们围在药铺门口。"],
                    "reason": "泛称",
                },
                {
                    "name": "药铺门口",
                    "knowledge_type": "location",
                    "description": "普通功能空间。",
                    "evidence_excerpts": ["少年们围在药铺门口。"],
                    "reason": "普通地点",
                },
            ],
            "ignored": [],
        },
        ensure_ascii=False,
    )
