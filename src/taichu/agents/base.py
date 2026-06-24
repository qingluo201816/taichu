"""Agent 协议：定义每个 Agent 必须实现的接口。"""

from typing import Any, TypedDict

from langgraph.graph.state import CompiledStateGraph


class AgentMeta(TypedDict):
    """Agent 元信息，用于注册和 UI 展示。"""
    name: str           # 唯一标识，如 "chat"
    label: str          # 显示名称，如 "对话"
    description: str    # 功能描述


# 每个 Agent 的 graph.py 必须导出这两个符号：
# - agent_meta: AgentMeta
# - build_graph() -> CompiledStateGraph
