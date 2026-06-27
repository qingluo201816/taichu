"""Chapter API schemas."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from taichu.api.schemas.ai_cards import AIResultCardInfo
from taichu.domain.models.source_ref import SourceRef


class ChapterInfo(BaseModel):
    """Chapter metadata exposed by the API."""

    id: str
    volume_id: str | None = None
    title: str
    order: int
    markdown_path: str
    status: str
    word_count: int
    created_at: str
    updated_at: str


class ChapterListResponse(BaseModel):
    """Chapter list response."""

    chapters: list[ChapterInfo] = Field(default_factory=list)


class ChapterReadResponse(BaseModel):
    """One chapter plus its Markdown body."""

    chapter: ChapterInfo
    markdown: str


class ChapterSaveRequest(BaseModel):
    """Request body for Markdown persistence."""

    markdown: str


class PendingFactInfo(BaseModel):
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


class ChapterSummaryInfo(BaseModel):
    """ChapterSummary transport shape."""

    id: str
    chapter_id: str
    status: str
    summary: str
    key_events: list[str] = Field(default_factory=list)
    character_changes: list[dict[str, Any]] = Field(default_factory=list)
    new_setting_candidates: list[PendingFactInfo] = Field(default_factory=list)
    foreshadow_candidates: list[dict[str, Any]] = Field(default_factory=list)
    next_chapter_hooks: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ChapterSummaryRunResponse(BaseModel):
    """Response for generating a chapter summary card."""

    summary: ChapterSummaryInfo
    card: AIResultCardInfo


class ChapterSummaryListResponse(BaseModel):
    """Response for listing chapter summaries."""

    summaries: list[ChapterSummaryInfo] = Field(default_factory=list)


class ChapterSummaryResponse(BaseModel):
    """One ChapterSummary response."""

    summary: ChapterSummaryInfo


class PendingFactResponse(BaseModel):
    """One PendingFact response."""

    pending_fact: PendingFactInfo


class ChapterSummaryAction(StrEnum):
    """Supported summary lifecycle actions."""

    CONFIRM = "confirm"
    IGNORE = "ignore"


class ChapterSummaryEditInfo(BaseModel):
    """Editable summary fields accepted at confirmation time."""

    summary: str | None = Field(default=None, min_length=1)
    key_events: list[str] | None = None
    character_changes: list[dict[str, Any]] | None = None
    foreshadow_candidates: list[dict[str, Any]] | None = None
    next_chapter_hooks: list[str] | None = None


class ChapterSummaryActionRequest(BaseModel):
    """Request body for a summary lifecycle action."""

    action: ChapterSummaryAction
    edits: ChapterSummaryEditInfo | None = None
