"""AI card API schemas."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from taichu.domain.models.source_ref import SourceRef


class SelectionRangeInfo(BaseModel):
    """Editor selection range in Tiptap document coordinates."""

    from_: int = Field(alias="from", ge=0)
    to: int = Field(ge=0)


class SelectionModeInfo(StrEnum):
    """Selection AI API modes."""

    ASK = "ask"
    ENRICH_SETTING = "enrich_setting"
    CONTINUE_TEXT = "continue_text"


class SelectionContextInfo(BaseModel):
    """Editor selection context validated at the API boundary."""

    chapter_id: str = Field(min_length=1)
    selected_text: str = Field(min_length=1)
    surrounding_text: str = ""
    selection_range: SelectionRangeInfo
    source_ref: SourceRef


class SelectionAIRequest(BaseModel):
    """Request body for editor selection AI."""

    mode: SelectionModeInfo
    selection_context: SelectionContextInfo
    user_prompt: str | None = None
    target_words: int | None = Field(default=None, gt=0)
    parent_card_id: str | None = None


class AIResultCardInfo(BaseModel):
    """AIResultCard transport shape."""

    id: str
    type: str
    workflow: str
    status: str
    chapter_id: str | None = None
    input_context: dict[str, Any]
    content: dict[str, Any] | str
    source_refs: list[SourceRef] = Field(default_factory=list)
    parent_card_id: str | None = None
    created_at: str
    updated_at: str


class AICardResponse(BaseModel):
    """One AIResultCard response."""

    card: AIResultCardInfo


class AICardListResponse(BaseModel):
    """AIResultCard list response."""

    cards: list[AIResultCardInfo] = Field(default_factory=list)


class AICardAction(StrEnum):
    """Supported persisted card actions."""

    INSERTED = "inserted"
    DISCARD = "discard"
    SAVE_TO_IDEA = "save_to_idea"


class AICardActionRequest(BaseModel):
    """Request body for a card lifecycle action."""

    action: AICardAction
