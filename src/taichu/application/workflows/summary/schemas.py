"""Native structured-output schemas for the chapter summary workflow."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _SummaryOutputModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SummaryCandidate(_SummaryOutputModel):
    """A candidate setting extracted from a chapter summary run."""

    fact_type: Literal[
        "character",
        "realm",
        "technique",
        "location",
        "faction",
        "item",
        "rule",
        "event",
        "foreshadow",
        "other",
    ]
    title: str = Field(min_length=1)
    content: str = Field(description="具体、可读且尚未经作者确认的候选设定。")


class SummaryCharacterChange(_SummaryOutputModel):
    """One character state change grounded in the chapter."""

    character: str
    change: str


class SummaryForeshadowCandidate(_SummaryOutputModel):
    """One unconfirmed foreshadowing observation."""

    title: str
    description: str


class SummaryWorkflowOutput(_SummaryOutputModel):
    """Strict result contract sent through the native tool parameters."""

    summary: str = Field(min_length=1)
    key_events: list[str]
    character_changes: list[SummaryCharacterChange]
    new_setting_candidates: list[SummaryCandidate]
    foreshadow_candidates: list[SummaryForeshadowCandidate]
    next_chapter_hooks: list[str]
