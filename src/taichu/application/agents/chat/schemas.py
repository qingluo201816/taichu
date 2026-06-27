"""Chat Agent 输入与输出模型。"""

from pydantic import BaseModel, Field

from taichu.domain.models.source_ref import SourceRef


class ChatAgentInput(BaseModel):
    """Chat Agent 输入。"""

    message: str = Field(min_length=1)
    chapter_id: str | None = None
    include_current_chapter: bool = True
    include_confirmed_facts: bool = True


class ChatAgentOutput(BaseModel):
    """Chat Agent output wrapped by an AIResultCard in product APIs."""

    answer: str
    card_id: str
    source_refs: list[SourceRef] = Field(default_factory=list)
