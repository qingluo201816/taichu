"""Vector Graph RAG 后端契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildResult,
    VectorGraphExtractedTriplets,
    VectorGraphIndexStatus,
    VectorGraphRetrievalResult,
    VectorGraphSourceDocument,
)


@runtime_checkable
class VectorGraphBackend(Protocol):
    async def inspect(
        self,
        plan: VectorGraphBuildPlan,
    ) -> VectorGraphIndexStatus: ...

    async def update(
        self,
        documents: list[VectorGraphSourceDocument],
        *,
        plan: VectorGraphBuildPlan,
        extracted_triplets: VectorGraphExtractedTriplets | None = None,
    ) -> VectorGraphBuildResult: ...

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
    ) -> VectorGraphRetrievalResult: ...

    async def retrieve_without_graph(
        self,
        query: str,
        *,
        top_k: int,
    ) -> VectorGraphRetrievalResult: ...
