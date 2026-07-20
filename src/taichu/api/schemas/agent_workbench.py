"""API schemas for the Agent workbench."""

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from taichu.application.agents.models.agent_run import AgentReviewItem, AgentRun
from taichu.application.services.knowledge_service import AuthorMergeMode


class CreateKnowledgeExtractionRunRequest(BaseModel):
    """Create one synchronous knowledge extraction run."""

    chapter_id: str = Field(min_length=1)
    model_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_id", "model_name"),
    )
    force: bool = False


class CreateBatchKnowledgeExtractionRunRequest(BaseModel):
    """Create one multi-chapter knowledge extraction run."""

    chapter_ids: list[str] = Field(min_length=1)
    model_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_id", "model_name"),
    )
    force: bool = False


class CreateSummaryRepairRunRequest(BaseModel):
    """Create one review-only historical summary repair run."""

    card_ids: list[str] = Field(default_factory=list)
    model_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_id", "model_name"),
    )


class EditConfirmCandidateRequest(BaseModel):
    """Confirm a candidate after author edits."""

    card_updates: dict[str, Any] = Field(default_factory=dict)
    target_card_id: str | None = None
    merge_mode: AuthorMergeMode = "merge"


class KnowledgeExtractionRunSummary(BaseModel):
    """Compact run info used by lists and create responses."""

    run_id: str
    agent_name: str
    status: str
    scope_type: str = "chapter"
    chapter_id: str
    chapter_title: str
    chapter_ids: list[str] = Field(default_factory=list)
    chapter_titles: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    pending_count: int = 0
    confirmed_count: int = 0
    rejected_count: int = 0
    total_chapter_count: int = 0
    completed_chapter_count: int = 0
    failed_chapter_count: int = 0
    started_at: str
    finished_at: str | None = None


class KnowledgeExtractionRunCreateResponse(BaseModel):
    """Response for creating one run."""

    run: KnowledgeExtractionRunSummary


class KnowledgeExtractionRunListResponse(BaseModel):
    """Paginated run list response."""

    runs: list[KnowledgeExtractionRunSummary] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class KnowledgeExtractionRunDetailResponse(BaseModel):
    """Full run detail response."""

    run: AgentRun


class KnowledgeExtractionRunDeleteResponse(BaseModel):
    """Response after deleting one run record."""

    run_id: str
    deleted: bool = True


class KnowledgeExtractionCandidateListResponse(BaseModel):
    """Candidate list response."""

    candidates: list[AgentReviewItem] = Field(default_factory=list)


class KnowledgeExtractionCandidateActionResponse(BaseModel):
    """Response after changing one candidate status."""

    run: AgentRun


class KnowledgeSedimentationProgressResponse(BaseModel):
    """Current continuous knowledge-sedimentation frontier."""

    last_accepted_chapter_id: str | None = None
    updated_at: str | None = None
