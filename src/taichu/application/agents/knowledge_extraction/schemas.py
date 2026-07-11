"""Input and output schemas for the knowledge extraction Agent manifest."""

from pydantic import AliasChoices, BaseModel, Field


class KnowledgeExtractionAgentInput(BaseModel):
    """Input accepted by the knowledge extraction Agent graph."""

    chapter_id: str = Field(min_length=1)
    model_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_id", "model_name"),
    )
    force: bool = False


class KnowledgeExtractionAgentOutput(BaseModel):
    """Minimal output returned by the knowledge extraction Agent graph."""

    run_id: str
    status: str
    candidate_count: int = 0
