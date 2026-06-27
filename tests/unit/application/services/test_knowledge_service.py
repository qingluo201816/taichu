"""Knowledge service fact-scope listing tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.services.knowledge_service import (
    KnowledgeService,
    knowledge_category_for_type,
)
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


class KnowledgeServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify KnowledgeService keeps fact-scope defaults confirmed-only."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.service = KnowledgeService(self.storage)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_list_cards_defaults_to_confirmed_only(self) -> None:
        confirmed = _knowledge_card(
            knowledge_id="knowledge_confirmed",
            name="Confirmed sword",
            status=KnowledgeCardStatus.CONFIRMED,
        )
        archived = _knowledge_card(
            knowledge_id="knowledge_archived",
            name="Archived sword",
            status=KnowledgeCardStatus.ARCHIVED,
        )
        await self._write_card(confirmed)
        await self._write_card(archived)

        cards = await self.service.list_cards()
        all_cards = await self.service.list_all_cards()

        self.assertEqual([card.id for card in cards], ["knowledge_confirmed"])
        self.assertEqual(
            {card.id for card in all_cards},
            {"knowledge_confirmed", "knowledge_archived"},
        )

    async def _write_card(self, card: KnowledgeCard) -> None:
        await self.storage.write_knowledge_record(
            knowledge_category_for_type(card.type),
            card.id,
            card.model_dump(mode="json"),
        )


def _knowledge_card(
    *,
    knowledge_id: str,
    name: str,
    status: KnowledgeCardStatus,
) -> KnowledgeCard:
    return KnowledgeCard(
        id=knowledge_id,
        type=KnowledgeCardType.TECHNIQUE,
        name=name,
        aliases=[],
        summary=f"{name} summary",
        fields={},
        source_refs=[_source_ref()],
        status=status,
        created_at="2026-06-27T00:00:00Z",
        updated_at="2026-06-27T00:00:00Z",
    )


def _source_ref() -> SourceRef:
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        char_start=0,
        char_end=8,
        excerpt="source text",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )
