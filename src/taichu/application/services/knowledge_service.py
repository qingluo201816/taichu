"""Structured knowledge use cases backed by one repository contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from taichu.application.contracts.knowledge_repository import (
    KnowledgeCardPage,
    KnowledgeCardQuery,
    KnowledgeRepositoryConcurrentUpdateError,
    KnowledgeRepositoryConflictError,
    KnowledgeRepositoryError,
    KnowledgeRepositoryNotFoundError,
    KnowledgeRepositoryUnavailableError,
    StructuredKnowledgeRepository,
)
from taichu.domain.models import (
    KnowledgeTypeSchema,
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
    all_knowledge_type_schemas,
    knowledge_type_field_keys,
    knowledge_type_schema,
    type_specific_field_keys,
)
from taichu.domain.models.structured_knowledge import (
    FORBIDDEN_KNOWLEDGE_FIELD_KEYS,
)

AuthorMergeMode = Literal["append", "overwrite"]

_SYSTEM_FIELDS = frozenset(
    {"id", "type", "lifecycle", "created_at", "updated_at", "identity_keys"}
)
_AUTHOR_READONLY_FIELDS = frozenset({"appearance_chapter_count"})
_AGENT_FORBIDDEN_FIELDS = FORBIDDEN_KNOWLEDGE_FIELD_KEYS | {
    "current_goal",
    "secret",
    "known_secrets",
}


class KnowledgeService:
    """Own all structured-knowledge validation and lifecycle transitions."""

    def __init__(self, repository: StructuredKnowledgeRepository) -> None:
        self._repository = repository

    def list_types(self) -> list[StructuredKnowledgeType]:
        """Return all supported structured knowledge types."""
        return list(StructuredKnowledgeType)

    def list_schemas(self) -> list[KnowledgeTypeSchema]:
        """Return backend schema definitions for all knowledge types."""
        return all_knowledge_type_schemas()

    def get_schema(
        self, knowledge_type: StructuredKnowledgeType
    ) -> KnowledgeTypeSchema:
        """Return one backend knowledge schema."""
        return knowledge_type_schema(knowledge_type)

    async def list_cards(
        self,
        knowledge_type: StructuredKnowledgeType,
        *,
        lifecycle: str = "all",
        q: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> KnowledgeCardPage:
        """Return one page; rejected records require an explicit filter."""
        lifecycles = _lifecycles_for_filter(lifecycle)
        query = KnowledgeCardQuery(
            type=knowledge_type,
            lifecycles=lifecycles,
            q=q.strip() if q and q.strip() else None,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        try:
            return await self._repository.list_cards(query)
        except KnowledgeRepositoryUnavailableError as error:
            raise KnowledgeUnavailableError(str(error)) from error

    async def list_confirmed_cards(
        self,
        knowledge_type: StructuredKnowledgeType | None = None,
    ) -> list[StructuredKnowledgeCard]:
        """Return only author-confirmed facts for downstream context."""
        try:
            return await self._repository.list_confirmed_cards(knowledge_type)
        except KnowledgeRepositoryUnavailableError as error:
            raise KnowledgeUnavailableError(str(error)) from error

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard:
        """Return one card or a Chinese not-found error."""
        try:
            card = await self._repository.get_card(card_id)
        except KnowledgeRepositoryUnavailableError as error:
            raise KnowledgeUnavailableError(str(error)) from error
        if card is None:
            raise KnowledgeCardNotFoundError(card_id)
        return card

    async def create_card(
        self,
        knowledge_type: StructuredKnowledgeType,
        data: dict[str, Any] | None = None,
    ) -> StructuredKnowledgeCard:
        """Create an author-editable draft; public creation cannot confirm it."""
        now = _now_iso()
        payload = dict(data or {})
        _reject_system_fields(payload)
        _reject_author_readonly_fields(payload)
        card = _card_from_payload(
            knowledge_type,
            payload,
            lifecycle=StructuredKnowledgeLifecycle.DRAFT,
            now=now,
            card_id=f"{knowledge_type.value}-{uuid4().hex}",
            created_at=now,
        )
        return await self._create(card)

    async def create_confirmed_from_data(
        self,
        knowledge_type: StructuredKnowledgeType,
        data: dict[str, Any],
    ) -> StructuredKnowledgeCard:
        """Create a confirmed fact after an explicit author action."""
        now = _now_iso()
        payload = dict(data)
        supplied_id = str(payload.pop("id", "")).strip()
        for key in ("type", "lifecycle", "created_at", "updated_at"):
            payload.pop(key, None)
        card = _card_from_payload(
            knowledge_type,
            payload,
            lifecycle=StructuredKnowledgeLifecycle.CONFIRMED,
            now=now,
            card_id=supplied_id or f"{knowledge_type.value}-{uuid4().hex}",
            created_at=now,
        )
        return await self.create_confirmed_card(card)

    async def create_confirmed_card(
        self,
        card: StructuredKnowledgeCard,
    ) -> StructuredKnowledgeCard:
        """Persist one already-reviewed confirmed knowledge card."""
        if card.lifecycle is not StructuredKnowledgeLifecycle.CONFIRMED:
            raise KnowledgeCardValidationError("作者确认后只能写入已确认知识卡。")
        _validate_confirmed_card(card)
        await self._assert_no_identity_conflict(card)
        return await self._create(card)

    async def patch_card(
        self,
        card_id: str,
        updates: dict[str, Any],
    ) -> StructuredKnowledgeCard:
        """Patch editable fields without allowing lifecycle or system changes."""
        current = await self.get_card(card_id)
        if current.lifecycle is StructuredKnowledgeLifecycle.REJECTED:
            raise KnowledgeCardValidationError("已废弃知识卡不能继续编辑。")
        _reject_system_fields(updates)
        _reject_author_readonly_fields(updates)
        _reject_forbidden_fields(updates)
        allowed_keys = knowledge_type_field_keys(current.type) - {"lifecycle"}
        unknown_keys = set(updates) - allowed_keys
        if unknown_keys:
            raise KnowledgeCardValidationError(
                f"知识卡字段不支持：{', '.join(sorted(unknown_keys))}"
            )
        payload = current.model_dump(mode="json")
        payload.update(updates)
        payload["updated_at"] = _now_iso()
        card = StructuredKnowledgeCard.model_validate(payload)
        if card.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED:
            _validate_confirmed_card(card)
            await self._assert_no_identity_conflict(card, exclude_id=card.id)
        return await self._update(card, expected_updated_at=current.updated_at)

    async def confirm_card(self, card_id: str) -> StructuredKnowledgeCard:
        """Promote one complete draft into the confirmed fact set."""
        current = await self.get_card(card_id)
        if current.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED:
            return current
        if current.lifecycle is StructuredKnowledgeLifecycle.REJECTED:
            raise KnowledgeCardValidationError("已废弃知识卡不能直接恢复为有效。")
        confirmed = current.model_copy(
            update={
                "lifecycle": StructuredKnowledgeLifecycle.CONFIRMED,
                "updated_at": _now_iso(),
            }
        )
        _validate_confirmed_card(confirmed)
        await self._assert_no_identity_conflict(confirmed, exclude_id=confirmed.id)
        return await self._update(
            confirmed,
            expected_updated_at=current.updated_at,
        )

    async def reject_card(self, card_id: str) -> StructuredKnowledgeCard:
        """Soft-delete one card by moving it to rejected lifecycle."""
        current = await self.get_card(card_id)
        if current.lifecycle is StructuredKnowledgeLifecycle.REJECTED:
            return current
        rejected = current.model_copy(
            update={
                "lifecycle": StructuredKnowledgeLifecycle.REJECTED,
                "updated_at": _now_iso(),
            }
        )
        return await self._update(rejected, expected_updated_at=current.updated_at)

    async def search_confirmed_identity(
        self,
        knowledge_type: StructuredKnowledgeType,
        name: str,
        aliases: list[str],
    ) -> list[StructuredKnowledgeCard]:
        """Find confirmed cards with the same normalized identity."""
        try:
            return await self._repository.search_confirmed_identity(
                knowledge_type,
                name,
                aliases,
            )
        except KnowledgeRepositoryUnavailableError as error:
            raise KnowledgeUnavailableError(str(error)) from error

    async def apply_author_confirmed_updates(
        self,
        card_id: str,
        updates: dict[str, Any],
        *,
        merge_mode: AuthorMergeMode = "append",
        allow_appearance_count_update: bool = False,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        """Apply explicit author edits to a confirmed card."""
        if merge_mode not in {"append", "overwrite"}:
            raise KnowledgeCardValidationError("编辑后确认方式不支持。")
        current = await self.get_card(card_id)
        if current.lifecycle is not StructuredKnowledgeLifecycle.CONFIRMED:
            raise KnowledgeCardValidationError("只能更新已确认知识卡。")
        if (
            expected_updated_at is not None
            and current.updated_at != expected_updated_at
        ):
            raise KnowledgeConcurrentUpdateError(
                "知识卡已被其他操作更新，请刷新后重新确认。"
            )
        _reject_system_fields(updates)
        if not allow_appearance_count_update:
            _reject_author_readonly_fields(updates)
        _reject_forbidden_fields(updates, agent=True)
        allowed_keys = knowledge_type_field_keys(current.type) - {"lifecycle"}
        unknown_keys = set(updates) - allowed_keys
        if unknown_keys:
            raise KnowledgeCardValidationError(
                f"知识卡字段不支持：{', '.join(sorted(unknown_keys))}"
            )
        payload = current.model_dump(mode="json")
        for key, value in updates.items():
            payload[key] = (
                value
                if merge_mode == "overwrite" and key != "appearance_chapter_count"
                else _merge_author_value(key, payload.get(key), value)
            )
        payload["updated_at"] = _now_iso()
        card = StructuredKnowledgeCard.model_validate(payload)
        _validate_confirmed_card(card)
        await self._assert_no_identity_conflict(card, exclude_id=card.id)
        return await self._update(card, expected_updated_at=current.updated_at)

    async def _assert_no_identity_conflict(
        self,
        card: StructuredKnowledgeCard,
        *,
        exclude_id: str | None = None,
    ) -> None:
        matches = await self.search_confirmed_identity(
            card.type,
            card.name,
            card.aliases,
        )
        conflicts = [match for match in matches if match.id != exclude_id]
        if conflicts:
            summary = "、".join(
                f"{match.name}（{match.summary[:40]}）" for match in conflicts
            )
            raise KnowledgeIdentityConflictError(f"知识卡名称或别名已存在：{summary}")

    async def _create(self, card: StructuredKnowledgeCard) -> StructuredKnowledgeCard:
        try:
            return await self._repository.create_card(card)
        except KnowledgeRepositoryConflictError as error:
            raise KnowledgeIdentityConflictError(str(error)) from error
        except KnowledgeRepositoryUnavailableError as error:
            raise KnowledgeUnavailableError(str(error)) from error
        except KnowledgeRepositoryError as error:
            raise KnowledgeCardValidationError(str(error)) from error

    async def _update(
        self,
        card: StructuredKnowledgeCard,
        *,
        expected_updated_at: str,
    ) -> StructuredKnowledgeCard:
        try:
            return await self._repository.update_card(
                card,
                expected_updated_at=expected_updated_at,
            )
        except KnowledgeRepositoryNotFoundError as error:
            raise KnowledgeCardNotFoundError(card.id) from error
        except KnowledgeRepositoryConcurrentUpdateError as error:
            raise KnowledgeConcurrentUpdateError(
                "知识卡已被其他操作更新，请刷新后重试。"
            ) from error
        except KnowledgeRepositoryConflictError as error:
            raise KnowledgeIdentityConflictError(str(error)) from error
        except KnowledgeRepositoryUnavailableError as error:
            raise KnowledgeUnavailableError(str(error)) from error
        except KnowledgeRepositoryError as error:
            raise KnowledgeCardValidationError(str(error)) from error


class KnowledgeCardNotFoundError(LookupError):
    """Raised when a knowledge card is absent."""

    def __init__(self, card_id: str) -> None:
        super().__init__(f"知识卡“{card_id}”不存在")


class KnowledgeCardValidationError(ValueError):
    """Raised when a knowledge card violates application rules."""


class KnowledgeIdentityConflictError(KnowledgeCardValidationError):
    """Raised when a confirmed identity already exists."""


class KnowledgeConcurrentUpdateError(KnowledgeCardValidationError):
    """Raised when a compare-and-set update loses a race."""


class KnowledgeUnavailableError(RuntimeError):
    """Raised when MongoDB cannot serve a knowledge request."""


def _lifecycles_for_filter(value: str) -> frozenset[StructuredKnowledgeLifecycle]:
    if value == "all":
        return frozenset(
            {
                StructuredKnowledgeLifecycle.DRAFT,
                StructuredKnowledgeLifecycle.CONFIRMED,
            }
        )
    try:
        return frozenset({StructuredKnowledgeLifecycle(value)})
    except ValueError as error:
        raise KnowledgeCardValidationError("未知的知识卡生命周期") from error


def _validate_confirmed_card(card: StructuredKnowledgeCard) -> None:
    if (
        not card.name.strip()
        or not card.summary.strip()
        or card.source_origin is None
        or not card.source_note.strip()
    ):
        raise KnowledgeCardValidationError(
            "名称、摘要、来源方式和来源说明补齐后，才能确认入库。"
        )


def _card_from_payload(
    knowledge_type: StructuredKnowledgeType,
    payload: dict[str, Any],
    *,
    lifecycle: StructuredKnowledgeLifecycle,
    now: str,
    card_id: str,
    created_at: str,
) -> StructuredKnowledgeCard:
    _reject_forbidden_fields(payload)
    allowed_keys = knowledge_type_field_keys(knowledge_type) - {"lifecycle"}
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
        "appearance_chapter_count": payload.get("appearance_chapter_count"),
        "lifecycle": lifecycle.value,
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


def _reject_system_fields(payload: dict[str, Any]) -> None:
    forbidden = _SYSTEM_FIELDS & set(payload)
    if forbidden:
        raise KnowledgeCardValidationError(
            f"知识卡系统字段不能直接修改：{', '.join(sorted(forbidden))}"
        )


def _reject_author_readonly_fields(payload: dict[str, Any]) -> None:
    readonly = _AUTHOR_READONLY_FIELDS & set(payload)
    if readonly:
        raise KnowledgeCardValidationError(
            f"知识卡统计字段由正文知识沉淀维护：{', '.join(sorted(readonly))}"
        )


def _reject_forbidden_fields(
    payload: dict[str, Any],
    *,
    agent: bool = False,
) -> None:
    forbidden_keys = (
        _AGENT_FORBIDDEN_FIELDS if agent else FORBIDDEN_KNOWLEDGE_FIELD_KEYS
    )
    forbidden = forbidden_keys & set(payload)
    if forbidden:
        raise KnowledgeCardValidationError(
            f"知识卡第一版不支持字段：{', '.join(sorted(forbidden))}"
        )


def _merge_author_value(key: str, current: object, incoming: object) -> object:
    if key in {"summary", "source_note"}:
        return _append_text(str(current or ""), str(incoming or ""))
    if key == "aliases":
        return _merge_aliases(current, incoming)
    if key == "last_seen_chapter_id":
        return incoming
    if key == "appearance_chapter_count":
        current_count = current if isinstance(current, int) else 0
        incoming_count = incoming if isinstance(incoming, int) else 0
        return current_count + incoming_count
    if _is_empty_value(current) or current == incoming:
        return incoming
    return current


def _merge_aliases(current: object, incoming: object) -> list[str]:
    merged: list[str] = []
    for value in [*_as_string_list(current), *_as_string_list(incoming)]:
        if value not in merged:
            merged.append(value)
    return merged


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _append_text(current: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return current
    if not current.strip():
        return addition
    if addition in current:
        return current
    return f"{current.rstrip()}\n\n{addition}"


def _is_empty_value(value: object) -> bool:
    return value is None or value == "" or (isinstance(value, list) and not value)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
