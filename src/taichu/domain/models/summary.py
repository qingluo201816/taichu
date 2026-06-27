"""Chapter summary draft contract."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.pending_fact import PendingFact
from taichu.domain.models.source_ref import SourceRef


class ChapterSummaryStatus(StrEnum):
    """Lifecycle states for chapter summaries."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"


class ChapterSummary(DomainModel):
    """Chapter summary asset that must point back to chapter source."""

    id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    status: ChapterSummaryStatus
    summary: str = Field(min_length=1)
    key_events: list[str] = Field(default_factory=list)
    character_changes: list[dict[str, Any]] = Field(default_factory=list)
    new_setting_candidates: list[PendingFact] = Field(default_factory=list)
    foreshadow_candidates: list[dict[str, Any]] = Field(default_factory=list)
    next_chapter_hooks: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
