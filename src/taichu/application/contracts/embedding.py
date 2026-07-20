"""Embedding 网关与脱敏调用遥测的跨层契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.embeddings.models import (
    EmbeddingCallRecord,
    EmbeddingModelProfile,
    EmbeddingRequest,
    EmbeddingResponse,
)


@runtime_checkable
class EmbeddingGateway(Protocol):
    """由本地或外部真实 Embedding 服务实现。"""

    def profile(self) -> EmbeddingModelProfile: ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


@runtime_checkable
class EmbeddingUsageRepository(Protocol):
    """追加保存不含原文和向量的调用遥测。"""

    async def append(self, record: EmbeddingCallRecord) -> None: ...
