"""PendingFact confirmation service tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.services.ai_card_service import PENDING_FACTS_FILE
from taichu.application.services.knowledge_service import (
    KnowledgeIdentityConflictError,
    KnowledgeService,
    KnowledgeSourceRefError,
)
from taichu.application.services.pending_fact_confirmation_service import (
    PendingFactConfirmationEdits,
    PendingFactConfirmationService,
)
from taichu.domain.models.knowledge import KnowledgeCardStatus, KnowledgeCardType
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
from taichu.domain.rules.fact_scope import is_allowed_in_fact_scope
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class PendingFactConfirmationServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify PendingFact promotion writes only confirmed Knowledge."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.knowledge_service = KnowledgeService(self.storage)
        self.confirmation_service = PendingFactConfirmationService(
            self.storage,
            self.knowledge_service,
        )

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_confirm_pending_fact_writes_confirmed_knowledge(
        self,
    ) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        result = await self.confirmation_service.confirm_pending_fact(
            pending_fact.id
        )

        self.assertTrue(result.created)
        self.assertEqual(result.pending_fact.status, PendingFactStatus.CONFIRMED)
        self.assertEqual(
            result.pending_fact.target_knowledge_id,
            result.knowledge_card.id,
        )
        self.assertEqual(result.knowledge_card.status, KnowledgeCardStatus.CONFIRMED)
        self.assertEqual(result.knowledge_card.type, KnowledgeCardType.TECHNIQUE)
        self.assertEqual(result.knowledge_card.source_refs, pending_fact.source_refs)
        self.assertFalse(is_allowed_in_fact_scope(result.pending_fact))
        self.assertTrue(is_allowed_in_fact_scope(result.knowledge_card))
        knowledge_path = (
            self.assets_root
            / "source"
            / "knowledge"
            / "techniques"
            / f"{result.knowledge_card.id}.json"
        )
        self.assertTrue(knowledge_path.exists())

    async def test_duplicate_confirm_is_idempotent(self) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        first = await self.confirmation_service.confirm_pending_fact(
            pending_fact.id
        )
        second = await self.confirmation_service.confirm_pending_fact(
            pending_fact.id
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.knowledge_card.id, second.knowledge_card.id)
        self.assertEqual(
            len(list((self.assets_root / "source" / "knowledge").rglob("*.json"))),
            1,
        )

    async def test_reject_pending_fact_marks_ignored_without_knowledge(
        self,
    ) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        first = await self.confirmation_service.reject_pending_fact(
            pending_fact.id
        )
        second = await self.confirmation_service.reject_pending_fact(
            pending_fact.id
        )

        self.assertEqual(first.pending_fact.status, PendingFactStatus.IGNORED)
        self.assertEqual(second.pending_fact.status, PendingFactStatus.IGNORED)
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )
        self.assertFalse(is_allowed_in_fact_scope(first.pending_fact))

    async def test_confirm_edited_preserves_source_refs_and_author_fields(
        self,
    ) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        result = await self.confirmation_service.confirm_pending_fact_with_edits(
            pending_fact.id,
            PendingFactConfirmationEdits(
                name="Edited technique",
                summary="Author approved summary",
                aliases=["Alias A"],
                fields={"rule": "edited"},
            ),
        )

        self.assertEqual(
            result.pending_fact.status,
            PendingFactStatus.EDITED_CONFIRMED,
        )
        self.assertEqual(result.knowledge_card.name, "Edited technique")
        self.assertEqual(result.knowledge_card.aliases, ["Alias A"])
        self.assertEqual(result.knowledge_card.summary, "Author approved summary")
        self.assertEqual(result.knowledge_card.fields, {"rule": "edited"})
        self.assertEqual(result.knowledge_card.source_refs, pending_fact.source_refs)

    async def test_confirm_without_source_ref_is_rejected(self) -> None:
        pending_fact = _pending_fact(source_refs=[])
        await self._append_pending_fact(pending_fact)

        with self.assertRaises(KnowledgeSourceRefError):
            await self.confirmation_service.confirm_pending_fact(pending_fact.id)

        records = await self.storage.list_workspace_records(PENDING_FACTS_FILE)
        stored = PendingFact.model_validate(records[0])
        self.assertEqual(stored.status, PendingFactStatus.PENDING)
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )

    async def test_alias_conflict_is_rejected(self) -> None:
        first = _pending_fact(
            pending_fact_id="pending_fact_first",
            title="Existing name",
        )
        second = _pending_fact(
            pending_fact_id="pending_fact_second",
            title="New name",
        )
        await self._append_pending_fact(first)
        await self._append_pending_fact(second)

        await self.confirmation_service.confirm_pending_fact(first.id)

        with self.assertRaises(KnowledgeIdentityConflictError):
            await self.confirmation_service.confirm_pending_fact_with_edits(
                second.id,
                PendingFactConfirmationEdits(aliases=["Existing name"]),
            )

    async def _append_pending_fact(self, pending_fact: PendingFact) -> None:
        await self.storage.append_workspace_record(
            PENDING_FACTS_FILE,
            pending_fact.model_dump(mode="json"),
        )


def _pending_fact(
    *,
    pending_fact_id: str = "pending_fact_001",
    title: str = "Taichu sword intent",
    source_refs: list[SourceRef] | None = None,
) -> PendingFact:
    return PendingFact(
        id=pending_fact_id,
        fact_type=PendingFactType.TECHNIQUE,
        title=title,
        content={"rule": "heart fire reveals the sword path"},
        proposed_by=ProposedBy.AI,
        source_refs=_source_refs() if source_refs is None else source_refs,
        status=PendingFactStatus.PENDING,
        created_at="2026-06-27T00:00:00Z",
    )


def _source_refs() -> list[SourceRef]:
    return [
        SourceRef(
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
    ]
