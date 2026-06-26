"""自由对话 Agent 的 LangGraph 节点。"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

from taichu.application.agents.chat.prompts import SYSTEM_PROMPT

AgentNode = Callable[
    [dict[str, Any]],
    Awaitable[dict[str, Any]],
]


def create_call_model_node(llm: BaseChatModel) -> AgentNode:
    """创建使用注入 LLM 的调用节点。"""

    async def call_model(state: dict[str, Any]) -> dict[str, Any]:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            *state["messages"],
        ]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    return call_model
