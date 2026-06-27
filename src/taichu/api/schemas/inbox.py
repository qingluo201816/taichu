"""Creative inbox API schemas."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from taichu.api.schemas.ai_cards import AIResultCardInfo
from taichu.domain.models.source_ref import SourceRef

WorkspaceScope = Literal["workspace_scope"]
NonFactStatus = Literal["non_fact"]


class InboxItemMeta(BaseModel):
    """Shared workspace lane metadata."""

    scope: WorkspaceScope = "workspace_scope"
    fact_status: NonFactStatus = "non_fact"
    source_href: str | None = None


class IdeaCardInfo(InboxItemMeta):
    """IdeaCard transport shape."""

    id: str
    content: str
    source: str
    linked_chapter_id: str | None = None
    status: str
    source_card_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class PendingFactInfo(InboxItemMeta):
    """PendingFact transport shape."""

    id: str
    fact_type: str
    title: str
    content: dict[str, Any] | str
    proposed_by: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: str
    target_knowledge_id: str | None = None
    created_at: str
    confirmed_at: str | None = None


class SavedAICardInfo(AIResultCardInfo):
    """Saved AI card transport shape with non-fact metadata."""

    scope: WorkspaceScope = "workspace_scope"
    fact_status: NonFactStatus = "non_fact"
    source_href: str | None = None


class ChapterIssueInfo(InboxItemMeta):
    """Chapter issue transport shape."""

    id: str
    title: str
    description: str = ""
    chapter_id: str | None = None
    status: str
    source: str
    source_card_id: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_at: str
    updated_at: str


class InboxResponse(BaseModel):
    """Four-lane creative inbox response."""

    ideas: list[IdeaCardInfo] = Field(default_factory=list)
    pending_facts: list[PendingFactInfo] = Field(default_factory=list)
    saved_ai_cards: list[SavedAICardInfo] = Field(default_factory=list)
    chapter_issues: list[ChapterIssueInfo] = Field(default_factory=list)


class SaveIdeaResponse(BaseModel):
    """Response after saving a suggestion card as an idea."""

    idea: IdeaCardInfo
    card: SavedAICardInfo


class ConvertPendingFactResponse(BaseModel):
    """Response after converting an AI card to a pending fact."""

    pending_fact: PendingFactInfo
    card: SavedAICardInfo


class PendingFactActionResponse(BaseModel):
    """Response after changing a pending fact lifecycle state."""

    pending_fact: PendingFactInfo
