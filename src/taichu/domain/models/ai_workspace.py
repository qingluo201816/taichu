"""MVP writing-area AI conversation contracts."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.mvp_source_ref import SourceReference


class AIWorkspaceTaskType(StrEnum):
    """Task entries in the writing-area right rail."""

    CHAT = "chat"
    CONTINUE = "continue"
    POLISH = "polish"
    SETTING = "setting"
    SUGGESTION = "suggestion"
    EVIDENCE = "evidence"
    CHAPTER_SUMMARY = "chapter_summary"


class AIWorkspaceSubtaskType(StrEnum):
    """Subtasks used by selected AI task entries."""

    EXPAND = "expand"
    SHORTEN = "shorten"
    REWRITE = "rewrite"


class AIReferenceScope(StrEnum):
    """Reference scope for each AI message."""

    NONE = "none"
    SELECTION = "selection"
    CHAPTER = "chapter"
    FULLTEXT = "fulltext"


class AIWorkspaceMessageRole(StrEnum):
    """Message roles saved inside a writing-area AI conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    ERROR = "error"


class AIWorkspaceOutputType(StrEnum):
    """Assistant output shapes for mock and future real AI."""

    TEXT_CANDIDATE = "text_candidate"
    SETTING_RESULT = "setting_result"
    SUGGESTION_RESULT = "suggestion_result"
    EVIDENCE_RESULT = "evidence_result"
    CHAPTER_SUMMARY = "chapter_summary"
    ERROR = "error"


class PromptSnapshot(DomainModel):
    """Debug snapshot of the prompt actually prepared for a model call."""

    structured: dict[str, Any] = Field(default_factory=dict)
    final_prompt: str = Field(min_length=1)


class AIWorkspaceMessage(DomainModel):
    """One message inside an AIWorkspaceConversation."""

    message_id: str = Field(min_length=1)
    role: AIWorkspaceMessageRole
    content: dict[str, Any] | str
    task_type: AIWorkspaceTaskType
    subtask_type: AIWorkspaceSubtaskType | None = None
    reference_scope: AIReferenceScope
    prompt_snapshot: PromptSnapshot | None = None
    skill: str | None = None
    route: str | None = None
    output_type: AIWorkspaceOutputType | None = None
    source_refs: list[SourceReference] = Field(default_factory=list)
    is_mock: bool = True
    created_at: str = Field(min_length=1)


class AIWorkspaceConversation(DomainModel):
    """Writing-area AI conversation fixed to one chapter and task entry."""

    id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    task_type: AIWorkspaceTaskType
    subtask_type: AIWorkspaceSubtaskType | None = None
    reference_scope: AIReferenceScope
    model_name: str = "mock-llm"
    is_mock: bool = True
    source_refs: list[SourceReference] = Field(default_factory=list)
    messages: list[AIWorkspaceMessage] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
