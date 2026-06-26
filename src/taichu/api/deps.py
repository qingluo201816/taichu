"""从应用状态提供 FastAPI 依赖。"""

from fastapi import Request

from taichu.application.agents.registry import AgentRegistry
from taichu.application.contracts.storage import StorageBackend


def provide_agent_registry(request: Request) -> AgentRegistry:
    """返回应用启动时创建的 Agent 注册中心。"""
    return request.app.state.agent_registry


def provide_storage(request: Request) -> StorageBackend:
    """返回应用启动时创建的存储实现。"""
    return request.app.state.storage
