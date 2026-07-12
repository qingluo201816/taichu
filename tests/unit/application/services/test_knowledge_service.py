"""Knowledge application service lifecycle and validation tests."""

import unittest

from taichu.application.contracts.knowledge_repository import (
    KnowledgeRepositoryConcurrentUpdateError,
)
from taichu.application.services.knowledge_service import (
    KnowledgeCardValidationError,
    KnowledgeConcurrentUpdateError,
    KnowledgeIdentityConflictError,
    KnowledgeService,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
)
from tests.fakes import InMemoryKnowledgeRepository


class KnowledgeServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify application rules without coupling tests to MongoDB."""

    async def asyncSetUp(self) -> None:
        self.repository = InMemoryKnowledgeRepository()
        self.service = KnowledgeService(self.repository)

    async def test_public_create_always_creates_draft(self) -> None:
        card = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            _complete_character_data("秦阳"),
        )

        self.assertTrue(card.id.startswith("character-"))
        self.assertEqual(card.lifecycle, StructuredKnowledgeLifecycle.DRAFT)
        self.assertEqual(card.name, "秦阳")

    async def test_create_and_patch_reject_system_managed_fields(self) -> None:
        with self.assertRaisesRegex(KnowledgeCardValidationError, "系统字段"):
            await self.service.create_card(
                StructuredKnowledgeType.CHARACTER,
                {
                    **_complete_character_data("秦阳"),
                    "lifecycle": "confirmed",
                },
            )

        card = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            _complete_character_data("秦阳"),
        )
        with self.assertRaisesRegex(KnowledgeCardValidationError, "系统字段"):
            await self.service.patch_card(
                card.id,
                {"lifecycle": "confirmed"},
            )

    async def test_confirm_reject_and_default_list_excludes_rejected(self) -> None:
        draft = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            _complete_character_data("秦阳"),
        )

        confirmed = await self.service.confirm_card(draft.id)
        self.assertEqual(
            confirmed.lifecycle,
            StructuredKnowledgeLifecycle.CONFIRMED,
        )
        confirmed_cards = await self.service.list_confirmed_cards(
            StructuredKnowledgeType.CHARACTER
        )
        self.assertEqual([card.id for card in confirmed_cards], [draft.id])

        rejected = await self.service.reject_card(draft.id)
        self.assertEqual(rejected.lifecycle, StructuredKnowledgeLifecycle.REJECTED)
        default_page = await self.service.list_cards(
            StructuredKnowledgeType.CHARACTER
        )
        rejected_page = await self.service.list_cards(
            StructuredKnowledgeType.CHARACTER,
            lifecycle="rejected",
        )
        self.assertEqual(default_page.cards, [])
        self.assertEqual([card.id for card in rejected_page.cards], [draft.id])

    async def test_incomplete_draft_cannot_be_confirmed(self) -> None:
        draft = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {"name": "秦阳"},
        )

        with self.assertRaises(KnowledgeCardValidationError):
            await self.service.confirm_card(draft.id)
        persisted = await self.service.get_card(draft.id)
        self.assertEqual(persisted.lifecycle, StructuredKnowledgeLifecycle.DRAFT)

    async def test_confirmed_name_or_alias_conflict_is_rejected(self) -> None:
        first = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                **_complete_character_data("秦阳"),
                "aliases": ["秦师兄"],
            },
        )
        second = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                **_complete_character_data("另一人"),
                "aliases": ["秦阳"],
            },
        )
        await self.service.confirm_card(first.id)

        with self.assertRaises(KnowledgeIdentityConflictError):
            await self.service.confirm_card(second.id)
        persisted = await self.service.get_card(second.id)
        self.assertEqual(persisted.lifecycle, StructuredKnowledgeLifecycle.DRAFT)

    async def test_repository_cas_failure_maps_to_service_error(self) -> None:
        repository = _ConcurrentUpdateRepository()
        service = KnowledgeService(repository)
        card = await service.create_card(
            StructuredKnowledgeType.CHARACTER,
            _complete_character_data("秦阳"),
        )
        repository.fail_updates = True

        with self.assertRaises(KnowledgeConcurrentUpdateError):
            await service.patch_card(card.id, {"summary": "新的摘要"})

    async def test_occurrence_count_is_system_managed_and_accumulates(self) -> None:
        draft = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            _complete_character_data("秦阳"),
        )
        confirmed = await self.service.confirm_card(draft.id)

        with self.assertRaisesRegex(KnowledgeCardValidationError, "统计字段"):
            await self.service.patch_card(
                confirmed.id,
                {"appearance_chapter_count": 1},
            )

        first = await self.service.apply_author_confirmed_updates(
            confirmed.id,
            {"appearance_chapter_count": 2},
            allow_appearance_count_update=True,
        )
        second = await self.service.apply_author_confirmed_updates(
            first.id,
            {"appearance_chapter_count": 3},
            merge_mode="overwrite",
            allow_appearance_count_update=True,
        )

        self.assertEqual(first.appearance_chapter_count, 2)
        self.assertEqual(second.appearance_chapter_count, 5)


class _ConcurrentUpdateRepository(InMemoryKnowledgeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail_updates = False

    async def update_card(
        self,
        card: StructuredKnowledgeCard,
        *,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        if self.fail_updates:
            raise KnowledgeRepositoryConcurrentUpdateError("模拟并发更新")
        return await super().update_card(
            card,
            expected_updated_at=expected_updated_at,
        )


def _complete_character_data(name: str) -> dict[str, object]:
    return {
        "name": name,
        "aliases": [],
        "summary": f"{name}的事实摘要。",
        "source_origin": "manual",
        "source_note": "作者手动确认。",
        "role_type": "protagonist",
    }
