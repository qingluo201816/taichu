"""PendingFact confirmation workflow for author-approved Knowledge."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.services.ai_card_service import PENDING_FACTS_FILE
from taichu.application.services.knowledge_service import (
    KnowledgeService,
)
from taichu.domain.models.knowledge import (
    KnowledgeCard,
    KnowledgeCardStatus,
    KnowledgeCardType,
)
from taichu.domain.models.pending_fact import PendingFact, PendingFactStatus
from taichu.domain.rules.card_state import assert_pending_fact_transition_allowed


_SAFE_ID_PART = re.compile(r"[^a-z0-9_-]+")

_KNOWLEDGE_TYPE_BY_PENDING_TYPE: dict[str, KnowledgeCardType] = {
    "character": KnowledgeCardType.CHARACTER,
    "realm": KnowledgeCardType.REALM,
    "technique": KnowledgeCardType.TECHNIQUE,
    "location": KnowledgeCardType.LOCATION,
    "faction": KnowledgeCardType.FACTION,
    "item": KnowledgeCardType.ITEM,
    "rule": KnowledgeCardType.RULE,
    "event": KnowledgeCardType.EVENT,
    "foreshadow": KnowledgeCardType.FORESHADOW,
}


@dataclass(frozen=True)
class PendingFactConfirmationEdits:
    """Author edits applied at confirmation time."""

    name: str | None = None
    summary: str | None = None
    aliases: list[str] | None = None
    fields: dict[str, Any] | None = None


@dataclass(frozen=True)
class PendingFactConfirmationResult:
    """Result of confirming a PendingFact into Knowledge."""

    pending_fact: PendingFact
    knowledge_card: KnowledgeCard
    created: bool


@dataclass(frozen=True)
class PendingFactRejectionResult:
    """Result of rejecting a PendingFact."""

    pending_fact: PendingFact


class PendingFactConfirmationService:
    """Use cases for author confirmation or rejection of PendingFact records."""

    def __init__(
        self,
        storage: ProjectAssetStorageContract,
        knowledge_service: KnowledgeService,
    ) -> None:
        self._storage = storage
        self._knowledge_service = knowledge_service

    async def confirm_pending_fact(
        self,
        pending_fact_id: str,
    ) -> PendingFactConfirmationResult:
        """Confirm a PendingFact without edits."""
        return await self._confirm(
            pending_fact_id,
            target_status=PendingFactStatus.CONFIRMED,
            edits=None,
        )

    async def confirm_pending_fact_with_edits(
        self,
        pending_fact_id: str,
        edits: PendingFactConfirmationEdits,
    ) -> PendingFactConfirmationResult:
        """Confirm a PendingFact after explicit author edits."""
        return await self._confirm(
            pending_fact_id,
            target_status=PendingFactStatus.EDITED_CONFIRMED,
            edits=edits,
        )

    async def reject_pending_fact(
        self,
        pending_fact_id: str,
    ) -> PendingFactRejectionResult:
        """Reject a PendingFact so it remains outside fact_scope."""
        records = await self._list_pending_fact_records()
        pending_fact = _find_pending_fact(records, pending_fact_id)
        if pending_fact.status is PendingFactStatus.IGNORED:
            return PendingFactRejectionResult(pending_fact=pending_fact)

        assert_pending_fact_transition_allowed(
            pending_fact.status,
            PendingFactStatus.IGNORED,
        )
        updated = pending_fact.model_copy(
            update={"status": PendingFactStatus.IGNORED}
        )
        await self._replace_pending_fact(updated)
        return PendingFactRejectionResult(pending_fact=updated)

    async def _confirm(
        self,
        pending_fact_id: str,
        *,
        target_status: PendingFactStatus,
        edits: PendingFactConfirmationEdits | None,
    ) -> PendingFactConfirmationResult:
        records = await self._list_pending_fact_records()
        pending_fact = _find_pending_fact(records, pending_fact_id)
        if pending_fact.status in {
            PendingFactStatus.CONFIRMED,
            PendingFactStatus.EDITED_CONFIRMED,
        }:
            knowledge = await self._confirmed_knowledge_for(pending_fact)
            return PendingFactConfirmationResult(
                pending_fact=pending_fact,
                knowledge_card=knowledge,
                created=False,
            )

        assert_pending_fact_transition_allowed(pending_fact.status, target_status)
        card = _knowledge_card_from_pending_fact(pending_fact, edits)
        write_result = await self._knowledge_service.write_confirmed_card(card)
        now = _now_iso()
        updated = pending_fact.model_copy(
            update={
                "status": target_status,
                "target_knowledge_id": write_result.card.id,
                "confirmed_at": now,
            }
        )
        await self._replace_pending_fact(updated)
        return PendingFactConfirmationResult(
            pending_fact=updated,
            knowledge_card=write_result.card,
            created=write_result.created,
        )

    async def _confirmed_knowledge_for(
        self,
        pending_fact: PendingFact,
    ) -> KnowledgeCard:
        if not pending_fact.target_knowledge_id:
            raise PendingFactConfirmationError(
                "Confirmed PendingFact is missing target_knowledge_id"
            )
        knowledge = await self._knowledge_service.get_card(
            pending_fact.target_knowledge_id
        )
        if knowledge is None:
            raise PendingFactConfirmationError(
                "Confirmed PendingFact target Knowledge is missing"
            )
        return knowledge

    async def _list_pending_fact_records(self) -> list[PendingFact]:
        records = await self._storage.list_workspace_records(PENDING_FACTS_FILE)
        return [PendingFact.model_validate(record) for record in records]

    async def _replace_pending_fact(self, updated: PendingFact) -> None:
        records = await self._storage.list_workspace_records(PENDING_FACTS_FILE)
        rewritten: list[dict[str, object]] = []
        replaced = False
        for record in records:
            pending_fact = PendingFact.model_validate(record)
            if pending_fact.id == updated.id:
                rewritten.append(updated.model_dump(mode="json"))
                replaced = True
            else:
                rewritten.append(pending_fact.model_dump(mode="json"))
        if not replaced:
            raise PendingFactNotFoundError(updated.id)
        await self._storage.rewrite_workspace_records(PENDING_FACTS_FILE, rewritten)


class PendingFactNotFoundError(LookupError):
    """Raised when a PendingFact id is absent from workspace records."""

    def __init__(self, pending_fact_id: str) -> None:
        super().__init__(f"PendingFact '{pending_fact_id}' was not found")


class PendingFactConfirmationError(ValueError):
    """Raised when a PendingFact cannot be promoted to Knowledge."""


class UnsupportedPendingFactTypeError(PendingFactConfirmationError):
    """Raised when a PendingFact type has no KnowledgeCard mapping."""


def _find_pending_fact(
    records: list[PendingFact],
    pending_fact_id: str,
) -> PendingFact:
    for pending_fact in records:
        if pending_fact.id == pending_fact_id:
            return pending_fact
    raise PendingFactNotFoundError(pending_fact_id)


def _knowledge_card_from_pending_fact(
    pending_fact: PendingFact,
    edits: PendingFactConfirmationEdits | None,
) -> KnowledgeCard:
    now = _now_iso()
    fields = _fields_from_content(pending_fact.content)
    if edits is not None and edits.fields is not None:
        fields = dict(edits.fields)
    fields["pending_fact_id"] = pending_fact.id
    return KnowledgeCard(
        id=pending_fact.target_knowledge_id
        or _knowledge_id_for_pending_fact(pending_fact),
        type=_knowledge_type_for_pending_fact(pending_fact),
        name=(edits.name if edits and edits.name else pending_fact.title),
        aliases=edits.aliases if edits and edits.aliases is not None else [],
        summary=(
            edits.summary
            if edits and edits.summary
            else _summary_from_content(pending_fact.content)
        ),
        fields=fields,
        source_refs=pending_fact.source_refs,
        status=KnowledgeCardStatus.CONFIRMED,
        created_at=now,
        updated_at=now,
    )


def _knowledge_type_for_pending_fact(
    pending_fact: PendingFact,
) -> KnowledgeCardType:
    try:
        return _KNOWLEDGE_TYPE_BY_PENDING_TYPE[pending_fact.fact_type.value]
    except KeyError as error:
        raise UnsupportedPendingFactTypeError(
            f"PendingFact type '{pending_fact.fact_type.value}' cannot be confirmed"
        ) from error


def _knowledge_id_for_pending_fact(pending_fact: PendingFact) -> str:
    digest = hashlib.sha1(pending_fact.id.encode("utf-8")).hexdigest()[:12]
    normalized = _SAFE_ID_PART.sub("_", pending_fact.id.casefold()).strip("_")
    if normalized:
        return f"knowledge_{normalized}_{digest}"
    return f"knowledge_{digest}"


def _fields_from_content(content: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(content, dict):
        return dict(content)
    return {"text": content}


def _summary_from_content(content: dict[str, Any] | str) -> str:
    if isinstance(content, str):
        return content
    for key in ("summary", "body", "content", "text", "rule", "description"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
