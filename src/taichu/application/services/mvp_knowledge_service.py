"""MVP structured knowledge use cases."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models import (
    SourceReference,
    StructuredKnowledgeCard,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
)


class MVPKnowledgeService:
    """Manage structured knowledge cards for the MVP."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    def list_types(self) -> list[StructuredKnowledgeType]:
        """Return all supported structured knowledge types."""
        return list(StructuredKnowledgeType)

    async def list_cards(
        self,
        knowledge_type: StructuredKnowledgeType,
        status: str = "all",
        q: str | None = None,
    ) -> list[StructuredKnowledgeCard]:
        """List cards inside one selected knowledge type."""
        records = await self._storage.list_structured_knowledge_records(
            knowledge_type.value
        )
        cards = [StructuredKnowledgeCard.model_validate(record) for record in records]
        if status == "deprecated":
            cards = [
                card
                for card in cards
                if card.status is StructuredKnowledgeStatus.DEPRECATED
            ]
        else:
            cards = [
                card
                for card in cards
                if card.status is not StructuredKnowledgeStatus.DEPRECATED
            ]
            if status != "all":
                expected = StructuredKnowledgeStatus(status)
                cards = [card for card in cards if card.status is expected]
        if q and q.strip():
            query = q.strip().casefold()
            cards = [card for card in cards if query in _searchable_text(card)]
        return sorted(cards, key=lambda card: card.updated_at, reverse=True)

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard:
        """Return one structured knowledge card across all types."""
        for knowledge_type in StructuredKnowledgeType:
            record = await self._storage.read_structured_knowledge_record(
                knowledge_type.value,
                card_id,
            )
            if record is not None:
                return StructuredKnowledgeCard.model_validate(record)
        raise KnowledgeCardNotFoundError(card_id)

    async def create_card(
        self,
        knowledge_type: StructuredKnowledgeType,
        data: dict[str, Any] | None = None,
    ) -> StructuredKnowledgeCard:
        """Create one draft knowledge card."""
        now = _now_iso()
        payload = dict(data or {})
        card = StructuredKnowledgeCard.model_validate(
            {
                "id": payload.get("id") or f"{knowledge_type.value}-{uuid4().hex}",
                "type": knowledge_type.value,
                "name": payload.get("name", ""),
                "aliases": payload.get("aliases", []),
                "summary": payload.get("summary", ""),
                "body": payload.get("body", ""),
                "tags": payload.get("tags", []),
                "importance": payload.get("importance", "normal"),
                "status": payload.get("status", "draft"),
                "source_refs": payload.get("source_refs", []),
                "fields": payload.get("fields", {}),
                "created_at": payload.get("created_at", now),
                "updated_at": now,
            }
        )
        await self._write(card)
        return card

    async def patch_card(
        self,
        card_id: str,
        updates: dict[str, Any],
    ) -> StructuredKnowledgeCard:
        """Patch author-editable fields on one card."""
        current = await self.get_card(card_id)
        payload = current.model_dump(mode="json")
        for key in (
            "name",
            "aliases",
            "summary",
            "body",
            "tags",
            "importance",
            "source_refs",
            "fields",
        ):
            if key in updates:
                payload[key] = updates[key]
        payload["updated_at"] = _now_iso()
        card = StructuredKnowledgeCard.model_validate(payload)
        await self._write(card)
        return card

    async def mark_active(self, card_id: str) -> StructuredKnowledgeCard:
        """Mark a complete draft as active knowledge."""
        card = await self.get_card(card_id)
        _validate_active_card(card)
        active = card.model_copy(
            update={
                "status": StructuredKnowledgeStatus.ACTIVE,
                "updated_at": _now_iso(),
            }
        )
        await self._write(active)
        return active

    async def mark_deprecated(self, card_id: str) -> StructuredKnowledgeCard:
        """Mark a knowledge card as deprecated without physical deletion."""
        card = await self.get_card(card_id)
        deprecated = card.model_copy(
            update={
                "status": StructuredKnowledgeStatus.DEPRECATED,
                "updated_at": _now_iso(),
            }
        )
        await self._write(deprecated)
        return deprecated

    async def _write(self, card: StructuredKnowledgeCard) -> None:
        await self._storage.write_structured_knowledge_record(
            card.type.value,
            card.id,
            card.model_dump(mode="json"),
        )


class KnowledgeCardNotFoundError(LookupError):
    """Raised when a structured knowledge card does not exist."""

    def __init__(self, card_id: str) -> None:
        super().__init__(f"知识卡“{card_id}”不存在")


class KnowledgeCardValidationError(ValueError):
    """Raised when a knowledge card cannot enter the requested state."""


def _validate_active_card(card: StructuredKnowledgeCard) -> None:
    if not card.name.strip() or not card.summary.strip() or not card.source_refs:
        raise KnowledgeCardValidationError("名称、摘要和来源引用补齐后，才能标记为有效。")
    for source_ref in card.source_refs:
        SourceReference.model_validate(source_ref.model_dump(mode="json"))


def _searchable_text(card: StructuredKnowledgeCard) -> str:
    value = " ".join(
        [
            card.name,
            " ".join(card.aliases),
            card.summary,
            card.body,
            json.dumps(card.fields, ensure_ascii=False, sort_keys=True),
        ]
    )
    return value.casefold()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
