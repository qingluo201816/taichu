"""MVP structured knowledge use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models import (
    KnowledgeTypeSchema,
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
    all_knowledge_type_schemas,
    knowledge_type_field_keys,
    knowledge_type_schema,
    type_specific_field_keys,
)
from taichu.domain.models.structured_knowledge import FORBIDDEN_KNOWLEDGE_FIELD_KEYS


class MVPKnowledgeService:
    """Manage structured knowledge cards for the MVP."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    def list_types(self) -> list[StructuredKnowledgeType]:
        """Return all supported structured knowledge types."""
        return list(StructuredKnowledgeType)

    def list_schemas(self) -> list[KnowledgeTypeSchema]:
        """Return backend schema definitions for all supported card types."""
        return all_knowledge_type_schemas()

    def get_schema(self, knowledge_type: StructuredKnowledgeType) -> KnowledgeTypeSchema:
        """Return the backend schema definition for one card type."""
        return knowledge_type_schema(knowledge_type)

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
        card = _card_from_payload(
            knowledge_type,
            payload,
            now=now,
            card_id=str(payload.get("id") or f"{knowledge_type.value}-{uuid4().hex}"),
            created_at=str(payload.get("created_at") or now),
        )
        if card.status is StructuredKnowledgeStatus.ACTIVE:
            _validate_active_card(card)
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
        _reject_forbidden_fields(updates)
        allowed_keys = knowledge_type_field_keys(current.type)
        unknown_keys = set(updates) - allowed_keys
        if unknown_keys:
            raise KnowledgeCardValidationError(
                f"知识卡字段不支持：{', '.join(sorted(unknown_keys))}"
            )
        payload.update(updates)
        payload["updated_at"] = _now_iso()
        card = StructuredKnowledgeCard.model_validate(payload)
        if card.status is StructuredKnowledgeStatus.ACTIVE:
            _validate_active_card(card)
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
            _storage_record(card),
        )


class KnowledgeCardNotFoundError(LookupError):
    """Raised when a structured knowledge card does not exist."""

    def __init__(self, card_id: str) -> None:
        super().__init__(f"知识卡“{card_id}”不存在")


class KnowledgeCardValidationError(ValueError):
    """Raised when a knowledge card cannot enter the requested state."""


def _validate_active_card(card: StructuredKnowledgeCard) -> None:
    if (
        not card.name.strip()
        or not card.summary.strip()
        or card.source_origin is None
        or not card.source_note.strip()
    ):
        raise KnowledgeCardValidationError(
            "名称、摘要、来源方式和来源说明补齐后，才能标记为有效。"
        )


def _searchable_text(card: StructuredKnowledgeCard) -> str:
    data = _storage_record(card)
    value = " ".join(str(value) for value in data.values() if value is not None)
    return value.casefold()


def _card_from_payload(
    knowledge_type: StructuredKnowledgeType,
    payload: dict[str, Any],
    *,
    now: str,
    card_id: str,
    created_at: str,
) -> StructuredKnowledgeCard:
    _reject_forbidden_fields(payload)
    allowed_keys = knowledge_type_field_keys(knowledge_type) | {
        "id",
        "type",
        "created_at",
        "updated_at",
    }
    unknown_keys = set(payload) - allowed_keys
    if unknown_keys:
        raise KnowledgeCardValidationError(
            f"知识卡字段不支持：{', '.join(sorted(unknown_keys))}"
        )
    base_payload: dict[str, Any] = {
        "id": card_id,
        "type": knowledge_type.value,
        "name": payload.get("name", ""),
        "aliases": payload.get("aliases", []),
        "summary": payload.get("summary", ""),
        "importance": payload.get("importance", "normal"),
        "status": payload.get("status", "draft"),
        "source_origin": payload.get("source_origin"),
        "source_note": payload.get("source_note", ""),
        "created_at": created_at,
        "updated_at": now,
    }
    for field_key in type_specific_field_keys(knowledge_type):
        if field_key in payload:
            base_payload[field_key] = payload[field_key]
    if base_payload["source_origin"] == "":
        base_payload["source_origin"] = None
    if base_payload["source_origin"] is not None:
        base_payload["source_origin"] = StructuredKnowledgeSourceOrigin(
            base_payload["source_origin"]
        )
    return StructuredKnowledgeCard.model_validate(base_payload)


def _reject_forbidden_fields(payload: dict[str, Any]) -> None:
    forbidden = FORBIDDEN_KNOWLEDGE_FIELD_KEYS & set(payload)
    if forbidden:
        raise KnowledgeCardValidationError(
            f"知识卡第一版不支持字段：{', '.join(sorted(forbidden))}"
        )


def _storage_record(card: StructuredKnowledgeCard) -> dict[str, object]:
    full_record = card.model_dump(mode="json", exclude_none=False)
    record = card.model_dump(mode="json", exclude_none=True)
    for key in (
        "id",
        "type",
        "name",
        "aliases",
        "summary",
        "importance",
        "status",
        "source_origin",
        "source_note",
        "created_at",
        "updated_at",
    ):
        record[key] = full_record[key]
    for field_key in type_specific_field_keys(card.type):
        value = getattr(card, field_key)
        if value is not None:
            record[field_key] = value
    return record


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
