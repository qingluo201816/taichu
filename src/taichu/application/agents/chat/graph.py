"""构建自由对话 Agent 的 LangGraph。"""

from typing import TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from taichu.application.agents.chat.nodes import create_call_model_node
from taichu.application.agents.chat.schemas import (
    ChatAgentInput,
    ChatAgentOutput,
)
from taichu.application.agents.contract import AgentManifest
from taichu.application.capabilities import CapabilityContext


class ChatState(TypedDict):
    """自由对话工作流状态。"""

    messages: list[BaseMessage]


manifest = AgentManifest(
    name="chat",
    label="对话",
    description="与太初助手进行对话，讨论当前玄幻小说的创作",
    input_schema=ChatAgentInput,
    output_schema=ChatAgentOutput,
    required_capabilities=frozenset({"llm"}),
    exposures=frozenset({"api", "ui", "mcp"}),
    supports_streaming=False,
)


def build_graph(context: CapabilityContext) -> CompiledStateGraph:
    """使用注入能力构建并编译 Chat Agent。"""
    llm = context.require("llm", BaseChatModel)
    builder = StateGraph(ChatState)
    builder.add_node("call_model", create_call_model_node(llm))
    builder.set_entry_point("call_model")
    builder.add_edge("call_model", END)
    return builder.compile()
