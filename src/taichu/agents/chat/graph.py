"""Chat Agent - 最小对话 Agent，验证骨架可运行。"""

from typing import TypedDict

from langgraph.graph import StateGraph, END

from taichu.agents.base import AgentMeta
from taichu.agents.chat.nodes import call_model


class ChatState(TypedDict):
    messages: list


agent_meta: AgentMeta = {
    "name": "chat",
    "label": "对话",
    "description": "与太初助手进行对话，讨论写作相关话题",
}


def build_graph() -> StateGraph:
    builder = StateGraph(ChatState)
    builder.add_node("call_model", call_model)
    builder.set_entry_point("call_model")
    builder.add_edge("call_model", END)
    return builder.compile()
