"""Agent run records used by application workflows and workbench features."""

from __future__ import annotations

from enum import StrEnum
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


class AgentModel(BaseModel):
    """Immutable base for application-layer Agent records."""

    model_config = ConfigDict(frozen=True, extra="forbid")


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


class AgentRunScope(AgentModel):
    """Scope covered by one Agent run."""

    scope_type: str = "chapter"
    chapter_id: str = ""
    chapter_title: str = ""
    content_hash: str = ""
    chapter_ids: list[str] = Field(default_factory=list)
    chapter_titles: list[str] = Field(default_factory=list)
    chapter_content_hashes: dict[str, str] = Field(default_factory=dict)


class AgentRunNode(AgentModel):
    """One LangGraph node execution record."""

    node_name: str = Field(min_length=1)
    status: AgentRunNodeStatus = AgentRunNodeStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = 0
    input_summary: str = ""
    output_summary: str = ""
    error: str | None = None


class AgentRunGraphNode(AgentModel):
    """One node in the persisted Agent graph blueprint."""

    node_name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    lane: str = ""


class AgentRunGraphEdge(AgentModel):
    """One directed edge in the persisted Agent graph blueprint."""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class AgentBatchChapterProgress(AgentModel):
    """Progress for one chapter branch inside a batch Agent run."""

    chapter_id: str = Field(min_length=1)
    chapter_title: str = ""
    status: AgentRunNodeStatus = AgentRunNodeStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    candidate_count: int = 0
    nodes: list[AgentRunNode] = Field(default_factory=list)
    error: str | None = None


class AgentLLMCall(AgentModel):
    """One complete LLM call trace."""

    call_id: str = Field(min_length=1)
    node_name: str = Field(min_length=1)
    model_name: str = ""
    model_id: str = ""
    model_display_name: str = ""
    upstream_model: str = ""
    wire_protocol: str = ""
    prompt_version: str = Field(min_length=1)
    input_prompt: str = ""
    raw_response: str = ""
    parsed_output: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = 0
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    cost_amount: Decimal | None = None
    cost_currency: str = "CNY"
    cost_kind: str = "unavailable"
    provider_request_id: str | None = None
    error: str | None = None


class AgentRawMention(AgentModel):
    """One raw mention extracted from chapter text before entity aggregation."""

    mention_id: str = Field(min_length=1)
    name: str = ""
    knowledge_type: StructuredKnowledgeType
    description: str = ""
    evidence_excerpts: list[str] = Field(default_factory=list)
    reason: str = ""
    segment_index: int = 1


class AgentEntityGroup(AgentModel):
    """Aggregated mentions that refer to the same candidate entity."""

    entity_group_id: str = Field(min_length=1)
    canonical_name: str = ""
    knowledge_type: StructuredKnowledgeType
    raw_names: list[str] = Field(default_factory=list)
    mention_count: int = 0
    evidence_excerpts: list[str] = Field(default_factory=list)
    quality_decision: str = ""
    quality_reason: str = ""


class AgentIgnoredExtraction(AgentModel):
    """Text ignored by extraction with an author-readable reason."""

    text: str = ""
    reason: str = ""
    segment_index: int | None = None


class AgentSchemaValidation(AgentModel):
    """Schema validation result for one review item."""

    passed: bool = True
    errors: list[str] = Field(default_factory=list)


class AgentReviewItem(AgentModel):
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


class AgentMetrics(AgentModel):
    """Metrics shown in the workbench replay panel."""

    candidate_total: int = 0
    character_candidate_count: int = 0
    location_candidate_count: int = 0
    faction_candidate_count: int = 0
    item_candidate_count: int = 0
    realm_candidate_count: int = 0
    technique_candidate_count: int = 0
    rule_candidate_count: int = 0
    event_candidate_count: int = 0
    candidate_count_by_type: dict[str, int] = Field(default_factory=dict)
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


class AgentRun(AgentModel):
    """A complete JSON intermediate state for one knowledge extraction run."""

    run_id: str = Field(min_length=1)
    agent_name: str = "knowledge_extraction"
    agent_version: str = "v0.1"
    schema_version: str = "knowledge_fields_v2"
    prompt_version: str = "knowledge_extraction_prompt_v2"
    model_name: str = ""
    requested_model_name: str | None = None
    model_id: str = ""
    model_display_name: str = ""
    upstream_model: str = ""
    wire_protocol: str = ""
    generation_model_identity: LLMModelIdentity = Field(
        default_factory=lambda: LLMModelIdentity.unknown(
            "旧运行记录未保存真实模型身份。"
        )
    )
    status: AgentRunStatus = AgentRunStatus.PENDING
    scope: AgentRunScope
    started_at: str = Field(min_length=1)
    finished_at: str | None = None
    nodes: list[AgentRunNode] = Field(default_factory=list)
    graph_nodes: list[AgentRunGraphNode] = Field(default_factory=list)
    graph_edges: list[AgentRunGraphEdge] = Field(default_factory=list)
    batch_chapter_progress: list[AgentBatchChapterProgress] = Field(
        default_factory=list
    )
    max_concurrency: int = 1
    current_concurrency: int = 0
    total_chapter_count: int = 0
    completed_chapter_count: int = 0
    failed_chapter_count: int = 0
    llm_calls: list[AgentLLMCall] = Field(default_factory=list)
    raw_mentions: list[AgentRawMention] = Field(default_factory=list)
    entity_groups: list[AgentEntityGroup] = Field(default_factory=list)
    raw_candidates: list[dict[str, Any]] = Field(default_factory=list)
    typed_candidates: list[dict[str, Any]] = Field(default_factory=list)
    review_items: list[AgentReviewItem] = Field(default_factory=list)
    ignored: list[AgentIgnoredExtraction] = Field(default_factory=list)
    metrics: AgentMetrics = Field(default_factory=AgentMetrics)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def add_legacy_model_identity(cls, value: Any) -> Any:
        """Load historical JSON without claiming its display name is verified."""
        if not isinstance(value, dict) or "generation_model_identity" in value:
            return value
        payload = dict(value)
        legacy_model_name = str(payload.get("model_name") or "")
        payload["generation_model_identity"] = LLMModelIdentity.unknown(
            "旧运行记录未保存真实模型身份。",
            model_id=legacy_model_name,
        ).model_dump(mode="json")
        return payload
