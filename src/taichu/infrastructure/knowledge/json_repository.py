"""JSON-backed structured knowledge repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models.structured_knowledge import (
    FORBIDDEN_KNOWLEDGE_FIELD_KEYS,
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
    all_knowledge_card_field_keys,
    knowledge_type_field_keys,
    type_specific_field_keys,
)

_AGENT_FORBIDDEN_FIELDS = FORBIDDEN_KNOWLEDGE_FIELD_KEYS | {
    "current_goal",
    "secret",
    "known_secrets",
}


class JSONKnowledgeRepository:
    """Persist structured knowledge cards through project asset storage."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def list_active_cards(
        self,
        type: str | None = None,
    ) -> list[StructuredKnowledgeCard]:
        """List active cards, optionally filtered by type."""
        records = await self._storage.list_structured_knowledge_records(type)
        cards = [StructuredKnowledgeCard.model_validate(record) for record in records]
        active_cards = [
            card
            for card in cards
            if card.status is StructuredKnowledgeStatus.ACTIVE
        ]
        return sorted(active_cards, key=lambda card: (card.type.value, card.name))

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard | None:
        """Return one card across all structured knowledge types."""
        for knowledge_type in StructuredKnowledgeType:
            record = await self._storage.read_structured_knowledge_record(
                knowledge_type.value,
                card_id,
            )
            if record is not None:
                return StructuredKnowledgeCard.model_validate(record)
        return None

    async def create_active_card(
        self,
        card: StructuredKnowledgeCard,
    ) -> StructuredKnowledgeCard:
        """Write one author-confirmed active card."""
        _validate_active_agent_card(card)
        existing = await self.get_card(card.id)
        if existing is not None:
            raise KnowledgeRepositoryError(f"知识卡“{card.id}”已存在。")
        conflicts = await self.search_active_identity(
            card.type.value,
            card.name,
            card.aliases,
        )
        if conflicts:
            conflict_names = "、".join(card.name for card in conflicts)
            raise KnowledgeRepositoryError(
                f"知识卡名称或别名已存在：{conflict_names}"
            )
        await self._write(card)
        return card

    async def patch_active_card(
        self,
        card_id: str,
        updates: dict[str, Any],
    ) -> StructuredKnowledgeCard:
        """Patch an active card without overwriting existing non-empty fields."""
        current = await self.get_card(card_id)
        if current is None:
            raise KnowledgeRepositoryNotFoundError(f"知识卡“{card_id}”不存在。")
        if current.status is not StructuredKnowledgeStatus.ACTIVE:
            raise KnowledgeRepositoryError("只能更新有效知识卡。")
        _reject_forbidden_fields(updates)
        allowed_keys = knowledge_type_field_keys(current.type)
        unknown_keys = set(updates) - allowed_keys
        if unknown_keys:
            raise KnowledgeRepositoryError(
                f"知识卡字段不支持：{', '.join(sorted(unknown_keys))}"
            )

        payload = current.model_dump(mode="json")
        for key, value in updates.items():
            if key == "source_note":
                payload[key] = _append_source_note(
                    str(payload.get(key) or ""),
                    str(value or ""),
                )
                continue
            if key == "last_seen_chapter_id":
                payload[key] = value
                continue
            existing_value = payload.get(key)
            if _is_empty_value(existing_value) or existing_value == value:
                payload[key] = value
                continue
            raise KnowledgeRepositoryError(f"不能覆盖已有非空字段：{key}")

        payload["updated_at"] = _now_iso()
        patched = StructuredKnowledgeCard.model_validate(payload)
        _validate_active_agent_card(patched)
        await self._write(patched)
        return patched

    async def search_active_identity(
        self,
        type: str,
        name: str,
        aliases: list[str],
    ) -> list[StructuredKnowledgeCard]:
        """Search active cards by names, aliases and clear textual mentions."""
        knowledge_type = StructuredKnowledgeType(type)
        query_terms = _identity_terms(name, aliases)
        if not query_terms:
            return []
        matches: list[StructuredKnowledgeCard] = []
        for card in await self.list_active_cards(knowledge_type.value):
            card_terms = _identity_terms(card.name, card.aliases)
            if query_terms & card_terms:
                matches.append(card)
                continue
            searchable_text = _normalize_identity(
                f"{card.summary} {card.source_note}"
            )
            if any(term and term in searchable_text for term in query_terms):
                matches.append(card)
        return matches

    async def _write(self, card: StructuredKnowledgeCard) -> None:
        await self._storage.write_structured_knowledge_record(
            card.type.value,
            card.id,
            _storage_record(card),
        )


class KnowledgeRepositoryError(ValueError):
    """Raised when an Agent knowledge write is invalid."""


class KnowledgeRepositoryNotFoundError(KnowledgeRepositoryError):
    """Raised when a target knowledge card does not exist."""


def _validate_active_agent_card(card: StructuredKnowledgeCard) -> None:
    if card.status is not StructuredKnowledgeStatus.ACTIVE:
        raise KnowledgeRepositoryError("候选确认后只能写入有效知识卡。")
    if card.source_origin is not StructuredKnowledgeSourceOrigin.AGENT_EXTRACT:
        raise KnowledgeRepositoryError("正文知识沉淀候选来源必须是正文自动提取。")
    if not card.name.strip() or not card.summary.strip():
        raise KnowledgeRepositoryError("有效知识卡必须包含名称和摘要。")
    if not card.source_note.strip():
        raise KnowledgeRepositoryError("有效知识卡必须包含来源说明。")


def _reject_forbidden_fields(payload: dict[str, Any]) -> None:
    forbidden = _AGENT_FORBIDDEN_FIELDS & set(payload)
    if forbidden:
        raise KnowledgeRepositoryError(
            f"正文知识沉淀不支持字段：{', '.join(sorted(forbidden))}"
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
    return {
        key: value
        for key, value in record.items()
        if key in all_knowledge_card_field_keys()
    }


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
    return "".join(value.split()).casefold()


def _is_empty_value(value: object) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, list) and not value:
        return True
    return False


def _append_source_note(current: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return current
    if not current.strip():
        return addition
    if addition in current:
        return current
    return f"{current.rstrip()}\n\n{addition}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
