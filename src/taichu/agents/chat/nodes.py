"""Chat Agent 图节点实现。"""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from taichu.agents.chat.prompts import SYSTEM_PROMPT
from taichu.core.llm import get_llm


async def call_model(state: dict[str, Any]) -> dict[str, Any]:
    """调用 LLM 生成回复。"""
    llm = get_llm()
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = await llm.ainvoke(messages)
    return {"messages": [response]}
