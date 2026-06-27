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
from taichu.domain.models.source_ref import SourceRef
from taichu.domain.rules.source_ref import validate_source_ref_contract


_KNOWLEDGE_CATEGORY_BY_TYPE: dict[KnowledgeCardType, str] = {
    KnowledgeCardType.CHARACTER: "characters",
    KnowledgeCardType.REALM: "worldbuilding",
    KnowledgeCardType.TECHNIQUE: "techniques",
    KnowledgeCardType.LOCATION: "locations",
    KnowledgeCardType.FACTION: "factions",
    KnowledgeCardType.ITEM: "items",
    KnowledgeCardType.RULE: "worldbuilding",
    KnowledgeCardType.EVENT: "events",
    KnowledgeCardType.FORESHADOW: "foreshadows",
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
        """List all confirmed knowledge records from source/knowledge."""
        cards = await self.list_all_cards()
        return [card for card in cards if card.status is KnowledgeCardStatus.CONFIRMED]

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

    async def write_confirmed_card(
        self,
        card: KnowledgeCard,
    ) -> KnowledgeWriteResult:
        """Write a confirmed KnowledgeCard, or reuse the existing same id."""
        if card.status is not KnowledgeCardStatus.CONFIRMED:
            raise KnowledgeWriteError("Only confirmed KnowledgeCard can be written")
        _validate_knowledge_source_refs(card.source_refs)

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


class KnowledgeSourceRefError(KnowledgeWriteError):
    """Raised when confirmed Knowledge lacks valid SourceRef evidence."""


def knowledge_category_for_type(card_type: KnowledgeCardType) -> str:
    """Return the source/knowledge category directory for a card type."""
    return _KNOWLEDGE_CATEGORY_BY_TYPE[card_type]


def _validate_knowledge_source_refs(source_refs: list[SourceRef]) -> None:
    if not source_refs:
        raise KnowledgeSourceRefError("Confirmed Knowledge requires SourceRef evidence")
    for source_ref in source_refs:
        validate_source_ref_contract(source_ref)


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
