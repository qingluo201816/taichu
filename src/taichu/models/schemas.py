"""通用 Pydantic 数据模型。"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    agent: str = "chat"
    message: str


class ChatResponse(BaseModel):
    agent: str
    response: str


class AgentInfo(BaseModel):
    name: str
    label: str
    description: str


class AgentListResponse(BaseModel):
    agents: list[AgentInfo]
