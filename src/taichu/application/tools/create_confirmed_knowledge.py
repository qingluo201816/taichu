"""在作者授权后创建已确认知识事实。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.tools._shared import (
    ORCHESTRATOR_WRITE_CALLERS,
    sha256_text,
)
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolIdempotencyPolicy,
    ToolManifest,
    ToolSideEffect,
)
from taichu.application.tools.models import (
    CreateConfirmedKnowledgeInput,
    CreateConfirmedKnowledgeOutput,
)


manifest = ToolManifest(
    name="create_confirmed_knowledge",
    description="把作者确认且通过 Schema、来源和冲突校验的候选写入 MongoDB。",
    input_schema=CreateConfirmedKnowledgeInput,
    output_schema=CreateConfirmedKnowledgeOutput,
    required_capabilities=frozenset({"knowledge_service"}),
    exposures=frozenset({"agent_runtime"}),
    side_effect=ToolSideEffect.WRITE,
    allowed_callers=ORCHESTRATOR_WRITE_CALLERS,
    authorization_policy=ToolAuthorizationPolicy.AUTHOR_GRANT,
    idempotency_policy=ToolIdempotencyPolicy.REQUIRED,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = CreateConfirmedKnowledgeInput.model_validate(input_data)
    payload = dict(tool_input.card)
    payload.setdefault("source_note", "；".join(tool_input.source_refs))
    card = await context.require(
        "knowledge_service",
        KnowledgeService,
    ).create_confirmed_from_data(tool_input.knowledge_type, payload)
    return CreateConfirmedKnowledgeOutput(
        card=card,
        audit_ref=f"knowledge_write:{sha256_text(tool_input.idempotency_key)[:24]}",
        source_refs=tool_input.source_refs,
    )
