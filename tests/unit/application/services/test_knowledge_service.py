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

    async def test_schema_exposes_field_merge_strategies(self) -> None:
        schema = self.service.get_schema(StructuredKnowledgeType.CHARACTER)
        strategies = {
            field.field_key: field.merge_strategy.value for field in schema.fields
        }

        self.assertEqual(strategies["summary"], "replace")
        self.assertEqual(strategies["source_note"], "append_unique")
        self.assertEqual(strategies["aliases"], "union")
        self.assertEqual(strategies["appearance_chapter_count"], "sum")
        self.assertEqual(strategies["last_seen_chapter_id"], "latest")
        self.assertEqual(strategies["identity"], "preserve_existing")

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
        default_page = await self.service.list_cards(StructuredKnowledgeType.CHARACTER)
        rejected_page = await self.service.list_cards(
            StructuredKnowledgeType.CHARACTER,
            lifecycle="rejected",
        )
        self.assertEqual(default_page.cards, [])
        self.assertEqual([card.id for card in rejected_page.cards], [draft.id])

    async def test_list_uses_realm_order_and_other_types_use_appearance_count(
        self,
    ) -> None:
        repository = InMemoryKnowledgeRepository(
            [
                _stored_card("realm-3", StructuredKnowledgeType.REALM, level_order=3),
                _stored_card("realm-1", StructuredKnowledgeType.REALM, level_order=1),
                _stored_card("realm-none", StructuredKnowledgeType.REALM),
                _stored_card(
                    "character-2",
                    StructuredKnowledgeType.CHARACTER,
                    appearance_chapter_count=2,
                ),
                _stored_card(
                    "character-8",
                    StructuredKnowledgeType.CHARACTER,
                    appearance_chapter_count=8,
                ),
                _stored_card("character-none", StructuredKnowledgeType.CHARACTER),
            ]
        )
        service = KnowledgeService(repository)

        realm_page = await service.list_cards(
            StructuredKnowledgeType.REALM,
            page_size=2,
        )
        realm_last_page = await service.list_cards(
            StructuredKnowledgeType.REALM,
            page=2,
            page_size=2,
        )
        character_page = await service.list_cards(
            StructuredKnowledgeType.CHARACTER,
        )

        self.assertEqual([card.id for card in realm_page.cards], ["realm-1", "realm-3"])
        self.assertEqual([card.id for card in realm_last_page.cards], ["realm-none"])
        self.assertEqual(
            [card.id for card in character_page.cards],
            ["character-8", "character-2", "character-none"],
        )

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

    async def test_merge_confirmed_cards_keeps_primary_and_retires_duplicate(
        self,
    ) -> None:
        primary = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                **_complete_character_data("黄龙真人"),
                "aliases": ["黄龙"],
                "summary": "黄龙真人是太初教掌教。",
                "source_note": "第1章：黄龙真人出现。",
            },
        )
        duplicate = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                **_complete_character_data("太初教掌教"),
                "summary": "太初教掌教重视灰种弟子。",
                "source_note": "第2章：掌教关注灰种。",
            },
        )
        primary = await self.service.confirm_card(primary.id)
        duplicate = await self.service.confirm_card(duplicate.id)

        merged_primary, retired = await self.service.merge_confirmed_cards(
            primary.id,
            duplicate.id,
        )

        self.assertEqual(merged_primary.id, primary.id)
        self.assertEqual(
            merged_primary.lifecycle, StructuredKnowledgeLifecycle.CONFIRMED
        )
        self.assertIn("太初教掌教", merged_primary.aliases)
        self.assertIn("黄龙真人是太初教掌教。", merged_primary.summary)
        self.assertIn("太初教掌教重视灰种弟子。", merged_primary.summary)
        self.assertEqual(retired.id, duplicate.id)
        self.assertEqual(retired.lifecycle, StructuredKnowledgeLifecycle.REJECTED)
        self.assertEqual(
            [card.id for card in await self.service.list_confirmed_cards()],
            [primary.id],
        )

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

    async def test_schema_merge_strategies_drive_confirmed_updates(self) -> None:
        draft = await self.service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                **_complete_character_data("秦浩轩"),
                "aliases": ["浩轩"],
                "summary": "大田镇少年，靠采药补贴家用。",
                "source_note": "第1章\n关键原文：旧证据",
                "identity": "大田镇少年",
                "last_seen_chapter_id": "chapter_001",
            },
        )
        confirmed = await self.service.confirm_card(draft.id)

        updated = await self.service.apply_author_confirmed_updates(
            confirmed.id,
            {
                "aliases": ["小浩", "浩轩"],
                "summary": "秦浩轩是大田镇少年，靠采药补贴家用，并参加太初教入门测试。",
                "source_note": ("第1章\n关键原文：旧证据\n\n第2章\n关键原文：新证据"),
                "identity": "不应覆盖已有身份",
                "last_seen_chapter_id": "chapter_002",
                "appearance_chapter_count": 2,
            },
            merge_mode="merge",
            allow_appearance_count_update=True,
        )

        self.assertEqual(
            updated.summary,
            "秦浩轩是大田镇少年，靠采药补贴家用，并参加太初教入门测试。",
        )
        self.assertEqual(updated.summary.count("大田镇少年"), 1)
        self.assertEqual(updated.aliases, ["浩轩", "小浩"])
        self.assertEqual(
            updated.source_note,
            "第1章\n关键原文：旧证据\n\n第2章\n关键原文：新证据",
        )
        self.assertEqual(updated.identity, "大田镇少年")
        self.assertEqual(updated.last_seen_chapter_id, "chapter_002")
        self.assertEqual(updated.appearance_chapter_count, 2)

        with self.assertRaisesRegex(KnowledgeCardValidationError, "方式不支持"):
            await self.service.apply_author_confirmed_updates(
                updated.id,
                {"summary": "旧协议"},
                merge_mode="append",  # type: ignore[arg-type]
            )


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


def _stored_card(
    card_id: str,
    knowledge_type: StructuredKnowledgeType,
    *,
    appearance_chapter_count: int | None = None,
    level_order: float | None = None,
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=knowledge_type,
        name=card_id,
        appearance_chapter_count=appearance_chapter_count,
        level_order=level_order,
        lifecycle=StructuredKnowledgeLifecycle.CONFIRMED,
        source_origin="manual",
        created_at="2026-08-16T00:00:00Z",
        updated_at="2026-08-16T00:00:00Z",
    )
