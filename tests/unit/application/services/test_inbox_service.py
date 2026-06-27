"""Creative inbox service tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.services.ai_card_service import AICardService
from taichu.application.services.inbox_service import InboxService
from taichu.domain.models.ai_card import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
)
from taichu.domain.models.pending_fact import (
    PendingFact,
    PendingFactStatus,
    PendingFactType,
    ProposedBy,
)
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class InboxServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify creative inbox use cases without real project assets."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.ai_card_service = AICardService(self.storage)
        self.inbox_service = InboxService(self.storage, self.ai_card_service)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_save_duplicate_suggestion_card_does_not_duplicate_idea(
        self,
    ) -> None:
        card = await self.ai_card_service.create_card(_suggestion_card())

        first = await self.inbox_service.save_card_as_idea(card.id)
        second = await self.inbox_service.save_card_as_idea(card.id)
        snapshot = await self.inbox_service.list_inbox()

        self.assertEqual(first.idea.id, second.idea.id)
        self.assertEqual(len(snapshot.ideas), 1)
        self.assertEqual(len(snapshot.saved_ai_cards), 1)

    async def test_convert_pending_fact_card_then_ignore_removes_active_lane(
        self,
    ) -> None:
        card = await self.ai_card_service.create_card(_pending_fact_card())

        result = await self.inbox_service.convert_card_to_pending_fact(card.id)
        active_snapshot = await self.inbox_service.list_inbox()
        ignored = await self.inbox_service.ignore_pending_fact(
            result.pending_fact.id
        )
        final_snapshot = await self.inbox_service.list_inbox()

        self.assertEqual(
            result.card.status,
            AIResultCardStatus.CONVERTED_TO_PENDING_FACT,
        )
        self.assertEqual(len(active_snapshot.pending_facts), 1)
        self.assertEqual(ignored.status, PendingFactStatus.IGNORED)
        self.assertEqual(final_snapshot.pending_facts, [])
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )

    async def test_duplicate_pending_fact_conversion_is_idempotent(
        self,
    ) -> None:
        card = await self.ai_card_service.create_card(_pending_fact_card())

        first = await self.inbox_service.convert_card_to_pending_fact(card.id)
        second = await self.inbox_service.convert_card_to_pending_fact(card.id)
        snapshot = await self.inbox_service.list_inbox()

        self.assertEqual(first.pending_fact.id, second.pending_fact.id)
        self.assertEqual(len(snapshot.pending_facts), 1)


def _suggestion_card() -> AIResultCard:
    return AIResultCard(
        id="card_suggestion",
        type=AIResultCardType.SUGGESTION,
        workflow=AIWorkflow.ASK_SELECTION,
        status=AIResultCardStatus.GENERATED,
        chapter_id="chapter_001",
        input_context={},
        content={"body": "这条建议可以保存为灵感。"},
        source_refs=[_source_ref()],
        created_at="2026-06-27T00:00:00Z",
        updated_at="2026-06-27T00:00:00Z",
    )


def _pending_fact_card() -> AIResultCard:
    pending_fact = PendingFact(
        id="pending_fact_001",
        fact_type=PendingFactType.TECHNIQUE,
        title="太初剑意",
        content={"rule": "以心火照见剑路。"},
        proposed_by=ProposedBy.AI,
        source_refs=[_source_ref()],
        status=PendingFactStatus.PENDING,
        created_at="2026-06-27T00:00:00Z",
    )
    return AIResultCard(
        id="card_pending",
        type=AIResultCardType.PENDING_FACT,
        workflow=AIWorkflow.ENRICH_SETTING,
        status=AIResultCardStatus.GENERATED,
        chapter_id="chapter_001",
        input_context={},
        content=pending_fact.model_dump(mode="json"),
        source_refs=[_source_ref()],
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
        char_end=2,
        excerpt="正文",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )
