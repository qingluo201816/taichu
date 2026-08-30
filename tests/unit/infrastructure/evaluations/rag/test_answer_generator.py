import asyncio

from langchain_core.messages import AIMessage

from taichu.application.vector_graph.models import VectorGraphRetrievalResult
from taichu.infrastructure.evaluations.rag.answer_generator import RAGAnswerGenerator
from tests.fakes.native_tool_chat_model import NativeToolCallSequenceChatModel


def test_answer_prompt_requires_causes_and_plot_instead_of_synonym_rephrasing() -> None:
    llm = NativeToolCallSequenceChatModel(
        responses=[AIMessage(content="依据上下文生成的答案")]
    )
    generator = RAGAnswerGenerator(llm, model_id="test-model")

    answer = asyncio.run(
        generator.generate(
            "李靖为什么针对秦浩轩，张狂对此做了什么？",
            VectorGraphRetrievalResult(query="问题"),
        )
    )

    assert answer == "依据上下文生成的答案"
    system_prompt = llm.seen_messages[0][0].content
    assert isinstance(system_prompt, str)
    assert "必须给出证据支持的起因与因果链" in system_prompt
    assert "不能用“针对、敌视、不满”等同义词重复问题" in system_prompt
    assert "必须交代关键动作、前后变化或代表性情节" in system_prompt
    assert "只问单一名称、地点、类型或归属时，直接简洁回答" in system_prompt
    assert "不复述题目中的外观、身份等识别线索" in system_prompt
    assert "只回答现有资料无法确认" in system_prompt
