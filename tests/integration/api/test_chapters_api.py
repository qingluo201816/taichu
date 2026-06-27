"""Chapter API integration tests."""

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


class ChapterApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify chapter routes delegate to the active-root service."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(storage).import_text(
            "第一章 开始\n正文",
            source_name="api_fixture.txt",
        )
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[AIMessage(content="unused")]
            ),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_list_chapters_reads_manifest(self) -> None:
        response = await self.client.get("/api/chapters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["chapters"][0]["markdown_path"],
            "manuscripts/chapters/chapter_001.md",
        )

    async def test_read_chapter_returns_markdown(self) -> None:
        response = await self.client.get("/api/chapters/chapter_001")

        self.assertEqual(response.status_code, 200)
        self.assertIn("正文", response.json()["markdown"])

    async def test_save_chapter_updates_markdown_and_manifest(self) -> None:
        markdown = "# 第一章 开始\n\n保存后的中文长段落，带着灵气与山风。\n"

        save_response = await self.client.put(
            "/api/chapters/chapter_001",
            json={"markdown": markdown},
        )
        read_response = await self.client.get("/api/chapters/chapter_001")
        list_response = await self.client.get("/api/chapters")

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(read_response.json()["markdown"], markdown)
        self.assertGreater(
            list_response.json()["chapters"][0]["word_count"],
            0,
        )

    async def test_missing_chapter_returns_404(self) -> None:
        response = await self.client.get("/api/chapters/missing")

        self.assertEqual(response.status_code, 404)

    async def test_save_missing_chapter_returns_404(self) -> None:
        response = await self.client.put(
            "/api/chapters/missing",
            json={"markdown": "# 不存在\n"},
        )

        self.assertEqual(response.status_code, 404)
