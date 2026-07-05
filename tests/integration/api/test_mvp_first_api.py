"""MVP first-version API integration tests."""

import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from taichu.application.services.import_service import ImportService
from taichu.config import Settings
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel
from taichu.main import create_app


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
            llm=MVPNoRealLLMChatModel(),
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
                "data": {"id": "character-qin-yang"},
            },
        )
        schema_response = await self.client.get("/api/knowledge/schemas/character")
        patch_response = await self.client.patch(
            "/api/knowledge/cards/character-qin-yang",
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
        active_response = await self.client.post(
            "/api/knowledge/cards/character-qin-yang/mark-active"
        )
        deprecated_response = await self.client.post(
            "/api/knowledge/cards/character-qin-yang/mark-deprecated"
        )
        all_response = await self.client.get(
            "/api/knowledge/cards?type=character&status=all"
        )
        deprecated_list_response = await self.client.get(
            "/api/knowledge/cards?type=character&status=deprecated"
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
        self.assertNotIn("fields", schema_field_keys)
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(active_response.json()["card"]["status"], "active")
        self.assertEqual(deprecated_response.json()["card"]["status"], "deprecated")
        self.assertEqual(all_response.json()["cards"], [])
        self.assertEqual(len(deprecated_list_response.json()["cards"]), 1)
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
                        "id": f"{knowledge_type}-acceptance",
                        "name": f"{knowledge_type} card",
                        "summary": f"{knowledge_type} summary",
                        "status": "active",
                        "source_origin": "manual",
                        "source_note": "acceptance test",
                        **type_payload,
                    },
                },
            )

            self.assertEqual(response.status_code, 200)
            card = response.json()["card"]
            self.assertEqual(card["type"], knowledge_type)
            self.assertEqual(card["status"], "active")
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
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_response.json()["pending_fact"]["status"], "processed")
        self.assertEqual(
            confirm_response.json()["knowledge_card"]["status"],
            "draft",
        )
        self.assertEqual(
            confirm_response.json()["knowledge_card"]["source_origin"],
            "inbox_fact",
        )
        self.assertNotIn("source_refs", confirm_response.json()["knowledge_card"])
        self.assertEqual(pending_list_response.json()["items"], [])

    async def test_mock_ai_conversation_and_history(self) -> None:
        chat_response = await self.client.post(
            "/api/ai-workspace-conversations",
            json={
                "chapter_id": "chapter_001",
                "task_type": "chat",
                "reference_scope": "none",
            },
        )
        create_response = await self.client.post(
            "/api/ai-workspace-conversations",
            json={
                "chapter_id": "chapter_001",
                "task_type": "continue",
                "reference_scope": "chapter",
            },
        )
        conversation_id = create_response.json()["conversation"]["id"]
        send_response = await self.client.post(
            f"/api/ai-workspace-conversations/{conversation_id}/messages",
            json={
                "user_input": "续写 200 字，压迫感更强",
                "reference": {"chapter_id": "chapter_001", "chapter_text": "正文"},
            },
        )
        history_response = await self.client.get(
            "/api/ai-history?chapter_id=chapter_001&task_type=continue&has_source=false"
        )
        regenerate_response = await self.client.post(
            f"/api/ai-workspace-conversations/{conversation_id}/regenerate"
        )
        delete_response = await self.client.delete(
            f"/api/ai-workspace-conversations/{conversation_id}"
        )
        deleted_history_response = await self.client.get(
            "/api/ai-history?chapter_id=chapter_001&task_type=continue"
        )

        self.assertEqual(chat_response.status_code, 422)
        self.assertIn("纯对话", chat_response.json()["error"]["message"])
        self.assertEqual(create_response.status_code, 200)
        conversation = send_response.json()["conversation"]
        self.assertTrue(conversation["is_mock"])
        self.assertEqual(len(conversation["messages"]), 2)
        self.assertIn(
            "模拟提示词",
            conversation["messages"][0]["prompt_snapshot"]["final_prompt"],
        )
        self.assertEqual(history_response.json()["conversations"][0]["id"], conversation_id)
        regenerated = regenerate_response.json()["conversation"]
        self.assertEqual(regenerate_response.status_code, 200)
        self.assertEqual(len(regenerated["messages"]), 2)
        self.assertNotEqual(
            regenerated["messages"][1]["message_id"],
            conversation["messages"][1]["message_id"],
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json(), {"deleted": True})
        self.assertEqual(deleted_history_response.json()["conversations"], [])

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
