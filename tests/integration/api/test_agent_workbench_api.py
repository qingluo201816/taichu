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
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
)
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

    async def test_delete_run_removes_run_record(self) -> None:
        await self.app.state.knowledge_run_store.write_run(_manual_review_run())

        delete_response = await self.client.delete(
            "/api/agent-workbench/knowledge-extraction/runs/extract_run_20260704_153022_b1c2d3"
        )
        detail_response = await self.client.get(
            "/api/agent-workbench/knowledge-extraction/runs/extract_run_20260704_153022_b1c2d3"
        )
        list_response = await self.client.get(
            "/api/agent-workbench/knowledge-extraction/runs?page=1&page_size=20&status=all"
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["deleted"])
        self.assertEqual(
            delete_response.json()["run_id"],
            "extract_run_20260704_153022_b1c2d3",
        )
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["total"], 0)

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
        ignore_reject_response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_ignore/reject"
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
        self.assertEqual(ignore_reject_response.status_code, 200)
        self.assertEqual(
            ignore_reject_response.json()["run"]["review_items"][1]["candidate_status"],
            "rejected",
        )

    async def test_direct_confirm_update_card_appends_to_existing_card(self) -> None:
        await self.app.state.knowledge_repository.create_active_card(
            _active_character_card(
                "character-qin-direct",
                summary="秦阳原本是太初教弟子。",
                source_note="第1章旧来源。",
                aliases=["阿阳"],
                identity="太初教弟子",
            )
        )
        await self.app.state.knowledge_run_store.write_run(
            _targeted_update_run("review_item_direct_update", "character-qin-direct")
        )

        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_direct_update/confirm"
        )
        card = await self.app.state.knowledge_repository.get_card(
            "character-qin-direct"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["run"]["review_items"][0]["candidate_status"],
            "confirmed",
        )
        self.assertIsNotNone(card)
        assert card is not None
        self.assertIn("秦阳原本是太初教弟子。", card.summary)
        self.assertIn("新章显示秦阳进入山门。", card.summary)
        self.assertIn("第1章旧来源。", card.source_note)
        self.assertIn("第2章新来源。", card.source_note)
        self.assertEqual(card.aliases, ["阿阳", "小秦"])
        self.assertEqual(card.identity, "太初教弟子")
        self.assertEqual(card.last_seen_chapter_id, "chapter_002")

    async def test_scoped_confirm_uses_run_id_when_candidate_ids_repeat(self) -> None:
        await self.app.state.knowledge_repository.create_active_card(
            _active_character_card(
                "character-qin-scoped",
                summary="秦阳原本是太初教弟子。",
                source_note="第1章旧来源。",
                aliases=["阿阳"],
                identity="太初教弟子",
            )
        )
        older_run_id = "extract_run_20260704_153020_oldone"
        newer_run_id = "extract_run_20260704_153120_newone"
        await self.app.state.knowledge_run_store.write_run(
            _targeted_update_run(
                "review_item_same",
                "character-qin-scoped",
                run_id=older_run_id,
                started_at="2026-07-04T15:30:20Z",
            )
        )
        await self.app.state.knowledge_run_store.write_run(
            _processed_review_run(
                "review_item_same",
                run_id=newer_run_id,
                started_at="2026-07-04T15:31:20Z",
            )
        )

        response = await self.client.post(
            f"/api/agent-workbench/knowledge-extraction/runs/{older_run_id}/candidates/review_item_same/confirm"
        )
        older_response = await self.client.get(
            f"/api/agent-workbench/knowledge-extraction/runs/{older_run_id}"
        )
        newer_response = await self.client.get(
            f"/api/agent-workbench/knowledge-extraction/runs/{newer_run_id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["run_id"], older_run_id)
        self.assertEqual(
            older_response.json()["run"]["review_items"][0]["candidate_status"],
            "confirmed",
        )
        self.assertEqual(
            newer_response.json()["run"]["review_items"][0]["candidate_status"],
            "confirmed",
        )

    async def test_edit_confirm_can_append_to_existing_card(self) -> None:
        await self.app.state.knowledge_repository.create_active_card(
            _active_character_card(
                "character-qin",
                summary="秦阳原本是太初教弟子。",
                source_note="第1章旧来源。",
                aliases=["阿阳"],
                identity="太初教弟子",
            )
        )
        await self.app.state.knowledge_run_store.write_run(
            _targeted_conflict_run("review_item_append", "character-qin")
        )

        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_append/edit-confirm",
            json={
                "target_card_id": "character-qin",
                "merge_mode": "append",
                "card_updates": {
                    "type": "character",
                    "name": "秦阳",
                    "aliases": ["小秦"],
                    "summary": "新章显示秦阳进入山门。",
                    "source_note": "第2章新来源。",
                    "identity": "新身份不应覆盖",
                    "last_seen_chapter_id": "chapter_002",
                },
            },
        )
        card = await self.app.state.knowledge_repository.get_card("character-qin")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["run"]["review_items"][0]["candidate_status"],
            "confirmed",
        )
        self.assertIsNotNone(card)
        assert card is not None
        self.assertIn("秦阳原本是太初教弟子。", card.summary)
        self.assertIn("新章显示秦阳进入山门。", card.summary)
        self.assertIn("第1章旧来源。", card.source_note)
        self.assertIn("第2章新来源。", card.source_note)
        self.assertEqual(card.aliases, ["阿阳", "小秦"])
        self.assertEqual(card.identity, "太初教弟子")
        self.assertEqual(card.last_seen_chapter_id, "chapter_002")

    async def test_edit_confirm_can_overwrite_existing_card(self) -> None:
        await self.app.state.knowledge_repository.create_active_card(
            _active_character_card(
                "character-qin-overwrite",
                summary="旧摘要。",
                source_note="旧来源。",
                aliases=["旧别名"],
                identity="旧身份",
            )
        )
        await self.app.state.knowledge_run_store.write_run(
            _targeted_conflict_run(
                "review_item_overwrite",
                "character-qin-overwrite",
            )
        )

        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/candidates/review_item_overwrite/edit-confirm",
            json={
                "target_card_id": "character-qin-overwrite",
                "merge_mode": "overwrite",
                "card_updates": {
                    "type": "character",
                    "name": "秦阳",
                    "aliases": ["新别名"],
                    "summary": "覆盖后的摘要。",
                    "source_note": "覆盖后的来源。",
                    "identity": "覆盖后的身份",
                },
            },
        )
        card = await self.app.state.knowledge_repository.get_card(
            "character-qin-overwrite"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual(card.summary, "覆盖后的摘要。")
        self.assertEqual(card.source_note, "覆盖后的来源。")
        self.assertEqual(card.aliases, ["新别名"])
        self.assertEqual(card.identity, "覆盖后的身份")


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
                "mentions": [
                    {
                        "name": "秦阳",
                        "knowledge_type": "character",
                        "description": "秦阳走入太初教山门。",
                        "evidence_excerpts": [excerpt],
                        "reason": "稳定专名角色。",
                    }
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


def _targeted_conflict_run(review_item_id: str, target_card_id: str) -> AgentRun:
    now = "2026-07-04T15:30:22Z"
    run_id = (
        "extract_run_20260704_153023_append"
        if "append" in review_item_id
        else "extract_run_20260704_153024_overwr"
    )
    return AgentRun(
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        scope=AgentRunScope(chapter_id="chapter_001", chapter_title="第一章 山门"),
        started_at=now,
        finished_at=now,
        review_items=[
            AgentReviewItem(
                review_item_id=review_item_id,
                run_id=run_id,
                candidate_action=AgentReviewCandidateAction.CONFLICT,
                knowledge_type=StructuredKnowledgeType.CHARACTER,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="秦阳",
                suggested_card={"type": "character", "name": "秦阳"},
                target_card_id=target_card_id,
                matched_card_name="秦阳",
                match_reason="名称相同",
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="存在冲突，建议编辑后确认",
                created_at=now,
                updated_at=now,
            )
        ],
    )


def _targeted_update_run(
    review_item_id: str,
    target_card_id: str,
    *,
    run_id: str = "extract_run_20260704_153025_update",
    started_at: str = "2026-07-04T15:30:22Z",
) -> AgentRun:
    return AgentRun(
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        scope=AgentRunScope(chapter_id="chapter_001", chapter_title="第一章 山门"),
        started_at=started_at,
        finished_at=started_at,
        review_items=[
            AgentReviewItem(
                review_item_id=review_item_id,
                run_id=run_id,
                candidate_action=AgentReviewCandidateAction.UPDATE_CARD,
                knowledge_type=StructuredKnowledgeType.CHARACTER,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="秦阳",
                suggested_card={
                    "type": "character",
                    "name": "秦阳",
                    "aliases": ["小秦"],
                    "summary": "新章显示秦阳进入山门。",
                    "source_note": "第2章新来源。",
                    "identity": "新身份不应覆盖",
                    "last_seen_chapter_id": "chapter_002",
                },
                target_card_id=target_card_id,
                matched_card_name="秦阳",
                match_reason="名称相同",
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="建议补充已有知识卡",
                created_at=started_at,
                updated_at=started_at,
            )
        ],
    )


def _processed_review_run(
    review_item_id: str,
    *,
    run_id: str,
    started_at: str,
) -> AgentRun:
    return AgentRun(
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        scope=AgentRunScope(chapter_id="chapter_002", chapter_title="第二章 重复编号"),
        started_at=started_at,
        finished_at=started_at,
        review_items=[
            AgentReviewItem(
                review_item_id=review_item_id,
                run_id=run_id,
                candidate_action=AgentReviewCandidateAction.CREATE_CARD,
                knowledge_type=StructuredKnowledgeType.CHARACTER,
                candidate_status=AgentReviewCandidateStatus.CONFIRMED,
                display_title="已处理候选",
                suggested_card={"type": "character", "name": "已处理候选"},
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="建议创建新知识卡",
                author_action="confirm",
                created_knowledge_card_id="character-processed",
                created_at=started_at,
                updated_at=started_at,
            )
        ],
    )


def _active_character_card(
    card_id: str,
    *,
    summary: str,
    source_note: str,
    aliases: list[str],
    identity: str,
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=StructuredKnowledgeType.CHARACTER,
        name="秦阳",
        aliases=aliases,
        summary=summary,
        importance="core",
        status=StructuredKnowledgeStatus.ACTIVE,
        source_origin=StructuredKnowledgeSourceOrigin.AGENT_EXTRACT,
        source_note=source_note,
        role_type="protagonist",
        identity=identity,
        first_seen_chapter_id="chapter_001",
        last_seen_chapter_id="chapter_001",
        created_at="2026-07-04T00:00:00Z",
        updated_at="2026-07-04T00:00:00Z",
    )
