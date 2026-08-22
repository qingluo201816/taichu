import asyncio

from taichu.application.vector_graph.models import VectorGraphRetrievalResult
from taichu.infrastructure.evaluations.rag.answer_generator import RAGAnswerGenerator


class _RecordingGateway:
    def __init__(self) -> None:
        self.request = None

    async def complete(self, request):  # type: ignore[no-untyped-def]
        self.request = request
        return "依据上下文生成的答案"


def test_answer_prompt_requires_causes_and_plot_instead_of_synonym_rephrasing() -> None:
    gateway = _RecordingGateway()
    generator = RAGAnswerGenerator(gateway, model_id="test-model")  # type: ignore[arg-type]

    answer = asyncio.run(
        generator.generate(
            "李靖为什么针对秦浩轩，张狂对此做了什么？",
            VectorGraphRetrievalResult(query="问题"),
        )
    )

    assert answer == "依据上下文生成的答案"
    assert gateway.request is not None
    system_prompt = gateway.request.messages[0].content
    assert "必须给出证据支持的起因与因果链" in system_prompt
    assert "不能用“针对、敌视、不满”等同义词重复问题" in system_prompt
    assert "必须交代关键动作、前后变化或代表性情节" in system_prompt
    assert "只问单一名称、地点、类型或归属时，直接简洁回答" in system_prompt
