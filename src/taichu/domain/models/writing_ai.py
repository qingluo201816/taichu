"""Writing-page real AI run contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel


class WritingAIButtonType(StrEnum):
    """Writing-page AI buttons routed through the unified real LLM workflow."""

    CHAT = "chat"
    CONTINUE = "continue"
    POLISH = "polish"
    SETTING = "setting"
    SUGGESTION = "suggestion"
    EVIDENCE = "evidence"
    CHAPTER_SUMMARY = "chapter_summary"
    INSPIRATION = "inspiration"
    FACT = "fact"


class WritingAIReferenceScope(StrEnum):
    """Reference scope sent by the writing page."""

    NONE = "none"
    SELECTION = "selection"
    CHAPTER = "chapter"
    FULL_TEXT = "full_text"


class WritingAIRunStatus(StrEnum):
    """Synchronous run lifecycle checkpoints."""

    QUEUED = "queued"
    RETRIEVING = "retrieving"
    CALLING_LLM = "calling_llm"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"


class WritingAIOutputType(StrEnum):
    """Structured output type returned by the fixed prompt for each button."""

    CHAT_ANSWER = "chat_answer"
    TEXT_CANDIDATE = "text_candidate"
    POLISHED_TEXT = "polished_text"
    SETTING_SUGGESTION = "setting_suggestion"
    WRITING_SUGGESTION = "writing_suggestion"
    EVIDENCE_ANSWER = "evidence_answer"
    CHAPTER_SUMMARY = "chapter_summary"
    INSPIRATION = "inspiration"
    PENDING_FACT_CANDIDATES = "pending_fact_candidates"


class WritingAISelectionRange(DomainModel):
    """Optional selected text position supplied by the editor."""

    paragraph_start: int | None = None
    paragraph_end: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class WritingAIInput(DomainModel):
    """Input snapshot saved for every writing AI run."""

    user_input: str = ""
    selected_text: str = ""
    selection_range: WritingAISelectionRange | None = None
    target_words: int | None = None
    draft_chapter_text: str | None = None


class WritingAIPromptSnapshot(DomainModel):
    """Prompt snapshot actually rendered for a writing AI run."""

    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    rendered_at: str = Field(min_length=1)


class WritingAIRetrievalEvidenceItem(DomainModel):
    """One chapter or knowledge evidence item used by the run."""

    item_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    excerpt: str = ""
    usage: str = ""


class WritingAIRetrievalContext(DomainModel):
    """Knowledge and evidence context injected into the prompt."""

    used: bool = True
    empty_reason: str | None = None
    items: list[WritingAIRetrievalEvidenceItem] = Field(default_factory=list)
    knowledge_context: str = ""
    evidence_context: str = ""


class WritingAIStructuredOutput(DomainModel):
    """Normalized model output stored after JSON parsing."""

    output_type: WritingAIOutputType
    content: dict[str, Any] = Field(default_factory=dict)


class WritingAIRun(DomainModel):
    """Persisted trace for one writing-page AI call."""

    run_id: str = Field(min_length=1)
    status: WritingAIRunStatus
    button_type: WritingAIButtonType
    button_label: str = Field(min_length=1)
    model: str = ""
    chapter_id: str = Field(min_length=1)
    chapter_title: str = ""
    reference_scope: WritingAIReferenceScope
    input: WritingAIInput
    prompt_snapshot: WritingAIPromptSnapshot | None = None
    retrieval_context: WritingAIRetrievalContext | None = None
    raw_llm_output: str = ""
    structured_output: WritingAIStructuredOutput | None = None
    error: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
