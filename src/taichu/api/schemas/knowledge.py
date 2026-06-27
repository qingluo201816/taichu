"""Knowledge and PendingFact confirmation API schemas."""

from typing import Any

from pydantic import BaseModel, Field

from taichu.domain.models.source_ref import SourceRef


class KnowledgeCardInfo(BaseModel):
    """Transport shape for a confirmed KnowledgeCard."""

    id: str
    type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    summary: str
    fields: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: str
    created_at: str
    updated_at: str


class KnowledgeListResponse(BaseModel):
    """Confirmed Knowledge list response."""

    cards: list[KnowledgeCardInfo] = Field(default_factory=list)


class PendingFactInfo(BaseModel):
    """Transport shape for PendingFact lifecycle responses."""

    id: str
    fact_type: str
    title: str
    content: dict[str, Any] | str
    proposed_by: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: str
    target_knowledge_id: str | None = None
    created_at: str
    confirmed_at: str | None = None


class ConfirmEditedPendingFactRequest(BaseModel):
    """Author edits supplied when confirming a PendingFact."""

    name: str | None = None
    summary: str | None = None
    aliases: list[str] | None = None
    fields: dict[str, Any] | None = None
    source_refs: list[SourceRef] | None = None


class PendingFactConfirmationResponse(BaseModel):
    """Response after confirming a PendingFact into Knowledge."""

    pending_fact: PendingFactInfo
    knowledge_card: KnowledgeCardInfo
    created: bool


class PendingFactRejectionResponse(BaseModel):
    """Response after rejecting a PendingFact."""

    pending_fact: PendingFactInfo
