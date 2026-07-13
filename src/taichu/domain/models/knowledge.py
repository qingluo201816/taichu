"""Knowledge card compatibility exports for the first-version schema."""

from taichu.domain.models.base import DomainModel
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
)

KnowledgeCard = StructuredKnowledgeCard
KnowledgeCardType = StructuredKnowledgeType
KnowledgeCardLifecycle = StructuredKnowledgeLifecycle


class CharacterCard(DomainModel):
    """Minimal dedicated view over a character knowledge card."""

    knowledge_base: KnowledgeCard
    current_realm: str | None = None
    current_location: str | None = None
    faction: str | None = None
    relationship_summary: str | None = None
