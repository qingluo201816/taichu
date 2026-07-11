"""Create the semantic evaluation judge from auditable runtime settings."""

from __future__ import annotations

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.infrastructure.evaluations.llm_judge_adapter import (
    LLMEvaluationJudgeAdapter,
)
from taichu.infrastructure.llm.adapter import LangChainLLMAdapter
from taichu.infrastructure.llm.factory import LLMRuntime, create_llm
from taichu.infrastructure.llm.providers.deepseek import (
    create_deepseek,
    deepseek_model_family,
    deepseek_model_identity,
)
from taichu.infrastructure.llm.unavailable import UnavailableLLMChatModel


def create_evaluation_judge(
    settings: Settings,
    fallback_runtime: LLMRuntime | None = None,
) -> LLMEvaluationJudgeAdapter:
    """Create a dedicated judge, or reuse the configured default runtime.

    An explicitly requested judge never silently falls back to another model.
    Missing credentials therefore produce an unavailable adapter whose identity
    still records the requested provider and model for a useful preview response.
    """

    requested_model = settings.evaluation_judge_model.strip()
    runtime = (
        _create_dedicated_runtime(settings, requested_model)
        if requested_model
        else (fallback_runtime or create_llm(settings))
    )
    return LLMEvaluationJudgeAdapter(
        LangChainLLMAdapter(runtime.chat_model, runtime.model_identity),
        configured=runtime.configured,
    )


def _create_dedicated_runtime(settings: Settings, model_id: str) -> LLMRuntime:
    if settings.llm_provider != "deepseek":
        return _unavailable_runtime(
            "当前裁判模型供应商不受支持。",
            provider=settings.llm_provider,
            model_id=model_id,
        )
    if not all(
        (
            settings.deepseek_api_key.strip(),
            settings.deepseek_api_base.strip(),
            model_id,
        )
    ):
        return _unavailable_runtime(
            "语义裁判缺少可用的模型配置。",
            provider="deepseek",
            model_id=model_id,
            family=deepseek_model_family(model_id),
            endpoint_kind="openai_compatible",
        )
    return LLMRuntime(
        chat_model=create_deepseek(settings, model=model_id),
        model_identity=deepseek_model_identity(model_id),
        configured=True,
    )


def _unavailable_runtime(
    reason: str,
    *,
    provider: str,
    model_id: str,
    family: str = "",
    endpoint_kind: str = "",
) -> LLMRuntime:
    return LLMRuntime(
        chat_model=UnavailableLLMChatModel(),
        model_identity=LLMModelIdentity.unknown(
            reason,
            provider=provider,
            model_id=model_id,
            family=family,
            endpoint_kind=endpoint_kind,
        ),
        configured=False,
    )
