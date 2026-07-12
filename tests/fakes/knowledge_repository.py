"""In-memory implementation of the structured knowledge repository contract."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from taichu.application.contracts.knowledge_repository import (
    KnowledgeCardPage,
    KnowledgeCardQuery,
    KnowledgeRepositoryConcurrentUpdateError,
    KnowledgeRepositoryConflictError,
    KnowledgeRepositoryNotFoundError,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
)


class InMemoryKnowledgeRepository:
    """Store knowledge cards in memory while matching repository semantics."""

    def __init__(self, cards: list[StructuredKnowledgeCard] | None = None) -> None:
        self._cards = {card.id: card for card in cards or []}

    async def list_cards(self, query: KnowledgeCardQuery) -> KnowledgeCardPage:
        cards = [
            card
            for card in self._cards.values()
            if card.lifecycle in query.lifecycles
            and (query.type is None or card.type is query.type)
            and _matches_text(card, query.q)
        ]
        cards.sort(key=lambda card: card.id)
        cards.sort(key=lambda card: card.updated_at, reverse=True)
        return KnowledgeCardPage(
            cards=cards[query.offset : query.offset + query.limit],
            total=len(cards),
            offset=query.offset,
            limit=query.limit,
        )

    async def list_confirmed_cards(
        self,
        type: StructuredKnowledgeType | None = None,
    ) -> list[StructuredKnowledgeCard]:
        cards = [
            card
            for card in self._cards.values()
            if card.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED
            and (type is None or card.type is type)
        ]
        cards.sort(key=lambda card: card.id)
        cards.sort(key=lambda card: card.updated_at, reverse=True)
        return cards

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard | None:
        return self._cards.get(card_id)

    async def create_card(
        self,
        card: StructuredKnowledgeCard,
    ) -> StructuredKnowledgeCard:
        if card.id in self._cards:
            raise KnowledgeRepositoryConflictError(f"知识卡“{card.id}”已存在。")
        self._cards[card.id] = card
        return card

    async def update_card(
        self,
        card: StructuredKnowledgeCard,
        *,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        current = self._require_card(card.id)
        _ensure_current(current, expected_updated_at)
        self._cards[card.id] = card
        return card

    async def set_lifecycle(
        self,
        card_id: str,
        lifecycle: StructuredKnowledgeLifecycle,
        *,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        current = self._require_card(card_id)
        _ensure_current(current, expected_updated_at)
        updated = current.model_copy(
            update={
                "lifecycle": lifecycle,
                "updated_at": _now_iso(),
            }
        )
        self._cards[card_id] = updated
        return updated

    async def search_confirmed_identity(
        self,
        type: StructuredKnowledgeType,
        name: str,
        aliases: list[str],
    ) -> list[StructuredKnowledgeCard]:
        requested = _identity_keys(name, aliases)
        return sorted(
            (
                card
                for card in self._cards.values()
                if card.type is type
                and card.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED
                and requested.intersection(_identity_keys(card.name, card.aliases))
            ),
            key=lambda card: card.id,
        )

    def _require_card(self, card_id: str) -> StructuredKnowledgeCard:
        card = self._cards.get(card_id)
        if card is None:
            raise KnowledgeRepositoryNotFoundError(f"知识卡“{card_id}”不存在。")
        return card


def _matches_text(card: StructuredKnowledgeCard, query: str | None) -> bool:
    if query is None:
        return True
    needle = query.strip().casefold()
    if not needle:
        return True
    return any(
        needle in value.casefold()
        for value in (card.name, card.summary, *card.aliases)
    )


def _identity_keys(name: str, aliases: list[str]) -> set[str]:
    return {
        normalized
        for value in (name, *aliases)
        if (normalized := re.sub(r"\s+", "", value).casefold())
    }


def _ensure_current(
    current: StructuredKnowledgeCard,
    expected_updated_at: str | None,
) -> None:
    if expected_updated_at is not None and current.updated_at != expected_updated_at:
        raise KnowledgeRepositoryConcurrentUpdateError(
            f"知识卡“{current.id}”已被其他操作更新。"
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
