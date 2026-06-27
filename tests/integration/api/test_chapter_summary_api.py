"""Chapter summary API integration tests."""

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


class ChapterSummaryApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify chapter summary endpoints stay in workspace scope."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(storage).import_text(
            "第一章 整理\n秦浩轩得到太初古卷。",
            source_name="summary_api.txt",
        )
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[
                    AIMessage(content=_summary_json()),
                    AIMessage(content=_summary_json()),
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

    async def test_summary_endpoint_persists_summary_and_card(self) -> None:
        response = await self.client.post("/api/chapters/chapter_001/summary")
        cards_response = await self.client.get(
            "/api/ai-cards",
            params={"chapter_id": "chapter_001"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["status"], "draft")
        self.assertEqual(payload["card"]["type"], "chapter_summary")
        self.assertEqual(cards_response.json()["cards"][0]["id"], payload["card"]["id"])
        self.assertTrue(
            (
                self.assets_root / "source" / "workspace" / "chapter_summaries.jsonl"
            ).exists()
        )

    async def test_candidate_conversion_writes_pending_fact_not_knowledge(
        self,
    ) -> None:
        summary_response = await self.client.post("/api/chapters/chapter_001/summary")
        payload = summary_response.json()
        summary_id = payload["summary"]["id"]
        pending_fact_id = payload["summary"]["new_setting_candidates"][0]["id"]

        convert_response = await self.client.post(
            f"/api/chapter-summaries/{summary_id}/pending-facts/{pending_fact_id}"
        )

        self.assertEqual(convert_response.status_code, 200)
        self.assertEqual(
            convert_response.json()["pending_fact"]["status"],
            "pending",
        )
        self.assertIn(
            pending_fact_id,
            (
                self.assets_root / "source" / "workspace" / "pending_facts.jsonl"
            ).read_text(encoding="utf-8"),
        )
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )

    async def test_confirm_and_ignore_summary_do_not_write_knowledge(self) -> None:
        first = (await self.client.post("/api/chapters/chapter_001/summary")).json()
        confirm_response = await self.client.post(
            f"/api/chapter-summaries/{first['summary']['id']}/actions",
            json={
                "action": "confirm",
                "edits": {"summary": "作者确认的摘要草稿"},
            },
        )
        second = (await self.client.post("/api/chapters/chapter_001/summary")).json()
        ignore_response = await self.client.post(
            f"/api/chapter-summaries/{second['summary']['id']}/actions",
            json={"action": "ignore"},
        )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_response.json()["summary"]["status"], "confirmed")
        self.assertEqual(ignore_response.status_code, 200)
        self.assertEqual(ignore_response.json()["summary"]["status"], "ignored")
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )


def _summary_json() -> str:
    return json.dumps(
        {
            "summary": "秦浩轩得到太初古卷。",
            "key_events": ["秦浩轩得到太初古卷"],
            "character_changes": [{"character": "秦浩轩", "change": "获得古卷"}],
            "new_setting_candidates": [
                {
                    "fact_type": "item",
                    "title": "太初古卷",
                    "content": "太初古卷仍需作者确认。",
                }
            ],
            "foreshadow_candidates": [],
            "next_chapter_hooks": ["继续探索古卷"],
        },
        ensure_ascii=False,
    )
