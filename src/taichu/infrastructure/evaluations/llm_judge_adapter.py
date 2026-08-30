"""LangChain ChatModel 驱动的语义评估裁判。"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from taichu.application.contracts.evaluation_judge import EvaluationJudgeResponse
from taichu.application.contracts.llm import (
    LLMModelCatalogContract,
    LLMModelIdentity,
)
from taichu.application.invocations.callbacks import ModelResponseCapture
from taichu.application.invocations.config import model_call_config


class LLMEvaluationJudgeAdapter:
    """通过 LangChain 原生结构化输出调用统一模型传输层。"""

    def __init__(
        self,
        llm: BaseChatModel,
        model_catalog: LLMModelCatalogContract,
        *,
        model_id: str,
        configured: bool,
    ) -> None:
        self._llm = llm
        self._model_id = model_id
        self._configured = configured
        profile = next(
            (item for item in model_catalog.list_models() if item.id == model_id), None
        )
        self._identity = (
            LLMModelIdentity(
                provider="rightcode",
                model_id=profile.id,
                family=profile.id.rsplit("-", 1)[0],
                endpoint_kind=profile.wire_protocol,
                known=profile.upstream_verified,
                unknown_reason=(
                    None
                    if profile.upstream_verified
                    else "上游模型名尚未完成真实密钥探测。"
                ),
            )
            if profile is not None
            else LLMModelIdentity.unknown(
                "裁判模型不在当前模型目录中。", model_id=model_id
            )
        )

    @property
    def available(self) -> bool:
        return self._configured and self._identity.model_id != ""

    @property
    def model_identity(self) -> LLMModelIdentity:
        return self._identity

    async def complete(
        self,
        prompt: str,
        *,
        output_schema: type[BaseModel],
    ) -> EvaluationJudgeResponse:
        if not self.available:
            raise EvaluationJudgeUnavailableError("语义裁判当前不可用。")
        capture = ModelResponseCapture()
        structured_model = self._llm.with_structured_output(
            output_schema,
            method="function_calling",
            strict=True,
        )
        result = await structured_model.ainvoke(
            [
                SystemMessage(content="你是太初知识抽取效果评估裁判。"),
                HumanMessage(content=prompt),
            ],
            config=model_call_config(
                model_id=self._model_id,
                task_type="knowledge_evaluation_judge",
                task_name="知识抽取语义裁判",
                feature="知识沉淀评估",
                callbacks=(capture,),
            ),
        )
        validated = output_schema.model_validate(result)
        usage = capture.response.usage_metadata if capture.response is not None else None
        token_usage = (
            {
                key: value
                for key, value in {
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                }.items()
                if isinstance(value, int)
            }
            if usage is not None
            else None
        )
        return EvaluationJudgeResponse(
            output=validated,
            raw_response=validated.model_dump_json(),
            model_identity=self.model_identity,
            token_usage=token_usage,
        )


class EvaluationJudgeUnavailableError(RuntimeError):
    """未配置安全密钥或模型时，在调用前阻止语义裁判。"""
