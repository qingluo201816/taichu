"""按知识类型、名称和别名解析已确认知识身份。"""

from typing import Literal

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.retrieval.models import (
    RetrievalConsumerContext,
    RetrievalIdentityQuery,
    RetrievalMode,
    RetrievalRequest,
)
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.tools._shared import INTERNAL_READ_CALLERS
from taichu.application.tools.contract import ToolManifest
from taichu.application.tools.models import (
    ResolveKnowledgeIdentityInput,
    ResolveKnowledgeIdentityOutput,
)


manifest = ToolManifest(
    name="resolve_knowledge_identity",
    description="按知识类型、名称和别名解析唯一、歧义或不存在的已确认知识。",
    input_schema=ResolveKnowledgeIdentityInput,
    output_schema=ResolveKnowledgeIdentityOutput,
    required_capabilities=frozenset({"retrieval_service"}),
    exposures=frozenset({"agent_runtime"}),
    allowed_callers=INTERNAL_READ_CALLERS,
    retryable=True,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    tool_input = ResolveKnowledgeIdentityInput.model_validate(input_data)
    result = await context.require("retrieval_service", RetrievalService).retrieve(
        RetrievalRequest(
            mode=RetrievalMode.IDENTITY,
            identity=RetrievalIdentityQuery(
                knowledge_type=tool_input.knowledge_type,
                name=tool_input.name,
                aliases=tool_input.aliases,
            ),
            top_k=20,
            max_content_chars=tool_input.max_content_chars,
            consumer=RetrievalConsumerContext(
                consumer_type="general_agent_runtime",
                run_id=invocation.run_id,
                stage=invocation.phase,
            ),
        )
    )
    cards = [item.knowledge_card for item in result.items]
    if not cards:
        resolution: Literal["unique", "ambiguous", "not_found"] = "not_found"
        reason = "没有找到名称或别名相同的已确认知识卡。"
    elif len(cards) == 1:
        resolution = "unique"
        reason = "找到唯一已确认知识卡。"
    else:
        resolution = "ambiguous"
        reason = "找到多个可能实体，调用方必须进一步澄清，不能静默选择。"
    source_refs = [f"knowledge:{card.id}" for card in cards]
    return ResolveKnowledgeIdentityOutput(
        resolution=resolution,
        matches=cards,
        reason=reason,
        retrieval_id=result.retrieval_id,
        source_refs=source_refs,
    )
