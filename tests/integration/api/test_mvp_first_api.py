"""MVP first-version API integration tests."""

import json
import tempfile
import unittest
from pathlib import Path
from pydantic import SecretStr
from typing import Any

from httpx import ASGITransport, AsyncClient
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from taichu.application.services.import_service import ImportService
from taichu.config import Settings
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class MVPFirstApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify the first MVP API surface without real LLM or RAG calls."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(storage).import_text(
            "第一章 开始\n正文带着灵火向前。",
            source_name="mvp_api_fixture.txt",
        )
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=_WritingAIChatModel(responses=[_writing_ai_continue_response()]),
            knowledge_repository=InMemoryKnowledgeRepository(),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_outline_created_chapter_uses_existing_chapter_api(self) -> None:
        outline_response = await self.client.get("/api/outline")
        volume_id = outline_response.json()["outline"]["volumes"][0]["volume_id"]

        create_response = await self.client.post(
            "/api/outline/chapters",
            json={
                "volume_id": volume_id,
                "display_title": "第2章 山门回声",
            },
        )
        created_chapter = create_response.json()["outline"]["volumes"][0]["chapters"][-1]
        chapter_id = created_chapter["chapter_id"]
        markdown = "# 第2章 山门回声\n\n第一行\n\n\n    缩进保留\n"

        save_response = await self.client.put(
            f"/api/chapters/{chapter_id}",
            json={"markdown": markdown},
        )
        read_response = await self.client.get(f"/api/chapters/{chapter_id}")

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(created_chapter["display_title"], "第2章 山门回声")
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(read_response.json()["markdown"], markdown)

    async def test_structured_knowledge_lifecycle(self) -> None:
        types_response = await self.client.get("/api/knowledge/types")
        create_response = await self.client.post(
            "/api/knowledge/cards",
            json={
                "type": "character",
                "data": {},
            },
        )
        card_id = create_response.json()["card"]["id"]
        schema_response = await self.client.get("/api/knowledge/schemas/character")
        patch_response = await self.client.patch(
            f"/api/knowledge/cards/{card_id}",
            json={
                "updates": {
                    "name": "秦阳",
                    "summary": "初入山门的少年。",
                    "source_origin": "manual",
                    "source_note": "作者手动确认。",
                    "role_type": "protagonist",
                }
            },
        )
        confirmed_response = await self.client.post(
            f"/api/knowledge/cards/{card_id}/confirm"
        )
        rejected_response = await self.client.post(
            f"/api/knowledge/cards/{card_id}/reject"
        )
        all_response = await self.client.get(
            "/api/knowledge/cards?type=character&lifecycle=all"
        )
        rejected_list_response = await self.client.get(
            "/api/knowledge/cards?type=character&lifecycle=rejected"
        )
        foreshadow_response = await self.client.post(
            "/api/knowledge/cards",
            json={"type": "foreshadow", "data": {"name": "不应创建"}},
        )
        forbidden_response = await self.client.post(
            "/api/knowledge/cards",
            json={"type": "character", "data": {"fields": {"note": "旧字段"}}},
        )

        self.assertEqual(types_response.status_code, 200)
        self.assertIn(
            {"value": "character", "label": "角色"},
            types_response.json()["types"],
        )
        self.assertNotIn(
            {"value": "foreshadow", "label": "伏笔"},
            types_response.json()["types"],
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(schema_response.status_code, 200)
        schema_field_keys = {
            field["field_key"]
            for field in schema_response.json()["schema"]["fields"]
        }
        self.assertIn("role_type", schema_field_keys)
        self.assertIn("lifecycle", schema_field_keys)
        self.assertNotIn("status", schema_field_keys)
        self.assertNotIn("fields", schema_field_keys)
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(
            confirmed_response.json()["card"]["lifecycle"],
            "confirmed",
        )
        self.assertEqual(
            rejected_response.json()["card"]["lifecycle"],
            "rejected",
        )
        self.assertEqual(all_response.json()["cards"], [])
        self.assertEqual(len(rejected_list_response.json()["cards"]), 1)
        self.assertEqual(foreshadow_response.status_code, 422)
        self.assertEqual(forbidden_response.status_code, 422)

    async def test_structured_knowledge_creates_all_v1_types(self) -> None:
        expected_types = {
            "character",
            "realm",
            "technique",
            "location",
            "faction",
            "item",
            "rule",
            "event",
        }
        forbidden_fields = {
            "body",
            "tags",
            "fields",
            "confidence",
            "source_refs",
            "relations",
            "foreshadow",
            "personality",
            "motivation",
            "appearance",
        }
        type_payloads: dict[str, dict[str, object]] = {
            "character": {"role_type": "protagonist", "identity": "outer disciple"},
            "realm": {"system": "qi refining", "level_order": 1},
            "technique": {
                "technique_type": "cultivation_method",
                "grade": "yellow",
                "practice_condition": "quiet room",
            },
            "location": {
                "controlling_faction_id": "faction-sect",
                "first_seen_chapter_id": "chapter_001",
            },
            "faction": {"faction_type": "sect", "leader_id": "character-master"},
            "item": {
                "item_type": "magic_treasure",
                "grade": "low",
                "current_holder_id": "character-qin-yang",
            },
            "rule": {"exceptions": "none"},
            "event": {"chapter_id": "chapter_001", "description": "first arrival"},
        }

        schemas_response = await self.client.get("/api/knowledge/schemas")
        self.assertEqual(schemas_response.status_code, 200)
        schemas = schemas_response.json()["schemas"]
        self.assertEqual({schema["type"] for schema in schemas}, expected_types)
        for schema in schemas:
            schema_field_keys = {field["field_key"] for field in schema["fields"]}
            self.assertTrue(schema_field_keys.isdisjoint(forbidden_fields))

        for knowledge_type, type_payload in type_payloads.items():
            response = await self.client.post(
                "/api/knowledge/cards",
                json={
                    "type": knowledge_type,
                    "data": {
                        "name": f"{knowledge_type} card",
                        "summary": f"{knowledge_type} summary",
                        "source_origin": "manual",
                        "source_note": "acceptance test",
                        **type_payload,
                    },
                },
            )

            self.assertEqual(response.status_code, 200)
            card = response.json()["card"]
            self.assertEqual(card["type"], knowledge_type)
            self.assertEqual(card["lifecycle"], "draft")
            self.assertNotIn("status", card)
            self.assertTrue(forbidden_fields.isdisjoint(card))
            for field_key, expected_value in type_payload.items():
                self.assertEqual(card[field_key], expected_value)

    async def test_mvp_inbox_tabs_and_manual_pending_fact_confirmation(self) -> None:
        idea_response = await self.client.post(
            "/api/inbox/ideas",
            json={"data": {"content": "这里可以埋一个山门伏笔。"}},
        )
        ideas_response = await self.client.get("/api/inbox?tab=ideas")
        pending_response = await self.client.post(
            "/api/inbox/pending-facts",
            json={
                "data": {
                    "title": "金鳞异象",
                    "content": "秦阳掌心出现金鳞异象。",
                    "origin": "作者手动记录",
                    "priority": "high",
                }
            },
        )
        pending_id = pending_response.json()["item"]["id"]
        issue_response = await self.client.post(
            "/api/inbox/issues",
            json={
                "data": {
                    "title": "抽取输出截断",
                    "content": "通用抽取输出达到上限后未覆盖全部类型。",
                }
            },
        )
        all_response = await self.client.get("/api/inbox?tab=all")
        confirm_response = await self.client.post(
            f"/api/inbox/pending-facts/{pending_id}/confirm",
            json={
                "knowledge_type": "rule",
                "card_preview": {
                    "name": "金鳞异象",
                    "summary": "元神外显的早期征兆。",
                },
            },
        )
        pending_list_response = await self.client.get("/api/inbox/pending-facts")

        self.assertEqual(idea_response.status_code, 200)
        self.assertEqual(ideas_response.json()["items"][0]["content"], "这里可以埋一个山门伏笔。")
        self.assertEqual(pending_response.status_code, 200)
        self.assertEqual(issue_response.status_code, 200)
        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(all_response.json()["total"], 3)
        self.assertCountEqual(
            [item["id"] for item in all_response.json()["items"]],
            [
                idea_response.json()["item"]["id"],
                pending_id,
                issue_response.json()["item"]["id"],
            ],
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_response.json()["pending_fact"]["status"], "processed")
        self.assertEqual(
            confirm_response.json()["knowledge_card"]["lifecycle"],
            "confirmed",
        )
        self.assertEqual(
            confirm_response.json()["knowledge_card"]["source_origin"],
            "inbox_fact",
        )
        self.assertNotIn("source_refs", confirm_response.json()["knowledge_card"])
        self.assertEqual(pending_list_response.json()["items"], [])

    async def test_writing_ai_run_history_and_replay(self) -> None:
        create_card_response = await self.client.post(
            "/api/knowledge/cards",
            json={
                "type": "character",
                "data": {
                    "name": "秦阳",
                    "summary": "主角，掌心出现过金鳞异象。",
                    "source_origin": "manual",
                    "source_note": "作者手动确认。",
                    "role_type": "protagonist",
                },
            },
        )
        card_id = create_card_response.json()["card"]["id"]
        confirmed_response = await self.client.post(
            f"/api/knowledge/cards/{card_id}/confirm"
        )
        run_response = await self.client.post(
            "/api/writing-ai/runs",
            json={
                "button_type": "continue",
                "chapter_id": "chapter_001",
                "reference_scope": "chapter",
                "user_input": "续写 200 字，压迫感更强。",
                "draft_chapter_text": "秦阳掌心的金鳞异象在山门前亮起。",
            },
        )
        run = run_response.json()
        run_id = run["run_id"]
        list_response = await self.client.get(
            "/api/writing-ai/runs?chapter_id=chapter_001&button_type=continue"
        )
        read_response = await self.client.get(f"/api/writing-ai/runs/{run_id}")
        replay_response = await self.client.post(
            f"/api/writing-ai/runs/{run_id}/replay"
        )

        self.assertEqual(create_card_response.status_code, 200)
        self.assertEqual(
            confirmed_response.json()["card"]["lifecycle"],
            "confirmed",
        )
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["button_type"], "continue")
        self.assertEqual(run["prompt_snapshot"]["prompt_id"], "continue_prompt_v1")
        self.assertEqual(run["structured_output"]["output_type"], "text_candidate")
        self.assertEqual(run["structured_output"]["content"]["text"], "真实续写正文。")
        source_types = {
            item["source_type"] for item in run["retrieval_context"]["items"]
        }
        self.assertIn("chapter", source_types)
        self.assertIn("knowledge", source_types)
        self.assertTrue(run["retrieval_context"]["retrieval_id"].startswith("retrieval_"))
        self.assertEqual(run["retrieval_context"]["strategy"], "mongo_lexical")
        self.assertGreaterEqual(run["retrieval_context"]["candidate_count"], 1)
        self.assertIn("真实续写正文", run["raw_llm_output"])
        self.assertEqual(list_response.json()["runs"][0]["run_id"], run_id)
        self.assertEqual(read_response.json()["run_id"], run_id)
        self.assertEqual(replay_response.json()["run_id"], run_id)
        self.assertEqual(replay_response.json()["raw_llm_output"], run["raw_llm_output"])

    async def test_writing_ai_missing_llm_config_saves_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            assets_root = Path(temporary_directory)
            storage = ProjectAssetStorageBackend(assets_root)
            await ImportService(storage).import_text(
                "第一章 开始\n正文带着灵火向前。",
                source_name="mvp_api_fixture.txt",
            )
            app = create_app(
                app_settings=Settings(
                    project_assets_dir=assets_root,
                    rightcode_api_key=SecretStr(""),
                ),
                knowledge_repository=InMemoryKnowledgeRepository(),
            )
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                run_response = await client.post(
                    "/api/writing-ai/runs",
                    json={
                        "button_type": "continue",
                        "chapter_id": "chapter_001",
                        "reference_scope": "chapter",
                        "user_input": "续写 200 字。",
                    },
                )
                list_response = await client.get("/api/writing-ai/runs")

        run = run_response.json()
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "当前未配置可用模型，无法调用真实 LLM。")
        self.assertEqual(run["raw_llm_output"], "")
        self.assertEqual(list_response.json()["runs"][0]["run_id"], run["run_id"])

    async def test_settings_preferences_do_not_expose_model_configuration(self) -> None:
        patch_response = await self.client.patch(
            "/api/settings/preferences",
            json={
                "updates": {
                    "font_size": 20,
                    "font_style": "sans",
                    "editor_background": "soft",
                }
            },
        )
        get_response = await self.client.get("/api/settings/preferences")

        preferences = get_response.json()["preferences"]
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(preferences["font_size"], 20)
        self.assertNotIn("api_key", preferences)
        self.assertNotIn("model", preferences)


class _WritingAIChatModel(BaseChatModel):
    responses: list[str]

    @property
    def _llm_type(self) -> str:
        return "taichu-writing-ai-test"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if not self.responses:
            raise RuntimeError("没有可用的写作 AI 测试响应。")
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=self.responses.pop(0)))
            ]
        )


def _writing_ai_continue_response() -> str:
    return json.dumps(
        {
            "output_type": "text_candidate",
            "text": "真实续写正文。",
            "risk_notes": [],
            "used_evidence": ["chapter:chapter_001", "knowledge:character-qin-yang"],
        },
        ensure_ascii=False,
    )
