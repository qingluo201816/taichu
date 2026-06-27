"""Chapter summary candidates must not enter fact-scope retrieval."""

import json
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage

from taichu.application.contracts.retrieval import RetrievalQuery
from taichu.application.services.import_service import ImportService
from taichu.config import Settings
from taichu.infrastructure.indexing import SqliteProjectionRebuilder
from taichu.infrastructure.retrieval import SqliteFTSRetrievalBackend
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.main import create_app


class ChapterSummaryPollutionTest(unittest.IsolatedAsyncioTestCase):
    """Verify summary-generated PendingFacts stay out of fact_scope."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(storage).import_text(
            "第一章 正文\n秦浩轩沿山路前行。",
            source_name="pollution.txt",
        )
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[AIMessage(content=_summary_json())]
            ),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_converted_candidate_is_not_indexed_by_fact_scope(self) -> None:
        summary_response = await self.client.post("/api/chapters/chapter_001/summary")
        summary = summary_response.json()["summary"]
        candidate_id = summary["new_setting_candidates"][0]["id"]

        convert_response = await self.client.post(
            f"/api/chapter-summaries/{summary['id']}/pending-facts/{candidate_id}"
        )
        await SqliteProjectionRebuilder(self.assets_root).rebuild()
        hits = await SqliteFTSRetrievalBackend(self.assets_root).search(
            RetrievalQuery(text="灵渊晶核")
        )

        self.assertEqual(convert_response.status_code, 200)
        self.assertEqual(hits, [])


def _summary_json() -> str:
    return json.dumps(
        {
            "summary": "秦浩轩沿山路前行。",
            "key_events": ["秦浩轩前行"],
            "character_changes": [],
            "new_setting_candidates": [
                {
                    "fact_type": "item",
                    "title": "灵渊晶核",
                    "content": "灵渊晶核只是未确认候选。",
                }
            ],
            "foreshadow_candidates": [],
            "next_chapter_hooks": [],
        },
        ensure_ascii=False,
    )
