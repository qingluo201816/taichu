"""Vector Graph RAG 统一 LLM 契约适配测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from taichu.application.contracts.llm import LLMModelProfile
from taichu.infrastructure.llm.contracts import (
    LLMCost,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMToolCall,
    LLMUsage,
)
from taichu.infrastructure.llm.adapter import GatewayChatModel
from taichu.infrastructure.vector_graph.llm_adapter import (
    TaichuVectorGraphLLM,
    vector_graph_llm_run_context,
)


class RecordingGateway:
    def __init__(
        self,
        responses: list[str],
        *,
        finish_reasons: list[str | None] | None = None,
    ) -> None:
        self._responses = iter(responses)
        self._finish_reasons = iter(finish_reasons or [None] * len(responses))
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        tool_name = request.tools[0].name
        return LLMResponse(
            text="",
            model_id=request.model_id,
            upstream_model=request.model_id,
            usage=LLMUsage(),
            cost=LLMCost(),
            finish_reason=next(self._finish_reasons),
            tool_calls=(
                LLMToolCall(
                    call_id="call-vector-graph",
                    name=tool_name,
                    arguments_json=next(self._responses),
                ),
            ),
        )

    async def stream(self, _request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        if False:
            yield LLMStreamEvent(event_type="started")

    def list_models(self) -> list[LLMModelProfile]:
        return []


def test_triplet_extraction_uses_unified_gateway_native_tool() -> None:
    gateway = RecordingGateway(
        ['{"triplets":[{"subject":"林玄","predicate":"持有","object":"赤霄剑"}]}']
    )
    adapter = TaichuVectorGraphLLM(
        GatewayChatModel(gateway, model_id="deepseek-v4-pro"),
        "deepseek-v4-pro",
    )

    assert asyncio.run(adapter.extract_triplets("林玄持有赤霄剑。")) == [
        ["林玄", "持有", "赤霄剑"]
    ]
    request = gateway.requests[0]
    assert request.task_name == "vector_graph.extract_triplets"
    assert request.model_id == "deepseek-v4-pro"
    assert request.feature == "milvus_vector_graph_rag"
    assert request.max_output_tokens == 4_096
    assert request.tool_choice == "required"
    assert len(request.tools) == 1
    assert request.tools[0].strict is True
    assert "triplets" in request.tools[0].parameters["properties"]
    assert "JSON" not in request.messages[0].content
    assert request.messages[2].tool_calls[0].name == request.tools[0].name
    assert request.messages[3].tool_call_id == request.messages[2].tool_calls[0].call_id


def test_vector_graph_run_context_attaches_replay_run_id() -> None:
    gateway = RecordingGateway(
        ['{"triplets":[{"subject":"秦浩轩","predicate":"位于","object":"灵田谷"}]}']
    )
    adapter = TaichuVectorGraphLLM(
        GatewayChatModel(gateway, model_id="deepseek-v4-pro"),
        "deepseek-v4-pro",
    )

    with vector_graph_llm_run_context("20260821T141241Z-smoke"):
        asyncio.run(adapter.extract_triplets("秦浩轩位于灵田谷。"))

    assert gateway.requests[0].run_id == "20260821T141241Z-smoke"


def test_truncated_json_response_reports_explicit_failure() -> None:
    gateway = RecordingGateway(
        ['{"triplets":[{"subject":"秦浩轩","predicate":"位于"'],
        finish_reasons=["max_tokens"],
    )
    adapter = TaichuVectorGraphLLM(
        GatewayChatModel(gateway, model_id="deepseek-v4-pro"),
        "deepseek-v4-pro",
    )

    with pytest.raises(ValueError, match="达到上限并被截断"):
        asyncio.run(adapter.extract_triplets("秦浩轩位于灵田谷。"))
