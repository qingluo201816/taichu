"""Corpus importer service tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.import_service import (
    ImportLimitExceededError,
    ImportService,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class ImportServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify bounded corpus imports into isolated active roots."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.importer = ImportService(self.storage)
        self.chapters = ChapterService(self.storage)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_imports_three_chapters_to_markdown_and_manifest(
        self,
    ) -> None:
        batch = await self.importer.import_text(
            "\n".join(
                [
                    "第一章 初临",
                    "第一章正文",
                    "第二章 入山",
                    "第二章正文",
                    "第三章 问道",
                    "第三章正文",
                ]
            ),
            source_name="fixture.txt",
        )

        manifest = await self.chapters.get_manifest()
        first = await self.chapters.read_chapter("chapter_001")

        self.assertEqual(batch.chapter_count, 3)
        self.assertEqual(
            batch.chapter_ids,
            ["chapter_001", "chapter_002", "chapter_003"],
        )
        self.assertEqual(manifest.current_chapter_id, "chapter_001")
        self.assertEqual(
            [chapter.title for chapter in manifest.chapters],
            [
                "第一章 初临",
                "第二章 入山",
                "第三章 问道",
            ],
        )
        self.assertEqual(
            manifest.chapters[0].markdown_path,
            "manuscripts/chapters/chapter_001.md",
        )
        self.assertIn("# 第一章 初临", first.markdown)

    async def test_duplicate_titles_get_distinct_chapter_ids(self) -> None:
        batch = await self.importer.import_text(
            "\n".join(
                [
                    "第一章 重名",
                    "正文一",
                    "第一章 重名",
                    "正文二",
                ]
            ),
            source_name="duplicates.md",
        )

        self.assertEqual(batch.chapter_ids, ["chapter_001", "chapter_002"])
        manifest = await self.chapters.get_manifest()
        self.assertEqual(
            [chapter.markdown_path for chapter in manifest.chapters],
            [
                "manuscripts/chapters/chapter_001.md",
                "manuscripts/chapters/chapter_002.md",
            ],
        )

    async def test_import_over_five_chapters_fails_without_writes(
        self,
    ) -> None:
        await self.storage.ensure_skeleton()
        text = "\n".join(
            [
                f"第{number}章 标题\n正文"
                for number in ["一", "二", "三", "四", "五", "六"]
            ]
        )

        with self.assertRaisesRegex(ImportLimitExceededError, "limit is 5"):
            await self.importer.import_text(
                text,
                source_name="six_chapters.txt",
            )

        manifest = await self.chapters.get_manifest()
        self.assertEqual(manifest.chapters, [])
        self.assertFalse(
            (
                self.assets_root
                / "source"
                / "manuscripts"
                / "chapters"
                / "chapter_001.md"
            ).exists()
        )

    async def test_active_roots_are_isolated(self) -> None:
        other_directory = tempfile.TemporaryDirectory()
        self.addCleanup(other_directory.cleanup)
        other_storage = ProjectAssetStorageBackend(Path(other_directory.name))
        other_importer = ImportService(other_storage)

        await self.importer.import_text(
            "第一章 原创\n原创正文",
            source_name="original.txt",
        )
        await other_importer.import_text(
            "第一章 测试\n测试正文",
            source_name="test_corpus.txt",
        )

        original_text = await self.storage.read_chapter_markdown(
            "manuscripts/chapters/chapter_001.md"
        )
        fixture_text = await other_storage.read_chapter_markdown(
            "manuscripts/chapters/chapter_001.md"
        )
        self.assertIn("原创正文", original_text)
        self.assertIn("测试正文", fixture_text)
        self.assertNotEqual(original_text, fixture_text)

    async def test_generated_rebuild_stub_preserves_source(self) -> None:
        await self.importer.import_text(
            "第一章 正文\n原创正文",
            source_name="original.txt",
        )
        generated_file = self.assets_root / "generated" / "temp" / "cache.tmp"
        generated_file.write_text("cache", encoding="utf-8")

        await self.chapters.clear_generated_projection_stub()

        self.assertFalse(generated_file.exists())
        source_text = await self.storage.read_chapter_markdown(
            "manuscripts/chapters/chapter_001.md"
        )
        self.assertIn("原创正文", source_text)
