"""把 Milvus Vector Graph RAG 的模型任务接入太初统一 LLM 契约。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import re
from collections.abc import Iterator
from typing import Any

from vector_graph_rag.llm.extractor import (  # type: ignore[import-untyped]
    EXTRACTION_EXAMPLE_INPUT,
    EXTRACTION_EXAMPLE_OUTPUT,
    EXTRACTION_SYSTEM_PROMPT,
    NER_ONE_SHOT_INPUT,
    NER_ONE_SHOT_OUTPUT,
    NER_SYSTEM_PROMPT,
    NER_TEMPLATE,
)
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMRequest,
    response_text,
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.S)
_VECTOR_GRAPH_RUN_ID: ContextVar[str | None] = ContextVar(
    "vector_graph_run_id",
    default=None,
)
_RELATION_RERANK_SYSTEM_PROMPT = """你负责从知识图谱候选关系中选择回答小说问题所需的最小充分证据链。
先判断问题真正需要的证据类型：事实结果、原因/动机、过程/相关情节、人物反应，或时间/地点。
为什么/为何类问题必须优先选择能说明诱因、动机、冲突背景和因果结果的关系；仅把“针对”改写成“敌视”、把“指使”改写成“要某人做某事”等同义关系，只是在复述问题，不算原因证据。
怎么/经历/做了什么类问题应选择能还原关键行为和情节变化的关系，不能只选择最终结论。
直接属性或归属问题若一条关系即可回答，只选该直接关系，不得为了出现多个实体而拼造多跳路径。
确需多跳时，所选关系必须首尾形成能回答问题的连续路径；不要选择只有实体共现、但对答案没有贡献的关系。
最多选择 5 条；如果没有任何候选能支持问题中的前提或真正答案，必须返回空数组。
只返回 JSON 对象，格式为 {"useful_relation_ids":["关系ID"]}。
不要输出分析过程、关系原文、Markdown 或其他字段。"""


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
        gateway: LLMGatewayContract,
        model_id: str,
        *,
        relation_candidate_limit: int = 60,
    ) -> None:
        if not model_id.strip():
            raise ValueError("Vector Graph RAG 模型 ID 不能为空。")
        if relation_candidate_limit < 1:
            raise ValueError("Vector Graph RAG 关系候选上限必须大于零。")
        self._gateway = gateway
        self._model_id = model_id
        self._relation_candidate_limit = relation_candidate_limit

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def extraction_configuration_sha256(self) -> str:
        """用于判定三元组抽取规则变化是否需要重做来源索引。"""
        payload = {
            "system_prompt": EXTRACTION_SYSTEM_PROMPT,
            "example_input": EXTRACTION_EXAMPLE_INPUT,
            "example_output": EXTRACTION_EXAMPLE_OUTPUT,
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
        payload = await self._complete_json(
            task_name="vector_graph.extract_triplets",
            messages=(
                LLMMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
                LLMMessage(role="user", content=EXTRACTION_EXAMPLE_INPUT),
                LLMMessage(role="assistant", content=EXTRACTION_EXAMPLE_OUTPUT),
                LLMMessage(role="user", content=f"Text: {text}"),
            ),
            max_output_tokens=4_096,
        )
        result: list[list[str]] = []
        for item in payload.get("triplets", []):
            if not isinstance(item, list) or len(item) != 3:
                continue
            values = [str(value).strip() for value in item]
            if all(values):
                result.append(values)
        return result

    async def extract_query_entities(self, question: str) -> list[str]:
        payload = await self._complete_json(
            task_name="vector_graph.extract_query_entities",
            messages=(
                LLMMessage(role="system", content=NER_SYSTEM_PROMPT),
                LLMMessage(role="user", content=NER_ONE_SHOT_INPUT),
                LLMMessage(role="assistant", content=NER_ONE_SHOT_OUTPUT),
                LLMMessage(role="user", content=NER_TEMPLATE.format(question)),
            ),
            max_output_tokens=1_024,
        )
        raw = payload.get("named_entities", payload.get("entities", []))
        if not isinstance(raw, list):
            return []
        return list(
            dict.fromkeys(
                normalized
                for item in raw
                if (normalized := _normalize_entity(str(item)))
            )
        )

    async def rerank_relations(
        self,
        query: str,
        relation_ids: list[str],
        relation_texts: list[str],
    ) -> tuple[list[str], list[str]]:
        if not relation_ids:
            return [], []
        relation_ids = relation_ids[: self._relation_candidate_limit]
        relation_texts = relation_texts[: self._relation_candidate_limit]
        descriptions = "\n".join(
            f"[{relation_id}] {text}"
            for relation_id, text in zip(relation_ids, relation_texts, strict=True)
        )
        payload = await self._complete_json(
            task_name="vector_graph.rerank_relations",
            messages=(
                LLMMessage(role="system", content=_RELATION_RERANK_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=(
                        f"问题：\n{query}\n\n"
                        f"候选关系：\n{descriptions}"
                    ),
                ),
            ),
            max_output_tokens=2_048,
        )
        valid_ids = set(relation_ids)
        selected_ids: list[str] = []
        for item in payload.get("useful_relation_ids", []):
            if not isinstance(item, str):
                continue
            relation_id = item.strip()
            if relation_id in valid_ids and relation_id not in selected_ids:
                selected_ids.append(relation_id)
        by_id = dict(zip(relation_ids, relation_texts, strict=True))
        return selected_ids, [by_id[item] for item in selected_ids]

    async def _complete_json(
        self,
        *,
        task_name: str,
        messages: tuple[LLMMessage, ...],
        max_output_tokens: int,
    ) -> dict[str, Any]:
        response = await self._gateway.complete(
            LLMRequest(
                model_id=self._model_id,
                messages=messages,
                task_type="vector_graph_rag",
                task_name=task_name,
                response_mode="json",
                temperature=0,
                max_output_tokens=max_output_tokens,
                feature="milvus_vector_graph_rag",
                run_id=_VECTOR_GRAPH_RUN_ID.get(),
            )
        )
        if _output_was_truncated(response.finish_reason):
            raise ValueError("Vector Graph RAG 模型 JSON 输出达到上限并被截断。")
        return _parse_json_object(response_text(response))


def _parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        match = _JSON_OBJECT.search(candidate)
        if match is None:
            raise ValueError("Vector Graph RAG 模型没有返回 JSON 对象。") from None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Vector Graph RAG 模型返回值必须是 JSON 对象。")
    return payload


def _normalize_entity(value: str) -> str:
    """保留中文、字母和数字，修正官方英文归一化会清空中文的问题。"""
    return " ".join(re.sub(r"[^\w]+", " ", value.lower()).replace("_", " ").split())


def _output_was_truncated(finish_reason: str | None) -> bool:
    return (finish_reason or "").strip().casefold() in {
        "length",
        "max_output_tokens",
        "max_tokens",
    }


class StaticEntityExtractor:
    """把主事件循环已抽取的查询实体交给官方同步检索器。"""

    def __init__(self, entities: list[str]) -> None:
        self._entities = list(entities)

    def extract(self, _question: str) -> list[str]:
        return list(self._entities)
