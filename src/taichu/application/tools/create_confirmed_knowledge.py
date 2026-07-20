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
    ToolReconciliationResult,
    ToolReconciliationStatus,
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


async def reconcile(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> ToolReconciliationResult:
    """通过知识身份与授权字段核对确认卡是否已经创建。"""
    del invocation
    tool_input = CreateConfirmedKnowledgeInput.model_validate(input_data)
    service = context.require("knowledge_service", KnowledgeService)
    payload = dict(tool_input.card)
    name = str(payload.get("name", "")).strip()
    aliases = [
        str(item) for item in payload.get("aliases", []) if isinstance(item, str)
    ]
    matches = await service.search_confirmed_identity(
        tool_input.knowledge_type,
        name,
        aliases,
    )
    expected = dict(payload)
    expected.setdefault("source_note", "；".join(tool_input.source_refs))
    exact = [
        card
        for card in matches
        if all(
            card.model_dump(mode="json").get(key) == value
            for key, value in expected.items()
        )
    ]
    evidence = {
        "knowledge_type": tool_input.knowledge_type.value,
        "identity_name": name,
        "matched_card_ids": [card.id for card in matches],
    }
    if len(exact) == 1:
        output = CreateConfirmedKnowledgeOutput(
            card=exact[0],
            audit_ref=(
                f"knowledge_write:{sha256_text(tool_input.idempotency_key)[:24]}"
            ),
            source_refs=tool_input.source_refs,
        )
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
            evidence=evidence,
            reason="已确认知识库中存在唯一且字段一致的目标卡片。",
        )
    if not matches:
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.NOT_APPLIED,
            evidence=evidence,
            reason="已确认知识库中没有目标身份。",
        )
    return ToolReconciliationResult(
        status=ToolReconciliationStatus.UNKNOWN,
        evidence=evidence,
        reason="存在同身份知识卡，但无法唯一证明是本次写入结果。",
    )
