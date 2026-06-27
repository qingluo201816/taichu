"""Selection workflow input and output contracts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taichu.domain.models.ai_card import AIResultCard, AIWorkflow
from taichu.domain.models.source_ref import SourceRef
from taichu.domain.rules.fact_scope import RetrievalScopeName

_ALLOWED_SELECTION_WORKFLOWS = frozenset(
    {
        AIWorkflow.ASK_SELECTION,
        AIWorkflow.ENRICH_SETTING,
        AIWorkflow.CONTINUE_TEXT,
    }
)


class SelectionWorkflowInput(BaseModel):
    """Input contract for editor selection AI workflows."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow: AIWorkflow
    chapter_id: str = Field(min_length=1)
    selected_text: str = Field(min_length=1)
    selection_ref: SourceRef
    prompt: str | None = None
    target_word_count: int | None = Field(default=None, gt=0)
    retrieval_scope: RetrievalScopeName = RetrievalScopeName.FACT
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workflow")
    @classmethod
    def workflow_must_be_selection_workflow(
        cls,
        value: AIWorkflow,
    ) -> AIWorkflow:
        """Keep Selection AI out of generic Agent Chat contracts."""
        if value not in _ALLOWED_SELECTION_WORKFLOWS:
            raise ValueError("workflow is not a selection workflow")
        return value


class SelectionWorkflowOutput(BaseModel):
    """Output contract: Selection AI must return an AIResultCard."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    card: AIResultCard
