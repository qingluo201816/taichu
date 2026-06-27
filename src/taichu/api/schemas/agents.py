"""Agent API 请求与响应模型。"""

from pydantic import BaseModel


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
