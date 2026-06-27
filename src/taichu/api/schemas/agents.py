"""Agent API 请求与响应模型。"""

from pydantic import BaseModel, Field

from taichu.api.schemas.ai_cards import AIResultCardInfo
from taichu.domain.models.source_ref import SourceRef


class AgentInfo(BaseModel):
    """可供 API 和前端展示的 Agent 信息。"""

    name: str
    label: str
    description: str
    required_capabilities: list[str]
    exposures: list[str]
    supports_streaming: bool


class AgentListResponse(BaseModel):
    """Agent 列表响应。"""

    agents: list[AgentInfo]


class AgentChatRequest(BaseModel):
    """Request body for Basic Agent Chat."""

    message: str = Field(min_length=1)
    chapter_id: str | None = None
    include_current_chapter: bool = True
    include_confirmed_facts: bool = True


class AgentConversationInfo(BaseModel):
    """Transport shape for one stateless Agent Chat exchange."""

    id: str
    agent_name: str
    message: str
    chapter_id: str | None = None
    used_current_chapter: bool
    used_confirmed_facts: bool
    source_refs: list[SourceRef] = Field(default_factory=list)
    card_id: str
    created_at: str


class AgentChatResponse(BaseModel):
    """Basic Agent Chat response with AIResultCard output."""

    conversation: AgentConversationInfo
    card: AIResultCardInfo
