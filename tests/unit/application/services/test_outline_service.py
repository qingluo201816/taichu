"""Outline service chapter ordering tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.services.outline_service import OutlineService
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class OutlineServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify global chapter numbering and manuscript file movement."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.service = OutlineService(self.storage)
        await self.storage.ensure_skeleton()

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_second_volume_chapters_continue_global_numbers(self) -> None:
        first_volume_id = (await self.service.create_volume("第一卷")).current_volume_id
        self.assertIsNotNone(first_volume_id)
        outline = await self.service.create_chapter(
            first_volume_id or "",
            "第0001章 大田金鳞元神出",
        )
        outline = await self.service.create_chapter(first_volume_id or "", "山门回声")
        second_volume_id = (await self.service.create_volume("第二卷")).current_volume_id
        self.assertIsNotNone(second_volume_id)

        outline = await self.service.create_chapter(second_volume_id or "", "测试第3")
        third = outline.volumes[1].chapters[0]

        self.assertEqual(third.display_title, "第3章 测试第3")
        self.assertEqual(third.order, 3)
        self.assertEqual(
            third.markdown_path,
            "manuscripts/chapters/volume_002_第二卷/chapter_003_测试第3.md",
        )

        manifest = await self.storage.read_manifest()
        self.assertEqual(
            [
                chapter["title"]
                for chapter in manifest["chapters"]  # type: ignore[index]
            ],
            ["第1章 大田金鳞元神出", "第2章 山门回声", "第3章 测试第3"],
        )

    async def test_inserted_chapter_renumbers_later_chapters_across_volumes(
        self,
    ) -> None:
        first_volume_id = (await self.service.create_volume("第一卷")).current_volume_id
        self.assertIsNotNone(first_volume_id)
        outline = await self.service.create_chapter(first_volume_id or "", "第一章")
        first = outline.volumes[0].chapters[0]
        second_volume_id = (await self.service.create_volume("第二卷")).current_volume_id
        self.assertIsNotNone(second_volume_id)
        outline = await self.service.create_chapter(second_volume_id or "", "原第二卷")
        moved = outline.volumes[1].chapters[0]
        await self.storage.write_chapter_markdown(moved.markdown_path, "原第二卷正文")

        outline = await self.service.create_chapter(
            first_volume_id or "",
            "插入章",
            after_chapter_id=first.chapter_id,
        )

        self.assertEqual(
            [
                chapter.display_title
                for volume in outline.volumes
                for chapter in volume.chapters
            ],
            ["第1章", "第2章 插入章", "第3章 原第二卷"],
        )
        moved_after_insert = outline.volumes[1].chapters[0]
        self.assertEqual(moved_after_insert.order, 3)
        self.assertEqual(
            await self.storage.read_chapter_markdown(moved_after_insert.markdown_path),
            "原第二卷正文",
        )

    async def test_deleted_chapter_is_archived_and_later_chapters_shift(self) -> None:
        volume_id = (await self.service.create_volume("第一卷")).current_volume_id
        self.assertIsNotNone(volume_id)

        outline = await self.service.create_chapter(volume_id or "", "第一章")
        first = outline.volumes[0].chapters[0]
        outline = await self.service.create_chapter(volume_id or "", "第二章")
        second = outline.volumes[0].chapters[1]
        outline = await self.service.create_chapter(volume_id or "", "第三章")
        third = outline.volumes[0].chapters[2]
        await self.storage.write_chapter_markdown(second.markdown_path, "待删除正文")
        await self.storage.write_chapter_markdown(third.markdown_path, "原第三章正文")

        outline = await self.service.delete_chapter(second.chapter_id)
        chapters = outline.volumes[0].chapters

        self.assertEqual(
            [chapter.chapter_id for chapter in chapters],
            [first.chapter_id, third.chapter_id],
        )
        self.assertEqual(
            [chapter.display_title for chapter in chapters],
            ["第1章", "第2章"],
        )
        self.assertEqual(
            await self.storage.read_chapter_markdown(chapters[1].markdown_path),
            "原第三章正文",
        )

        deleted_root = (
            self.assets_root
            / "source"
            / "manuscripts"
            / "deleted_chapters"
            / "volume_001_第一卷"
        )
        deleted_files = list(deleted_root.glob("*.md"))
        self.assertEqual(len(deleted_files), 1)
        self.assertEqual(deleted_files[0].read_text(encoding="utf-8"), "待删除正文")

        manifest = await self.storage.read_manifest()
        self.assertEqual(
            [
                chapter["id"]
                for chapter in manifest["chapters"]  # type: ignore[index]
            ],
            [first.chapter_id, third.chapter_id],
        )

    async def test_renaming_volume_moves_chapter_directory(self) -> None:
        volume_id = (await self.service.create_volume("第一卷")).current_volume_id
        self.assertIsNotNone(volume_id)
        outline = await self.service.create_chapter(volume_id or "", "开篇")
        chapter = outline.volumes[0].chapters[0]
        await self.storage.write_chapter_markdown(chapter.markdown_path, "正文")

        outline = await self.service.rename_volume(volume_id or "", "正篇")
        renamed = outline.volumes[0].chapters[0]

        self.assertEqual(
            renamed.markdown_path,
            "manuscripts/chapters/volume_001_正篇/chapter_001_开篇.md",
        )
        self.assertEqual(
            await self.storage.read_chapter_markdown(renamed.markdown_path),
            "正文",
        )

    async def test_deleting_volume_archives_chapters_and_renumbers_remaining(
        self,
    ) -> None:
        first_volume_id = (await self.service.create_volume("第一卷")).current_volume_id
        self.assertIsNotNone(first_volume_id)
        outline = await self.service.create_chapter(first_volume_id or "", "第一章")
        kept = outline.volumes[0].chapters[0]
        second_volume_id = (await self.service.create_volume("第二卷")).current_volume_id
        self.assertIsNotNone(second_volume_id)
        outline = await self.service.create_chapter(second_volume_id or "", "删除章")
        deleted = outline.volumes[1].chapters[0]
        await self.storage.write_chapter_markdown(deleted.markdown_path, "删除卷正文")

        outline = await self.service.delete_volume(second_volume_id or "")

        self.assertEqual(len(outline.volumes), 1)
        self.assertEqual(outline.volumes[0].chapters[0].chapter_id, kept.chapter_id)
        self.assertEqual(outline.volumes[0].chapters[0].display_title, "第1章")
        deleted_root = (
            self.assets_root
            / "source"
            / "manuscripts"
            / "deleted_chapters"
            / "volume_002_第二卷"
        )
        deleted_files = list(deleted_root.glob("*.md"))
        self.assertEqual(len(deleted_files), 1)
        self.assertEqual(deleted_files[0].read_text(encoding="utf-8"), "删除卷正文")

