"""Agent 自动发现：扫描 agents/ 下所有子目录，收集 Agent 模块。

新增 Agent：在 agents/ 下创建 <name>/ 目录，包含 graph.py，
其中导出 agent_meta (AgentMeta) 和 build_graph()，即可被自动发现。
"""

from importlib import import_module
from pathlib import Path

from taichu.agents.base import AgentMeta

_agents: dict[str, tuple[AgentMeta, object]] = {}


def _discover():
    """扫描 agents/ 下所有子目录，导入符合协议的 Agent 模块。"""
    global _agents
    if _agents:
        return

    agents_dir = Path(__file__).parent
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


def list_agents() -> dict[str, AgentMeta]:
    """返回所有已注册的 Agent 元信息。"""
    _discover()
    return {name: meta for name, (meta, _) in _agents.items()}


def get_agent(name: str):
    """返回已编译的 Agent Graph。"""
    _discover()
    if name not in _agents:
        raise KeyError(f"Agent '{name}' not found. Available: {list(_agents.keys())}")
    _, build = _agents[name]
    return build()
