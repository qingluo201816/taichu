"""Agent run records used by product workbench features."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


class AgentRunStatus(StrEnum):
    """Lifecycle states for one synchronous Agent run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunNodeStatus(StrEnum):
    """Lifecycle states for one node inside an Agent run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentReviewCandidateAction(StrEnum):
    """Author-facing review action suggested by the Agent."""

    CREATE_CARD = "create_card"
    UPDATE_CARD = "update_card"
    CONFLICT = "conflict"
    IGNORE = "ignore"


class AgentReviewCandidateStatus(StrEnum):
    """Author processing status for one review item."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AgentRunScope(DomainModel):
    """Scope covered by one Agent run."""

    scope_type: str = "chapter"
    chapter_id: str = Field(min_length=1)
    chapter_title: str = ""
    content_hash: str = ""


class AgentRunNode(DomainModel):
    """One LangGraph node execution record."""

    node_name: str = Field(min_length=1)
    status: AgentRunNodeStatus = AgentRunNodeStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = 0
    input_summary: str = ""
    output_summary: str = ""
    error: str | None = None


class AgentLLMCall(DomainModel):
    """One complete LLM call trace."""

    call_id: str = Field(min_length=1)
    node_name: str = Field(min_length=1)
    model_name: str = ""
    prompt_version: str = Field(min_length=1)
    input_prompt: str = ""
    raw_response: str = ""
    parsed_output: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = 0
    error: str | None = None


class AgentRawMention(DomainModel):
    """One raw mention extracted from chapter text before entity aggregation."""

    mention_id: str = Field(min_length=1)
    name: str = ""
    knowledge_type: StructuredKnowledgeType
    description: str = ""
    evidence_excerpts: list[str] = Field(default_factory=list)
    reason: str = ""
    segment_index: int = 1


class AgentEntityGroup(DomainModel):
    """Aggregated mentions that refer to the same candidate entity."""

    entity_group_id: str = Field(min_length=1)
    canonical_name: str = ""
    knowledge_type: StructuredKnowledgeType
    raw_names: list[str] = Field(default_factory=list)
    mention_count: int = 0
    evidence_excerpts: list[str] = Field(default_factory=list)
    quality_decision: str = ""
    quality_reason: str = ""


class AgentIgnoredExtraction(DomainModel):
    """Text ignored by extraction with an author-readable reason."""

    text: str = ""
    reason: str = ""
    segment_index: int | None = None


class AgentSchemaValidation(DomainModel):
    """Schema validation result for one review item."""

    passed: bool = True
    errors: list[str] = Field(default_factory=list)


class AgentReviewItem(DomainModel):
    """One candidate card or update waiting for author review."""

    review_item_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    candidate_action: AgentReviewCandidateAction
    knowledge_type: StructuredKnowledgeType
    candidate_status: AgentReviewCandidateStatus = (
        AgentReviewCandidateStatus.PENDING
    )
    display_title: str = ""
    suggested_card: dict[str, Any] = Field(default_factory=dict)
    target_card_id: str | None = None
    matched_card_name: str | None = None
    match_reason: str = ""
    source_excerpt: str = ""
    schema_validation: AgentSchemaValidation = Field(
        default_factory=AgentSchemaValidation
    )
    internal_conflicts: list[str] = Field(default_factory=list)
    external_conflicts: list[str] = Field(default_factory=list)
    suggested_action_label: str = ""
    author_action: str | None = None
    created_knowledge_card_id: str | None = None
    updated_knowledge_card_id: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class AgentMetrics(DomainModel):
    """Metrics shown in the workbench replay panel."""

    candidate_total: int = 0
    character_candidate_count: int = 0
    location_candidate_count: int = 0
    faction_candidate_count: int = 0
    item_candidate_count: int = 0
    create_card_count: int = 0
    update_card_count: int = 0
    conflict_count: int = 0
    schema_passed_count: int = 0
    schema_failed_count: int = 0
    confirmed_count: int = 0
    rejected_count: int = 0
    pending_count: int = 0
    total_duration_ms: int = 0
    llm_call_count: int = 0
    node_duration_ms: dict[str, int] = Field(default_factory=dict)


class AgentRun(DomainModel):
    """A complete JSON intermediate state for one knowledge extraction run."""

    run_id: str = Field(min_length=1)
    agent_name: str = "knowledge_extraction"
    agent_version: str = "v0.1"
    schema_version: str = "knowledge_fields_v2"
    prompt_version: str = "knowledge_extraction_prompt_v2"
    model_name: str = ""
    status: AgentRunStatus = AgentRunStatus.PENDING
    scope: AgentRunScope
    started_at: str = Field(min_length=1)
    finished_at: str | None = None
    nodes: list[AgentRunNode] = Field(default_factory=list)
    llm_calls: list[AgentLLMCall] = Field(default_factory=list)
    raw_mentions: list[AgentRawMention] = Field(default_factory=list)
    entity_groups: list[AgentEntityGroup] = Field(default_factory=list)
    raw_candidates: list[dict[str, Any]] = Field(default_factory=list)
    typed_candidates: list[dict[str, Any]] = Field(default_factory=list)
    review_items: list[AgentReviewItem] = Field(default_factory=list)
    ignored: list[AgentIgnoredExtraction] = Field(default_factory=list)
    metrics: AgentMetrics = Field(default_factory=AgentMetrics)
    errors: list[str] = Field(default_factory=list)
