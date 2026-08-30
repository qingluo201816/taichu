"""Selection workflow input and output contracts."""

from typing import Any, Literal

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


class SelectionSuggestionContent(BaseModel):
    """Author-facing suggestion content returned through a native result tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(description="建议标题；不需要标题时为 null。")
    body: str = Field(description="直接面向作者的具体中文建议。")


class SelectionTextCandidateContent(BaseModel):
    """Insertable manuscript candidate returned through a native result tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(description="可直接插入正文的候选文本。")


class SelectionPendingFactContent(BaseModel):
    """Unconfirmed fact candidate returned through a native result tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_type: Literal[
        "character",
        "realm",
        "technique",
        "location",
        "faction",
        "item",
        "rule",
        "event",
        "foreshadow",
        "other",
    ]
    title: str = Field(description="待确认事实标题。")
    content: str = Field(description="具体、可读且尚未经作者确认的候选事实。")


class SelectionAskOutput(BaseModel):
    """Native output contract for asking about a selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    card_type: Literal["suggestion"]
    content: SelectionSuggestionContent


class SelectionContinueOutput(BaseModel):
    """Native output contract for continuing selected text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    card_type: Literal["text_candidate"]
    content: SelectionTextCandidateContent


class SelectionEnrichOutput(BaseModel):
    """Native output contract for suggestions or unconfirmed setting facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    card_type: Literal["suggestion", "pending_fact"]
    content: SelectionSuggestionContent | SelectionPendingFactContent
