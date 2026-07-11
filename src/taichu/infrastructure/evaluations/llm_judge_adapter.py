"""统一模型网关驱动的语义评估裁判。"""

from __future__ import annotations

from taichu.application.contracts.evaluation_judge import EvaluationJudgeResponse
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMModelIdentity,
    LLMRequest,
    response_text,
)


class LLMEvaluationJudgeAdapter:
    """让评估裁判也经过统一网关并记录遥测。"""

    def __init__(
        self,
        llm: LLMGatewayContract,
        *,
        model_id: str,
        configured: bool,
    ) -> None:
        self._llm = llm
        self._model_id = model_id
        self._configured = configured
        profile = next(
            (item for item in llm.list_models() if item.id == model_id), None
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

    async def complete(self, prompt: str) -> EvaluationJudgeResponse:
        if not self.available:
            raise EvaluationJudgeUnavailableError("语义裁判当前不可用。")
        response = await self._llm.complete(
            LLMRequest(
                model_id=self._model_id,
                messages=(
                    LLMMessage(
                        role="system",
                        content="你是太初知识抽取效果评估裁判，必须返回合法 JSON。",
                    ),
                    LLMMessage(role="user", content=prompt),
                ),
                task_type="knowledge_evaluation_judge",
                task_name="知识抽取语义裁判",
                response_mode="json",
                feature="知识沉淀评估",
            )
        )
        usage = response.usage if hasattr(response, "usage") else None
        token_usage = None
        if usage is not None:
            token_usage = {
                key: value
                for key, value in {
                    "input_tokens": usage.input_tokens,
                    "cached_input_tokens": usage.cached_input_tokens,
                    "output_tokens": usage.output_tokens,
                    "reasoning_tokens": usage.reasoning_tokens,
                    "total_tokens": usage.total_tokens,
                }.items()
                if value is not None
            }
        return EvaluationJudgeResponse(
            raw_response=response_text(response),
            model_identity=self.model_identity,
            token_usage=token_usage,
        )


class EvaluationJudgeUnavailableError(RuntimeError):
    """未配置安全密钥或模型时，在调用前阻止语义裁判。"""
