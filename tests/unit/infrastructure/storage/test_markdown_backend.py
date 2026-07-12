"""Project asset Markdown storage tests."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from taichu.application.contracts import ProjectAssetStorageContract
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class ProjectAssetStorageBackendTest(unittest.IsolatedAsyncioTestCase):
    """Verify project source asset storage boundaries."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_ensure_skeleton_creates_source_without_generated_placeholders(
        self,
    ) -> None:
        self.assertIsInstance(self.storage, ProjectAssetStorageContract)

        await self.storage.ensure_skeleton()

        self.assertTrue((self.assets_root / "source" / "metadata.yaml").exists())
        self.assertTrue(
            (self.assets_root / "source" / "manuscripts" / "manifest.json").exists()
        )
        self.assertTrue(
            (self.assets_root / "source" / "manuscripts" / "deleted_chapters").exists()
        )
        self.assertTrue(
            (self.assets_root / "source" / "manuscripts" / "outline.json").exists()
        )
        self.assertTrue(
            (self.assets_root / "source" / "workspace" / "ai_cards.jsonl").exists()
        )
        self.assertTrue(
            (
                self.assets_root / "source" / "workspace" / "chapter_issues.jsonl"
            ).exists()
        )
        self.assertTrue(
            (
                self.assets_root
                / "source"
                / "workspace"
                / "writing_ai_runs.jsonl"
            ).exists()
        )
        self.assertTrue(
            (
                self.assets_root / "source" / "workspace" / "settings_preferences.json"
            ).exists()
        )
        self.assertFalse((self.assets_root / "source" / "knowledge").exists())
        self.assertFalse((self.assets_root / "generated").exists())

    async def test_ensure_skeleton_does_not_overwrite_source_assets(
        self,
    ) -> None:
        source_root = self.assets_root / "source"
        metadata_path = source_root / "metadata.yaml"
        manifest_path = source_root / "manuscripts" / "manifest.json"
        chapter_path = source_root / "manuscripts" / "chapters" / "chapter_999.md"
        ideas_path = source_root / "workspace" / "ideas.jsonl"
        editor_state_path = source_root / "workspace" / "editor_state.json"

        for path in [
            metadata_path,
            manifest_path,
            chapter_path,
            ideas_path,
            editor_state_path,
        ]:
            path.parent.mkdir(parents=True, exist_ok=True)

        original_files = {
            metadata_path: "schema_version: 9\ntitle: 用户小说\n",
            manifest_path: '{"schema_version": "9", "chapters": ["keep"]}\n',
            chapter_path: "# 用户章节\n\n正文不能被覆盖\n",
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

    async def test_chapter_markdown_preserves_author_whitespace(self) -> None:
        await self.storage.ensure_skeleton()
        markdown = "第一行  保留空格\n\n\n    缩进行\n\n\n\n结尾  \n"

        await self.storage.write_chapter_markdown(
            "manuscripts/chapters/chapter_001.md",
            markdown,
        )

        self.assertEqual(
            await self.storage.read_chapter_markdown(
                "manuscripts/chapters/chapter_001.md"
            ),
            markdown,
        )

    async def test_chapter_markdown_can_move_to_deleted_chapters(self) -> None:
        await self.storage.ensure_skeleton()
        source = "manuscripts/chapters/volume-001/chapter_001.md"
        target = (
            "manuscripts/deleted_chapters/volume-001/"
            "deleted_20260702t120000z_chapter_001.md"
        )
        await self.storage.write_chapter_markdown(source, "被删除正文")

        await self.storage.move_chapter_markdown(source, target)

        self.assertFalse(
            (
                self.assets_root
                / "source"
                / "manuscripts"
                / "chapters"
                / "volume-001"
                / "chapter_001.md"
            ).exists()
        )
        self.assertEqual(
            (
                self.assets_root
                / "source"
                / "manuscripts"
                / "deleted_chapters"
                / "volume-001"
                / "deleted_20260702t120000z_chapter_001.md"
            ).read_text(encoding="utf-8"),
            "被删除正文",
        )

    async def test_chapter_markdown_allows_chinese_volume_paths(
        self,
    ) -> None:
        await self.storage.ensure_skeleton()
        source = (
            "manuscripts/chapters/volume_001_第一卷/"
            "chapter_001_大田金鳞元神出.md"
        )
        target = (
            "manuscripts/deleted_chapters/volume_001_第一卷/"
            "deleted_20260702t120000z_chapter_001_大田金鳞元神出.md"
        )

        await self.storage.write_chapter_markdown(source, "正文")
        await self.storage.move_chapter_markdown(source, target)

        self.assertEqual(
            (
                self.assets_root
                / "source"
                / "manuscripts"
                / "deleted_chapters"
                / "volume_001_第一卷"
                / "deleted_20260702t120000z_chapter_001_大田金鳞元神出.md"
            ).read_text(encoding="utf-8"),
            "正文",
        )

    async def test_outline_json_write_read(self) -> None:
        outline: dict[str, object] = {
            "volumes": [
                {
                    "volume_id": "volume-001",
                    "name": "第一卷 大田初醒",
                    "order": 1,
                    "chapters": [
                        {
                            "chapter_id": "chapter-001",
                            "display_title": "第1章 大田金鳞元神出",
                            "order": 1,
                            "markdown_path": (
                                "manuscripts/chapters/volume-001/chapter-001.md"
                            ),
                        }
                    ],
                }
            ],
            "current_volume_id": "volume-001",
            "current_chapter_id": "chapter-001",
            "updated_at": "2026-06-30T12:00:00+09:00",
        }

        await self.storage.write_outline(outline)

        self.assertEqual(await self.storage.read_outline(), outline)
        self.assertTrue(
            (self.assets_root / "source" / "manuscripts" / "outline.json").exists()
        )

    async def test_workspace_jsonl_append_preserves_concurrent_records(
        self,
    ) -> None:
        await self.storage.ensure_skeleton()

        await asyncio.gather(
            *[
                self.storage.append_workspace_record(
                    "ai_cards.jsonl",
                    {"id": f"card_{index:03d}", "order": index},
                )
                for index in range(20)
            ]
        )

        records = await self.storage.list_workspace_records("ai_cards.jsonl")
        self.assertEqual(len(records), 20)
        self.assertEqual(
            {record["id"] for record in records},
            {f"card_{index:03d}" for index in range(20)},
        )

    async def test_workspace_jsonl_append_failure_keeps_existing_file(
        self,
    ) -> None:
        await self.storage.ensure_skeleton()
        await self.storage.append_workspace_record(
            "ideas.jsonl",
            {"id": "idea_001", "content": "保留"},
        )
        ideas_path = self.assets_root / "source" / "workspace" / "ideas.jsonl"
        original_text = ideas_path.read_text(encoding="utf-8")

        with self.assertRaises(TypeError):
            await self.storage.append_workspace_record(
                "ideas.jsonl",
                {"id": "idea_bad", "content": object()},
            )

        self.assertEqual(ideas_path.read_text(encoding="utf-8"), original_text)

    async def test_workspace_jsonl_rewrite_failure_keeps_existing_file(
        self,
    ) -> None:
        await self.storage.ensure_skeleton()
        await self.storage.append_workspace_record(
            "ai_cards.jsonl",
            {"id": "card_001", "status": "generated"},
        )
        cards_path = self.assets_root / "source" / "workspace" / "ai_cards.jsonl"
        original_text = cards_path.read_text(encoding="utf-8")

        with self.assertRaises(TypeError):
            await self.storage.rewrite_workspace_records(
                "ai_cards.jsonl",
                [{"id": "card_bad", "content": object()}],
            )

        self.assertEqual(cards_path.read_text(encoding="utf-8"), original_text)

    async def test_preferences_json_write_read(self) -> None:
        preferences = {
            "font_size": 19,
            "font_style": "serif",
            "editor_background": "dark",
            "updated_at": "2026-06-30T12:00:00+09:00",
        }

        await self.storage.write_preferences(preferences)

        self.assertEqual(await self.storage.read_preferences(), preferences)
