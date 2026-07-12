"""Knowledge card compatibility exports for the first-version schema."""

from enum import StrEnum

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeImportance,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
)

KnowledgeCard = StructuredKnowledgeCard
KnowledgeCardType = StructuredKnowledgeType
KnowledgeCardLifecycle = StructuredKnowledgeLifecycle


class CharacterImportance(StrEnum):
    """Minimal character importance buckets for legacy character views."""

    CORE = "core"
    MAJOR = "major"
    MINOR = "minor"
    CAMEO = "cameo"


class CharacterCard(DomainModel):
    """Minimal dedicated view over a character knowledge card."""

    knowledge_base: KnowledgeCard
    current_realm: str | None = None
    current_location: str | None = None
    faction: str | None = None
    relationship_summary: str | None = None
    importance: CharacterImportance | StructuredKnowledgeImportance = Field(
        default=CharacterImportance.MINOR
    )
