"""JSON structured knowledge repository tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
)
from taichu.infrastructure.knowledge import JSONKnowledgeRepository
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend


class JSONKnowledgeRepositoryTest(unittest.IsolatedAsyncioTestCase):
    """Verify Agent-facing structured knowledge storage behavior."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.repository = JSONKnowledgeRepository(self.storage)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_list_and_search_active_cards_ignore_draft_and_deprecated(
        self,
    ) -> None:
        active = _card("character-qin", "秦阳", StructuredKnowledgeStatus.ACTIVE)
        draft = _card("character-draft", "秦阳", StructuredKnowledgeStatus.DRAFT)
        deprecated = _card(
            "character-old",
            "秦阳",
            StructuredKnowledgeStatus.DEPRECATED,
        )
        await self.repository.create_active_card(active)
        await self._write_raw(draft)
        await self._write_raw(deprecated)

        cards = await self.repository.list_active_cards("character")
        matches = await self.repository.search_active_identity(
            "character",
            "秦阳",
            [],
        )

        self.assertEqual([card.id for card in cards], ["character-qin"])
        self.assertEqual([card.id for card in matches], ["character-qin"])

    async def test_patch_active_card_appends_source_note_and_keeps_non_empty(
        self,
    ) -> None:
        active = _card("character-qin", "秦阳", StructuredKnowledgeStatus.ACTIVE)
        await self.repository.create_active_card(active)

        patched = await self.repository.patch_active_card(
            "character-qin",
            {
                "identity": "太初教弟子",
                "source_note": "来自章节《第一章》。原文摘录：秦阳入山。",
                "last_seen_chapter_id": "chapter_002",
            },
        )

        self.assertEqual(patched.identity, "太初教弟子")
        self.assertEqual(patched.last_seen_chapter_id, "chapter_002")
        self.assertIn("作者手动添加", patched.source_note)
        self.assertIn("秦阳入山", patched.source_note)
        with self.assertRaisesRegex(ValueError, "不能覆盖已有非空字段"):
            await self.repository.patch_active_card(
                "character-qin",
                {"summary": "不应覆盖"},
            )

    async def test_search_active_identity_does_not_match_summary_mentions(
        self,
    ) -> None:
        active = _card("character-zhang", "张狂", StructuredKnowledgeStatus.ACTIVE)
        active = active.model_copy(
            update={
                "aliases": [],
                "summary": "张狂与秦浩轩同章出现，但不是同一名角色。",
                "source_note": "来自章节《第一章》。原文摘录：秦浩轩与张狂发生冲突。",
            }
        )
        await self.repository.create_active_card(active)

        matches = await self.repository.search_active_identity(
            "character",
            "秦浩轩",
            [],
        )

        self.assertEqual(matches, [])

    async def _write_raw(self, card: StructuredKnowledgeCard) -> None:
        await self.storage.write_structured_knowledge_record(
            card.type.value,
            card.id,
            card.model_dump(mode="json"),
        )


def _card(
    card_id: str,
    name: str,
    status: StructuredKnowledgeStatus,
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=StructuredKnowledgeType.CHARACTER,
        name=name,
        aliases=["阿阳"],
        summary=f"{name} 摘要",
        status=status,
        source_origin=StructuredKnowledgeSourceOrigin.AGENT_EXTRACT,
        source_note="作者手动添加。来自章节《第一章》。原文摘录：秦阳入山。",
        created_at="2026-07-04T00:00:00Z",
        updated_at="2026-07-04T00:00:00Z",
    )
