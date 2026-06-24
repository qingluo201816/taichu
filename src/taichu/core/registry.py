"""Agent 注册中心：对 agents/__init__.py 的薄封装。

提供统一的 Agent 发现和获取 API。
"""

from taichu.agents import list_agents, get_agent as _get_agent


def list_agents():
    """返回所有已注册的 Agent 元信息。"""
    from taichu.agents import list_agents as _list
    return _list()


def get_agent(name: str):
    """返回已编译的 Agent Graph。"""
    from taichu.agents import get_agent as _get
    return _get(name)
