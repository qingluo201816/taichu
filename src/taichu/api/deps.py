"""FastAPI 依赖注入。"""

from functools import lru_cache

from taichu.core.registry import get_agent, list_agents
from taichu.core.storage import JsonStorageBackend, StorageBackend
from taichu.config import settings


@lru_cache()
def get_storage() -> StorageBackend:
    """获取存储后端实例（单例）。"""
    return JsonStorageBackend(base_dir=settings.data_dir)


def get_agent_graph(name: str):
    """获取指定 Agent 的编译后 Graph。"""
    return get_agent(name)
