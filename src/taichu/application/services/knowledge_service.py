"""Minimal confirmed Knowledge JSON use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models.knowledge import (
    KnowledgeCard,
    KnowledgeCardStatus,
    KnowledgeCardType,
)


_KNOWLEDGE_CATEGORY_BY_TYPE: dict[KnowledgeCardType, str] = {
    KnowledgeCardType.CHARACTER: "character",
    KnowledgeCardType.REALM: "realm",
    KnowledgeCardType.TECHNIQUE: "technique",
    KnowledgeCardType.LOCATION: "location",
    KnowledgeCardType.FACTION: "faction",
    KnowledgeCardType.ITEM: "item",
    KnowledgeCardType.RULE: "rule",
    KnowledgeCardType.EVENT: "event",
}


@dataclass(frozen=True)
class KnowledgeWriteResult:
    """Result of writing or reusing a confirmed knowledge card."""

    card: KnowledgeCard
    created: bool


class KnowledgeService:
    """Application service for author-confirmed Knowledge JSON records."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def list_cards(self) -> list[KnowledgeCard]:
        """List all active knowledge records from source/knowledge."""
        cards = await self.list_all_cards()
        return [card for card in cards if card.status is KnowledgeCardStatus.ACTIVE]

    async def list_all_cards(self) -> list[KnowledgeCard]:
        """List all knowledge records from source/knowledge."""
        records = await self._storage.list_knowledge_records()
        cards = [KnowledgeCard.model_validate(record) for record in records]
        return sorted(cards, key=lambda card: (card.type.value, card.name, card.id))

    async def get_card(self, knowledge_id: str) -> KnowledgeCard | None:
        """Return a knowledge card by id across all knowledge categories."""
        for card in await self.list_cards():
            if card.id == knowledge_id:
                return card
        return None

    async def write_active_card(
        self,
        card: KnowledgeCard,
    ) -> KnowledgeWriteResult:
        """Write an active KnowledgeCard, or reuse the existing same id."""
        if card.status is not KnowledgeCardStatus.ACTIVE:
            raise KnowledgeWriteError("只有有效知识可以写入知识库")
        _validate_active_knowledge_source(card)

        category = knowledge_category_for_type(card.type)
        existing_record = await self._storage.read_knowledge_record(
            category,
            card.id,
        )
        if existing_record is not None:
            existing = KnowledgeCard.model_validate(existing_record)
            return KnowledgeWriteResult(card=existing, created=False)

        await self._assert_no_identity_conflict(card)
        await self._storage.write_knowledge_record(
            category,
            card.id,
            card.model_dump(mode="json"),
        )
        return KnowledgeWriteResult(card=card, created=True)

    async def write_confirmed_card(
        self,
        card: KnowledgeCard,
    ) -> KnowledgeWriteResult:
        """Deprecated name kept for older application services."""
        return await self.write_active_card(card)

    async def _assert_no_identity_conflict(self, card: KnowledgeCard) -> None:
        new_terms = _identity_terms(card.name, card.aliases)
        if not new_terms:
            return
        for existing in await self.list_cards():
            if existing.id == card.id:
                continue
            if new_terms & _identity_terms(existing.name, existing.aliases):
                raise KnowledgeIdentityConflictError(
                    f"Knowledge identity conflicts with '{existing.id}'"
                )


class KnowledgeWriteError(ValueError):
    """Raised when a Knowledge write violates the source contract."""


class KnowledgeIdentityConflictError(KnowledgeWriteError):
    """Raised when a Knowledge name or alias conflicts with an existing card."""


class KnowledgeSourceError(KnowledgeWriteError):
    """Raised when active Knowledge lacks source origin or source note."""


def knowledge_category_for_type(card_type: KnowledgeCardType) -> str:
    """Return the source/knowledge category directory for a card type."""
    return _KNOWLEDGE_CATEGORY_BY_TYPE[card_type]


def _validate_active_knowledge_source(card: KnowledgeCard) -> None:
    if not card.name.strip() or not card.summary.strip():
        raise KnowledgeSourceError("有效知识必须包含名称和摘要")
    if card.source_origin is None or not card.source_note.strip():
        raise KnowledgeSourceError("有效知识必须包含来源方式和来源说明")


def _identity_terms(name: str, aliases: list[str]) -> set[str]:
    terms: set[str] = set()
    for value in [name, *aliases]:
        normalized = _normalize_identity(value)
        if normalized:
            terms.add(normalized)
    return terms


def _normalize_identity(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().casefold()
