"""Creative inbox API integration tests."""

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


class InboxApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 4 inbox routes and non-fact boundaries."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(storage).import_text(
            "第一章 开始\n正文带着灵火向前。",
            source_name="inbox_fixture.txt",
        )
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[
                    AIMessage(content=_suggestion_response()),
                    AIMessage(content=_pending_fact_response()),
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

    async def test_save_suggestion_card_to_idea_and_source_jump(self) -> None:
        card_id = await self._create_selection_card("ask")

        save_response = await self.client.post(
            f"/api/inbox/cards/{card_id}/save-idea"
        )
        inbox_response = await self.client.get("/api/inbox")

        self.assertEqual(save_response.status_code, 200)
        inbox = inbox_response.json()
        self.assertEqual(inbox["ideas"][0]["fact_status"], "non_fact")
        self.assertEqual(inbox["ideas"][0]["scope"], "workspace_scope")
        self.assertEqual(
            inbox["ideas"][0]["source_href"],
            "/editor?chapter_id=chapter_001",
        )
        self.assertEqual(inbox["saved_ai_cards"][0]["id"], card_id)
        self.assertEqual(inbox["chapter_issues"], [])

    async def test_convert_and_ignore_pending_fact_without_knowledge_write(
        self,
    ) -> None:
        await self._create_selection_card("ask")
        card_id = await self._create_selection_card("enrich_setting")

        convert_response = await self.client.post(
            f"/api/inbox/cards/{card_id}/convert-pending-fact"
        )
        inbox_response = await self.client.get("/api/inbox")
        pending_fact_id = convert_response.json()["pending_fact"]["id"]
        ignore_response = await self.client.post(
            f"/api/inbox/pending-facts/{pending_fact_id}/ignore"
        )
        final_inbox_response = await self.client.get("/api/inbox")

        self.assertEqual(convert_response.status_code, 200)
        self.assertEqual(
            inbox_response.json()["pending_facts"][0]["fact_status"],
            "non_fact",
        )
        self.assertEqual(
            inbox_response.json()["pending_facts"][0]["source_href"],
            "/editor?chapter_id=chapter_001",
        )
        self.assertEqual(ignore_response.status_code, 200)
        self.assertEqual(final_inbox_response.json()["pending_facts"], [])
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )

    async def _create_selection_card(self, mode: str) -> str:
        response = await self.client.post(
            "/api/ai-cards/selection",
            json=_selection_payload(mode),
        )
        self.assertEqual(response.status_code, 200)
        card_id = response.json()["card"]["id"]
        assert isinstance(card_id, str)
        return card_id


def _suggestion_response() -> str:
    return json.dumps(
        {
            "card_type": "suggestion",
            "content": {"body": "可以保存成一个后续灵感。"},
        },
        ensure_ascii=False,
    )


def _pending_fact_response() -> str:
    return json.dumps(
        {
            "card_type": "pending_fact",
            "content": {
                "fact_type": "technique",
                "title": "太初剑意",
                "content": {"rule": "以心火照见剑路。"},
            },
        },
        ensure_ascii=False,
    )


def _selection_payload(mode: str) -> dict[str, object]:
    return {
        "mode": mode,
        "selection_context": {
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
        },
        "user_prompt": "收进创作收件箱",
    }
