"""API schemas for the Agent workbench."""

from typing import Any

from pydantic import BaseModel, Field

from taichu.application.contracts.knowledge_repository import AuthorMergeMode
from taichu.domain.models.agent_run import AgentReviewItem, AgentRun


class CreateKnowledgeExtractionRunRequest(BaseModel):
    """Create one synchronous knowledge extraction run."""

    chapter_id: str = Field(min_length=1)
    model_name: str | None = None
    force: bool = False


class EditConfirmCandidateRequest(BaseModel):
    """Confirm a candidate after author edits."""

    card_updates: dict[str, Any] = Field(default_factory=dict)
    target_card_id: str | None = None
    merge_mode: AuthorMergeMode = "append"


class KnowledgeExtractionRunSummary(BaseModel):
    """Compact run info used by lists and create responses."""

    run_id: str
    agent_name: str
    status: str
    chapter_id: str
    chapter_title: str
    candidate_count: int = 0
    pending_count: int = 0
    confirmed_count: int = 0
    rejected_count: int = 0
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
