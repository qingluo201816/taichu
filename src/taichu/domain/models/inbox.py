"""Creative inbox contracts."""

from enum import StrEnum

from pydantic import Field

from taichu.domain.models.base import DomainModel


class IdeaCardSource(StrEnum):
    """Origin of a creative idea."""

    AUTHOR = "author"
    AI = "ai"


class IdeaCardStatus(StrEnum):
    """Lifecycle states for non-fact creative ideas."""

    OPEN = "open"
    CONVERTED = "converted"
    ARCHIVED = "archived"


class IdeaCard(DomainModel):
    """Creative workspace asset that is never a novel fact by itself."""

    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: IdeaCardSource
    linked_chapter_id: str | None = None
    status: IdeaCardStatus
    source_card_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
