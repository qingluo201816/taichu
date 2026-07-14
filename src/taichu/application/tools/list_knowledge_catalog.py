"""分页浏览已确认知识目录。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.retrieval.models import (
    RetrievalConsumerContext,
    RetrievalMode,
    RetrievalRequest,
)
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.tools._shared import INTERNAL_READ_CALLERS
from taichu.application.tools.contract import ToolManifest
from taichu.application.tools.models import (
    KnowledgeCatalogItem,
    ListKnowledgeCatalogInput,
    ListKnowledgeCatalogOutput,
)


manifest = ToolManifest(
    name="list_knowledge_catalog",
    description="按知识类型和分页条件浏览已确认知识的轻量目录。",
    input_schema=ListKnowledgeCatalogInput,
    output_schema=ListKnowledgeCatalogOutput,
    required_capabilities=frozenset({"retrieval_service"}),
    exposures=frozenset({"agent_runtime"}),
    allowed_callers=INTERNAL_READ_CALLERS,
    max_result_chars=100_000,
    retryable=True,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    tool_input = ListKnowledgeCatalogInput.model_validate(input_data)
    top_k = min(200, tool_input.offset + tool_input.limit)
    result = await context.require("retrieval_service", RetrievalService).retrieve(
        RetrievalRequest(
            mode=RetrievalMode.CATALOG,
            knowledge_types=frozenset(tool_input.knowledge_types),
            top_k=max(1, top_k),
            max_content_chars=50_000,
            consumer=RetrievalConsumerContext(
                consumer_type="general_agent_runtime",
                run_id=invocation.run_id,
                stage=invocation.phase,
            ),
        )
    )
    selected = result.items[tool_input.offset : tool_input.offset + tool_input.limit]
    items = [
        KnowledgeCatalogItem(
            card_id=item.knowledge_card.id,
            knowledge_type=item.knowledge_card.type,
            name=item.knowledge_card.name,
            aliases=item.knowledge_card.aliases,
            summary=item.knowledge_card.summary,
            updated_at=item.knowledge_card.updated_at,
        )
        for item in selected
    ]
    source_refs = [f"knowledge:{item.card_id}" for item in items]
    return ListKnowledgeCatalogOutput(
        items=items,
        total=result.candidate_count,
        offset=tool_input.offset,
        limit=tool_input.limit,
        truncated=(
            result.truncated or tool_input.offset + len(items) < result.candidate_count
        ),
        retrieval_id=result.retrieval_id,
        source_refs=source_refs,
    )
