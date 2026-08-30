import asyncio
import hashlib
from decimal import Decimal

from pydantic import BaseModel

from taichu.application.contracts.llm import LLMModelProfile
from taichu.infrastructure.llm.contracts import (
    LLMCost,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMUsage,
)
from taichu.application.evaluations.rag.models import (
    RAGGoldenCase,
)
from taichu.application.vector_graph.models import (
    VectorGraphEvidence,
    VectorGraphRetrievalResult,
    VectorGraphSourceType,
)
from taichu.infrastructure.evaluations.rag.deepeval_adapter import (
    TaichuDeepEvalLLM,
    TaichuGraphContextualRelevancyTemplate,
    _assemble_retrieval_context,
    _semantic_metric_types,
)
from taichu.infrastructure.llm.adapter import GatewayChatModel


class _Verdict(BaseModel):
    verdict: str


def test_deepeval_adapter_uses_unified_gateway_and_structured_output() -> None:
    class GatewayFake:
        request: LLMRequest | None = None

        async def complete(self, request: LLMRequest) -> LLMResponse:
            self.request = request
            tool_name = request.tools[0].name
            return LLMResponse(
                text="",
                model_id="judge",
                upstream_model="judge",
                usage=LLMUsage(),
                cost=LLMCost(amount=Decimal("0")),
                tool_calls=(
                    LLMToolCall(
                        call_id="call-deepeval",
                        name=tool_name,
                        arguments_json='{"verdict":"yes"}',
                    ),
                ),
            )

        def list_models(self) -> list[LLMModelProfile]:
            return []

    gateway = GatewayFake()
    adapter = TaichuDeepEvalLLM(
        GatewayChatModel(gateway, model_id="judge"),  # type: ignore[arg-type]
        "judge",
    )

    result = asyncio.run(adapter.a_generate("判断", schema=_Verdict))

    assert result == _Verdict(verdict="yes")
    assert gateway.request is not None
    assert gateway.request.task_type == "rag_evaluation_judge"
    assert gateway.request.max_output_tokens == 100_000
    assert gateway.request.tool_choice == "required"
    assert len(gateway.request.tools) == 1
    assert "verdict" in gateway.request.tools[0].parameters["properties"]
    assert gateway.request.tools[0].strict is True
    assert "JSON" not in gateway.request.messages[0].content


def test_hard_negative_does_not_run_contextual_relevancy() -> None:
    case = RAGGoldenCase(
        case_id="negative-001",
        query="秦浩轩什么时候飞升仙界？",
        category="hard_negative",
        expected_claims=["现有资料没有该事实"],
        reference_answer="现有资料无法确认。",
    )

    assert [metric.__name__ for metric in _semantic_metric_types(case)] == [
        "FaithfulnessMetric",
        "AnswerRelevancyMetric",
    ]


def test_graph_evidences_are_evaluated_as_the_final_assembled_context() -> None:
    def evidence(source_id: str, content: str, rank: int) -> VectorGraphEvidence:
        return VectorGraphEvidence(
            source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
            source_id=source_id,
            source_ref=f"knowledge:{source_id}",
            title=source_id,
            content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
            rank=rank,
            context_content=content,
        )

    retrieval = VectorGraphRetrievalResult(
        query="秦浩轩用哪件武器击杀了夏云子的弟子？",
        evidences=[
            evidence("relation-identity", "耶律齐师从夏云子。", 1),
            evidence("relation-weapon", "秦浩轩使用无形剑击杀耶律齐。", 2),
        ],
    )

    contexts = _assemble_retrieval_context(retrieval)

    assert len(contexts) == 1
    assert contexts[0].index("耶律齐师从夏云子") < contexts[0].index(
        "秦浩轩使用无形剑击杀耶律齐"
    )
    assert "[knowledge:relation-identity]" in contexts[0]
    assert "[knowledge:relation-weapon]" in contexts[0]


def test_contextual_relevancy_template_counts_multi_hop_bridge_facts() -> None:
    prompt = TaichuGraphContextualRelevancyTemplate.generate_verdicts(
        "秦浩轩用哪件武器击杀了夏云子的弟子？",
        "耶律齐师从夏云子。秦浩轩使用无形剑击杀耶律齐。",
    )

    assert "forms a necessary bridge in a connected multi-hop relation path" in prompt
    assert "Do not require every bridge statement" in prompt
