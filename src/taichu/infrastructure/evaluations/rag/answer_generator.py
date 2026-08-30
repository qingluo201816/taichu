"""使用 LangChain ChatModel 基于权威检索上下文生成评测答案。"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from taichu.application.invocations.config import model_call_config
from taichu.application.vector_graph.models import VectorGraphRetrievalResult


RAG_ANSWER_SYSTEM_PROMPT = """你是太初小说事实问答助手。只能依据提供的权威上下文回答，不得补造。

回答前先识别问题实际要求的维度：事实结果、原因或动机、过程或相关情节、人物反应、时间与地点。问题明确询问的每个维度都必须回答完整：
- 问“为什么、为何、原因、动机”时，必须给出证据支持的起因与因果链，不能用“针对、敌视、不满”等同义词重复问题。
- 问“如何、怎样、经历过什么、做了什么”时，必须交代关键动作、前后变化或代表性情节，不能只给抽象关系标签。
- 涉及幕后指使、实际执行、表面行为与真实目的时，必须区分不同角色及其动机。
- 只问单一名称、地点、类型或归属时，直接简洁回答，不为凑长度附加无关剧情。
- 单一事实问答只输出答案及必要限定，不复述题目中的外观、身份等识别线索。

若上下文只能证明结果、不能证明原因或过程，应明确指出缺少哪部分证据；若整体证据不足，只回答现有资料无法确认，不复述无关的已知背景。"""


class RAGAnswerGenerator:
    def __init__(self, llm: BaseChatModel, *, model_id: str) -> None:
        self._llm = llm
        self._model_id = model_id

    async def generate(
        self,
        query: str,
        retrieval: VectorGraphRetrievalResult,
    ) -> str:
        context = "\n\n".join(
            f"[{item.source_ref}]\n{item.context_content or item.content}"
            for item in retrieval.evidences
        )
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=RAG_ANSWER_SYSTEM_PROMPT),
                HumanMessage(
                    content=f"问题：{query}\n\n权威上下文：\n{context or '无'}"
                ),
            ],
            config=model_call_config(
                model_id=self._model_id,
                task_type="rag_evaluation_generation",
                task_name="RAG 评测答案生成",
                temperature=0,
                feature="Graph RAG 质量评测",
            ),
        )
        if not isinstance(response.content, str):
            raise TypeError("RAG 评测答案生成必须返回文本内容。")
        return response.content.strip()
