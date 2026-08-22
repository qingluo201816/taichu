"""统一召回正文、已确认知识卡与多跳关系证据。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.tools._shared import INTERNAL_READ_CALLERS
from taichu.application.tools.contract import ToolManifest
from taichu.application.tools.models import (
    RetrieveStoryContextInput,
    RetrieveStoryContextOutput,
    StoryContextEvidence,
)
from taichu.application.vector_graph.service import VectorGraphRAGService


manifest = ToolManifest(
    name="retrieve_story_context",
    description=(
        "在正文与已确认知识卡之间统一执行 Milvus BM25、稠密向量、"
        "Vector Graph 多跳、倒数排名融合和 BGE 重排，并返回权威回源证据。"
    ),
    input_schema=RetrieveStoryContextInput,
    output_schema=RetrieveStoryContextOutput,
    required_capabilities=frozenset({"vector_graph_rag_service"}),
    exposures=frozenset({"agent_runtime"}),
    allowed_callers=INTERNAL_READ_CALLERS,
    default_timeout_seconds=120,
    max_result_chars=100_000,
    retryable=True,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = RetrieveStoryContextInput.model_validate(input_data)
    result = await context.require(
        "vector_graph_rag_service", VectorGraphRAGService
    ).retrieve(tool_input.query, top_k=tool_input.max_passages)
    return RetrieveStoryContextOutput(
        query=result.query,
        evidences=[
            StoryContextEvidence.model_validate(item.model_dump(mode="json"))
            for item in result.evidences
        ],
        retrieved_relations=result.retrieved_relations,
        expanded_relations=result.expanded_relations,
        reranked_relations=result.reranked_relations,
        source_refs=result.source_refs,
    )
