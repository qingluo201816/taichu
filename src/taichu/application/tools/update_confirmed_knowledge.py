"""在作者授权和并发校验后更新已确认知识事实。"""

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
    UpdateConfirmedKnowledgeInput,
    UpdateConfirmedKnowledgeOutput,
)


manifest = ToolManifest(
    name="update_confirmed_knowledge",
    description="在作者授权、字段和并发版本校验后更新已确认知识。",
    input_schema=UpdateConfirmedKnowledgeInput,
    output_schema=UpdateConfirmedKnowledgeOutput,
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
    tool_input = UpdateConfirmedKnowledgeInput.model_validate(input_data)
    card = await context.require(
        "knowledge_service",
        KnowledgeService,
    ).apply_author_confirmed_updates(
        tool_input.card_id,
        tool_input.updates,
        merge_mode=tool_input.merge_mode,
        expected_updated_at=tool_input.expected_updated_at,
    )
    return UpdateConfirmedKnowledgeOutput(
        card=card,
        changed_fields=sorted(tool_input.updates),
        audit_ref=f"knowledge_write:{sha256_text(tool_input.idempotency_key)[:24]}",
        source_refs=tool_input.source_refs,
    )


async def reconcile(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> ToolReconciliationResult:
    """通过卡片当前字段和并发版本核对更新是否已经生效。"""
    del invocation
    tool_input = UpdateConfirmedKnowledgeInput.model_validate(input_data)
    card = await context.require("knowledge_service", KnowledgeService).get_card(
        tool_input.card_id
    )
    current = card.model_dump(mode="json")
    matches = all(
        _field_matches(current.get(key), value, merge_mode=tool_input.merge_mode)
        for key, value in tool_input.updates.items()
    )
    evidence = {
        "card_id": card.id,
        "expected_updated_at": tool_input.expected_updated_at,
        "actual_updated_at": card.updated_at,
        "matched_fields": matches,
    }
    if matches:
        output = UpdateConfirmedKnowledgeOutput(
            card=card,
            changed_fields=sorted(tool_input.updates),
            audit_ref=(
                f"knowledge_write:{sha256_text(tool_input.idempotency_key)[:24]}"
            ),
            source_refs=tool_input.source_refs,
        )
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
            evidence=evidence,
            reason="目标知识卡已经包含授权更新后的字段值。",
        )
    if card.updated_at == tool_input.expected_updated_at:
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.NOT_APPLIED,
            evidence=evidence,
            reason="知识卡仍是授权时的并发版本，目标字段尚未生效。",
        )
    return ToolReconciliationResult(
        status=ToolReconciliationStatus.UNKNOWN,
        evidence=evidence,
        reason="知识卡已发生其他变化，无法证明本次更新是否完整生效。",
    )


def _field_matches(current: object, expected: object, *, merge_mode: str) -> bool:
    if (
        merge_mode == "merge"
        and isinstance(current, list)
        and isinstance(expected, list)
    ):
        return all(item in current for item in expected)
    return current == expected
