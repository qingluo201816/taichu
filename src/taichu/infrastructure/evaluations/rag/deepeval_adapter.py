"""让 DeepEval 的 LLM-as-Judge 复用太初统一模型网关。"""

from __future__ import annotations

import asyncio
from typing import Any

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from pydantic import BaseModel, Field

from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMRequest,
    response_text,
)
from taichu.application.evaluations.rag.models import (
    RAGEvaluationModel,
    RAGGoldenCase,
)
from taichu.application.vector_graph.models import VectorGraphRetrievalResult


class DeepEvalMetricScore(RAGEvaluationModel):
    metric: str
    score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    passed: bool
    reason: str | None = None


class DeepEvalCaseScore(RAGEvaluationModel):
    case_id: str
    actual_answer: str
    source_refs: list[str]
    metrics: list[DeepEvalMetricScore]


class TaichuDeepEvalLLM(DeepEvalBaseLLM):
    """DeepEval 模型接口到统一网关的薄适配，不绕过遥测与模型目录。"""

    def __init__(self, gateway: LLMGatewayContract, model_id: str) -> None:
        self._gateway = gateway
        self._model_id = model_id
        super().__init__(model=model_id)

    def load_model(self, *args: Any, **kwargs: Any) -> TaichuDeepEvalLLM:
        return self

    def get_model_name(self, *args: Any, **kwargs: Any) -> str:
        return self._model_id

    def generate(self, prompt: str, schema: type[BaseModel] | None = None) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.a_generate(prompt, schema=schema))
        raise RuntimeError("事件循环运行中请使用 TaichuDeepEvalLLM.a_generate。")

    async def a_generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> Any:
        response = await self._gateway.complete(
            LLMRequest(
                model_id=self._model_id,
                messages=(
                    LLMMessage(
                        role="system",
                        content=(
                            "你是太初 RAG 质量评测裁判。严格依据评测提示完成判断；"
                            "要求 JSON 时只返回合法 JSON。"
                        ),
                    ),
                    LLMMessage(role="user", content=prompt),
                ),
                task_type="rag_evaluation_judge",
                task_name="RAG 语义质量评测",
                response_mode="json" if schema is not None else "text",
                temperature=0,
                feature="Graph RAG 质量评测",
            )
        )
        text = response_text(response)
        return schema.model_validate_json(text) if schema is not None else text

    def supports_structured_outputs(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return True


async def evaluate_semantic_case(
    case: RAGGoldenCase,
    *,
    actual_answer: str,
    retrieval: VectorGraphRetrievalResult,
    judge: TaichuDeepEvalLLM,
    threshold: float = 0.7,
) -> DeepEvalCaseScore:
    retrieval_context = [
        evidence.context_content or evidence.content for evidence in retrieval.evidences
    ]
    test_case = LLMTestCase(
        input=case.query,
        actual_output=actual_answer,
        retrieval_context=retrieval_context,
    )
    metrics = [
        ContextualRelevancyMetric(threshold=threshold, model=judge),
        FaithfulnessMetric(threshold=threshold, model=judge),
        AnswerRelevancyMetric(threshold=threshold, model=judge),
    ]
    scores: list[DeepEvalMetricScore] = []
    for metric in metrics:
        score = await metric.a_measure(
            test_case,
            _show_indicator=False,
            _log_metric_to_confident=False,
        )
        scores.append(
            DeepEvalMetricScore(
                metric=metric.__name__,
                score=float(score),
                threshold=threshold,
                passed=bool(metric.is_successful()),
                reason=metric.reason,
            )
        )
    return DeepEvalCaseScore(
        case_id=case.case_id,
        actual_answer=actual_answer,
        source_refs=retrieval.source_refs,
        metrics=scores,
    )
