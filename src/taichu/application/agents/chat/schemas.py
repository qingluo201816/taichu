"""Chat Agent 输入与输出模型。"""

from pydantic import BaseModel, Field


class ChatAgentInput(BaseModel):
    """Chat Agent 输入。"""

    message: str = Field(min_length=1)


class ChatAgentOutput(BaseModel):
    """Chat Agent 输出。"""

    response: str
