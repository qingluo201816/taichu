"""把统一召回服务暴露为通用 Agent 可调用的知识工具。"""

from pydantic import BaseModel, ConfigDict, Field

from taichu.application.capabilities import CapabilityContext
from taichu.application.retrieval.models import (
    RetrievalConsumerContext,
    RetrievalRequest,
    RetrievalResult,
)
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.tools.contract import ToolManifest
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


class KnowledgeRetrievalToolInput(BaseModel):
    """通用 Agent 发起相关性知识召回时可控制的参数。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str = Field(min_length=1, max_length=20_000)
    context_text: str = Field(default="", max_length=100_000)
    knowledge_types: frozenset[StructuredKnowledgeType] = Field(
        default_factory=frozenset
    )
    top_k: int | None = Field(default=None, ge=1, le=50)
    max_content_chars: int | None = Field(default=None, ge=500, le=20_000)
    run_id: str | None = Field(default=None, max_length=128)
    stage: str | None = Field(default=None, max_length=128)


manifest = ToolManifest(
    name="retrieve_knowledge",
    description="从作者已确认的知识库中召回与当前写作任务相关的设定。",
    input_schema=KnowledgeRetrievalToolInput,
    output_schema=RetrievalResult,
    required_capabilities=frozenset({"retrieval_service"}),
    exposures=frozenset({"agent_runtime"}),
)


async def run(
    input_data: BaseModel,
    context: CapabilityContext,
) -> BaseModel:
    """通过统一召回服务执行只读相关性查询。"""
    tool_input = KnowledgeRetrievalToolInput.model_validate(
        input_data.model_dump(mode="json")
    )
    service = context.require("retrieval_service", RetrievalService)
    return await service.retrieve(
        RetrievalRequest(
            query_text=tool_input.query_text,
            context_text=tool_input.context_text,
            knowledge_types=tool_input.knowledge_types,
            top_k=tool_input.top_k,
            max_content_chars=tool_input.max_content_chars,
            consumer=RetrievalConsumerContext(
                consumer_type="general_agent_runtime",
                run_id=tool_input.run_id,
                stage=tool_input.stage or "knowledge_retrieval_tool",
            ),
        )
    )
