"""统一召回后端与技术遥测的跨层契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.retrieval.models import (
    RetrievalBackendResult,
    RetrievalRequest,
    RetrievalTraceRecord,
)


@runtime_checkable
class RetrievalBackend(Protocol):
    """由词法、向量或混合实现提供候选知识。"""

    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult: ...


@runtime_checkable
class RetrievalTraceRepository(Protocol):
    """保存与业务日志分离的召回技术记录。"""

    async def append(self, record: RetrievalTraceRecord) -> None: ...
