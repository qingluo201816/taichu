"""Agent API 请求与响应模型。"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Agent 对话请求。"""

    agent: str = "chat"
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    """Agent 对话响应。"""

    agent: str
    response: str


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
