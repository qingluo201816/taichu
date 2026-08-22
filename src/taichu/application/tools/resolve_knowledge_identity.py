"""直接通过 MongoDB 事实源解析已确认知识身份。"""

from typing import Literal

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.tools._shared import INTERNAL_READ_CALLERS
from taichu.application.tools.contract import ToolManifest
from taichu.application.tools.models import (
    ResolveKnowledgeIdentityInput,
    ResolveKnowledgeIdentityOutput,
    KnowledgeIdentityMatch,
)


manifest = ToolManifest(
    name="resolve_knowledge_identity",
    description="按知识类型、名称和别名解析唯一、歧义或不存在的已确认知识。",
    input_schema=ResolveKnowledgeIdentityInput,
    output_schema=ResolveKnowledgeIdentityOutput,
    required_capabilities=frozenset({"knowledge_repository"}),
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
    del invocation
    cards = await context.require(
        "knowledge_repository", StructuredKnowledgeRepository
    ).search_confirmed_identity(
        tool_input.knowledge_type,
        tool_input.name,
        tool_input.aliases,
    )
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
        matches=[
            KnowledgeIdentityMatch(
                card_id=card.id,
                knowledge_type=card.type,
                canonical_name=card.name,
                matched_aliases=[
                    alias
                    for alias in card.aliases
                    if alias in {tool_input.name, *tool_input.aliases}
                ],
            )
            for card in cards
        ],
        reason=reason,
        source_refs=source_refs,
    )
