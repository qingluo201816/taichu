"""API schemas for writing-page AI real LLM runs."""

from pydantic import BaseModel, Field

from taichu.domain.models import (
    WritingAIButtonType,
    WritingAIReferenceScope,
    WritingAIRun,
    WritingAISelectionRange,
)


class CreateWritingAIRunRequest(BaseModel):
    """Create one writing AI run through the unified backend workflow."""

    button_type: WritingAIButtonType
    chapter_id: str
    reference_scope: WritingAIReferenceScope
    user_input: str = ""
    selected_text: str = ""
    selection_range: WritingAISelectionRange | None = None
    target_words: int | None = Field(default=None, ge=1)
    draft_chapter_text: str | None = None


class WritingAIRunListResponse(BaseModel):
    """Paginated writing AI run list."""

    runs: list[WritingAIRun] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0
