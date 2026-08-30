"""把 Milvus Vector Graph RAG 的模型任务接入 LangChain ChatModel。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
from collections.abc import Iterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel, ConfigDict, Field

from taichu.application.invocations.callbacks import ModelResponseCapture
from taichu.application.invocations.config import model_call_config

_TRIPLET_TOOL_NAME = "VectorGraphTripletOutput"
_TRIPLET_SYSTEM_PROMPT = """你是知识图谱构建专家。请从给定文本中提取有意义的知识三元组。
主体和客体应是简洁但完整的人物、地点、事物或概念；关系应清晰具体。
可以抽取文本明确表达或由同一句上下文直接蕴含的关系，但不得补造文本不支持的事实。"""
_EXAMPLE_INPUT = (
    "文本：Albert Einstein was born in Ulm, Germany in 1879. "
    "He developed the theory of relativity, which revolutionized physics. "
    "Einstein worked at the Institute for Advanced Study in Princeton."
)
_VECTOR_GRAPH_RUN_ID: ContextVar[str | None] = ContextVar(
    "vector_graph_run_id",
    default=None,
)


class _StrictOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VectorGraphTriplet(_StrictOutputModel):
    subject: str = Field(description="关系主体。", min_length=1)
    predicate: str = Field(description="主体与客体之间的具体关系。", min_length=1)
    object: str = Field(description="关系客体。", min_length=1)


class VectorGraphTripletOutput(_StrictOutputModel):
    triplets: list[VectorGraphTriplet] = Field(
        description="从输入文本中提取的知识三元组；没有关系时为空数组。"
    )


_EXAMPLE_OUTPUT = VectorGraphTripletOutput(
    triplets=[
        VectorGraphTriplet(
            subject="Albert Einstein",
            predicate="was born in",
            object="Ulm, Germany",
        ),
        VectorGraphTriplet(
            subject="Albert Einstein",
            predicate="was born in",
            object="1879",
        ),
        VectorGraphTriplet(
            subject="Albert Einstein",
            predicate="developed",
            object="the theory of relativity",
        ),
        VectorGraphTriplet(
            subject="the theory of relativity",
            predicate="revolutionized",
            object="physics",
        ),
        VectorGraphTriplet(
            subject="Albert Einstein",
            predicate="worked at",
            object="the Institute for Advanced Study",
        ),
        VectorGraphTriplet(
            subject="the Institute for Advanced Study",
            predicate="is located in",
            object="Princeton",
        ),
    ]
)


@contextmanager
def vector_graph_llm_run_context(run_id: str) -> Iterator[None]:
    """为当前异步评测链路附加可回放的运行标识。"""

    token = _VECTOR_GRAPH_RUN_ID.set(run_id)
    try:
        yield
    finally:
        _VECTOR_GRAPH_RUN_ID.reset(token)


class TaichuVectorGraphLLM:
    """复用太初模型目录、协议转换、用量审计和失败降级。"""

    def __init__(
        self,
        llm: BaseChatModel,
        model_id: str,
    ) -> None:
        if not model_id.strip():
            raise ValueError("Vector Graph RAG 模型 ID 不能为空。")
        self._llm = llm
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def extraction_configuration_sha256(self) -> str:
        """用于判定三元组抽取规则变化是否需要重做来源索引。"""
        payload = {
            "system_prompt": _TRIPLET_SYSTEM_PROMPT,
            "example_input": _EXAMPLE_INPUT,
            "example_output": _EXAMPLE_OUTPUT.model_dump(mode="json"),
            "output_schema": VectorGraphTripletOutput.model_json_schema(),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def extract_triplets(self, text: str) -> list[list[str]]:
        if not text.strip():
            return []
        output = await self._complete_structured(
            task_name="vector_graph.extract_triplets",
            messages=[
                SystemMessage(content=_TRIPLET_SYSTEM_PROMPT),
                HumanMessage(content=_EXAMPLE_INPUT),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "vector-graph-example",
                            "name": _TRIPLET_TOOL_NAME,
                            "args": _EXAMPLE_OUTPUT.model_dump(mode="json"),
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content="示例三元组已接收。",
                    tool_call_id="vector-graph-example",
                    name=_TRIPLET_TOOL_NAME,
                ),
                HumanMessage(content=f"文本：{text}"),
            ],
            max_output_tokens=4_096,
        )
        return [
            [item.subject.strip(), item.predicate.strip(), item.object.strip()]
            for item in output.triplets
        ]

    async def _complete_structured(
        self,
        *,
        task_name: str,
        messages: list[BaseMessage],
        max_output_tokens: int,
    ) -> VectorGraphTripletOutput:
        capture = ModelResponseCapture()
        structured_model = self._llm.with_structured_output(
            VectorGraphTripletOutput,
            method="function_calling",
            strict=True,
        )
        try:
            result = await structured_model.ainvoke(
                messages,
                config=model_call_config(
                    model_id=self._model_id,
                    task_type="vector_graph_rag",
                    task_name=task_name,
                    run_id=_VECTOR_GRAPH_RUN_ID.get(),
                    temperature=0,
                    max_output_tokens=max_output_tokens,
                    feature="milvus_vector_graph_rag",
                    callbacks=(capture,),
                ),
            )
        except Exception as exc:
            if _captured_output_was_truncated(capture):
                raise ValueError(
                    "Vector Graph RAG 模型结构化输出达到上限并被截断。"
                ) from exc
            raise
        if _captured_output_was_truncated(capture):
            raise ValueError("Vector Graph RAG 模型结构化输出达到上限并被截断。")
        return VectorGraphTripletOutput.model_validate(result)


def _captured_output_was_truncated(capture: ModelResponseCapture) -> bool:
    finish_reason = (
        capture.response.response_metadata.get("finish_reason")
        if capture.response is not None
        else None
    )
    return _output_was_truncated(
        finish_reason if isinstance(finish_reason, str) else None
    )


def _output_was_truncated(finish_reason: str | None) -> bool:
    return (finish_reason or "").strip().casefold() in {
        "length",
        "max_output_tokens",
        "max_tokens",
    }
