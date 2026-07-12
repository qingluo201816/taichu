"""Export service tests."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast

from taichu.application.contracts.knowledge_repository import (
    KnowledgeCardPage,
    KnowledgeCardQuery,
    StructuredKnowledgeRepository,
)
from taichu.application.services.ai_card_service import IDEAS_FILE
from taichu.application.services.export_service import ExportService
from taichu.application.services.import_service import ImportService
from taichu.domain.models.inbox import IdeaCard, IdeaCardSource, IdeaCardStatus
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class InMemoryKnowledgeRepository:
    """Return deterministic pages without touching JSON knowledge storage."""

    def __init__(
        self,
        cards: list[StructuredKnowledgeCard],
        *,
        max_page_size: int = 2,
    ) -> None:
        self.cards = cards
        self.max_page_size = max_page_size
        self.queries: list[KnowledgeCardQuery] = []

    async def list_cards(self, query: KnowledgeCardQuery) -> KnowledgeCardPage:
        self.queries.append(query)
        matched = [
            card
            for card in self.cards
            if card.lifecycle in query.lifecycles
            and (query.type is None or card.type is query.type)
        ]
        limit = min(query.limit, self.max_page_size)
        page_cards = matched[query.offset : query.offset + limit]
        return KnowledgeCardPage(
            cards=page_cards,
            total=len(matched),
            offset=query.offset,
            limit=limit,
        )


class ExportServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify v2 export reads knowledge from the repository and source elsewhere."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(self.storage).import_text(
            "第一章 导出\n秦阳轩记录太初古卷。",
            source_name="export.txt",
        )
        self.knowledge_repository = InMemoryKnowledgeRepository(
            [
                _knowledge_card(
                    "knowledge_export_draft",
                    StructuredKnowledgeLifecycle.DRAFT,
                ),
                _knowledge_card(
                    "knowledge_export_confirmed",
                    StructuredKnowledgeLifecycle.CONFIRMED,
                ),
                _knowledge_card(
                    "knowledge_export_rejected",
                    StructuredKnowledgeLifecycle.REJECTED,
                ),
            ]
        )
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

    async def test_build_bundle_exports_source_assets_and_all_knowledge(self) -> None:
        bundle = await ExportService(
            self.storage,
            cast(StructuredKnowledgeRepository, self.knowledge_repository),
        ).build_bundle()
        files = {file.path: file for file in bundle.files}

        self.assertEqual(bundle.schema_version, "taichu_export_v2")
        self.assertIn("source/metadata.yaml", files)
        self.assertIn("source/manuscripts/manifest.json", files)
        self.assertIn("source/manuscripts/chapters/chapter_001.md", files)
        self.assertIn("source/workspace/ideas.jsonl", files)
        self.assertIn("knowledge/knowledge_cards.json", files)
        self.assertIn(
            "秦阳轩记录太初古卷。",
            files["source/manuscripts/chapters/chapter_001.md"].content,
        )

        manifest = json.loads(files["source/manuscripts/manifest.json"].content)
        snapshot = json.loads(files["knowledge/knowledge_cards.json"].content)
        idea_lines = [
            json.loads(line)
            for line in files["source/workspace/ideas.jsonl"].content.splitlines()
            if line.strip()
        ]

        self.assertEqual(manifest["chapters"][0]["id"], "chapter_001")
        self.assertEqual(snapshot["schema_version"], "taichu_export_v2")
        self.assertEqual(snapshot["created_at"], bundle.created_at)
        self.assertEqual(idea_lines[0]["id"], "idea_export_001")

        cards = snapshot["cards"]
        self.assertEqual(
            {card["lifecycle"] for card in cards},
            {"draft", "confirmed", "rejected"},
        )
        self.assertEqual(len(cards), 3)
        for card in cards:
            self.assertTrue(card["created_at"].endswith("Z"))
            self.assertTrue(card["updated_at"].endswith("Z"))
            self.assertNotIn("status", card)
            self.assertNotIn("identity_keys", card)

        self.assertEqual(
            [query.offset for query in self.knowledge_repository.queries],
            [0, 2],
        )
        for query in self.knowledge_repository.queries:
            self.assertEqual(
                query.lifecycles,
                frozenset(StructuredKnowledgeLifecycle),
            )


def _knowledge_card(
    card_id: str,
    lifecycle: StructuredKnowledgeLifecycle,
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=StructuredKnowledgeType.ITEM,
        name=f"知识卡 {card_id}",
        aliases=[],
        summary="太初古卷是作者整理的设定。",
        lifecycle=lifecycle,
        source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
        source_note="作者手动整理。",
        created_at="2026-06-27T00:00:00Z",
        updated_at="2026-06-27T00:00:00Z",
    )
