"""AIResultCard persistence and lifecycle use cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models.ai_card import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
)
from taichu.domain.models.inbox import (
    IdeaCard,
    IdeaCardSource,
    IdeaCardStatus,
)
from taichu.domain.rules.card_state import assert_ai_card_transition_allowed

AI_CARDS_FILE = "ai_cards.jsonl"
IDEAS_FILE = "ideas.jsonl"


@dataclass(frozen=True)
class SaveIdeaResult:
    """Result of saving a suggestion card to the creative inbox."""

    card: AIResultCard
    idea: IdeaCard


class AICardService:
    """Application use cases for workspace AI result cards."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def create_card(self, card: AIResultCard) -> AIResultCard:
        """Persist a newly generated AIResultCard main record."""
        await self._storage.ensure_skeleton()
        await self._storage.append_workspace_record(
            AI_CARDS_FILE,
            card.model_dump(mode="json"),
        )
        return card

    async def list_cards(
        self,
        chapter_id: str | None = None,
    ) -> list[AIResultCard]:
        """List persisted AIResultCards, optionally filtered by chapter."""
        records = await self._storage.list_workspace_records(AI_CARDS_FILE)
        cards = [AIResultCard.model_validate(record) for record in records]
        if chapter_id is None:
            return cards
        return [card for card in cards if card.chapter_id == chapter_id]

    async def get_card(self, card_id: str) -> AIResultCard:
        """Return one persisted card by id."""
        for card in await self.list_cards():
            if card.id == card_id:
                return card
        raise AICardNotFoundError(card_id)

    async def mark_inserted(self, card_id: str) -> AIResultCard:
        """Mark a text candidate card as inserted into the manuscript."""
        card = await self.get_card(card_id)
        if card.type is not AIResultCardType.TEXT_CANDIDATE:
            raise InvalidCardActionError("Only text candidate cards can be inserted")
        return await self._transition_card(card, AIResultCardStatus.INSERTED)

    async def discard_card(self, card_id: str) -> AIResultCard:
        """Mark a generated card as discarded without writing fact assets."""
        card = await self.get_card(card_id)
        return await self._transition_card(card, AIResultCardStatus.DISCARDED)

    async def mark_retried(self, card_id: str) -> AIResultCard:
        """Mark a generated card as retried before creating a child card."""
        card = await self.get_card(card_id)
        return await self._transition_card(card, AIResultCardStatus.RETRIED)

    async def save_suggestion_as_idea(
        self,
        card_id: str,
    ) -> SaveIdeaResult:
        """Persist a suggestion card as a non-fact creative IdeaCard."""
        card = await self.get_card(card_id)
        if card.type is not AIResultCardType.SUGGESTION:
            raise InvalidCardActionError("Only suggestion cards can be saved as ideas")

        updated_card = await self._transition_card(
            card,
            AIResultCardStatus.SAVED_TO_INBOX,
        )
        now = _now_iso()
        idea = IdeaCard(
            id=f"idea_{uuid4().hex}",
            content=_idea_content(card.content),
            source=IdeaCardSource.AI,
            linked_chapter_id=card.chapter_id,
            status=IdeaCardStatus.OPEN,
            source_card_id=card.id,
            tags=[],
            created_at=now,
            updated_at=now,
        )
        await self._storage.append_workspace_record(
            IDEAS_FILE,
            idea.model_dump(mode="json"),
        )
        return SaveIdeaResult(card=updated_card, idea=idea)

    async def _transition_card(
        self,
        card: AIResultCard,
        target_status: AIResultCardStatus,
    ) -> AIResultCard:
        assert_ai_card_transition_allowed(card.status, target_status)
        updated = card.model_copy(
            update={
                "status": target_status,
                "updated_at": _now_iso(),
            }
        )
        await self._replace_card(updated)
        return updated

    async def _replace_card(self, updated: AIResultCard) -> None:
        records = await self._storage.list_workspace_records(AI_CARDS_FILE)
        rewritten: list[dict[str, object]] = []
        replaced = False
        for record in records:
            card = AIResultCard.model_validate(record)
            if card.id == updated.id:
                rewritten.append(updated.model_dump(mode="json"))
                replaced = True
            else:
                rewritten.append(card.model_dump(mode="json"))
        if not replaced:
            raise AICardNotFoundError(updated.id)
        await self._storage.rewrite_workspace_records(AI_CARDS_FILE, rewritten)


class AICardNotFoundError(LookupError):
    """Raised when an AIResultCard id is absent from the workspace record."""

    def __init__(self, card_id: str) -> None:
        super().__init__(f"AIResultCard '{card_id}' was not found")


class InvalidCardActionError(ValueError):
    """Raised when a card action is outside the product contract."""


def _idea_content(content: dict[str, Any] | str) -> str:
    if isinstance(content, str):
        return content
    for key in ("suggestion", "body", "text", "summary", "title"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
