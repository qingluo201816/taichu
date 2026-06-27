"""AI card API integration tests."""

import json
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage

from taichu.application.services.import_service import ImportService
from taichu.config import Settings
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.main import create_app


class AICardsApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify Selection AI and AIResultCard endpoints."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(storage).import_text(
            "第一章 开始\n正文带着灵火向前。",
            source_name="api_fixture.txt",
        )
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[
                    AIMessage(
                        content=json.dumps(
                            {
                                "card_type": "suggestion",
                                "content": {
                                    "body": "可以加强灵火与人物选择的关系。"
                                },
                            },
                            ensure_ascii=False,
                        )
                    )
                ]
            ),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_selection_endpoint_persists_ai_result_card(self) -> None:
        response = await self.client.post(
            "/api/ai-cards/selection",
            json=_selection_payload(),
        )
        list_response = await self.client.get(
            "/api/ai-cards",
            params={"chapter_id": "chapter_001"},
        )

        self.assertEqual(response.status_code, 200)
        card = response.json()["card"]
        self.assertEqual(card["type"], "suggestion")
        self.assertEqual(card["status"], "generated")
        self.assertEqual(list_response.json()["cards"][0]["id"], card["id"])

    async def test_save_suggestion_action_generates_idea_card(self) -> None:
        create_response = await self.client.post(
            "/api/ai-cards/selection",
            json=_selection_payload(),
        )
        card_id = create_response.json()["card"]["id"]

        action_response = await self.client.post(
            f"/api/ai-cards/{card_id}/actions",
            json={"action": "save_to_idea"},
        )
        ideas_path = (
            self.assets_root
            / "source"
            / "workspace"
            / "ideas.jsonl"
        )

        self.assertEqual(action_response.status_code, 200)
        self.assertEqual(action_response.json()["card"]["status"], "saved_to_inbox")
        self.assertIn(card_id, ideas_path.read_text(encoding="utf-8"))


def _selection_payload() -> dict[str, object]:
    return {
        "mode": "ask",
        "chapter_id": "chapter_001",
        "selected_text": "正文",
        "surrounding_text": "正文带着灵火向前。",
        "selection_range": {"from": 1, "to": 3},
        "source_ref": {
            "source_type": "chapter",
            "source_id": "chapter_001",
            "path": "manuscripts/chapters/chapter_001.md",
            "chapter_id": "chapter_001",
            "anchor_type": "paragraph",
            "paragraph_start": 0,
            "char_start": 0,
            "char_end": 2,
            "excerpt": "正文",
            "excerpt_hash": "hash_excerpt",
            "source_hash": "hash_source",
            "created_at": "2026-06-27T00:00:00Z",
        },
        "user_prompt": "哪里可以更好？",
    }
