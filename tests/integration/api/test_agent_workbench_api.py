"""Agent workbench API integration tests."""

from __future__ import annotations

import json
import asyncio
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
from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.application.agents.models.agent_run import (
    AgentBatchChapterProgress,
    AgentReviewCandidateAction,
    AgentReviewCandidateStatus,
    AgentReviewItem,
    AgentRun,
    AgentRunNode,
    AgentRunNodeStatus,
    AgentRunScope,
    AgentRunStatus,
    AgentSchemaValidation,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


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
            llm_model_identity=LLMModelIdentity(
                provider="test",
                model_id="test-model",
                family="test-model",
                endpoint_kind="test",
                known=True,
            ),
            knowledge_repository=InMemoryKnowledgeRepository(),
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
            "/api/knowledge/cards?type=character&lifecycle=confirmed"
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

    async def test_requested_model_mismatch_returns_specific_422_without_run(
        self,
    ) -> None:
        cases = [
            (
                "/api/agent-workbench/knowledge-extraction/runs",
                {"chapter_id": "chapter_001", "model_name": "other-model"},
            ),
            (
                "/api/agent-workbench/knowledge-extraction/runs/stream",
                {"chapter_id": "chapter_001", "model_name": "other-model"},
            ),
            (
                "/api/agent-workbench/knowledge-extraction/runs/start",
                {"chapter_id": "chapter_001", "model_name": "other-model"},
            ),
            (
                "/api/agent-workbench/knowledge-extraction/batch-runs/stream",
                {"chapter_ids": ["chapter_001"], "model_name": "other-model"},
            ),
            (
                "/api/agent-workbench/knowledge-extraction/batch-runs/start",
                {"chapter_ids": ["chapter_001"], "model_name": "other-model"},
            ),
        ]

        for path, payload in cases:
            with self.subTest(path=path):
                response = await self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json(),
                    {
                        "error": {
                            "code": "AGENT_MODEL_SELECTION_UNSUPPORTED",
                            "message": "所选模型不存在，请刷新模型列表后重试。",
                        }
                    },
                )

        runs_response = await self.client.get(
            "/api/agent-workbench/knowledge-extraction/runs"
        )
        self.assertEqual(runs_response.json()["total"], 0)

    async def test_matching_requested_model_records_runtime_identity(self) -> None:
        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/runs",
            json={"chapter_id": "chapter_001", "model_name": " test-model "},
        )
        run_id = response.json()["run"]["run_id"]
        detail_response = await self.client.get(
            f"/api/agent-workbench/knowledge-extraction/runs/{run_id}"
        )
        run = detail_response.json()["run"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run["model_name"], "test-model")
        self.assertEqual(run["requested_model_name"], " test-model ")
        self.assertEqual(run["generation_model_identity"]["provider"], "test")
        self.assertTrue(run["generation_model_identity"]["known"])

    async def test_stream_run_outputs_node_events_and_persists_run(self) -> None:
        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/runs/stream",
            json={"chapter_id": "chapter_001"},
        )
        events = [
            json.loads(line) for line in response.text.splitlines() if line.strip()
        ]
        event_types = [event["type"] for event in events]
        started = next(event for event in events if event["type"] == "run_started")
        completed = next(event for event in events if event["type"] == "run_completed")
        detail_response = await self.client.get(
            "/api/agent-workbench/knowledge-extraction/runs/"
            f"{completed['run']['run_id']}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["content-type"])
        self.assertIn("run_started", event_types)
        self.assertIn("node_started", event_types)
        self.assertIn("node_finished", event_types)
        self.assertIn("llm_call_finished", event_types)
        self.assertIn("run_completed", event_types)
        self.assertEqual(started["run"]["scope"]["chapter_title"], "第一章 山门")
        self.assertEqual(completed["run"]["status"], "completed")
        self.assertGreaterEqual(len(completed["run"]["graph_nodes"]), 1)
        self.assertEqual(detail_response.status_code, 200)

    async def test_start_run_returns_running_task_and_monitor_can_read_it(self) -> None:
        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/runs/start",
            json={"chapter_id": "chapter_001"},
        )
        run_id = response.json()["run"]["run_id"]
        monitor_response = await self.client.get(f"/api/agent-tasks/{run_id}")

        completed_detail = None
        for _ in range(20):
            detail_response = await self.client.get(f"/api/agent-tasks/{run_id}")
            if detail_response.status_code == 200:
                completed_detail = detail_response.json()["run"]
                if completed_detail["status"] == "completed":
                    break
            await asyncio.sleep(0.05)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["status"], "running")
        self.assertEqual(
            response.json()["run"]["chapter_title"],
            "第一章 山门",
        )
        self.assertEqual(monitor_response.status_code, 200)
        self.assertEqual(monitor_response.json()["run"]["run_id"], run_id)
        self.assertEqual(
            monitor_response.json()["run"]["scope"]["chapter_title"],
            "第一章 山门",
        )
        self.assertIsNotNone(completed_detail)
        assert completed_detail is not None
        self.assertEqual(completed_detail["status"], "completed")

    async def test_openapi_exposes_static_stream_routes(self) -> None:
        response = await self.client.get("/openapi.json")
        paths = response.json()["paths"]

        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/agent-workbench/knowledge-extraction/runs/stream", paths)
        self.assertIn(
            "/api/agent-workbench/knowledge-extraction/batch-runs/stream",
            paths,
        )
        self.assertIn("/api/agent-workbench/knowledge-extraction/runs/start", paths)
        self.assertIn(
            "/api/agent-workbench/knowledge-extraction/batch-runs/start",
            paths,
        )
        self.assertIn("/api/agent-tasks/stream/events", paths)
        self.assertIn(
            "post",
            paths["/api/agent-workbench/knowledge-extraction/runs/stream"],
        )

    async def test_batch_stream_run_writes_monitorable_task_and_candidates(
        self,
    ) -> None:
        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/batch-runs/stream",
            json={"chapter_ids": ["chapter_001"]},
        )
        events = [
            json.loads(line) for line in response.text.splitlines() if line.strip()
        ]
        event_types = [event["type"] for event in events]
        completed = next(event for event in events if event["type"] == "task_completed")
        run_id = completed["run"]["run_id"]
        monitor_list_response = await self.client.get(
            "/api/agent-tasks?page=1&page_size=20&status=all"
        )
        monitor_detail_response = await self.client.get(f"/api/agent-tasks/{run_id}")
        candidate_id = completed["run"]["review_items"][0]["review_item_id"]
        confirm_response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/runs/"
            f"{run_id}/candidates/{candidate_id}/confirm"
        )
        knowledge_response = await self.client.get(
            "/api/knowledge/cards?type=character&lifecycle=confirmed"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["content-type"])
        self.assertIn("task_started", event_types)
        self.assertIn("chapter_branch_started", event_types)
        self.assertIn("chapter_branch_node_started", event_types)
        self.assertIn("chapter_branch_node_finished", event_types)
        self.assertIn("chapter_branch_finished", event_types)
        self.assertIn("llm_call_finished", event_types)
        self.assertIn("node_started", event_types)
        self.assertIn("node_finished", event_types)
        self.assertIn("task_completed", event_types)
        first_branch_event = next(
            event for event in events if event["type"] == "chapter_branch_node_started"
        )
        self.assertEqual(
            first_branch_event["chapter_progress"]["nodes"][0]["node_name"],
            "LoadChapterNode",
        )
        self.assertEqual(
            first_branch_event["chapter_progress"]["nodes"][0]["status"],
            "running",
        )
        general_started_index = _branch_node_event_index(
            events,
            "chapter_branch_node_started",
            "GeneralExtractionNode",
        )
        general_llm_index = next(
            index
            for index, event in enumerate(events)
            if event["type"] == "llm_call_finished"
            and event["llm_call"]["node_name"] == "GeneralExtractionNode"
        )
        general_finished_index = _branch_node_event_index(
            events,
            "chapter_branch_node_finished",
            "GeneralExtractionNode",
        )
        self.assertLess(general_started_index, general_llm_index)
        self.assertLess(general_llm_index, general_finished_index)
        self.assertEqual(completed["run"]["scope"]["scope_type"], "chapter_batch")
        self.assertEqual(
            set(completed["run"]["scope"]["chapter_content_hashes"]),
            {"chapter_001"},
        )
        self.assertTrue(
            completed["run"]["scope"]["chapter_content_hashes"]["chapter_001"]
        )
        self.assertEqual(completed["run"]["max_concurrency"], 5)
        self.assertEqual(completed["run"]["current_concurrency"], 0)
        self.assertEqual(completed["run"]["total_chapter_count"], 1)
        self.assertEqual(completed["run"]["completed_chapter_count"], 1)
        self.assertEqual(
            completed["run"]["batch_chapter_progress"][0]["status"],
            "success",
        )
        self.assertTrue(completed["run"]["batch_chapter_progress"][0]["nodes"])
        self.assertEqual(
            completed["run"]["batch_chapter_progress"][0]["nodes"][0]["node_name"],
            "LoadChapterNode",
        )
        self.assertEqual(monitor_list_response.status_code, 200)
        self.assertTrue(
            any(
                task["run_id"] == run_id
                for task in monitor_list_response.json()["runs"]
            )
        )
        self.assertEqual(monitor_detail_response.status_code, 200)
        self.assertEqual(monitor_detail_response.json()["run"]["run_id"], run_id)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(knowledge_response.status_code, 200)
        self.assertEqual(knowledge_response.json()["cards"][0]["name"], "秦阳")

    async def test_start_batch_run_persists_branch_node_replay(self) -> None:
        response = await self.client.post(
            "/api/agent-workbench/knowledge-extraction/batch-runs/start",
            json={"chapter_ids": ["chapter_001"]},
        )
        run_id = response.json()["run"]["run_id"]

        completed_detail = None
        for _ in range(30):
            detail_response = await self.client.get(f"/api/agent-tasks/{run_id}")
            if detail_response.status_code == 200:
                completed_detail = detail_response.json()["run"]
                if completed_detail["status"] == "completed":
                    break
            await asyncio.sleep(0.05)

        persisted_response = await self.client.get(
            f"/api/agent-workbench/knowledge-extraction/runs/{run_id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(completed_detail)
        assert completed_detail is not None
        self.assertEqual(completed_detail["status"], "completed")
        self.assertTrue(completed_detail["batch_chapter_progress"][0]["nodes"])
        self.assertEqual(
            completed_detail["batch_chapter_progress"][0]["nodes"][0]["node_name"],
            "LoadChapterNode",
        )
        self.assertEqual(persisted_response.status_code, 200)
        self.assertTrue(
            persisted_response.json()["run"]["batch_chapter_progress"][0]["nodes"]
        )

    async def test_confirm_extended_types_create_confirmed_cards(self) -> None:
        run = _extended_type_review_run()
        await self.app.state.knowledge_run_store.write_run(run)

        for review_item in run.review_items:
            response = await self.client.post(
                "/api/agent-workbench/knowledge-extraction/runs/"
                f"{run.run_id}/candidates/{review_item.review_item_id}/confirm"
            )
            self.assertEqual(response.status_code, 200)

        expected_names = {
            "realm": "炼气一层",
            "technique": "太初引气诀",
            "event": "秦阳入山门",
            "rule": "持令牌方可入山",
        }
        for knowledge_type, expected_name in expected_names.items():
            cards_response = await self.client.get(
                f"/api/knowledge/cards?type={knowledge_type}&lifecycle=confirmed"
            )
            self.assertEqual(cards_response.status_code, 200)
            self.assertTrue(
                any(
                    card["name"] == expected_name
                    for card in cards_response.json()["cards"]
                )
            )

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

    async def test_agent_task_delete_removes_persisted_and_active_task(self) -> None:
        run = _manual_review_run()
        await self.app.state.knowledge_run_store.write_run(run)

        persisted_delete_response = await self.client.delete(
            f"/api/agent-tasks/{run.run_id}"
        )
        persisted_detail_response = await self.client.get(
            f"/api/agent-tasks/{run.run_id}"
        )
        await self.app.state.agent_task_events.publish(
            {
                "type": "run_started",
                "event_type": "run_started",
                "run_id": run.run_id,
                "message": "测试临时任务。",
                "run": run.model_copy(
                    update={"run_id": "extract_run_active_only"}
                ).model_dump(mode="json"),
            }
        )
        active_delete_response = await self.client.delete(
            "/api/agent-tasks/extract_run_active_only"
        )
        active_detail_response = await self.client.get(
            "/api/agent-tasks/extract_run_active_only"
        )

        self.assertEqual(persisted_delete_response.status_code, 200)
        self.assertEqual(persisted_detail_response.status_code, 404)
        self.assertEqual(active_delete_response.status_code, 200)
        self.assertEqual(active_detail_response.status_code, 404)

    async def test_agent_task_event_merges_chapter_progress_with_run_snapshot(
        self,
    ) -> None:
        run = AgentRun(
            run_id="extract_run_event_merge",
            status=AgentRunStatus.RUNNING,
            scope=AgentRunScope(
                scope_type="chapter_batch",
                chapter_id="chapter_001",
                chapter_title="第一章 山门",
                chapter_ids=["chapter_001"],
                chapter_titles=["第一章 山门"],
            ),
            started_at="2026-07-04T15:30:22Z",
            batch_chapter_progress=[
                AgentBatchChapterProgress(
                    chapter_id="chapter_001",
                    chapter_title="第一章 山门",
                    status=AgentRunNodeStatus.RUNNING,
                    started_at="2026-07-04T15:30:22Z",
                )
            ],
            total_chapter_count=1,
            current_concurrency=1,
            max_concurrency=5,
        )
        progress = AgentBatchChapterProgress(
            chapter_id="chapter_001",
            chapter_title="第一章 山门",
            status=AgentRunNodeStatus.RUNNING,
            started_at="2026-07-04T15:30:22Z",
            nodes=[
                AgentRunNode(
                    node_name="GeneralExtractionNode",
                    status=AgentRunNodeStatus.RUNNING,
                    started_at="2026-07-04T15:30:25Z",
                )
            ],
        )

        await self.app.state.agent_task_events.publish(
            {
                "type": "chapter_branch_node_started",
                "event_type": "chapter_branch_node_started",
                "run_id": run.run_id,
                "message": "章节节点开始。",
                "run": run.model_dump(mode="json"),
                "chapter_progress": progress.model_dump(mode="json"),
            }
        )
        detail_response = await self.client.get(f"/api/agent-tasks/{run.run_id}")

        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()["run"]
        self.assertEqual(
            detail["batch_chapter_progress"][0]["nodes"][0]["node_name"],
            "GeneralExtractionNode",
        )
        self.assertEqual(
            detail["batch_chapter_progress"][0]["nodes"][0]["status"],
            "running",
        )

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
        await self.app.state.knowledge_service.create_confirmed_card(
            _confirmed_character_card(
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
        self.assertEqual(card.appearance_chapter_count, 1)

    async def test_scoped_confirm_uses_run_id_when_candidate_ids_repeat(self) -> None:
        await self.app.state.knowledge_service.create_confirmed_card(
            _confirmed_character_card(
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
        await self.app.state.knowledge_service.create_confirmed_card(
            _confirmed_character_card(
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
        await self.app.state.knowledge_service.create_confirmed_card(
            _confirmed_character_card(
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


def _branch_node_event_index(
    events: list[dict[str, Any]],
    event_type: str,
    node_name: str,
) -> int:
    for index, event in enumerate(events):
        if event["type"] != event_type:
            continue
        nodes = event["chapter_progress"]["nodes"]
        if nodes and nodes[-1]["node_name"] == node_name:
            return index
    raise AssertionError(f"未找到分支节点事件：{event_type} {node_name}")


def _extended_type_review_run() -> AgentRun:
    now = "2026-07-04T15:30:26Z"
    run_id = "extract_run_20260704_153026_extend"
    base_fields = {
        "aliases": [],
        "source_note": "来自正文知识沉淀测试。",
    }
    return AgentRun(
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        scope=AgentRunScope(chapter_id="chapter_001", chapter_title="第一章 山门"),
        started_at=now,
        finished_at=now,
        review_items=[
            AgentReviewItem(
                review_item_id="review_item_realm",
                run_id=run_id,
                candidate_action=AgentReviewCandidateAction.CREATE_CARD,
                knowledge_type=StructuredKnowledgeType.REALM,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="炼气一层",
                suggested_card={
                    **base_fields,
                    "type": "realm",
                    "name": "炼气一层",
                    "summary": "太初修炼体系的早期境界。",
                    "system": "太初修炼体系",
                    "level_order": 1,
                },
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="建议创建新知识卡",
                created_at=now,
                updated_at=now,
            ),
            AgentReviewItem(
                review_item_id="review_item_technique",
                run_id=run_id,
                candidate_action=AgentReviewCandidateAction.CREATE_CARD,
                knowledge_type=StructuredKnowledgeType.TECHNIQUE,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="太初引气诀",
                suggested_card={
                    **base_fields,
                    "type": "technique",
                    "name": "太初引气诀",
                    "summary": "太初教入门功法。",
                    "technique_type": "cultivation_method",
                    "practice_condition": "持入门令牌后可修。",
                },
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="建议创建新知识卡",
                created_at=now,
                updated_at=now,
            ),
            AgentReviewItem(
                review_item_id="review_item_event",
                run_id=run_id,
                candidate_action=AgentReviewCandidateAction.CREATE_CARD,
                knowledge_type=StructuredKnowledgeType.EVENT,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="秦阳入山门",
                suggested_card={
                    **base_fields,
                    "type": "event",
                    "name": "秦阳入山门",
                    "summary": "秦阳进入太初教山门。",
                    "chapter_id": "chapter_001",
                    "description": "秦阳持青铜令牌进入太初教山门。",
                },
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="建议创建新知识卡",
                created_at=now,
                updated_at=now,
            ),
            AgentReviewItem(
                review_item_id="review_item_rule",
                run_id=run_id,
                candidate_action=AgentReviewCandidateAction.CREATE_CARD,
                knowledge_type=StructuredKnowledgeType.RULE,
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title="持令牌方可入山",
                suggested_card={
                    **base_fields,
                    "type": "rule",
                    "name": "持令牌方可入山",
                    "summary": "太初教山门通行需要青铜令牌。",
                    "exceptions": "未见例外。",
                },
                schema_validation=AgentSchemaValidation(passed=True),
                suggested_action_label="建议创建新知识卡",
                created_at=now,
                updated_at=now,
            ),
        ],
    )


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
                appearance_chapter_ids=["chapter_002"],
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


def _confirmed_character_card(
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
        lifecycle=StructuredKnowledgeLifecycle.CONFIRMED,
        source_origin=StructuredKnowledgeSourceOrigin.AGENT_EXTRACT,
        source_note=source_note,
        role_type="protagonist",
        identity=identity,
        first_seen_chapter_id="chapter_001",
        last_seen_chapter_id="chapter_001",
        created_at="2026-07-04T00:00:00Z",
        updated_at="2026-07-04T00:00:00Z",
    )
