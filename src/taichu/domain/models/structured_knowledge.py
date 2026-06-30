"""MVP structured knowledge card contracts."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.mvp_source_ref import SourceReference


class StructuredKnowledgeType(StrEnum):
    """Knowledge card types in the MVP structured knowledge base."""

    CHARACTER = "character"
    REALM = "realm"
    TECHNIQUE = "technique"
    LOCATION = "location"
    FACTION = "faction"
    ITEM = "item"
    RULE = "rule"
    EVENT = "event"
    FORESHADOW = "foreshadow"


class StructuredKnowledgeStatus(StrEnum):
    """Lifecycle states for structured knowledge cards."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class StructuredKnowledgeImportance(StrEnum):
    """Author-facing importance buckets for knowledge cards."""

    CORE = "core"
    MAJOR = "major"
    NORMAL = "normal"
    MINOR = "minor"


class CharacterStateRecord(DomainModel):
    """One structured character state record."""

    time_point: str = Field(min_length=1)
    chapter_id: str | None = None
    realm: str | None = None
    location: str | None = None
    life_status: str | None = None
    camp: str | None = None
    note: str | None = None


class CharacterKnowledgeFields(DomainModel):
    """Type-specific fields for character cards."""

    identity: str | None = None
    faction: str | None = None
    current_realm: str | None = None
    techniques: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    relationship_summary: str | None = None
    appearance_chapters: list[str] = Field(default_factory=list)
    state_records: list[CharacterStateRecord] = Field(default_factory=list)


class LocationKnowledgeFields(DomainModel):
    """Type-specific fields for location cards."""

    region: str | None = None
    parent_location: str | None = None
    controlling_faction: str | None = None
    location_rules: str | None = None
    important_resources: list[str] = Field(default_factory=list)
    danger_level: str | None = None
    appearance_chapters: list[str] = Field(default_factory=list)
    related_events: list[str] = Field(default_factory=list)


class FactionKnowledgeFields(DomainModel):
    """Type-specific fields for faction cards."""

    faction_type: str | None = None
    leader: str | None = None
    base: str | None = None
    territory: str | None = None
    relationships: str | None = None
    core_rules: str | None = None
    important_members: list[str] = Field(default_factory=list)
    related_locations: list[str] = Field(default_factory=list)


class RealmKnowledgeFields(DomainModel):
    """Type-specific fields for realm cards."""

    system: str | None = None
    order: str | None = None
    ability_boundary: str | None = None
    breakthrough_condition: str | None = None
    typical_manifestation: str | None = None
    cost_or_limit: str | None = None


class TechniqueKnowledgeFields(DomainModel):
    """Type-specific fields for technique cards."""

    technique_type: str | None = None
    practice_condition: str | None = None
    effect: str | None = None
    limit_or_cost: str | None = None
    related_characters: str | None = None
    related_realm: str | None = None
    origin: str | None = None


class ItemKnowledgeFields(DomainModel):
    """Type-specific fields for item cards."""

    item_type: str | None = None
    holder: str | None = None
    ability: str | None = None
    limit: str | None = None
    origin: str | None = None
    current_status: str | None = None
    related_events: list[str] = Field(default_factory=list)


class RuleKnowledgeFields(DomainModel):
    """Type-specific fields for rule cards."""

    rule_content: str | None = None
    scope: str | None = None
    limits: str | None = None
    exceptions: str | None = None
    related_settings: list[str] = Field(default_factory=list)


class EventKnowledgeFields(DomainModel):
    """Type-specific fields for event cards."""

    chapter_id: str | None = None
    related_characters: list[str] = Field(default_factory=list)
    related_locations: list[str] = Field(default_factory=list)
    event_summary: str | None = None
    impact: str | None = None


class ForeshadowKnowledgeFields(DomainModel):
    """Type-specific fields for foreshadow cards."""

    planted_chapter_id: str | None = None
    content: str | None = None
    related_characters_or_items: list[str] = Field(default_factory=list)
    current_status: str | None = None
    planned_resolution: str | None = None


class StructuredKnowledgeCard(DomainModel):
    """One JSON-file structured knowledge card."""

    id: str = Field(min_length=1)
    type: StructuredKnowledgeType
    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    importance: StructuredKnowledgeImportance = StructuredKnowledgeImportance.NORMAL
    status: StructuredKnowledgeStatus = StructuredKnowledgeStatus.DRAFT
    source_refs: list[SourceReference] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)

    def can_be_used_as_effective_knowledge(self) -> bool:
        """Return whether this card can participate in future AI reference."""
        return self.status is StructuredKnowledgeStatus.ACTIVE
