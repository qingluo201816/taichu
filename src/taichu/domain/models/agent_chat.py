"""Agent chat conversation result contracts."""

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.source_ref import SourceRef


class AgentConversation(DomainModel):
    """One stateless Agent Chat exchange returned to the UI."""

    id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    chapter_id: str | None = None
    used_current_chapter: bool
    used_confirmed_facts: bool
    source_refs: list[SourceRef] = Field(default_factory=list)
    card_id: str
    created_at: str = Field(min_length=1)
