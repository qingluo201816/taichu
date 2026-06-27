"""AI result card contract."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.source_ref import SourceRef


class AIResultCardType(StrEnum):
    """Product card types returned by AI workflows."""

    TEXT_CANDIDATE = "text_candidate"
    SUGGESTION = "suggestion"
    PENDING_FACT = "pending_fact"
    EVIDENCE = "evidence"
    CHAPTER_SUMMARY = "chapter_summary"
    INSPIRATION = "inspiration"


class AIWorkflow(StrEnum):
    """AI workflow identifiers exposed by product contracts."""

    ASK_SELECTION = "ask_selection"
    ENRICH_SETTING = "enrich_setting"
    CONTINUE_TEXT = "continue_text"
    POLISH = "polish"
    RETRIEVE = "retrieve"
    SUMMARIZE = "summarize"
    CHAT = "chat"


class AIResultCardStatus(StrEnum):
    """Lifecycle states for generated AI result cards."""

    GENERATED = "generated"
    INSERTED = "inserted"
    SAVED_TO_INBOX = "saved_to_inbox"
    CONVERTED_TO_PENDING_FACT = "converted_to_pending_fact"
    DISCARDED = "discarded"
    RETRIED = "retried"


class AIResultCard(DomainModel):
    """Stable product output wrapper for all AI-facing UI results."""

    id: str = Field(min_length=1)
    type: AIResultCardType
    workflow: AIWorkflow
    status: AIResultCardStatus
    chapter_id: str | None = None
    input_context: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] | str
    source_refs: list[SourceRef] = Field(default_factory=list)
    parent_card_id: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
