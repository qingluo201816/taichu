"""Agent 模块：提供 Agent 的发现与获取 API。

所有注册逻辑在 core/registry.py 中实现，本模块仅做 re-export。
"""

from taichu.core.registry import get_agent, list_agents

__all__ = ["get_agent", "list_agents"]
