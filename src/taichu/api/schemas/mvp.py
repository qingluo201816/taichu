"""MVP API schemas for writing, knowledge, Inbox, AI history and settings."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from taichu.domain.models import (
    EditorPreferences,
    KnowledgeTypeSchema,
    MVPInboxDecision,
    MVPInboxIdea,
    MVPInboxIssue,
    MVPInboxIssueLink,
    MVPInboxPriority,
    MVPInboxStatus,
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
    after_chapter_id: str | None = None


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


class KnowledgeSchemasResponse(BaseModel):
    """Supported knowledge type schemas."""

    schemas: list[KnowledgeTypeSchema] = Field(default_factory=list)


class KnowledgeSchemaResponse(BaseModel):
    """One knowledge type schema."""

    model_config = ConfigDict(populate_by_name=True)

    knowledge_schema: KnowledgeTypeSchema = Field(alias="schema")


class KnowledgeCardListResponse(BaseModel):
    """List of structured knowledge cards."""

    cards: list[StructuredKnowledgeCard] = Field(default_factory=list)
    page: int = 1
    page_size: int = 10
    total: int = 0


class KnowledgeCardResponse(BaseModel):
    """One structured knowledge card."""

    card: StructuredKnowledgeCard


class MergeKnowledgeCardsRequest(BaseModel):
    """Author-confirmed request to merge one confirmed card into another."""

    merged_card_id: str = Field(min_length=1)


class KnowledgeCardMergeResponse(BaseModel):
    """The retained card and the now-retired duplicate card."""

    primary_card: StructuredKnowledgeCard
    merged_card: StructuredKnowledgeCard


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
    page: int = 1
    page_size: int = 10
    total: int = 0


class CreateInboxItemRequest(BaseModel):
    """Create an Inbox item."""

    data: dict[str, Any] = Field(default_factory=dict)


class PatchInboxItemRequest(BaseModel):
    """Patch an Inbox item."""

    updates: dict[str, Any] = Field(default_factory=dict)


class PatchInboxIssueUpdates(BaseModel):
    """系统问题允许通过 CAS 修改的字段。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content: str | None = None
    source_chapter_id: str | None = None
    priority: MVPInboxPriority | None = None
    status: MVPInboxStatus | None = None
    links: tuple[MVPInboxIssueLink, ...] | None = None


class PatchInboxIssueRequest(BaseModel):
    """系统问题 expected revision CAS 请求。"""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    updates: PatchInboxIssueUpdates


class MVPInboxIdeaResponse(BaseModel):
    """One inspiration item."""

    item: MVPInboxIdea


class MVPInboxPendingFactResponse(BaseModel):
    """One pending fact item."""

    item: MVPInboxPendingFact


class MVPInboxIssueResponse(BaseModel):
    """One issue item."""

    item: MVPInboxIssue


class MVPInboxDecisionResponse(BaseModel):
    """One decision item."""

    item: MVPInboxDecision


class ConfirmPendingFactRequest(BaseModel):
    """Confirm a pending fact into structured knowledge."""

    knowledge_type: str
    card_preview: dict[str, Any] = Field(default_factory=dict)


class ConfirmPendingFactResponse(BaseModel):
    """Result of confirming a pending fact."""

    pending_fact: MVPInboxPendingFact
    knowledge_card: StructuredKnowledgeCard


class PreferencesResponse(BaseModel):
    """Editor preferences response."""

    preferences: EditorPreferences


class PatchPreferencesRequest(BaseModel):
    """Patch editor preferences."""

    updates: dict[str, Any] = Field(default_factory=dict)
