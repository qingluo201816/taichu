"""BM25、Milvus Vector Graph RAG 与 BGE 重排的统一后端。"""

from __future__ import annotations

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildResult,
    VectorGraphExtractedTriplets,
    VectorGraphIndexStatus,
    VectorGraphRetrievalResult,
    VectorGraphSourceDocument,
)
from taichu.infrastructure.vector_graph.backend import MilvusVectorGraphBackend
from taichu.infrastructure.vector_graph.reranker import BGEReranker


class HybridVectorGraphBackend:
    def __init__(
        self,
        *,
        milvus: MilvusVectorGraphBackend,
        reranker: BGEReranker,
        candidate_top_k: int = 30,
        final_top_k: int = 10,
    ) -> None:
        self._milvus = milvus
        self._reranker = reranker
        self.candidate_top_k = candidate_top_k
        self.final_top_k = final_top_k

    async def update(
        self,
        documents: list[VectorGraphSourceDocument],
        *,
        plan: VectorGraphBuildPlan,
        extracted_triplets: VectorGraphExtractedTriplets | None = None,
    ) -> VectorGraphBuildResult:
        result = await self._milvus.update(
            documents,
            plan=plan,
            extracted_triplets=extracted_triplets,
        )
        return result

    async def inspect(self, plan: VectorGraphBuildPlan) -> VectorGraphIndexStatus:
        return await self._milvus.inspect(plan)

    async def retrieve(self, query: str, *, top_k: int) -> VectorGraphRetrievalResult:
        return await self._retrieve_and_rerank(query, graph_enabled=True, top_k=top_k)

    async def retrieve_without_graph(
        self, query: str, *, top_k: int
    ) -> VectorGraphRetrievalResult:
        return await self._retrieve_and_rerank(query, graph_enabled=False, top_k=top_k)

    async def _retrieve_and_rerank(
        self,
        query: str,
        *,
        graph_enabled: bool,
        top_k: int,
    ) -> VectorGraphRetrievalResult:
        del top_k
        if graph_enabled:
            graph_result = await self._milvus.retrieve(
                query,
                top_k=self.candidate_top_k,
            )
        else:
            graph_result = await self._milvus.retrieve_without_graph(
                query,
                top_k=self.candidate_top_k,
            )
        evidences = await self._reranker.rerank(
            query,
            graph_result.evidences,
            top_k=self.final_top_k,
        )
        evidences = await self._milvus.expand_context(evidences)
        return graph_result.model_copy(
            update={
                "evidences": evidences,
                "source_refs": list(
                    dict.fromkeys(item.source_ref for item in evidences)
                ),
            }
        )

    async def close(self) -> None:
        await self._milvus.close()
