"""Schemas for the chapter summary workflow."""

from typing import Any

from pydantic import BaseModel, Field


class SummaryCandidate(BaseModel):
    """A candidate setting extracted from a chapter summary run."""

    fact_type: str = "other"
    title: str = Field(min_length=1)
    content: dict[str, Any] | str


class SummaryWorkflowOutput(BaseModel):
    """Strict JSON shape requested from the summarization workflow."""

    summary: str = Field(min_length=1)
    key_events: list[str] = Field(default_factory=list)
    character_changes: list[dict[str, Any]] = Field(default_factory=list)
    new_setting_candidates: list[SummaryCandidate] = Field(default_factory=list)
    foreshadow_candidates: list[dict[str, Any]] = Field(default_factory=list)
    next_chapter_hooks: list[str] = Field(default_factory=list)
