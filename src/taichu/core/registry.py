"""组件注册中心：发现和管理所有可插拔组件（Agent、Tool）。

新增 Agent：在 agents/ 下创建 <name>/ 目录，包含 graph.py，
其中导出 agent_meta 和 build_graph()，注册中心自动发现。

新增 Tool：在 tools/ 下创建 .py 文件，导出 run() 函数（未来实现）。
"""

from importlib import import_module
from pathlib import Path
from typing import Any

_agents: dict[str, tuple[dict, object]] = {}


def _discover_agents():
    """扫描 agents/ 目录，发现并注册所有 Agent 模块。"""
    global _agents
    if _agents:
        return

    # 惰性导入，避免 agents/__init__.py 循环依赖
    from taichu.agents.base import AgentMeta

    agents_dir = Path(__file__).parent.parent / "agents"
    for item in sorted(agents_dir.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith("_") or item.name.startswith("."):
            continue

        graph_file = item / "graph.py"
        if not graph_file.exists():
            continue

        try:
            mod = import_module(f"taichu.agents.{item.name}.graph")
            if hasattr(mod, "build_graph") and hasattr(mod, "agent_meta"):
                meta: AgentMeta = mod.agent_meta
                _agents[meta["name"]] = (meta, mod.build_graph)
        except ImportError:
            continue


def list_agents() -> dict[str, dict]:
    """返回所有已注册 Agent 的元信息。"""
    _discover_agents()
    return {name: meta for name, (meta, _) in _agents.items()}


def get_agent(name: str) -> Any:
    """返回已编译的 Agent Graph。"""
    _discover_agents()
    if name not in _agents:
        raise KeyError(f"Agent '{name}' not found. Available: {list(_agents.keys())}")
    _, build = _agents[name]
    return build()



# 未来扩展:
# def discover_tools():
#     """扫描 tools/ 目录，发现并注册所有 Tool 模块。"""
# def get_tool(name: str):
#     """获取指定 Tool 函数。"""
