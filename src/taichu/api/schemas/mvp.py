"""MVP API schemas for writing, knowledge, Inbox, AI history and settings."""

from typing import Any

from pydantic import BaseModel, Field

from taichu.domain.models import (
    AIWorkspaceConversation,
    EditorPreferences,
    MVPInboxIdea,
    MVPInboxIssue,
    MVPInboxPendingFact,
    StructuredKnowledgeCard,
    WritingOutline,
)


class ErrorBody(BaseModel):
    """Chinese error body used by MVP endpoints."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """MVP error envelope."""

    error: ErrorBody


class OutlineResponse(BaseModel):
    """Writing outline response."""

    outline: WritingOutline


class CreateVolumeRequest(BaseModel):
    """Create a volume."""

    name: str = ""


class RenameVolumeRequest(BaseModel):
    """Rename a volume."""

    name: str


class CreateChapterRequest(BaseModel):
    """Create a chapter under a volume."""

    volume_id: str
    display_title: str | None = None


class RenameChapterRequest(BaseModel):
    """Rename a chapter."""

    display_title: str


class KnowledgeTypeInfo(BaseModel):
    """Knowledge type with Chinese label."""

    value: str
    label: str


class KnowledgeTypesResponse(BaseModel):
    """Supported knowledge types."""

    types: list[KnowledgeTypeInfo] = Field(default_factory=list)


class KnowledgeCardListResponse(BaseModel):
    """List of structured knowledge cards."""

    cards: list[StructuredKnowledgeCard] = Field(default_factory=list)


class KnowledgeCardResponse(BaseModel):
    """One structured knowledge card."""

    card: StructuredKnowledgeCard


class CreateKnowledgeCardRequest(BaseModel):
    """Create a structured knowledge card."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class PatchKnowledgeCardRequest(BaseModel):
    """Patch a structured knowledge card."""

    updates: dict[str, Any] = Field(default_factory=dict)


class MVPInboxListResponse(BaseModel):
    """Inbox tab response."""

    items: list[Any] = Field(default_factory=list)


class CreateInboxItemRequest(BaseModel):
    """Create an Inbox item."""

    data: dict[str, Any] = Field(default_factory=dict)


class PatchInboxItemRequest(BaseModel):
    """Patch an Inbox item."""

    updates: dict[str, Any] = Field(default_factory=dict)


class MVPInboxIdeaResponse(BaseModel):
    """One inspiration item."""

    item: MVPInboxIdea


class MVPInboxPendingFactResponse(BaseModel):
    """One pending fact item."""

    item: MVPInboxPendingFact


class MVPInboxIssueResponse(BaseModel):
    """One issue item."""

    item: MVPInboxIssue


class ConfirmPendingFactRequest(BaseModel):
    """Confirm a pending fact into structured knowledge."""

    knowledge_type: str
    card_preview: dict[str, Any] = Field(default_factory=dict)


class ConfirmPendingFactResponse(BaseModel):
    """Result of confirming a pending fact."""

    pending_fact: MVPInboxPendingFact
    knowledge_card: StructuredKnowledgeCard


class CreateAIWorkspaceConversationRequest(BaseModel):
    """Create a writing-area AI conversation."""

    chapter_id: str
    task_type: str
    reference_scope: str
    subtask_type: str | None = None
    model_name: str = "mock-llm"


class SendAIWorkspaceMessageRequest(BaseModel):
    """Send one message to a writing-area AI conversation."""

    user_input: str = ""
    reference: dict[str, Any] = Field(default_factory=dict)


class AIWorkspaceConversationResponse(BaseModel):
    """One writing-area AI conversation."""

    conversation: AIWorkspaceConversation


class AIWorkspaceConversationListResponse(BaseModel):
    """Conversation list response."""

    conversations: list[AIWorkspaceConversation] = Field(default_factory=list)


class PreferencesResponse(BaseModel):
    """Editor preferences response."""

    preferences: EditorPreferences


class PatchPreferencesRequest(BaseModel):
    """Patch editor preferences."""

    updates: dict[str, Any] = Field(default_factory=dict)
