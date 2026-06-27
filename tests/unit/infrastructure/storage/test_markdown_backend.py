"""Project asset Markdown storage tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.contracts import ProjectAssetStorageContract
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class ProjectAssetStorageBackendTest(unittest.IsolatedAsyncioTestCase):
    """Verify source/generated storage boundaries."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_ensure_skeleton_creates_source_and_generated(self) -> None:
        self.assertIsInstance(self.storage, ProjectAssetStorageContract)

        await self.storage.ensure_skeleton()

        self.assertTrue(
            (self.assets_root / "source" / "metadata.yaml").exists()
        )
        self.assertTrue(
            (
                self.assets_root
                / "source"
                / "manuscripts"
                / "manifest.json"
            ).exists()
        )
        self.assertTrue(
            (
                self.assets_root
                / "source"
                / "workspace"
                / "ai_cards.jsonl"
            ).exists()
        )
        self.assertTrue((self.assets_root / "generated" / "sqlite").exists())

    async def test_ensure_skeleton_does_not_overwrite_source_assets(
        self,
    ) -> None:
        source_root = self.assets_root / "source"
        metadata_path = source_root / "metadata.yaml"
        manifest_path = source_root / "manuscripts" / "manifest.json"
        chapter_path = (
            source_root / "manuscripts" / "chapters" / "chapter_999.md"
        )
        knowledge_path = (
            source_root / "knowledge" / "characters" / "character_001.json"
        )
        ideas_path = source_root / "workspace" / "ideas.jsonl"
        editor_state_path = source_root / "workspace" / "editor_state.json"

        for path in [
            metadata_path,
            manifest_path,
            chapter_path,
            knowledge_path,
            ideas_path,
            editor_state_path,
        ]:
            path.parent.mkdir(parents=True, exist_ok=True)

        original_files = {
            metadata_path: "schema_version: 9\ntitle: 用户小说\n",
            manifest_path: '{"schema_version": "9", "chapters": ["keep"]}\n',
            chapter_path: "# 用户章节\n\n正文不能被覆盖\n",
            knowledge_path: '{"id": "character_001"}\n',
            ideas_path: '{"content": "保留灵感"}\n',
            editor_state_path: '{"active": "chapter_999"}\n',
        }
        for path, content in original_files.items():
            path.write_text(content, encoding="utf-8")

        await self.storage.ensure_skeleton()

        for path, content in original_files.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    async def test_rejects_unsafe_chapter_paths(self) -> None:
        await self.storage.ensure_skeleton()

        unsafe_paths = [
            "../escape.md",
            "manuscripts/chapters/../escape.md",
            "manuscripts\\chapters\\chapter_001.md",
            "manuscripts/chapters/第1章.md",
            "workspace/chapter_001.md",
            "manuscripts/chapters/chapter_001.txt",
        ]
        for path in unsafe_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    await self.storage.write_chapter_markdown(path, "text")

    async def test_clear_generated_does_not_delete_source(self) -> None:
        await self.storage.ensure_skeleton()
        await self.storage.write_chapter_markdown(
            "manuscripts/chapters/chapter_001.md",
            "# 第一章\n\n正文\n",
        )
        generated_file = self.assets_root / "generated" / "temp" / "cache.tmp"
        generated_file.write_text("cache", encoding="utf-8")

        await self.storage.clear_generated()

        self.assertFalse(generated_file.exists())
        self.assertEqual(
            await self.storage.read_chapter_markdown(
                "manuscripts/chapters/chapter_001.md"
            ),
            "# 第一章\n\n正文\n",
        )
        self.assertTrue((self.assets_root / "generated" / "temp").exists())
