"""Pending fact contract and status values."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.source_ref import SourceRef


class PendingFactType(StrEnum):
    """Supported candidate fact categories."""

    CHARACTER = "character"
    REALM = "realm"
    TECHNIQUE = "technique"
    LOCATION = "location"
    FACTION = "faction"
    ITEM = "item"
    RULE = "rule"
    EVENT = "event"
    FORESHADOW = "foreshadow"
    OTHER = "other"


class ProposedBy(StrEnum):
    """Origin of a pending fact proposal."""

    AI = "ai"
    AUTHOR = "author"


class PendingFactStatus(StrEnum):
    """Lifecycle states for candidate facts before knowledge write-in."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    EDITED_CONFIRMED = "edited_confirmed"
    IGNORED = "ignored"


class PendingFact(DomainModel):
    """Candidate setting that is not a fact until confirmed by author."""

    id: str = Field(min_length=1)
    fact_type: PendingFactType
    title: str = Field(min_length=1)
    content: dict[str, Any] | str
    proposed_by: ProposedBy
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: PendingFactStatus
    target_knowledge_id: str | None = None
    created_at: str = Field(min_length=1)
    confirmed_at: str | None = None
