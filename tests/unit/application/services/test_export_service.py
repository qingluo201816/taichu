"""Export service tests."""

import json
import tempfile
import unittest
from pathlib import Path

from taichu.application.services.ai_card_service import IDEAS_FILE
from taichu.application.services.export_service import ExportService
from taichu.application.services.import_service import ImportService
from taichu.application.services.knowledge_service import knowledge_category_for_type
from taichu.domain.models.inbox import IdeaCard, IdeaCardSource, IdeaCardStatus
from taichu.domain.models.knowledge import (
    KnowledgeCard,
    KnowledgeCardStatus,
    KnowledgeCardType,
)
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class ExportServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify source export is readable and complete for MVP assets."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(self.storage).import_text(
            "第一章 导出\n秦浩轩记录太初古卷。",
            source_name="export.txt",
        )
        await self._write_knowledge(_knowledge_card())
        await self.storage.append_workspace_record(
            IDEAS_FILE,
            IdeaCard(
                id="idea_export_001",
                content="导出灵感",
                source=IdeaCardSource.AI,
                status=IdeaCardStatus.OPEN,
                tags=[],
                created_at="2026-06-27T00:00:00Z",
                updated_at="2026-06-27T00:00:00Z",
            ).model_dump(mode="json"),
        )

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_build_bundle_exports_readable_source_assets(self) -> None:
        bundle = await ExportService(self.storage).build_bundle()
        files = {file.path: file for file in bundle.files}

        self.assertIn("source/metadata.yaml", files)
        self.assertIn("source/manuscripts/manifest.json", files)
        self.assertIn("source/manuscripts/chapters/chapter_001.md", files)
        self.assertIn("source/knowledge/items/knowledge_export_item.json", files)
        self.assertIn("source/workspace/ideas.jsonl", files)
        self.assertIn(
            "秦浩轩记录太初古卷",
            files["source/manuscripts/chapters/chapter_001.md"].content,
        )

        manifest = json.loads(files["source/manuscripts/manifest.json"].content)
        knowledge = json.loads(
            files["source/knowledge/items/knowledge_export_item.json"].content
        )
        idea_lines = [
            json.loads(line)
            for line in files["source/workspace/ideas.jsonl"].content.splitlines()
            if line.strip()
        ]

        self.assertEqual(manifest["chapters"][0]["id"], "chapter_001")
        self.assertEqual(knowledge["status"], "confirmed")
        self.assertEqual(idea_lines[0]["id"], "idea_export_001")

    async def _write_knowledge(self, card: KnowledgeCard) -> None:
        await self.storage.write_knowledge_record(
            knowledge_category_for_type(card.type),
            card.id,
            card.model_dump(mode="json"),
        )


def _knowledge_card() -> KnowledgeCard:
    return KnowledgeCard(
        id="knowledge_export_item",
        type=KnowledgeCardType.ITEM,
        name="太初古卷",
        aliases=[],
        summary="太初古卷是作者确认设定。",
        fields={},
        source_refs=[_source_ref()],
        status=KnowledgeCardStatus.CONFIRMED,
        created_at="2026-06-27T00:00:00Z",
        updated_at="2026-06-27T00:00:00Z",
    )


def _source_ref() -> SourceRef:
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="project_assets/source/manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        excerpt="秦浩轩记录太初古卷。",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )
