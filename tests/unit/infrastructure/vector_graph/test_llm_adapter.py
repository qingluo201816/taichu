"""Vector Graph RAG 统一 LLM 契约适配测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from taichu.application.contracts.llm import (
    LLMCost,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
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
        return LLMResponse(
            text=next(self._responses),
            model_id=request.model_id,
            upstream_model=request.model_id,
            usage=LLMUsage(),
            cost=LLMCost(),
            finish_reason=next(self._finish_reasons),
        )

    async def stream(self, _request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        if False:
            yield LLMStreamEvent(event_type="started")

    def list_models(self) -> list[LLMModelProfile]:
        return []


def test_all_vector_graph_model_tasks_use_unified_gateway_json_requests() -> None:
    gateway = RecordingGateway(
        [
            '{"triplets":[["林玄","持有","赤霄剑"]]}',
            '{"named_entities":["林玄","北荒城","林玄"]}',
            '{"useful_relation_ids":["r2"]}',
        ]
    )
    adapter = TaichuVectorGraphLLM(gateway, "deepseek-v4-pro")

    async def exercise() -> None:
        assert await adapter.extract_triplets("林玄持有赤霄剑。") == [
            ["林玄", "持有", "赤霄剑"]
        ]
        assert await adapter.extract_query_entities("林玄为何前往北荒城？") == [
            "林玄",
            "北荒城",
        ]
        assert await adapter.rerank_relations(
            "林玄为何前往北荒城？",
            ["r1", "r2"],
            ["林玄持有赤霄剑", "林玄前往北荒城"],
        ) == (["r2"], ["林玄前往北荒城"])

    asyncio.run(exercise())

    assert [item.task_name for item in gateway.requests] == [
        "vector_graph.extract_triplets",
        "vector_graph.extract_query_entities",
        "vector_graph.rerank_relations",
    ]
    assert all(item.model_id == "deepseek-v4-pro" for item in gateway.requests)
    assert all(item.response_mode == "json" for item in gateway.requests)
    assert all(item.feature == "milvus_vector_graph_rag" for item in gateway.requests)
    rerank_request = gateway.requests[-1]
    assert rerank_request.max_output_tokens == 2_048
    assert len(rerank_request.messages) == 2
    assert "thought_process" not in "".join(
        message.content for message in rerank_request.messages
    )
    rerank_system_prompt = rerank_request.messages[0].content
    assert "最小充分证据链" in rerank_system_prompt
    assert "原因/动机" in rerank_system_prompt
    assert "复述问题，不算原因证据" in rerank_system_prompt
    assert "一条关系即可回答" in rerank_system_prompt
    assert "关键行为和情节变化" in rerank_system_prompt


def test_relation_rerank_caps_candidates_and_allows_empty_selection() -> None:
    gateway = RecordingGateway(['{"useful_relation_ids":[]}'])
    adapter = TaichuVectorGraphLLM(
        gateway,
        "deepseek-v4-pro",
        relation_candidate_limit=2,
    )

    result = asyncio.run(
        adapter.rerank_relations(
            "没有资料支持的问题",
            ["r1", "r2", "r3"],
            ["关系一", "关系二", "关系三"],
        )
    )

    assert result == ([], [])
    prompt = gateway.requests[0].messages[-1].content
    assert "[r1]" in prompt
    assert "[r2]" in prompt
    assert "[r3]" not in prompt


def test_vector_graph_run_context_attaches_replay_run_id() -> None:
    gateway = RecordingGateway(['{"named_entities":["秦浩轩"]}'])
    adapter = TaichuVectorGraphLLM(gateway, "deepseek-v4-pro")

    with vector_graph_llm_run_context("20260821T141241Z-smoke"):
        asyncio.run(adapter.extract_query_entities("秦浩轩在哪里？"))

    assert gateway.requests[0].run_id == "20260821T141241Z-smoke"


def test_truncated_json_response_reports_explicit_failure() -> None:
    gateway = RecordingGateway(
        ['{"useful_relation_ids":["r1"'],
        finish_reasons=["max_tokens"],
    )
    adapter = TaichuVectorGraphLLM(gateway, "deepseek-v4-pro")

    with pytest.raises(ValueError, match="达到上限并被截断"):
        asyncio.run(adapter.rerank_relations("问题", ["r1"], ["关系一"]))
