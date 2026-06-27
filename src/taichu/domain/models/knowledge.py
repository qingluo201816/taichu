"""Confirmed knowledge card contracts."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.source_ref import SourceRef


class KnowledgeCardType(StrEnum):
    """Supported confirmed knowledge categories."""

    CHARACTER = "character"
    REALM = "realm"
    TECHNIQUE = "technique"
    LOCATION = "location"
    FACTION = "faction"
    ITEM = "item"
    RULE = "rule"
    EVENT = "event"
    FORESHADOW = "foreshadow"


class KnowledgeCardStatus(StrEnum):
    """Lifecycle states for author-confirmed knowledge."""

    CONFIRMED = "confirmed"
    ARCHIVED = "archived"


class KnowledgeCard(DomainModel):
    """Author-confirmed novel fact card."""

    id: str = Field(min_length=1)
    type: KnowledgeCardType
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    fields: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: KnowledgeCardStatus
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class CharacterImportance(StrEnum):
    """Minimal character importance buckets for MVP v1."""

    CORE = "core"
    MAJOR = "major"
    MINOR = "minor"
    CAMEO = "cameo"


class CharacterCard(DomainModel):
    """Minimal dedicated view over a confirmed character knowledge card."""

    knowledge_base: KnowledgeCard
    current_realm: str | None = None
    current_location: str | None = None
    faction: str | None = None
    known_secrets: list[str] = Field(default_factory=list)
    relationship_summary: str | None = None
    importance: CharacterImportance
