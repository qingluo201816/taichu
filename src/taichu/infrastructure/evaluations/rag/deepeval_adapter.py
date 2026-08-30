"""让 DeepEval 的 LLM-as-Judge 复用 LangChain ChatModel。"""

from __future__ import annotations

import asyncio
from typing import Any

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.metrics.contextual_relevancy.template import ContextualRelevancyTemplate
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from taichu.application.evaluations.rag.models import (
    RAGEvaluationModel,
    RAGGoldenCategory,
    RAGGoldenCase,
)
from taichu.application.invocations.config import model_call_config
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


class TaichuGraphContextualRelevancyTemplate(ContextualRelevancyTemplate):
    """让 DeepEval 按完整图路径判断桥接事实，而非要求每条事实独立作答。"""

    @staticmethod
    def generate_verdicts(
        input: str,
        context: str,
        multimodal: bool = False,
    ) -> str:
        base_prompt = ContextualRelevancyTemplate.generate_verdicts(
            input,
            context,
            multimodal,
        )
        graph_rules = """Graph-aware relevance rules:
1. Read the entire assembled context before judging individual statements.
2. A statement is relevant when it directly answers the input OR forms a necessary bridge in a connected multi-hop relation path that answers the input together with another statement in this same context.
3. For example, for a question asking which weapon killed a person's disciple, both 'B is that person's disciple' and 'A used weapon C to kill B' are relevant.
4. Do not require every bridge statement to independently contain the final answer. Still mark unrelated background details as irrelevant.

"""
        return graph_rules + base_prompt


class TaichuDeepEvalLLM(DeepEvalBaseLLM):
    """DeepEval 模型接口到 LangChain ChatModel 的薄适配。"""

    def __init__(self, llm: BaseChatModel, model_id: str) -> None:
        self._llm = llm
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
        messages = [
            SystemMessage(
                content="你是太初 RAG 质量评测裁判。严格依据评测提示完成判断。"
            ),
            HumanMessage(content=prompt),
        ]
        config = model_call_config(
            model_id=self._model_id,
            task_type="rag_evaluation_judge",
            task_name="RAG 语义质量评测",
            max_output_tokens=100_000,
            temperature=0,
            feature="Graph RAG 质量评测",
        )
        if schema is None:
            response = await self._llm.ainvoke(messages, config=config)
            return _message_text(response)
        structured_model = self._llm.with_structured_output(
            schema,
            method="function_calling",
            strict=True,
        )
        result = await structured_model.ainvoke(messages, config=config)
        return schema.model_validate(result)

    def supports_structured_outputs(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return False


def _message_text(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        str(item.get("text") or "") if isinstance(item, dict) else str(item)
        for item in message.content
    )


async def evaluate_semantic_case(
    case: RAGGoldenCase,
    *,
    actual_answer: str,
    retrieval: VectorGraphRetrievalResult,
    judge: TaichuDeepEvalLLM,
    threshold: float = 0.7,
) -> DeepEvalCaseScore:
    retrieval_context = _assemble_retrieval_context(retrieval)
    test_case = LLMTestCase(
        input=case.query,
        actual_output=actual_answer,
        retrieval_context=retrieval_context,
    )
    metrics = [
        _build_semantic_metric(metric_type, threshold=threshold, judge=judge)
        for metric_type in _semantic_metric_types(case)
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


def _assemble_retrieval_context(
    retrieval: VectorGraphRetrievalResult,
) -> list[str]:
    """按生成器实际顺序评估最终上下文，允许裁判读取跨来源图路径。"""

    if not retrieval.evidences:
        return []
    return [
        "\n\n".join(
            f"[{evidence.source_ref}]\n{evidence.context_content or evidence.content}"
            for evidence in retrieval.evidences
        )
    ]


def _semantic_metric_types(case: RAGGoldenCase) -> tuple[type[Any], ...]:
    """困难负例没有相关上下文目标，不以 Contextual Relevancy 惩罚空召回。"""

    if case.category is RAGGoldenCategory.HARD_NEGATIVE:
        return (FaithfulnessMetric, AnswerRelevancyMetric)
    return (
        ContextualRelevancyMetric,
        FaithfulnessMetric,
        AnswerRelevancyMetric,
    )


def _build_semantic_metric(
    metric_type: type[Any],
    *,
    threshold: float,
    judge: TaichuDeepEvalLLM,
) -> Any:
    if metric_type is ContextualRelevancyMetric:
        return metric_type(
            threshold=threshold,
            model=judge,
            evaluation_template=TaichuGraphContextualRelevancyTemplate,
        )
    return metric_type(threshold=threshold, model=judge)
